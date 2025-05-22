from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.contrib.gis.db import models as geomodels


class CustomUser(AbstractUser):
    is_verified = models.BooleanField(default=False)
    otp_code = models.CharField(max_length=6, blank=True, null=True)

    def __str__(self):
        return self.username



class Project(models.Model):
    owner      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="projects")
    name       = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} (by {self.owner.username})"


class UnionCouncil(models.Model):
    city_name = models.CharField(max_length=100)
    uc_name = models.CharField(max_length=100)
    geometry = geomodels.MultiPolygonField()

    class Meta:
        unique_together = ('city_name', 'uc_name')

    def __str__(self):
        return f"{self.uc_name} ({self.city_name})"



class ProjectArea(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="areas")
    name = models.CharField(max_length=100, blank=True, null=True)
    area_type = models.CharField(max_length=10, choices=[
        ('uc', 'Union Council'),
        ('custom', 'Custom Drawn'),
        ('kml', 'KML Uploaded'),
    ])
    selected_city = models.CharField(max_length=100, blank=True, null=True)
    uc_ids = models.ManyToManyField(UnionCouncil, blank=True)
    custom_geometry = models.JSONField(blank=True, null=True)
    kml_file = models.FileField(upload_to='kml_files/', blank=True, null=True)
    date_range_start = models.DateField(blank=True, null=True)
    date_range_end = models.DateField(blank=True, null=True)

    def __str__(self):
        return self.name or f"Area {self.id} for Project: {self.project.name}"



class MapState(models.Model):
    project_area = models.OneToOneField(ProjectArea, on_delete=models.CASCADE, related_name="map_state")
    active_layer = models.CharField(max_length=20, choices=[
        ('ndvi', 'NDVI'),
        ('thermal', 'Thermal'),
        ('aqi', 'AQI'),
    ], blank=True, null=True)
    toggle_state = models.JSONField(default=dict)
    zoom_level = models.FloatField(blank=True, null=True)
    center_coords = models.JSONField(blank=True, null=True)
    basemap_style = models.CharField(max_length=50, default='streets')

    def __str__(self):
        return f"MapState for Area {self.project_area.id}"



class AreaAnalysis(models.Model):
    project_area = models.ForeignKey(ProjectArea, on_delete=models.CASCADE, related_name="analyses")
    analysis_type = models.CharField(max_length=50, choices=[
        ('ndvi', 'NDVI'),
        ('thermal', 'Thermal'),
        ('aqi', 'AQI'),
    ])
    tile_url = models.URLField()
    stats = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('project_area', 'analysis_type')

    def __str__(self):
        return f"{self.analysis_type} analysis for Area {self.project_area.id}"


class Report(models.Model):
    project_area   = models.ForeignKey(
        'ProjectArea',
        on_delete=models.CASCADE,
        related_name='reports'
    )
    created_at     = models.DateTimeField(auto_now_add=True)
    report_type    = models.CharField(max_length=50)  
    parameters     = models.JSONField(default=dict, blank=True)  
    file           = models.FileField(upload_to='reports/')  

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Report[{self.report_type}] for Area {self.project_area.id}"
