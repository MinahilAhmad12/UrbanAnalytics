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




class AreaAnalysis(models.Model):
    project = models.ForeignKey(Project,on_delete=models.CASCADE,related_name="analyses", null=True,blank=True)
    analysis_type = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    area_type = models.CharField(max_length=20)
    geometry = models.JSONField(null=True, blank=True)
    stats = models.JSONField(null=True, blank=True)
    tile_url_template = models.CharField(max_length=500, null=True, blank=True)
    kml_hash = models.CharField(max_length=128, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_pixelwise = models.BooleanField(default=False)
    uc_name = models.CharField(max_length=255, null=True, blank=True)
    city_name = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        unique_together = ("project", "analysis_type", "start_date", "end_date", "area_type", "uc_name","kml_hash")
        ordering = ["uc_name", "start_date"]

    def __str__(self):
        return f"{self.analysis_type.upper()} | {self.area_type} | {self.uc_name or 'ALL'}"

    
class YearlyAnalysis(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="yearly_analyses", null=True, blank=True)
    analysis_type = models.CharField(max_length=50)  
    year = models.IntegerField()                     
    area_type = models.CharField(max_length=20)      
    uc_name = models.CharField(max_length=255, null=True, blank=True)
    city_name = models.CharField(max_length=255, null=True, blank=True)

    
    stats = models.JSONField(null=True, blank=True)
    kml_hash = models.CharField(max_length=64, null=True, blank=True)

    
    is_pixelwise = models.BooleanField(default=False)
    
    tile_url_template = models.CharField(max_length=500, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("project", "analysis_type", "year", "area_type", "uc_name", "is_pixelwise")
        ordering = ["uc_name", "year"]

    def _str_(self):
        return f"{self.analysis_type.upper()} | {self.year} | {self.area_type} | {self.uc_name or 'ALL'} | {'Pixelwise' if self.is_pixelwise else 'Annual'}"
   
class YearlyPixelValue(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="yearly_pixel_values", null=True, blank=True)
    analysis_type = models.CharField(max_length=50)  
    year = models.IntegerField()
    lat = models.FloatField()
    lng = models.FloatField()
    pixel_value = models.JSONField()  

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("project", "analysis_type", "year", "lat", "lng")

    def str(self):
        return f"{self.analysis_type.upper()} | {self.year} | ({self.lat}, {self.lng})"
class ProjectChatMessage(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="chat_messages")
    role = models.CharField(max_length=20)  # "user" or "assistant"
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.project.project_name} | {self.role}: {self.message[:30]}"     
class BeforeAfterAnalysis(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="before_after_analyses")
    analysis_type = models.CharField(max_length=50)   
    area_type = models.CharField(max_length=20)       
    uc_name = models.CharField(max_length=255, null=True, blank=True)
    city_name = models.CharField(max_length=255, null=True, blank=True)

    before_year = models.IntegerField()
    after_year = models.IntegerField()

    stats_before = models.JSONField(null=True, blank=True)
    stats_after = models.JSONField(null=True, blank=True)
    comparison = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("project", "analysis_type", "area_type", "uc_name", "before_year", "after_year")

    def __str__(self):
        return f"{self.analysis_type.upper()} | {self.before_year}-{self.after_year} | {self.area_type} | {self.uc_name or 'ALL'}"


class BeforeAfterPixelwise(models.Model):
    project = models.ForeignKey("Project", on_delete=models.CASCADE,null=True, blank=True)
    analysis_type = models.CharField(max_length=50)   
    area_type = models.CharField(max_length=20)       

    uc_name = models.CharField(max_length=255, null=True, blank=True)
    city_name = models.CharField(max_length=255, null=True, blank=True)

    before_year = models.IntegerField()
    after_year = models.IntegerField()
    kml_hash = models.CharField(max_length=64, null=True, blank=True)
    
    tile_url_before = models.CharField(max_length=500, null=True, blank=True)
    tile_url_after = models.CharField(max_length=500, null=True, blank=True)

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
            "kml_hash",
        )
        indexes = [
            models.Index(fields=["project", "analysis_type", "before_year", "after_year"]),
            models.Index(fields=["area_type"]),
            models.Index(fields=["kml_hash"]),
        ]

    def __str__(self):
        return f"{self.analysis_type.upper()} | {self.uc_name or 'Custom Area'} | {self.before_year} vs {self.after_year}"


class Report(models.Model):
    REPORT_TYPES = [
        ('average', 'Average'),
        ('1yr_average', '1-Year Average'),
        ('2yr_comparison', '2-Year Comparison'),
    ]

    ANALYSIS_TYPES = [
        ('ndvi', 'NDVI'),
        ('thermal', 'Thermal'),
        ('aqi', 'AQI'),
    ]

    AREA_TYPES = [
        ('uc', 'UC'),
        ('kml', 'KML'),
    ]

    project = models.ForeignKey('Project', on_delete=models.CASCADE)
    analysis_type = models.CharField(max_length=20, choices=ANALYSIS_TYPES)
    report_type = models.CharField(max_length=30, choices=REPORT_TYPES)
    area_type = models.CharField(max_length=10, choices=AREA_TYPES)

    
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    
    year = models.IntegerField(null=True, blank=True)

    
    before_year = models.IntegerField(null=True, blank=True)
    after_year = models.IntegerField(null=True, blank=True)

    file = models.FileField(max_length=500, upload_to="reports/", blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    message = models.TextField(null=True, blank=True)

    def __str__(self):
        if self.before_year and self.after_year:
            return f"{self.project} | {self.analysis_type.upper()} | {self.before_year}→{self.after_year}"
        elif self.year:
            return f"{self.project} | {self.analysis_type.upper()} | Year {self.year}"
        else:
            return f"{self.project} | {self.analysis_type.upper()} | {self.start_date}→{self.end_date}"


class MapState(models.Model):
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name="map_state")

    selected_analysis_type = models.CharField(max_length=50, null=True, blank=True)
    selected_mode = models.CharField(max_length=50, null=True, blank=True)   
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    
    selected_year = models.IntegerField(null=True, blank=True)

    
    before_year = models.IntegerField(null=True, blank=True)
    after_year = models.IntegerField(null=True, blank=True)

    
    map_center = models.JSONField(null=True, blank=True)  
    zoom_level = models.IntegerField(null=True, blank=True)

    
    area_type = models.CharField(max_length=20, null=True, blank=True)  
    city_name = models.CharField(max_length=255, null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)
