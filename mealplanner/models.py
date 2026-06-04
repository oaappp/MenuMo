from django.db import models
from django.contrib.auth.models import User
import json

class MealPlan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    budget = models.DecimalField(max_digits=10, decimal_places=2)
    members = models.IntegerField()
    dietary = models.CharField(max_length=500, blank=True, default='')
    region = models.CharField(max_length=50, default='Luzon')
    weekly_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    plan_json = models.TextField(blank=True, default='{}')
    created_at = models.DateTimeField(auto_now_add=True)
    session_key = models.CharField(max_length=100, blank=True, default='')

    def get_plan_data(self):
        try:
            return json.loads(self.plan_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_plan_data(self, data):
        self.plan_json = json.dumps(data)

    def __str__(self):
        return f"MealPlan {self.id} - {self.created_at.strftime('%b %d, %Y')}"

    class Meta:
        ordering = ['-created_at']


class SavedPlan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    meal_plan = models.ForeignKey(MealPlan, on_delete=models.CASCADE)
    saved_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"SavedPlan {self.id} by {self.user.username}"

    class Meta:
        ordering = ['-saved_at']
