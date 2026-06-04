from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('planner/', views.planner, name='planner'),
    path('generate/', views.generate_plan, name='generate_plan'),
    path('plan/<int:plan_id>/', views.plan_view, name='plan_view'),
    path('plan/<int:plan_id>/regenerate/', views.regenerate_meal, name='regenerate_meal'),
    path('plan/<int:plan_id>/save/', views.save_plan, name='save_plan'),
    path('grocery/<int:plan_id>/', views.grocery_list, name='grocery_list'),
    path('export/<int:plan_id>/', views.export_pdf, name='export_pdf'),
    path('saved/', views.saved_plans, name='saved_plans'),
    path('saved/<int:plan_id>/delete/', views.delete_saved_plan, name='delete_saved_plan'),
    path('about/', views.about, name='about'),
]
