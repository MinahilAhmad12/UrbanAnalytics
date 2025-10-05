from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.contrib.gis.db import models as geomodels
from django.core.exceptions import ValidationError
from django.utils import timezone



class CustomUser(AbstractUser):
    is_verified = models.BooleanField(default=False)
    otp_code = models.CharField(max_length=6, blank=True, null=True)

    def str(self):
        return self.username


class Project(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    project_name = models.CharField(max_length=255, default="Untitled Project")   
    location_name = models.CharField(max_length=255, null=True, blank=True) 
    kml_file = models.FileField(upload_to='kml_files/', null=True, blank=True)  
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("project_name", "owner")
        ordering = ["-created_at"]
        
    def clean(self):
        if not self.location_name and not self.kml_file:
            raise ValidationError("You must provide either a location name or a KML file.")
        if self.location_name and self.kml_file:
            raise ValidationError("Provide only one: location name OR KML file.")

    def __str__(self):
        return f"{self.project_name} (by {self.owner.username})"

    
class UnionCouncil(models.Model):
    city_name = models.CharField(max_length=100)
    uc_name = models.CharField(max_length=100)
    geometry = geomodels.MultiPolygonField()

    class Meta:
        unique_together = ('city_name', 'uc_name')

    def str(self):
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

    def str(self):
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

    def str(self):
        return f"MapState for Area {self.project_area.id}"


class AreaAnalysis(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="analyses")
    analysis_type = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    area_type = models.CharField(max_length=20)
    geometry = models.JSONField(null=True, blank=True)
    stats = models.JSONField(null=True, blank=True)
    tile_url_template = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_pixelwise = models.BooleanField(default=False)
    uc_name = models.CharField(max_length=255, null=True, blank=True)
    city_name = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        unique_together = ("project", "analysis_type", "start_date", "end_date", "area_type", "uc_name")
        ordering = ["uc_name", "start_date"]

    def __str__(self):
        return f"{self.analysis_type.upper()} | {self.area_type} | {self.uc_name or 'ALL'}"

    
class YearlyAnalysis(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="yearly_analyses")
    analysis_type = models.CharField(max_length=50)   # ndvi, thermal, aqi
    year = models.IntegerField()                      # the selected year
    area_type = models.CharField(max_length=20)       # uc/custom/kml
    uc_name = models.CharField(max_length=255, null=True, blank=True)
    city_name = models.CharField(max_length=255, null=True, blank=True)

    # Summary statistics
    stats = models.JSONField(null=True, blank=True)

    # Pixelwise / Annual toggle
    is_pixelwise = models.BooleanField(default=False)
    map_layer_path = models.CharField(max_length=500, null=True, blank=True) # saved tile/map URL JSON
    # GEE live map info
    map_layer = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("project", "analysis_type", "year", "area_type", "uc_name", "is_pixelwise")

    def __str__(self):
        return f"{self.analysis_type.upper()} | {self.year} | {self.area_type} | {self.uc_name or 'ALL'} | {'Pixelwise' if self.is_pixelwise else 'Annual'}"

    
class YearlyPixelValue(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="yearly_pixel_values", null=True, blank=True)
    analysis_type = models.CharField(max_length=50)  # ndvi, aqi, etc.
    year = models.IntegerField()
    lat = models.FloatField()
    lng = models.FloatField()
    pixel_value = models.JSONField()  # store value like {"NDVI": 0.23} or {"AQI": 12.3}

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("project", "analysis_type", "year", "lat", "lng")

    def str(self):
        return f"{self.analysis_type.upper()} | {self.year} | ({self.lat}, {self.lng})"
    
class BeforeAfterAnalysis(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="before_after_analyses")
    analysis_type = models.CharField(max_length=50)   # ndvi, thermal, aqi
    area_type = models.CharField(max_length=20)       # uc/custom/kml
    uc_name = models.CharField(max_length=255, null=True, blank=True)
    city_name = models.CharField(max_length=255, null=True, blank=True)

    before_year = models.IntegerField()
    after_year = models.IntegerField()

    stats_before = models.JSONField(null=True, blank=True)
    stats_after = models.JSONField(null=True, blank=True)
    comparison = models.JSONField(null=True, blank=True)

    map_layer_before_path = models.CharField(max_length=500, null=True, blank=True)
    map_layer_after_path = models.CharField(max_length=500, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("project", "analysis_type", "area_type", "uc_name", "before_year", "after_year")

    def __str__(self):
        return f"{self.analysis_type.upper()} | {self.before_year}-{self.after_year} | {self.area_type} | {self.uc_name or 'ALL'}"
    

class BeforeAfterPixelwise(models.Model):
    project = models.ForeignKey("Project", on_delete=models.CASCADE)
    analysis_type = models.CharField(max_length=50)   # ndvi, thermal, aqi
    area_type = models.CharField(max_length=20)       # uc / kml / custom

    uc_name = models.CharField(max_length=255, null=True, blank=True)
    city_name = models.CharField(max_length=255, null=True, blank=True)

    before_year = models.IntegerField()
    after_year = models.IntegerField()

    # Required cached file paths for storing map layers (JSON files)
    map_layer_before_path = models.CharField(max_length=500)
    map_layer_after_path = models.CharField(max_length=500)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (
            "project",
            "analysis_type",
            "area_type",
            "uc_name",
            "before_year",
            "after_year",
        )
        indexes = [
            models.Index(fields=["project", "analysis_type", "before_year", "after_year"]),
            models.Index(fields=["area_type"]),
        ]

    def _str_(self):
        return f"{self.analysis_type.upper()} | {self.uc_name or 'Custom Area'} | {self.before_year} vs {self.after_year}"
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

    def str(self):
        return f"Report[{self.report_type}] for Area {self.project_area.id}"