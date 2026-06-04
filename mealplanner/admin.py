from django.contrib import admin
from .models import MealPlan, SavedPlan

@admin.register(MealPlan)
class MealPlanAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'budget', 'members', 'region', 'weekly_total', 'created_at']
    list_filter = ['region', 'created_at']
    search_fields = ['user__username']

@admin.register(SavedPlan)
class SavedPlanAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'meal_plan', 'saved_at']
    list_filter = ['saved_at']
