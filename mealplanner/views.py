import json
import os
import re
from datetime import datetime

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import MealPlan, SavedPlan


def get_gemini_api_key():
    """Get Gemini API key from settings or environment."""
    return getattr(settings, 'GEMINI_API_KEY', os.environ.get('GEMINI_API_KEY', ''))


def call_gemini_api(prompt):
    """Call Google Gemini API with the given prompt and return the response text."""
    api_key = get_gemini_api_key()
    if not api_key:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

    headers = {"Content-Type": "application/json"}

    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192,
        }
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()

        candidates = result.get('candidates', [])
        if candidates:
            parts = candidates[0].get('content', {}).get('parts', [])
            if parts:
                return parts[0].get('text', '')
        return None
    except Exception as e:
        print(f"Gemini API error: {e}")
        return None


def extract_json_from_text(text):
    """Extract JSON from text that may contain markdown code blocks."""
    if not text:
        return None

    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        json_str = text.strip()

    start = json_str.find('{')
    end = json_str.rfind('}')
    if start != -1 and end != -1:
        json_str = json_str[start:end + 1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def build_gemini_prompt(budget, members, dietary, region, ingredients=""):
    """Build the prompt for Gemini API."""
    dietary_text = dietary if dietary else "Wala (none)"
    ingredients_text = f"\nMayroon na kaming mga sangkap na ito: {ingredients}" if ingredients else ""

    prompt = f"""You are a Filipino meal planning assistant. Generate a 7-day meal plan for a Filipino family of {members} members with a weekly food budget of ₱{budget}. Dietary restrictions: {dietary_text}. Region: {region}.{ingredients_text}

Use affordable, locally available Filipino ingredients. Return ONLY valid JSON in this format (no markdown, no code fences, just raw JSON):

{{
  "days": [
    {{
      "day": "Monday",
      "meals": {{
        "breakfast": {{"name": "Sinangag at Itlog", "ingredients": ["garlic", "rice", "eggs"], "estimated_cost": 35, "cook_time": "10 mins", "instructions": "1. Mag-gisa ng bawang. 2. Ilagay ang kanin. 3. Prituhin ang itlog."}},
        "lunch": {{"name": "Adobong Manok", "ingredients": ["chicken", "soy sauce", "vinegar", "garlic", "pepper"], "estimated_cost": 85, "cook_time": "30 mins", "instructions": "1. ..."}},
        "dinner": {{"name": "Tinolang Manok", "ingredients": ["chicken", "green papaya", "malunggay", "ginger", "garlic"], "estimated_cost": 80, "cook_time": "35 mins", "instructions": "1. ..."}}
      }},
      "day_total": 200
    }}
  ],
  "weekly_total": 1400,
  "grocery_list": [
    {{"item": "rice", "quantity": "2 kg", "est_cost": 60, "category": "Pantry"}},
    {{"item": "chicken", "quantity": "1 kg", "est_cost": 150, "category": "Protein"}}
  ]
}}

Include Filipino dishes like sinigang, adobo, tinola, ginataan, kare-kare, sisig, bulalo, nilaga, paksiw, menudo, caldereta, afritada, torta, lumpia, etc. Keep each day's meals within budget. Include estimated cost in pesos for every meal and every grocery item. Each grocery item MUST have a "category" field: "Vegetables", "Protein", "Pantry", "Dairy", "Fruits", or "Others". Make sure the grocery_list covers ALL ingredients from ALL meals across all 7 days."""

    return prompt


def build_regenerate_prompt(budget, members, dietary, region, day, meal_type, current_plan):
    """Build prompt to regenerate a single meal."""
    dietary_text = dietary if dietary else "Wala (none)"

    prompt = f"""You are a Filipino meal planning assistant. Generate a replacement for the {meal_type} meal on {day} for a Filipino family of {members} members. The total weekly budget is ₱{budget}. Dietary restrictions: {dietary_text}. Region: {region}.

The current meal plan is: {json.dumps(current_plan, indent=2)}

Return ONLY valid JSON (no markdown, no code fences) for just ONE meal in this format:
{{
  "name": "Dish Name",
  "ingredients": ["ingredient1", "ingredient2"],
  "estimated_cost": 50,
  "cook_time": "15 mins",
  "instructions": "1. Step one. 2. Step two."
}}

Make sure the meal is different from what's currently there, fits within the remaining budget, and uses Filipino ingredients."""

    return prompt


@never_cache
def landing_page(request):
    """Landing page view with sample data."""
    sample_days = [
        {
            'day': 'Lunes',
            'meals': {
                'breakfast': {'name': 'Sinangag at Itlog', 'estimated_cost': 35, 'cook_time': '10 mins'},
                'lunch': {'name': 'Adobong Manok', 'estimated_cost': 85, 'cook_time': '30 mins'},
                'dinner': {'name': 'Tinolang Manok', 'estimated_cost': 80, 'cook_time': '35 mins'},
            },
            'day_total': 200
        },
        {
            'day': 'Martes',
            'meals': {
                'breakfast': {'name': 'Tapsilog', 'estimated_cost': 55, 'cook_time': '15 mins'},
                'lunch': {'name': 'Sinigang na Baboy', 'estimated_cost': 90, 'cook_time': '40 mins'},
                'dinner': {'name': 'Tortang Talong', 'estimated_cost': 45, 'cook_time': '15 mins'},
            },
            'day_total': 190
        },
        {
            'day': 'Miyerkules',
            'meals': {
                'breakfast': {'name': 'Pandesal at Kape', 'estimated_cost': 25, 'cook_time': '5 mins'},
                'lunch': {'name': 'Menudo', 'estimated_cost': 85, 'cook_time': '35 mins'},
                'dinner': {'name': 'Ginataang Gulay', 'estimated_cost': 65, 'cook_time': '25 mins'},
            },
            'day_total': 175
        },
    ]
    response = render(request, 'landing.html', {'sample_days': sample_days})
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    response['Clear-Site-Data'] = '"cache"'
    return response


def planner(request):
    """Meal planner form page."""
    return render(request, 'planner.html')


def generate_plan(request):
    """Generate meal plan via Gemini API."""
    if request.method == 'POST':
        budget = request.POST.get('budget', '1500')
        members = request.POST.get('members', '4')
        region = request.POST.get('region', 'Luzon')
        ingredients = request.POST.get('ingredients', '')

        dietary_items = []
        if request.POST.get('no_pork'): dietary_items.append('No pork')
        if request.POST.get('no_beef'): dietary_items.append('No beef')
        if request.POST.get('vegetarian'): dietary_items.append('Vegetarian')
        if request.POST.get('no_seafood'): dietary_items.append('No seafood')
        if request.POST.get('no_spicy'): dietary_items.append('No spicy')
        dietary = ', '.join(dietary_items)

        prompt = build_gemini_prompt(budget, members, dietary, region, ingredients)
        gemini_response = call_gemini_api(prompt)

        plan_data = None
        if gemini_response:
            plan_data = extract_json_from_text(gemini_response)

        if not plan_data:
            plan_data = generate_fallback_plan(budget, members, dietary, region)

        meal_plan = MealPlan(
            budget=budget,
            members=members,
            dietary=dietary,
            region=region,
            weekly_total=plan_data.get('weekly_total', 0),
        )

        if request.user.is_authenticated:
            meal_plan.user = request.user
        else:
            meal_plan.session_key = request.session.session_key or ''

        meal_plan.set_plan_data(plan_data)
        meal_plan.save()

        request.session['current_plan_id'] = meal_plan.id

        return redirect('plan_view', plan_id=meal_plan.id)

    return redirect('planner')


def plan_view(request, plan_id):
    """Display a generated meal plan."""
    meal_plan = get_object_or_404(MealPlan, id=plan_id)
    plan_data = meal_plan.get_plan_data()

    can_save = request.user.is_authenticated

    is_saved = False
    if request.user.is_authenticated:
        is_saved = SavedPlan.objects.filter(
            user=request.user, meal_plan=meal_plan
        ).exists()

    return render(request, 'plan_display.html', {
        'meal_plan': meal_plan,
        'plan_data': plan_data,
        'days': plan_data.get('days', []),
        'weekly_total': plan_data.get('weekly_total', 0),
        'grocery_list': plan_data.get('grocery_list', []),
        'can_save': can_save,
        'is_saved': is_saved,
    })


@csrf_exempt
@require_POST
def regenerate_meal(request, plan_id):
    """Regenerate a single meal via Gemini API."""
    meal_plan = get_object_or_404(MealPlan, id=plan_id)
    plan_data = meal_plan.get_plan_data()

    try:
        data = json.loads(request.body)
        day = data.get('day', 'Monday')
        meal_type = data.get('meal_type', 'lunch')
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': 'Invalid request'}, status=400)

    prompt = build_regenerate_prompt(
        meal_plan.budget, meal_plan.members, meal_plan.dietary,
        meal_plan.region, day, meal_type, plan_data
    )

    gemini_response = call_gemini_api(prompt)
    new_meal = None
    if gemini_response:
        new_meal = extract_json_from_text(gemini_response)

    if not new_meal or 'name' not in new_meal:
        new_meal = generate_fallback_meal(day, meal_type, plan_data)

    for day_data in plan_data.get('days', []):
        if day_data['day'] == day:
            if meal_type in day_data.get('meals', {}):
                old_cost = day_data['meals'][meal_type].get('estimated_cost', 0)
                day_data['meals'][meal_type] = new_meal
                new_cost = new_meal.get('estimated_cost', 0)
                day_data['day_total'] = day_data.get('day_total', 0) - old_cost + new_cost
                break

    weekly_total = sum(d.get('day_total', 0) for d in plan_data.get('days', []))
    plan_data['weekly_total'] = weekly_total
    plan_data['grocery_list'] = rebuild_grocery_list(plan_data)

    meal_plan.set_plan_data(plan_data)
    meal_plan.weekly_total = weekly_total
    meal_plan.save()

    return JsonResponse({
        'success': True,
        'meal': new_meal,
        'day_total': next((d['day_total'] for d in plan_data.get('days', []) if d['day'] == day), 0),
        'weekly_total': weekly_total,
    })


def grocery_list(request, plan_id):
    """Display grocery list for a meal plan."""
    meal_plan = get_object_or_404(MealPlan, id=plan_id)
    plan_data = meal_plan.get_plan_data()
    grocery_list = plan_data.get('grocery_list', [])

    categories = {}
    for item in grocery_list:
        cat = item.get('category', 'Others')
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    return render(request, 'grocery_list.html', {
        'meal_plan': meal_plan,
        'grocery_list': grocery_list,
        'categories': categories,
        'total_cost': sum(item.get('est_cost', 0) for item in grocery_list),
    })


def export_pdf(request, plan_id):
    """Generate and download PDF of meal plan."""
    meal_plan = get_object_or_404(MealPlan, id=plan_id)
    plan_data = meal_plan.get_plan_data()

    html_content = render_to_pdf_html(meal_plan, plan_data)

    try:
        from weasyprint import HTML
        pdf_file = HTML(string=html_content).write_pdf()
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="menumo_plan_{meal_plan.id}.pdf"'
        return response
    except ImportError:
        try:
            from xhtml2pdf import pisa
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="menumo_plan_{meal_plan.id}.pdf"'
            pisa_status = pisa.CreatePDF(html_content, dest=response)
            if pisa_status.err:
                return HttpResponse('PDF generation failed', status=500)
            return response
        except ImportError:
            return render(request, 'pdf_export.html', {
                'meal_plan': meal_plan,
                'plan_data': plan_data,
                'days': plan_data.get('days', []),
                'weekly_total': plan_data.get('weekly_total', 0),
                'grocery_list': plan_data.get('grocery_list', []),
            })


def render_to_pdf_html(meal_plan, plan_data):
    """Generate XHTML-compliant HTML string for PDF export via xhtml2pdf."""
    days = plan_data.get('days', [])
    grocery_list = plan_data.get('grocery_list', [])
    weekly_total = plan_data.get('weekly_total', 0)

    days_html = ''
    for day_data in days:
        meals_html = ''
        for meal_type, meal in day_data.get('meals', {}).items():
            instructions = meal.get('instructions', '')
            meals_html += f'''
            <div class="meal-item">
                <strong>{meal_type.title()}:</strong> {meal.get('name', '')} - &#8369;{meal.get('estimated_cost', 0)}
                <br/><em>{meal.get('cook_time', '')}</em>
                <p>{instructions}</p>
            </div>
            '''

        days_html += f'''
        <div class="day-card">
            <h3>{day_data['day']}</h3>
            {meals_html}
            <p class="day-total">Day Total: &#8369;{day_data.get('day_total', 0)}</p>
        </div>
        '''

    grocery_html = ''
    for item in grocery_list:
        grocery_html += f'''
        <tr>
            <td>{item.get('item', '')}</td>
            <td>{item.get('quantity', '')}</td>
            <td>&#8369;{item.get('est_cost', 0)}</td>
            <td>{item.get('category', 'Others')}</td>
        </tr>
        '''

    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8"/>
        <title>MenuMo Meal Plan</title>
        <style>
            body {{ font-family: 'Helvetica', 'Arial', sans-serif; margin: 20px; color: #333; font-size: 12px; }}
            .header {{ text-align: center; margin-bottom: 30px; border-bottom: 3px solid #E67E22; padding-bottom: 15px; }}
            .header h1 {{ color: #E67E22; margin: 0; font-size: 28px; }}
            .header p {{ color: #666; margin: 5px 0; }}
            .plan-info {{ margin-bottom: 20px; padding: 10px; background-color: #FFF8F0; }}
            .plan-info span {{ margin-right: 20px; }}
            .day-card {{ border: 1px solid #ddd; padding: 15px; margin-bottom: 15px; page-break-inside: avoid; }}
            .day-card h3 {{ color: #E67E22; margin-top: 0; border-bottom: 1px solid #eee; padding-bottom: 8px; }}
            .meal-item {{ margin-bottom: 10px; padding: 8px; background-color: #f9f9f9; }}
            .meal-item p {{ margin: 5px 0 0 0; font-size: 11px; color: #666; }}
            .day-total {{ text-align: right; font-weight: bold; margin-top: 10px; }}
            .weekly-total {{ text-align: center; font-size: 18px; font-weight: bold; color: #E67E22; margin: 20px 0; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #E67E22; color: white; }}
            .footer {{ text-align: center; margin-top: 30px; font-size: 11px; color: #999; border-top: 1px solid #eee; padding-top: 10px; }}
            .section-title {{ color: #E67E22; font-size: 16px; font-weight: bold; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>MenuMo</h1>
            <p>AI Weekly Filipino Meal Plan</p>
        </div>
        <div class="plan-info">
            <span><strong>Budget:</strong> &#8369;{meal_plan.budget}</span>
            <span><strong>Family Members:</strong> {meal_plan.members}</span>
            <span><strong>Region:</strong> {meal_plan.region}</span>
            <span><strong>Dietary:</strong> {meal_plan.dietary or 'None'}</span>
        </div>
        <h2 class="section-title">Weekly Meal Plan</h2>
        {days_html}
        <p class="weekly-total">Weekly Total: &#8369;{weekly_total}</p>
        <h2 class="section-title">Grocery List</h2>
        <table>
            <thead>
                <tr><th>Item</th><th>Quantity</th><th>Est. Cost</th><th>Category</th></tr>
            </thead>
            <tbody>
                {grocery_html}
            </tbody>
        </table>
        <div class="footer">
            <p>Generated by MenuMo on {datetime.now().strftime('%B %d, %Y')}</p>
            <p>"Anong ulam ngayong linggo? MenuMo bahala na."</p>
        </div>
    </body>
    </html>
    '''
    return html


@login_required
@require_POST
def save_plan(request, plan_id):
    """Save a meal plan for logged-in user."""
    meal_plan = get_object_or_404(MealPlan, id=plan_id)

    saved, created = SavedPlan.objects.get_or_create(
        user=request.user,
        meal_plan=meal_plan
    )

    if created:
        if not meal_plan.user:
            meal_plan.user = request.user
            meal_plan.save()

    return JsonResponse({'success': True, 'saved': created})


@login_required
def saved_plans(request):
    """List all saved meal plans for the user."""
    saved_plans = SavedPlan.objects.filter(user=request.user).select_related('meal_plan')
    return render(request, 'saved_plans.html', {
        'saved_plans': saved_plans,
    })


@login_required
@require_POST
def delete_saved_plan(request, plan_id):
    """Delete a saved meal plan."""
    saved_plan = get_object_or_404(SavedPlan, id=plan_id, user=request.user)
    saved_plan.delete()
    return JsonResponse({'success': True})


@never_cache
def about(request):
    """About page."""
    response = render(request, 'about.html')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


def custom_logout(request):
    """Custom logout page with MenuMo styling."""
    if request.method == 'POST':
        from django.contrib.auth import logout
        logout(request)
        return redirect('landing')
    return render(request, 'account/logout.html')



# ============ FALLBACK DATA FUNCTIONS ============

def get_ingredient_price(ingredient_lower):
    """Get realistic price for an ingredient based on type."""
    price_map = {
        # Proteins (expensive)
        'manok': 150, 'chicken': 150, 'baboy': 160, 'pork': 160,
        'baka': 200, 'beef': 200, 'isda': 120, 'fish': 120,
        'hipon': 180, 'shrimp': 180, 'tapa': 180, 'goto': 100,
        'atay': 80, 'buntot ng baka': 180, 'liempo ng baboy': 200,
        'buto ng baka': 150, 'giniling na baboy': 160, 'lechon': 250,
        'itlog': 10, 'eggs': 10, 'tofu': 35,
        # Vegetables (cheap to moderate)
        'kangkong': 20, 'sitao': 25, 'kamatis': 15, 'sibuyas': 20,
        'luya': 15, 'ginger': 15, 'papaya': 30, 'green papaya': 30,
        'malunggay': 10, 'patatas': 30, 'karot': 20, 'bell pepper': 25,
        'sili': 10, 'ampalaya': 20, 'kalabasa': 25, 'sitaw': 20,
        'talong': 15, 'repolyo': 25, 'mais': 20, 'pechay': 15,
        'gulay': 20, 'vegetables': 20,
        # Fruits
        'kalamansi': 10, 'papaya': 30,
        # Pantry items (cheap)
        'bawang': 15, 'garlic': 15, 'kanin': 50, 'rice': 50,
        'bigas': 50, 'suka': 15, 'vinegar': 15, 'toyo': 15,
        'soy sauce': 15, 'asin': 10, 'mantika': 25, 'gata': 30,
        'paminta': 10, 'pepper': 10, 'asukal': 20, 'kape': 15,
        'pandesal': 5, 'sinigang mix': 15, 'peanut butter': 40,
        'bagoong': 20, 'malagkit': 40, 'wonton wrapper': 25,
        'broth': 20, 'turmeric': 15, 'dahon ng laurel': 10,
        'tsokolate': 25, 'gatas': 50, 'milk': 50,
    }
    return price_map.get(ingredient_lower, 20)


def get_ingredient_quantity(ingredient_lower):
    """Get realistic quantity for an ingredient."""
    quantity_map = {
        # Proteins
        'manok': '1 kg', 'chicken': '1 kg', 'baboy': '500 g', 'pork': '500 g',
        'baka': '500 g', 'beef': '500 g', 'isda': '500 g', 'fish': '500 g',
        'hipon': '250 g', 'shrimp': '250 g', 'tapa': '250 g', 'goto': '250 g',
        'atay': '250 g', 'buntot ng baka': '500 g', 'liempo ng baboy': '500 g',
        'buto ng baka': '500 g', 'giniling na baboy': '500 g', 'lechon': '500 g',
        'itlog': '6 pcs', 'eggs': '6 pcs', 'tofu': '1 block',
        # Vegetables
        'kangkong': '1 bundle', 'sitao': '1 bundle', 'kamatis': '3 pcs',
        'sibuyas': '3 pcs', 'luya': '1 pc', 'ginger': '1 pc',
        'papaya': '1 pc', 'green papaya': '1 pc', 'malunggay': '1 bundle',
        'patatas': '3 pcs', 'karot': '3 pcs', 'bell pepper': '2 pcs',
        'sili': '5 pcs', 'ampalaya': '2 pcs', 'kalabasa': '1/2 pc',
        'sitaw': '1 bundle', 'talong': '3 pcs', 'repolyo': '1/2 head',
        'mais': '2 pcs', 'pechay': '1 bundle', 'gulay': '1 bundle',
        # Fruits
        'kalamansi': '5 pcs',
        # Pantry
        'bawang': '1 head', 'garlic': '1 head', 'kanin': '2 kg', 'rice': '2 kg',
        'bigas': '2 kg', 'suka': '1 bottle', 'vinegar': '1 bottle',
        'toyo': '1 bottle', 'soy sauce': '1 bottle', 'asin': '1 pack',
        'mantika': '1 bottle', 'gata': '2 packs', 'paminta': '1 pack',
        'pepper': '1 pack', 'asukal': '1 kg', 'kape': '1 pack',
        'pandesal': '10 pcs', 'sinigang mix': '2 packs',
        'peanut butter': '1 jar', 'bagoong': '1 jar', 'malagkit': '1 kg',
        'wonton wrapper': '1 pack', 'broth': '2 cubes', 'turmeric': '1 pc',
        'dahon ng laurel': '5 leaves', 'tsokolate': '2 tablets',
        'gatas': '1 liter', 'milk': '1 liter',
    }
    return quantity_map.get(ingredient_lower, '1 pack/bundle')


def rebuild_grocery_list(plan_data):
    """Rebuild grocery list from all meals."""
    all_ingredients = {}
    category_map = {
        'bawang': 'Pantry', 'kanin': 'Pantry', 'itlog': 'Dairy', 'bigas': 'Pantry',
        'tapa': 'Protein', 'suka': 'Pantry', 'pandesal': 'Pantry', 'kape': 'Pantry',
        'asukal': 'Pantry', 'gatas': 'Dairy', 'tsokolate': 'Pantry',
        'goto': 'Protein', 'luya': 'Vegetables', 'toyo': 'Pantry',
        'manok': 'Protein', 'paminta': 'Pantry', 'dahon ng laurel': 'Pantry',
        'baboy': 'Protein', 'kangkong': 'Vegetables', 'sitao': 'Vegetables',
        'kamatis': 'Vegetables', 'sibuyas': 'Vegetables', 'sinigang mix': 'Pantry',
        'papaya': 'Fruits', 'malunggay': 'Vegetables',
        'atay': 'Protein', 'patatas': 'Vegetables', 'karot': 'Vegetables',
        'bell pepper': 'Vegetables', 'isda': 'Protein', 'sili': 'Vegetables',
        'ampalaya': 'Vegetables', 'kalabasa': 'Vegetables', 'sitaw': 'Vegetables',
        'gata': 'Pantry', 'talong': 'Vegetables', 'asin': 'Pantry', 'mantika': 'Pantry',
        'buntot ng baka': 'Protein', 'peanut butter': 'Pantry', 'bagoong': 'Pantry',
        'liempo ng baboy': 'Protein', 'kalamansi': 'Fruits',
        'buto ng baka': 'Protein', 'repolyo': 'Vegetables', 'mais': 'Vegetables',
        'pechay': 'Vegetables', 'malagkit': 'Pantry', 'lechon': 'Protein',
        'wonton wrapper': 'Pantry', 'giniling na baboy': 'Protein', 'broth': 'Pantry',
        'baka': 'Protein', 'turmeric': 'Pantry',
        'chicken': 'Protein', 'garlic': 'Pantry', 'rice': 'Pantry', 'eggs': 'Dairy',
        'soy sauce': 'Pantry', 'vinegar': 'Pantry', 'pepper': 'Pantry',
        'green papaya': 'Fruits', 'ginger': 'Vegetables',
        'pork': 'Protein', 'beef': 'Protein', 'fish': 'Protein',
        'shrimp': 'Protein', 'tofu': 'Protein',
    }

    for day_data in plan_data.get('days', []):
        for meal_type, meal in day_data.get('meals', {}).items():
            for ingredient in meal.get('ingredients', []):
                ing_lower = ingredient.lower().strip()
                if ing_lower not in all_ingredients:
                    cat = category_map.get(ing_lower, 'Others')
                    all_ingredients[ing_lower] = {
                        'item': ingredient,
                        'quantity': get_ingredient_quantity(ing_lower),
                        'est_cost': get_ingredient_price(ing_lower),
                        'category': cat
                    }

    return list(all_ingredients.values())


def generate_fallback_meal(day, meal_type, current_plan):
    """Generate a fallback meal for regeneration."""
    fallback_meals = [
        {'name': 'Adobong Manok', 'ingredients': ['manok', 'toyo', 'suka', 'bawang', 'paminta'], 'estimated_cost': 85, 'cook_time': '30 mins', 'instructions': '1. Igisa ang bawang. 2. Ilagay ang manok. 3. Idagdag ang toyo at suka. 4. Pakuluan hanggang maluto.'},
        {'name': 'Sinigang na Baboy', 'ingredients': ['baboy', 'kangkong', 'kamatis', 'sinigang mix'], 'estimated_cost': 90, 'cook_time': '40 mins', 'instructions': '1. Pakuluan ang baboy. 2. Ilagay ang kamatis at sinigang mix. 3. Idagdag ang kangkong. 4. Pakuluan ng 5 minuto.'},
        {'name': 'Tinolang Manok', 'ingredients': ['manok', 'papaya', 'malunggay', 'luya', 'bawang'], 'estimated_cost': 80, 'cook_time': '35 mins', 'instructions': '1. Igisa ang luya at bawang. 2. Ilagay ang manok. 3. Magdagdag ng tubig at papaya. 4. Idagdag ang malunggay.'},
        {'name': 'Tortang Talong', 'ingredients': ['talong', 'itlog', 'asin', 'mantika'], 'estimated_cost': 45, 'cook_time': '15 mins', 'instructions': '1. I-ihaw ang talong. 2. Balatan at durugin. 3. Haluin ang itlog. 4. Prituhin.'},
        {'name': 'Ginataang Gulay', 'ingredients': ['kalabasa', 'sitaw', 'gata', 'bawang', 'sibuyas'], 'estimated_cost': 65, 'cook_time': '25 mins', 'instructions': '1. Igisa ang bawang at sibuyas. 2. Ilagay ang kalabasa at sitaw. 3. Idagdag ang gata. 4. Pakuluan.'},
        {'name': 'Sinangag at Itlog', 'ingredients': ['bawang', 'kanin', 'itlog'], 'estimated_cost': 35, 'cook_time': '10 mins', 'instructions': '1. Mag-gisa ng bawang. 2. Ilagay ang kanin. 3. Prituhin ang itlog.'},
        {'name': 'Paksiw na Isda', 'ingredients': ['isda', 'suka', 'bawang', 'luya', 'sili'], 'estimated_cost': 70, 'cook_time': '20 mins', 'instructions': '1. Pakuluan ang suka na may bawang at luya. 2. Ilagay ang isda. 3. Idagdag ang sili.'},
        {'name': 'Menudo', 'ingredients': ['baboy', 'patatas', 'karot', 'bell pepper', 'toyo'], 'estimated_cost': 85, 'cook_time': '35 mins', 'instructions': '1. Igisa ang bawang at sibuyas. 2. Ilagay ang baboy. 3. Idagdag ang patatas at karot. 4. Pakuluan.'},
        {'name': 'Kare-Kare', 'ingredients': ['buntot ng baka', 'peanut butter', 'kangkong', 'talong', 'bagoong'], 'estimated_cost': 95, 'cook_time': '45 mins', 'instructions': '1. Pakuluan ang buntot ng baka. 2. Idagdag ang peanut butter. 3. Ilagay ang gulay. 4. Ihain na may bagoong.'},
        {'name': 'Sisig', 'ingredients': ['liempo ng baboy', 'sibuyas', 'sili', 'kalamansi', 'itlog'], 'estimated_cost': 75, 'cook_time': '25 mins', 'instructions': '1. Prituhin ang liempo. 2. Hiwain ng maliliit. 3. Igisa ang sibuyas at sili. 4. Lagyan ng kalamansi.'},
    ]

    import random
    return random.choice(fallback_meals)


def generate_fallback_plan(budget, members, dietary, region):
    """Generate fallback meal plan data when Gemini API is unavailable."""
    budget_float = float(budget)
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    breakfast_options = [
        {'name': 'Sinangag at Itlog', 'ingredients': ['bawang', 'kanin', 'itlog'], 'estimated_cost': 35, 'cook_time': '10 mins', 'instructions': '1. Mag-gisa ng bawang. 2. Ilagay ang kanin at haluin. 3. Prituhin ang itlog. 4. Ihain kasama ang sinangag.'},
        {'name': 'Tapsilog', 'ingredients': ['tapa', 'kanin', 'itlog', 'suka'], 'estimated_cost': 55, 'cook_time': '15 mins', 'instructions': '1. Prituhin ang tapa. 2. Mag-sinangag ng kanin. 3. Prituhin ang itlog. 4. Ihain na may suka.'},
        {'name': 'Pandesal at Kape', 'ingredients': ['pandesal', 'kape', 'asukal', 'gatas'], 'estimated_cost': 25, 'cook_time': '5 mins', 'instructions': '1. Magtimpla ng kape. 2. Ihain ang pandesal. 3. Enjoy!.'},
        {'name': 'Champorado', 'ingredients': ['bigas', 'tsokolate', 'asukal', 'gatas'], 'estimated_cost': 30, 'cook_time': '20 mins', 'instructions': '1. Maglaga ng bigas sa tubig. 2. Ilagay ang tsokolate at haluin. 3. Magdagdag ng asukal. 4. Ihain na may gatas.'},
        {'name': 'Goto', 'ingredients': ['goto', 'kanin', 'luya', 'bawang', 'toyo'], 'estimated_cost': 40, 'cook_time': '25 mins', 'instructions': '1. Mag-saute ng bawang at luya. 2. Ilagay ang goto at tubig. 3. Pakuluan hanggang lumambot. 4. Ihain na may kanin.'},
    ]

    lunch_options = [
        {'name': 'Adobong Manok', 'ingredients': ['manok', 'toyo', 'suka', 'bawang', 'paminta', 'dahon ng laurel'], 'estimated_cost': 85, 'cook_time': '30 mins', 'instructions': '1. I-marinate ang manok sa toyo at paminta. 2. Igisa ang bawang. 3. Ilagay ang manok at lutuin. 4. Idagdag ang suka at laurel. 5. Pakuluan hanggang maluto.'},
        {'name': 'Sinigang na Baboy', 'ingredients': ['baboy', 'kangkong', 'sitao', 'kamatis', 'sibuyas', 'sinigang mix'], 'estimated_cost': 90, 'cook_time': '40 mins', 'instructions': '1. Pakuluan ang baboy sa tubig. 2. Ilagay ang kamatis at sibuyas. 3. Idagdag ang sinigang mix. 4. Ilagay ang gulay. 5. Pakuluan ng 5 minuto.'},
        {'name': 'Tinolang Manok', 'ingredients': ['manok', 'papaya', 'malunggay', 'luya', 'bawang'], 'estimated_cost': 80, 'cook_time': '35 mins', 'instructions': '1. Igisa ang luya at bawang. 2. Ilagay ang manok at lutuin. 3. Magdagdag ng tubig at pakuluan. 4. Ilagay ang papaya. 5. Idagdag ang malunggay bago patayin ang apoy.'},
        {'name': 'Menudo', 'ingredients': ['baboy', 'atay', 'patatas', 'karot', 'bell pepper', 'toyo'], 'estimated_cost': 85, 'cook_time': '35 mins', 'instructions': '1. Igisa ang bawang at sibuyas. 2. Ilagay ang baboy at atay. 3. Magdagdag ng tubig at toyo. 4. Ilagay ang patatas at karot. 5. Pakuluan hanggang maluto.'},
        {'name': 'Paksiw na Isda', 'ingredients': ['isda', 'suka', 'bawang', 'luya', 'sili', 'ampalaya'], 'estimated_cost': 70, 'cook_time': '20 mins', 'instructions': '1. Pakuluan ang suka na may bawang at luya. 2. Ilagay ang isda. 3. Idagdag ang sili at ampalaya. 4. Pakuluan ng 10 minuto.'},
    ]

    dinner_options = [
        {'name': 'Ginataang Gulay', 'ingredients': ['kalabasa', 'sitaw', 'gata', 'bawang', 'sibuyas', 'luya'], 'estimated_cost': 65, 'cook_time': '25 mins', 'instructions': '1. Igisa ang bawang, sibuyas at luya. 2. Ilagay ang kalabasa at sitaw. 3. Idagdag ang gata. 4. Pakuluan hanggang maluto ang gulay.'},
        {'name': 'Tortang Talong', 'ingredients': ['talong', 'itlog', 'asin', 'mantika'], 'estimated_cost': 45, 'cook_time': '15 mins', 'instructions': '1. I-ihaw ang talong hanggang lumambot. 2. Balatan at durugin. 3. Haluin ang itlog at asin. 4. Isama ang talong sa itlog. 5. Prituhin hanggang golden brown.'},
        {'name': 'Kare-Kare', 'ingredients': ['buntot ng baka', 'peanut butter', 'kangkong', 'talong', 'bagoong'], 'estimated_cost': 95, 'cook_time': '45 mins', 'instructions': '1. Pakuluan ang buntot ng baka. 2. Idagdag ang peanut butter. 3. Ilagay ang talong at kangkong. 4. Pakuluan hanggang maluto. 5. Ihain na may bagoong.'},
        {'name': 'Sisig', 'ingredients': ['liempo ng baboy', 'sibuyas', 'sili', 'kalamansi', 'itlog'], 'estimated_cost': 75, 'cook_time': '25 mins', 'instructions': '1. Prituhin ang liempo hanggang crispy. 2. Hiwain ng maliliit. 3. Igisa ang sibuyas at sili. 4. Isama ang karne. 5. Lagyan ng kalamansi at itlog.'},
        {'name': 'Bulalo', 'ingredients': ['buto ng baka', 'repolyo', 'mais', 'patatas', 'pechay'], 'estimated_cost': 100, 'cook_time': '60 mins', 'instructions': '1. Pakuluan ang buto ng baka ng matagal. 2. Ilagay ang mais at patatas. 3. Idagdag ang repolyo at pechay. 4. Timplahan ng asin at paminta.'},
    ]

    def filter_by_dietary(options_list):
        filtered = []
        for dish in options_list:
            name_lower = dish['name'].lower()
            ingredients_lower = ' '.join(dish['ingredients']).lower()

            if 'no pork' in dietary.lower() and ('baboy' in name_lower or 'baboy' in ingredients_lower or 'pork' in name_lower):
                continue
            if 'no beef' in dietary.lower() and ('baka' in name_lower or 'baka' in ingredients_lower or 'beef' in name_lower):
                continue
            if 'vegetarian' in dietary.lower() and any(p in ingredients_lower for p in ['manok', 'baboy', 'baka', 'isda', 'chicken', 'pork', 'beef', 'fish']):
                continue
            if 'no seafood' in dietary.lower() and any(s in ingredients_lower for s in ['isda', 'fish', 'hipon', 'shrimp', 'seafood']):
                continue
            filtered.append(dish)
        return filtered

    breakfasts = filter_by_dietary(breakfast_options)
    lunches = filter_by_dietary(lunch_options)
    dinners = filter_by_dietary(dinner_options)

    if not breakfasts:
        breakfasts = [{'name': 'Sinangag at Itlog', 'ingredients': ['bawang', 'kanin', 'itlog'], 'estimated_cost': 35, 'cook_time': '10 mins', 'instructions': '1. Mag-gisa ng bawang. 2. Ilagay ang kanin. 3. Prituhin ang itlog.'}]
    if not lunches:
        lunches = [{'name': 'Adobong Manok', 'ingredients': ['manok', 'toyo', 'suka', 'bawang', 'paminta'], 'estimated_cost': 85, 'cook_time': '30 mins', 'instructions': '1. Igisa ang bawang. 2. Ilagay ang manok. 3. Idagdag ang toyo at suka. 4. Pakuluan.'}]
    if not dinners:
        dinners = [{'name': 'Ginataang Gulay', 'ingredients': ['kalabasa', 'sitaw', 'gata', 'bawang', 'sibuyas'], 'estimated_cost': 65, 'cook_time': '25 mins', 'instructions': '1. Igisa ang bawang at sibuyas. 2. Ilagay ang kalabasa at sitaw. 3. Idagdag ang gata. 4. Pakuluan.'}]

    import random
    days = []
    all_grocery_items = {}

    for i, day_name in enumerate(days_of_week):
        b = random.choice(breakfasts)
        l = random.choice(lunches)
        d = random.choice(dinners)

        day_total = b['estimated_cost'] + l['estimated_cost'] + d['estimated_cost']

        days.append({
            'day': day_name,
            'meals': {
                'breakfast': b,
                'lunch': l,
                'dinner': d
            },
            'day_total': day_total
        })

        for meal in [b, l, d]:
            for ing in meal['ingredients']:
                all_grocery_items[ing.lower()] = ing

    weekly_total = sum(day['day_total'] for day in days)

    # Build grocery list with realistic prices and quantities
    grocery_list = []
    for ing_lower, ing_original in all_grocery_items.items():
        cat = 'Others'
        if ing_lower in ['bawang', 'kanin', 'bigas', 'suka', 'toyo', 'asin', 'mantika', 'gata', 'paminta', 'asukal', 'kape', 'pandesal', 'sinigang mix', 'peanut butter', 'bagoong', 'malagkit', 'wonton wrapper', 'broth', 'turmeric', 'dahon ng laurel']:
            cat = 'Pantry'
        elif ing_lower in ['manok', 'baboy', 'baka', 'isda', 'tapa', 'goto', 'atay', 'lechon', 'buntot ng baka', 'liempo ng baboy', 'buto ng baka', 'giniling na baboy', 'itlog']:
            cat = 'Protein'
        elif ing_lower in ['kangkong', 'sitao', 'kamatis', 'sibuyas', 'luya', 'papaya', 'malunggay', 'patatas', 'karot', 'bell pepper', 'sili', 'ampalaya', 'kalabasa', 'sitaw', 'talong', 'repolyo', 'mais', 'pechay', 'gulay']:
            cat = 'Vegetables'
        elif ing_lower in ['gatas']:
            cat = 'Dairy'
        elif ing_lower in ['kalamansi']:
            cat = 'Fruits'

        grocery_list.append({
            'item': ing_original,
            'quantity': get_ingredient_quantity(ing_lower),
            'est_cost': get_ingredient_price(ing_lower),
            'category': cat
        })

    return {
        'days': days,
        'weekly_total': weekly_total,
        'grocery_list': grocery_list
    }


