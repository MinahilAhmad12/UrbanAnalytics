from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings


class CustomUser(AbstractUser):
    is_verified = models.BooleanField(default=False)
    otp_code = models.CharField(max_length=6, blank=True, null=True)

    def __str__(self):
        return self.username



class Project(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='projects')
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=255, blank=True, null=True) 
    kml_file = models.FileField(upload_to='kml_files/', blank=True, null=True)  
    map_data = models.JSONField(blank=True, null=True) 
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Report(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)  
    report_file = models.FileField(upload_to='reports/')  
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.generated_at}"

class CityAnalysis(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='city_analyses')
    city_name = models.CharField(max_length=255)
    selected_ucs = models.JSONField(default=list)
    ndvi = models.JSONField(null=True, blank=True)
    thermal = models.JSONField(null=True, blank=True)
    aqi = models.JSONField(null=True, blank=True)

