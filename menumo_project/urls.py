from django.contrib import admin
from django.urls import path, include, re_path
from mealplanner import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/logout/', views.custom_logout, name='account_logout'),
    path('accounts/', include('allauth.urls')),
    path('', include('mealplanner.urls')),
]


