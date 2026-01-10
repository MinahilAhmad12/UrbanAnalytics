from django.http import JsonResponse
from django.contrib.gis.geos import GEOSGeometry
from urbananalytics.models import UnionCouncil
from django.core.serializers import serialize
from django.contrib.gis.serializers import geojson
from django.http import HttpResponse
import ee
from django.contrib.gis.geos import GEOSGeometry, Polygon as GEOSPolygon
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from urbananalytics.models import AreaAnalysis, Project, YearlyAnalysis ,YearlyPixelValue,BeforeAfterAnalysis,BeforeAfterPixelwise
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from concurrent.futures import ThreadPoolExecutor
import json
from datetime import datetime
from dateutil.relativedelta import relativedelta
import fastkml
from shapely.geometry import shape, mapping
import os
from django.conf import settings
from urbananalytics.helpers import extract_bounds_from_kml
from fastkml import kml
from django.contrib.gis.geos import Polygon
import certifi
from django.shortcuts import get_object_or_404
import numpy as np
from rest_framework import status
from django.db.models import Avg, Min, Max
from django.http import JsonResponse
from django.contrib.gis.geos import GEOSGeometry
from urbananalytics.models import UnionCouncil
from django.core.serializers import serialize
from django.contrib.gis.serializers import geojson
from django.http import HttpResponse
import ee
from django.contrib.gis.geos import GEOSGeometry, Polygon as GEOSPolygon
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from urbananalytics.models import AreaAnalysis, Project, YearlyAnalysis ,YearlyPixelValue
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from concurrent.futures import ThreadPoolExecutor
import json
from datetime import datetime

import fastkml
from shapely.geometry import shape, mapping
import os
from django.conf import settings
from fastkml import kml
from django.contrib.gis.geos import Polygon
import certifi
from django.shortcuts import get_object_or_404
import numpy as np
from rest_framework import status
from django.db.models import Avg, Min, Max
import boto3
import geemap
import re
import shutil
import hashlib
from rio_cogeo.cogeo import cog_translate
from rasterio.enums import Resampling
from rio_cogeo.profiles import cog_profiles
import rasterio
import uuid
import re
import uuid
import shutil
import logging
from concurrent.futures import ThreadPoolExecutor
from shapely.geometry import shape, Polygon, MultiPolygon
import math
import subprocess
from pyproj import Transformer
from functools import partial


from rio_tiler.io import COGReader


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image
import mercantile
import time
import hashlib


DATA_DIR = os.path.join(settings.BASE_DIR, "local_data")
os.makedirs(DATA_DIR, exist_ok=True)

from django.core.exceptions import ImproperlyConfigured

from django.contrib.gis.geos import GEOSGeometry
from shapely.geometry import Polygon as ShapelyPolygon
import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timedelta



def kml_to_geosgeometry(kml_content: str) -> GEOSGeometry:
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    root = ET.fromstring(kml_content)

    polygon_elem = root.find('.//kml:Polygon', ns)
    if polygon_elem is None:
        raise ValueError("No Polygon found in KML")

    coords_text = polygon_elem.find('.//kml:coordinates', ns)
    if coords_text is None or not coords_text.text.strip():
        raise ValueError("Polygon has no coordinates")

    coords = []
    for coord_pair in coords_text.text.strip().split():
        lon, lat = map(float, coord_pair.split(',')[:2])
        coords.append((lon, lat))

    
    shapely_poly = ShapelyPolygon(coords)
    wkt = shapely_poly.wkt  
    
    return GEOSGeometry(wkt)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_ucs(request):
    project_id = request.query_params.get("project_id")
    if not project_id:
        return Response({"error": "project_id required"}, status=400)

    try:
        project = Project.objects.get(id=project_id)

        if project.location_name:
            city_name = project.location_name
            file_path = os.path.join(DATA_DIR, f"{city_name.lower()}_ucs.json")

            if os.path.exists(file_path):
                with open(file_path, "r") as f:
                    return Response(json.load(f))

            ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)
            if not ucs.exists():
                return Response({"error": "No UCs found for this city"}, status=404)

            geojson = serialize(
                "geojson", ucs,
                geometry_field="geometry",
                fields=("uc_name", "city_name")
            )
            geojson_data = json.loads(geojson)

            with open(file_path, "w") as f:
                json.dump(geojson_data, f)

            return Response(geojson_data)

        elif project.kml_file:
            kml_path = project.kml_file.path
            with open(kml_path, "rb") as f:
                kml_bytes = f.read()

            
            kml_hash = hashlib.md5(kml_bytes).hexdigest()
            content_cache_path = os.path.join(DATA_DIR, f"{kml_hash}_kml_ucs.json")

            
            if not os.path.exists(content_cache_path):
                kml_content = kml_bytes.decode("utf-8-sig")  
                polygon = kml_to_geosgeometry(kml_content)
                ucs = UnionCouncil.objects.filter(geometry__intersects=polygon)

                if not ucs.exists():
                    return Response({"error": "No UCs found in this KML area"}, status=404)

                geojson = serialize(
                    "geojson", ucs,
                    geometry_field="geometry",
                    fields=("uc_name", "city_name")
                )
                geojson_data = json.loads(geojson)

                
                with open(content_cache_path, "w") as f:
                    json.dump(geojson_data, f)
            else:
                
                with open(content_cache_path, "r") as f:
                    geojson_data = json.load(f)

            
            project_cache_path = os.path.join(DATA_DIR, f"project_{project.id}_kml_ucs.json")
            if not os.path.exists(project_cache_path):
                with open(project_cache_path, "w") as f:
                    json.dump(geojson_data, f)

            return Response(geojson_data)
            

        else:
            return Response({"error": "Project has neither location_name nor KML file"}, status=400)

    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=404)
    
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
os.environ['SSL_CERT_FILE'] = certifi.where()

def init_ee():
   
    
    if ee.data._initialized:
        return

    
    service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    
    if not service_account_path:
        service_account_path = os.path.join(settings.BASE_DIR, "service_account.json")

    
    if not os.path.exists(service_account_path):
        raise ImproperlyConfigured(
            f"Service account file not found at: {service_account_path}. "
            "Please check your GOOGLE_APPLICATION_CREDENTIALS path or upload the key file."
        )

    
    with open(service_account_path, "r") as f:
        service_account_info = json.load(f)

    service_account_email = service_account_info.get("client_email")
    if not service_account_email:
        raise ImproperlyConfigured("Invalid service_account.json — missing 'client_email'.")

    
    try:
        credentials = ee.ServiceAccountCredentials(service_account_email, key_file=service_account_path)
        ee.Initialize(credentials, project="urbananalytics-460415")
        print("Earth Engine initialized successfully.")
    except Exception as e:
        print("Failed to initialize Earth Engine:", e)
        raise RuntimeError("Earth Engine initialization failed. Check credentials or key file.")

def load_ucs_for_uc(city_name):
    
    file_path = os.path.join(DATA_DIR, f"{city_name.lower()}_ucs.json")
    if not os.path.exists(file_path):
        return None

    with open(file_path, "r") as f:
        return json.load(f) 
    
    
def load_ucs_for_kml(project_id):
    
    file_path = os.path.join(DATA_DIR, f"project_{project_id}_kml_ucs.json")
    if not os.path.exists(file_path):
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)  

s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_S3_REGION_NAME
)

def dispersion_scaling(pm25, blh, rh):
    """
    Time-agnostic PM2.5 scaling using atmospheric dispersion.
    Suitable for monthly, seasonal, and yearly analysis.
    """
    if pm25 is None or blh is None:
        return None

    # Normalize BLH (Pakistan urban climatology)
    blh_norm = min(max(blh, 300), 2000)

    # Lower BLH → higher concentration (inversion)
    blh_factor = 800 / blh_norm

    # RH hygroscopic growth (already partly applied, but damped here)
    rh_factor = 1 + 0.005 * max(0, rh - 50)

    # Final correction (empirical, literature-backed)
    correction = 0.45 * blh_factor * rh_factor

    return pm25 * correction


@api_view(['POST'])
def perform_gee_average_analysis(request):
    init_ee()

    analysis_type = request.data.get("analysis_type")
    start_date = request.data.get("start_date")
    end_date = request.data.get("end_date")
    area_type = request.data.get("area_type")
    project_id = request.data.get("project_id")
    city_name = request.data.get("city_name")
    geometry_data = request.data.get("geometry")

    if not all([analysis_type, start_date, end_date, area_type]):
        return Response({"error": "Missing required parameters"}, status=400)

    try:
        results = []

        
        if project_id and area_type in ["uc", "kml"]:
            cached_results = AreaAnalysis.objects.filter(
                project_id=project_id,
                analysis_type=analysis_type,
                start_date=start_date,
                end_date=end_date,
                area_type=area_type,
                is_pixelwise=False
            ).order_by('uc_name')

            if cached_results.exists():
                for cached in cached_results:
                    mean_value = cached.stats.get("mean", None)
                    if mean_value is not None:
                        mean_value = round(mean_value, 4)
                    results.append({
                        "uc_name": cached.uc_name,
                        "city_name": cached.city_name,
                        "mean_value": mean_value,
                        "color": cached.stats.get("color"),
                        "area_type": cached.area_type
                    })
                return Response({
                    "message": f"Cached {analysis_type.upper()} average analysis returned",
                    "results": results
                })

        def analyze_feature(feature):
            
            uc_name = feature["properties"].get("uc_name", "unknown_uc")
            city_name = feature["properties"].get("city_name", "unknown_city")

            try:
                
                geom = feature["geometry"]
                if geom["type"] == "MultiPolygon":
                    polygon = ee.Geometry.MultiPolygon(geom["coordinates"])
                else:
                    polygon = ee.Geometry.Polygon(geom["coordinates"])
                result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)

                if not result or "stats" not in result:
                    return {"mean": None, "color": "#000000", "status": "error"}


                mean_value = result["stats"].get("mean", None)
                status = result["stats"].get("status", "unknown")
                
                print(f"[{uc_name}] Result stats: {result['stats']}")
                print(f"[{uc_name}] Extracted mean_value: {mean_value}, status: {status}")
                
                if mean_value is None or (isinstance(mean_value, float) and math.isnan(mean_value)):
                    print(f"[{uc_name}] WARNING: mean_value is None or NaN, using 0")
                    mean_value = 0
                elif analysis_type.lower() == "ndvi":
                    mean_value =  mean_value
                elif analysis_type.lower() == "thermal":
                    mean_value = mean_value 
                elif analysis_type.lower() == "aqi":
                    mean_value = mean_value  

                
                mean_value = round(mean_value, 4)
                result["mean_value"] = mean_value
                color = result["stats"].get("color", "#000000")
                AreaAnalysis.objects.update_or_create(
                    project_id=project_id,
                    analysis_type=analysis_type,
                    start_date=start_date,
                    end_date=end_date,
                    area_type=area_type,
                    uc_name=uc_name,
                    defaults={
                        "city_name": city_name,
                        "stats": {"mean": mean_value, "color": color},
                        "is_pixelwise": False,
                        "tile_url_template": None
                    }
                )

                return {
                    "uc_name": uc_name,
                    "city_name": city_name,
                    "mean_value": mean_value,
                    "area_type": area_type,
                    "color": color,

                }

            except Exception as e:
                return {
                    "uc_name": uc_name,
                    "city_name": city_name,
                    "error": "1",
                    "error_msg": str(e),
                    "mean_value": None,
                    "color": "#000000",

                }
    
        if area_type == "uc":
            if not project_id:
                return Response({"error": "project_id is required for UC analysis"}, status=400)

            project = Project.objects.filter(id=project_id).first()
            if not project:
                return Response({"error": "Project not found"}, status=404)

            city_name = project.location_name

            uc_data = load_ucs_for_uc(city_name)

            if not uc_data:
                db_ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)
                if not db_ucs.exists():
                    return Response({"error": f"No UC data found for {city_name}"}, status=404)
                features = [
                    {
                        "geometry": json.loads(uc.geometry.geojson),
                        "properties": {"uc_name": uc.uc_name, "city_name": uc.city_name}
                    } for uc in db_ucs
                ]
            else:
                features = uc_data.get("features", [])

            if not features:
                return Response({"error": "No Union Councils found"}, status=404)

            

        elif area_type == "kml":
            if not project_id:
                return Response({"error": "project_id is required for KML analysis"}, status=400)

            local_kml_file = os.path.join(
                DATA_DIR, f"project_{project_id}_kml_ucs.json"
            )
            if os.path.exists(local_kml_file):
                with open(local_kml_file, "r") as f:
                    kml_data = json.load(f)
                features = kml_data.get("features", [])
            else:
                project = Project.objects.filter(id=project_id).first()
                if not project:
                    return Response({"error": "Project not found"}, status=404)

                db_ucs = UnionCouncil.objects.all()
                if not db_ucs.exists():
                    return Response({"error": "No UC data in database"}, status=404)

                features = [
                    {
                        "geometry": json.loads(uc.geometry.geojson),
                        "properties": {"uc_name": uc.uc_name, "city_name": uc.city_name}
                    } for uc in db_ucs
                ]

            if not features:
                return Response({"error": "No Union Councils found"}, status=404)
        else:
            return Response({"error": "Invalid area_type"}, status=400)

        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(analyze_feature, feature) for feature in features]
            for future in as_completed(futures):
                res = future.result()
                if res:
                    print(f"[RESPONSE] Adding result: {res}")
                    results.append(res)

       
        return Response({
            "message": f"{analysis_type.upper()} average analysis completed",
            "results": results
        })

    except Exception as e:
        return Response({"error": str(e)}, status=500)



def compute_aqi(concentration, breakpoints):
    """Calculate AQI using EPA linear interpolation formula."""
    if concentration is None or math.isnan(concentration) or concentration < 0:
        return None

    for bp_lo, bp_hi, aqi_lo, aqi_hi in breakpoints:
        if bp_lo <= concentration <= bp_hi:
            aqi = ((aqi_hi - aqi_lo) / (bp_hi - bp_lo)) * (concentration - bp_lo) + aqi_lo
            return round(aqi)

    
    if concentration > breakpoints[-1][1]:
        return 500

    return None



AQI_BREAKPOINTS = {
    "PM25": [  
        (0.0, 12.0, 0, 50),
        (12.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 150.4, 151, 200),
        (150.5, 250.4, 201, 300),
        (250.5, 500.4, 301, 500),
    ],
    "PM10": [  
        (0, 54, 0, 50),
        (55, 154, 51, 100),
        (155, 254, 101, 150),
        (255, 354, 151, 200),
        (355, 424, 201, 300),
        (425, 604, 301, 500),
    ],
    "NO2": [  
        (0, 53, 0, 50),
        (54, 100, 51, 100),
        (101, 360, 101, 150),
        (361, 649, 151, 200),
        (650, 1249, 201, 300),
        (1250, 2049, 301, 500),
    ],
    "SO2": [  
        (0, 35, 0, 50),
        (36, 75, 51, 100),
        (76, 185, 101, 150),
        (186, 304, 151, 200),
        (305, 604, 201, 300),
        (605, 1004, 301, 500),
    ],
    "O3": [  
        (0, 54, 0, 50),
        (55, 70, 51, 100),
        (71, 85, 101, 150),
        (86, 105, 151, 200),
        (106, 200, 201, 300),
        (201, 604, 301, 500),
    ],
}


def perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date):
    init_ee()
    

    try:
        
        if analysis_type.lower() == "ndvi":
            scale = 10 
            source = "Sentinel-2 (temporal mean NDVI)"  

            def mask_s2_sr(image):
                qa = image.select('QA60')
                cloud = qa.bitwiseAnd(1 << 10).Or(qa.bitwiseAnd(1 << 11))
                return image.updateMask(cloud.Not())

            
            s2 = (
                ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(polygon)
                .filterDate(start_date, end_date)
                .map(mask_s2_sr)
            )
            print("Sentinel-2 images:", s2.size().getInfo())

            if s2.size().getInfo() > 0:

                
                def per_image_ndvi(img):
                    ndvi = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
                    return ndvi.unmask(0).copyProperties(img, ['system:time_start'])

                
                ndvi_images = s2.map(per_image_ndvi)

                
                mean_ndvi_image = ndvi_images.mean().rename('NDVI')

                
                mean_value = mean_ndvi_image.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=polygon,
                    scale=10,
                    maxPixels=1e13
                ).getInfo().get('NDVI')

                image = mean_ndvi_image
                band_name = "NDVI"
                source = "Sentinel-2 (temporal mean NDVI)"
            else:
    
                l8 = (
                    ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
                    .filterBounds(polygon)
                    .filterDate(start_date, end_date)
                    .filter(ee.Filter.lt('CLOUD_COVER', 60))
                )

                if l8.size().getInfo() == 0:
                    raise ValueError("No NDVI images available for this date range.")

                
                def per_image_ndvi_l8(img):
                    nir = img.select('SR_B5').multiply(0.0000275).add(-0.2).unmask(0)
                    red = img.select('SR_B4').multiply(0.0000275).add(-0.2).unmask(0)
                    ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
                    return ndvi.copyProperties(img, ['system:time_start'])

                
                ndvi_images = l8.map(per_image_ndvi_l8)

                
                mean_ndvi_image = ndvi_images.mean().rename('NDVI')

                
                mean_value = mean_ndvi_image.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=polygon,
                    scale=30,
                    maxPixels=1e13
                ).getInfo().get('NDVI')

                image = mean_ndvi_image
                band_name = "NDVI"
                source = "Landsat-8 (temporal mean NDVI)"
                scale = 30  
                    
            if mean_value < 0.2:
                color = "#ffffcc"  
            elif mean_value < 0.4:
                color = "#c2e699"  
            elif mean_value < 0.6:
                color = "#78c679"  
            elif mean_value < 0.8:
                color = "#31a354"  
            else:
                color = "#006837"  

        elif analysis_type.lower() == "thermal":

            
            collection = (
                ee.ImageCollection('LANDSAT/LC09/C02/T1_L2')
                .filterBounds(polygon)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt('CLOUD_COVER', 60))
            )

            
            if collection.size().getInfo() == 0:
                print("[THERMAL] No Landsat 9 images found. Using Landsat 8.")
                collection = (
                    ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
                    .filterBounds(polygon)
                    .filterDate(start_date, end_date)
                    .filter(ee.Filter.lt('CLOUD_COVER', 60))
                )

        
            if collection.size().getInfo() == 0:
                print("[THERMAL] No Landsat 8/9 images found for this date range.")
                mean_value = 0
                color = "#000000"
                image = None
                band_name = "LST"
                scale = 30
                source = "NO IMAGES FOUND"
                status = "no_image"
                return {
                    "stats": {
                        "mean": mean_value,
                        "color": color,
                        "status": status,
                        "source": source
                    }
                }

            
            def per_image_lst(img):
                return img.select('ST_B10').multiply(0.00341802).add(149.0).rename('LST') \
                        .copyProperties(img, ['system:time_start'])

            
            lst_images = collection.map(per_image_lst)

            
            mean_lst_image = lst_images.mean().rename("LST").clip(polygon)

            
            stats = mean_lst_image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=polygon,
                scale=30,
                maxPixels=1e13
            )

            
            mean_value = stats.get("LST").getInfo() if stats else None

            
            if mean_value is None or isinstance(mean_value, float) and (mean_value != mean_value):
                print("[THERMAL] LST returned None/NaN. Using 0.")
                mean_value = 0

            print("Mean LST:", mean_value)

        
            if mean_value < 288:
                color = "#00008B"
            elif mean_value < 293:
                color = "#00FFFF"
            elif mean_value < 298:
                color = "#00FF00"
            elif mean_value < 303:
                color = "#FFFF00"
            elif mean_value < 308:
                color = "#FFA500"
            elif mean_value < 313:
                color = "#FF4500"
            else:
                color = "#FF0000"

            
            image = mean_lst_image
            band_name = "LST"
            scale = 30
            source = "Landsat 8/9 SC LST (temporal mean)"
            
        elif analysis_type.lower() == "aqi":
            import math

            
            try:
                era5 = (
                    ee.ImageCollection("ECMWF/ERA5/HOURLY")
                    .select(["boundary_layer_height"])
                    .filterBounds(polygon)
                    .filterDate(start_date, end_date)
                    .mean()
                )

                blh_result = era5.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=polygon,
                    scale=10000,
                    maxPixels=1e13
                ).getInfo()

                era5_land = (
                    ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
                    .select(["temperature_2m", "dewpoint_temperature_2m"])
                    .filterBounds(polygon)
                    .filterDate(start_date, end_date)
                    .mean()
                )

                temp_result = era5_land.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=polygon,
                    scale=10000,
                    maxPixels=1e13
                ).getInfo()

                blh = blh_result.get("boundary_layer_height") or 800
                temp = temp_result.get("temperature_2m")
                dew  = temp_result.get("dewpoint_temperature_2m")

            except Exception as e:
                blh = 800
                temp = None
                dew = None

         
            rh = 60
            if temp and dew:
                T  = temp - 273.15
                Td = dew  - 273.15
                rh = 100 * (
                    math.exp(17.625 * Td / (243.04 + Td)) /
                    math.exp(17.625 * T  / (243.04 + T))
                )
                rh = min(max(rh, 0), 100)

            
            
            pm25 = None
            pm10 = None
            
            
            
            
            MONTHLY_PM25_BASELINE = {
                1: 110,   
                2: 75,    
                3: 50,    
                4: 63,    
                5: 32,    
                6: 29,    
                7: 28,    
                8: 25,    
                9: 27,    
                10: 100,  
                11: 130, 
                12: 195   
            }
            
            from datetime import datetime, timedelta
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            date_range_days = (end_dt - start_dt).days + 1
            
            
            
            if date_range_days >= 300:  
                
                daily_aqi_values = []
                current_date = start_dt
                
                
                aod_annual_avg = None
                try:
                    modis_annual = (
                        ee.ImageCollection("MODIS/061/MCD19A2_GRANULES")
                        .select("Optical_Depth_047")
                        .filterBounds(polygon)
                        .filterDate(start_date, end_date)
                    )
                    if modis_annual.size().getInfo() > 0:
                        aod_val_annual = modis_annual.mean().reduceRegion(
                            reducer=ee.Reducer.mean(),
                            geometry=polygon,
                            scale=1000,
                            maxPixels=1e13
                        ).get("Optical_Depth_047").getInfo()
                        if aod_val_annual is not None:
                            aod_annual_avg = aod_val_annual * 0.001
                except:
                    pass
                
                
                while current_date <= end_dt:
                    month = current_date.month
                    day_baseline_pm25 = MONTHLY_PM25_BASELINE.get(month, 60)
                    
                    
                    import random
                    random.seed(hash(str(polygon.getInfo()) + str(current_date)))
                    daily_variation = random.uniform(0.95, 1.05)
                    
                    
                    aod_factor = 1.0
                    if aod_annual_avg is not None:
                        aod_clamped = max(0.1, min(aod_annual_avg, 1.5))
                        aod_reference = 0.5
                        aod_sensitivity = 0.6
                        aod_factor = 1.0 + aod_sensitivity * (aod_clamped - aod_reference)
                        aod_factor = max(0.7, min(aod_factor, 1.4))
                    
                    
                    daily_pm25 = day_baseline_pm25 * aod_factor * daily_variation
                    daily_pm25 = max(15, min(daily_pm25, 350))
                    
                    
                    daily_aqi = compute_aqi(daily_pm25, AQI_BREAKPOINTS["PM25"])
                    
                    if daily_aqi is not None:
                        daily_aqi_values.append(daily_aqi)
                    
                    current_date += timedelta(days=1)
                
                
                if daily_aqi_values:
                    annual_aqi = sum(daily_aqi_values) / len(daily_aqi_values)
                    
                    if annual_aqi <= 50:
                        pm25 = annual_aqi * 12 / 50
                    elif annual_aqi <= 100:
                        pm25 = 12 + (annual_aqi - 50) * 23.4 / 50
                    elif annual_aqi <= 150:
                        pm25 = 35.4 + (annual_aqi - 100) * 19.6 / 50
                    elif annual_aqi <= 200:
                        pm25 = 55 + (annual_aqi - 150) * 95 / 50
                    elif annual_aqi <= 300:
                        pm25 = 150 + (annual_aqi - 200) * 100 / 100
                    else:
                        pm25 = 250 + (annual_aqi - 300) * 100 / 100
                else:
                    
                    days_per_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
                    annual_sum = sum(
                        MONTHLY_PM25_BASELINE[month] * days 
                        for month, days in zip(range(1, 13), days_per_month)
                    )
                    pm25 = annual_sum / 365
                
                pm25 = max(15, min(pm25, 350))
                
            elif date_range_days > 45:  
                month_weights = {}
                current_date = start_dt
                
                while current_date <= end_dt:
                    month_key = current_date.month
                    if month_key not in month_weights:
                        month_weights[month_key] = 0
                    month_weights[month_key] += 1
                    current_date += timedelta(days=1)
                
                
                total_weight = sum(month_weights.values())
                baseline_pm25 = sum(
                    MONTHLY_PM25_BASELINE.get(month, 60) * weight 
                    for month, weight in month_weights.items()
                ) / total_weight
                aod_actual = None
                
                try:
                    modis = (
                        ee.ImageCollection("MODIS/061/MCD19A2_GRANULES")
                        .select("Optical_Depth_047")
                        .filterBounds(polygon)
                        .filterDate(start_date, end_date)
                    )
                    
                    if modis.size().getInfo() > 0:
                        aod_val = modis.mean().reduceRegion(
                            reducer=ee.Reducer.mean(),
                            geometry=polygon,
                            scale=1000,
                            maxPixels=1e13
                        ).get("Optical_Depth_047").getInfo()
                        
                        if aod_val is not None:
                            aod_actual = aod_val * 0.001
                except:
                    aod_actual = None
                
                aod_factor = 1.0
                
                if aod_actual is not None:
                    aod_actual = max(0.1, min(aod_actual, 1.5))
                    aod_reference = 0.5
                    aod_sensitivity = 0.6
                    aod_factor = 1.0 + aod_sensitivity * (aod_actual - aod_reference)
                    aod_factor = max(0.7, min(aod_factor, 1.4))
                
                met_factor = 1.0
                
                if blh:
                    if blh < 400:
                        met_factor *= 1.15
                    elif blh > 1800:
                        met_factor *= 0.85
                
                if rh:
                    if rh > 85:
                        met_factor *= 1.05
                    elif rh < 30:
                        met_factor *= 0.95
                
                if temp:
                    temp_c = temp - 273.15
                    if temp_c < 10:
                        met_factor *= 1.05
                    elif temp_c > 40:
                        met_factor *= 0.95
                
                
                pm25 = baseline_pm25 * aod_factor * met_factor
                pm25 = max(15, min(pm25, 350))
                
            else:
                
                
                month = start_dt.month
                baseline_pm25 = MONTHLY_PM25_BASELINE.get(month, 60)
                
                aod_actual = None
                
                try:
                    modis = (
                        ee.ImageCollection("MODIS/061/MCD19A2_GRANULES")
                        .select("Optical_Depth_047")
                        .filterBounds(polygon)
                        .filterDate(start_date, end_date)
                    )
                    
                    if modis.size().getInfo() > 0:
                        aod_val = modis.mean().reduceRegion(
                            reducer=ee.Reducer.mean(),
                            geometry=polygon,
                            scale=1000,
                            maxPixels=1e13
                        ).get("Optical_Depth_047").getInfo()
                        
                        if aod_val is not None:
                            aod_actual = aod_val * 0.001
                except:
                    aod_actual = None
                
                aod_factor = 1.0
                
                if aod_actual is not None:
                    aod_actual = max(0.1, min(aod_actual, 1.5))
                    aod_reference = 0.5
                    aod_sensitivity = 0.6
                    aod_factor = 1.0 + aod_sensitivity * (aod_actual - aod_reference)
                    aod_factor = max(0.7, min(aod_factor, 1.4))
                
                met_factor = 1.0
                
                if blh:
                    if blh < 400:
                        met_factor *= 1.15
                    elif blh > 1800:
                        met_factor *= 0.85
                
                if rh:
                    if rh > 85:
                        met_factor *= 1.05
                    elif rh < 30:
                        met_factor *= 0.95
                
                if temp:
                    temp_c = temp - 273.15
                    if temp_c < 10:
                        met_factor *= 1.05
                    elif temp_c > 40:
                        met_factor *= 0.95
                
                
                pm25 = baseline_pm25 * aod_factor * met_factor
                pm25 = max(15, min(pm25, 350))
            
            
            pm10 = pm25 * 1.67
            pm10 = max(20, min(pm10, 600))

            
            def fetch_gas_ppb_no2_so2(collection_id, band, molar_mass, scale_factor, max_cap):
                """Fetch NO2 and SO2 from Sentinel-5P"""
                try:
                    col = (
                        ee.ImageCollection(collection_id)
                        .select(band)
                        .filterBounds(polygon)
                        .filterDate(start_date, end_date)
                    )

                    if col.size().getInfo() == 0:
                        return None

                    val = col.mean().reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=polygon,
                        scale=7000,
                        maxPixels=1e13
                    ).get(band).getInfo()

                    if val and blh:
                        
                        ppb = (val * scale_factor / max(blh, 800)) * 1e9 * 24.45 / molar_mass
                        
                        from datetime import datetime
                        date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                        month = date_obj.month
                        
                        
                        if month in [6, 7, 8]: 
                            ppb *= 0.5
                        elif month in [9, 5]:  
                            ppb *= 0.65
                        elif month in [3, 4, 10]: 
                            ppb *= 0.75
                        elif month in [11, 2]:  
                            ppb *= 0.85
                        else:  
                            ppb *= 0.95
                        
                        return max(0, min(ppb, max_cap))
                except:
                    return None
                return None

            
            no2_ppb = fetch_gas_ppb_no2_so2(
                "COPERNICUS/S5P/NRTI/L3_NO2",
                "tropospheric_NO2_column_number_density",
                46.0,
                0.25,  
                2000
            )

            so2_ppb = fetch_gas_ppb_no2_so2(
                "COPERNICUS/S5P/NRTI/L3_SO2",
                "SO2_column_number_density",
                64.0,
                0.15,  
                1000
            )

        
            
            from datetime import datetime
            date_obj = datetime.strptime(start_date, '%Y-%m-%d')
            month = date_obj.month
            
            if pm25:
                
                if month in [12, 1, 2]:
                    o3_ppb = 15 + (pm25 * 0.08)  
                elif month in [3, 4]:
                    o3_ppb = 25 + (pm25 * 0.12)  
                elif month == 5:
                    o3_ppb = 35 + (pm25 * 0.15)  
                elif month in [6, 7, 8, 9]:
                    o3_ppb = 20 + (pm25 * 0.10)  
                elif month in [10, 11]:
                    o3_ppb = 30 + (pm25 * 0.10)  
                else:
                    o3_ppb = 25 + (pm25 * 0.10)
                
                
                if temp:
                    temp_c = temp - 273.15
                    if temp_c > 35:  
                        o3_ppb *= 1.15
                    elif temp_c < 15:  
                        o3_ppb *= 0.85
                
                
                o3_ppb = max(10, min(o3_ppb, 80))
            else:
                o3_ppb = None

            
            aqi_pm25 = compute_aqi(pm25, AQI_BREAKPOINTS["PM25"]) if pm25 else None
            aqi_pm10 = compute_aqi(pm10, AQI_BREAKPOINTS["PM10"]) if pm10 else None
            aqi_no2  = compute_aqi(no2_ppb, AQI_BREAKPOINTS["NO2"]) if no2_ppb else None
            aqi_so2  = compute_aqi(so2_ppb, AQI_BREAKPOINTS["SO2"]) if so2_ppb else None
            aqi_o3   = compute_aqi(o3_ppb, AQI_BREAKPOINTS["O3"]) if o3_ppb else None

            aqi_values = [aqi_pm25, aqi_pm10, aqi_no2, aqi_so2, aqi_o3]
            valid_aqis = [v for v in aqi_values if v is not None]

            if valid_aqis:
                mean_value = max(valid_aqis)
                status = "success"
            else:
                mean_value = None
                status = "no_data"
            pollutant_names = ["PM2.5", "PM10", "NO2", "SO2", "O3"]
            pollutant_aqis = [aqi_pm25, aqi_pm10, aqi_no2, aqi_so2, aqi_o3]

            dominant_pollutant = "N/A"
            category = "No Data"
            color = "#000000"

            if valid_aqis:
                overall_aqi = mean_value

                for i, aqi in enumerate(pollutant_aqis):
                    if aqi == overall_aqi:
                        dominant_pollutant = pollutant_names[i]
                        break

                
                if overall_aqi <= 50:
                    category = "Good"
                    color = "#00E400"
                elif overall_aqi <= 100:
                    category = "Moderate"
                    color = "#FFFF00"
                elif overall_aqi <= 150:
                    category = "Unhealthy for Sensitive Groups"
                    color = "#FF7E00"
                elif overall_aqi <= 200:
                    category = "Unhealthy"
                    color = "#FF0000"
                elif overall_aqi <= 300:
                    category = "Very Unhealthy"
                    color = "#8F3F97"
                else:
                    category = "Hazardous"
                    color = "#7E0023"
            source = "MODIS MAIAC + Sentinel-5P + ERA5 + EPA AQI"


        if analysis_type.lower() == "aqi":
            return {
                "stats": {
                    "mean": round(mean_value, 4) if mean_value is not None else None,
                    "PM2.5":aqi_pm25, 
                    "PM210":aqi_pm10, 
                    "NO2":aqi_no2, 
                    "SO2":aqi_so2, 
                    "O3":aqi_o3,
                    "color": color,
                    "status": status,
                    "category": category,
                    "dominant_pollutant": dominant_pollutant,
                    "source": source
                }
            }
        else:
            return {
                "stats": {
                    "mean": round(mean_value, 4) if mean_value is not None else None,
                    "color": color,
                    "status": "success",
                    "source": source
                }
            }


    except Exception as e:
        return {
            "stats": {
                "mean": None,
                "color": "#000000",
                "status": f"error: {str(e)}"
            }
        }
        
def compute_file_hash(file_path, length=12):
    
    h = hashlib.sha1()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()[:16]


@api_view(['POST']) 
@permission_classes([IsAuthenticated])
def pixelwise_analysis(request):
    init_ee()

    analysis_type = request.data.get("analysis_type")
    start_date = request.data.get("start_date")
    end_date = request.data.get("end_date")
    area_type = request.data.get("area_type")
    city_name = request.data.get("city_name")
    geometry_data = request.data.get("geometry")
    project_id = request.data.get("project_id")

    if not analysis_type or not start_date or not end_date or not area_type:
        return Response({"error": "Missing required parameters"}, status=400)

    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    results = []

    if project_id:
        project_cached = AreaAnalysis.objects.filter(
            project_id=project_id,
            analysis_type=analysis_type,
            start_date=start_date,
            end_date=end_date,
            area_type=area_type,
            is_pixelwise=True
        ).order_by('uc_name')

        if project_cached.exists():
            for cached in project_cached:
                results.append({
                    "uc_name": cached.uc_name,
                    "city_name": cached.city_name,
                    "tile_url_template": cached.tile_url_template,
                    "area_type": cached.area_type
                })
            return Response({
                "message": f"Cached {analysis_type.upper()} pixelwise analysis returned",
                "results": results
            })

    features = []
    kml_hash = None
    if area_type == "uc":
        if not project_id:
            return Response({"error": "project_id is required for UC analysis"}, status=400)
        project = Project.objects.filter(id=project_id).first()
        if not project:
            return Response({"error": "Project not found"}, status=404)
        city_name = project.location_name
        uc_data = load_ucs_for_uc(city_name)
        if not uc_data:
            db_ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)
            features = [{"geometry": json.loads(uc.geometry.geojson), "properties": {"uc_name": uc.uc_name, "city_name": uc.city_name}} for uc in db_ucs]
        else:
            features = uc_data.get("features", [])
    elif area_type == "kml":
        if not project_id:
            return Response({"error": "project_id is required for KML analysis"}, status=400)
        
        project = Project.objects.filter(id=project_id).first()
        if not project or not project.kml_file:
            return Response({"error": "KML file not found for this project"}, status=404)

        kml_path = project.kml_file.path

        
        with open(kml_path, "rb") as f:
            kml_bytes = f.read()

        
        kml_content = kml_bytes.decode("utf-8-sig")

        
        kml_hash = hashlib.md5(kml_bytes).hexdigest()

    
        content_cache_path = os.path.join(DATA_DIR, f"{kml_hash}_kml_ucs.json")

        
        if os.path.exists(content_cache_path):
            kml_data = json.load(open(content_cache_path))
        else:
            polygon = kml_to_geosgeometry(kml_content)
            ucs = UnionCouncil.objects.filter(geometry__intersects=polygon)
            if not ucs.exists():
                return Response({"error": "No UCs found in this area"}, status=404)

            geojson = serialize(
                "geojson", ucs,
                geometry_field="geometry",
                fields=("uc_name", "city_name")
            )
            kml_data = json.loads(geojson)
            with open(content_cache_path, "w") as f:
                json.dump(kml_data, f)

        
        features = kml_data.get("features", [])
    
    elif area_type == "custom":
        if not geometry_data:
            return Response({"error": "geometry data is required for custom analysis"}, status=400)
        geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
        features = [{"geometry": geom_json, "properties": {"uc_name": None, "city_name": None}}]

    
    def process_feature(feature):
        uc_name = feature["properties"].get("uc_name", "unknown_uc")
        city_name_local = feature["properties"].get("city_name", city_name)
        uc_safe = re.sub(r"[^\w\-]", "_", uc_name).lower()
        city_name_safe = re.sub(r"[^\w\-]", "_", city_name_local)
        
        shared_filter = {
            "project_id__isnull": True,
            "analysis_type": analysis_type,
            "start_date": start_date,
            "end_date": end_date,
            "area_type": area_type
        }

        if area_type == "uc":
            shared_filter["uc_name"] = uc_safe
            shared_filter["city_name__iexact"] = city_name_safe

        
        elif area_type == "kml":
            if kml_hash:
                
                shared_filter.update({
                    "kml_hash": kml_hash,
                    "start_date": start_date,
                    "end_date": end_date,
                    "uc_name": uc_safe,          
                    "city_name": city_name_safe
                })
            else:
                return {
                    "uc_name": uc_name,
                    "city_name": city_name,
                    "error": "1",
                    "error_msg": "KML hash missing for caching.",
                    "tile_url_before": None,
                    "tile_url_after": None
                }
                    



        shared_cache = AreaAnalysis.objects.filter(**shared_filter).first()
        if shared_cache:
            
            if project_id:
                
                AreaAnalysis.objects.update_or_create(
                    project_id=project_id,
                    analysis_type=analysis_type,
                    start_date=start_date,
                    end_date=end_date,
                    area_type=area_type,
                    uc_name=uc_safe,
                    defaults={
                        "city_name": city_name_local,
                        "kml_hash": kml_hash,
                        "is_pixelwise": True,
                        "tile_url_template": shared_cache.tile_url_template
                    }
                )
            return {
                "uc_name": uc_name,
                "city_name": city_name_local,
                "tile_url_template": shared_cache.tile_url_template,
                "cached": True
            }

        
        local_dir = os.path.join(
                settings.MEDIA_ROOT, "temp_exports", "pixelwise",
                "kml" if kml_hash else "uc",
                kml_hash if kml_hash else str(project_id),
                uc_safe
            )
        os.makedirs(local_dir, exist_ok=True)

        local_tif = os.path.join(local_dir, f"{analysis_type}{start_date}{end_date}.tif")
        tiles_dir = os.path.join(local_dir, "tiles")

        try:
            
            geojson_dict = feature.get("geometry")
            if not geojson_dict:
                raise ValueError("Missing geometry")
            polygon = ee.Geometry(geojson_dict)
            if not polygon:
                return {
                    "uc_name": uc_name,
                    "city_name": city_name,
                    "error": "1",
                    "error_msg": "Invalid or empty polygon",
                    "tile_url_template": None
                }
            if analysis_type.lower() == "aqi":
                polygon = polygon.buffer(10)
            if analysis_type.lower()!= "aqi":
                
                area_sq_m = polygon.area().getInfo()
                default_scales = {"ndvi": 10, "thermal": 100}
                scale = default_scales.get(analysis_type.lower(), 10)
                if area_sq_m is None:
                    return {
                        "uc_name": uc_name,
                        "city_name": city_name,
                        "error": "1",
                        "error_msg": "Polygon area could not be computed",
                        "tile_url_template": None
                    }
                
                if area_sq_m > 1e9:          
                    scale = max(scale, 60)
                elif area_sq_m > 5e8:        
                    scale = max(scale, 40)
                elif area_sq_m > 1e8:        
                    scale = max(scale, 20)
                    
                if area_sq_m < (scale**2):
                    scale = max(int(area_sq_m**0.5), 1)
                if analysis_type.lower() == "ndvi" and area_sq_m < 1e4:
                    scale = max(scale, 20)
                if area_sq_m < 100:
                    print(f" Skipped {uc_name} — area too small for export ({area_sq_m:.2f} m²)")
                    return {"uc_name": uc_name, "city_name": city_name, "error": "1",
                            "error_msg": "Polygon too small for analysis", "tile_url_template": None}
                

            if analysis_type.lower() == "aqi":
                image, vis_params, scale = run_pixelwise_analysis(analysis_type, polygon, start_date, end_date)
                if scale is None:
                    scale = 10
            else:
                image, vis_params, _ = run_pixelwise_analysis(analysis_type, polygon, start_date, end_date)
            
            if not image:
                return {"uc_name": uc_name, "city_name": city_name, "error": "1",
                        "error_msg": "No image generated", "tile_url_template": None}

            if image is None:
                print(f"[DEBUG] No image for {uc_name}")
                return {"uc_name": uc_name, "city_name": city_name, "error": "1",
                        "error_msg": "No image generated", "tile_url_template": None}

            
            polygon_3857 = polygon.transform("EPSG:3857", maxError=1)

            
            image = image.clip(polygon_3857)
            
            
            
            vis_image = image.visualize(
                min=vis_params["min"],
                max=vis_params["max"],
                palette=vis_params.get("palette")
            )

            
            data_type = "uint8"  
            vis_image = vis_image.reproject(crs="EPSG:3857", scale=scale)

            
            
            pixel_count = image.reduceRegion(
            reducer=ee.Reducer.count(),
            geometry=polygon,
            scale=scale,
            maxPixels=1e13
            ).getInfo()
            if not pixel_count or all(v == 0 for v in pixel_count.values()):
                
            
                print(f"Empty pixels for {uc_name}, trying larger buffer")
                polygon = polygon.buffer(50)  
                scale = 5  

            export_success = False
            attempt = 0
            max_attempts = 4

            while not export_success and attempt < max_attempts:
                try:
                    attempt += 1
                    print(f"Export attempt {attempt} at scale={scale} meters/pixel")
                    
                    geemap.ee_export_image(
                        vis_image,
                        filename=local_tif,
                        scale=scale,
                        file_per_band=False,
                        crs="EPSG:3857"
                    )

                    if os.path.exists(local_tif) and os.path.getsize(local_tif) > 0:
                        export_success = True
                    else:
                        raise Exception("Export produced empty or missing file")

                except Exception as e:
                    error_msg = str(e)
                    
                    scale = min(int(scale * 2), 200)
                    print(f"[EXPORT ERROR] {error_msg} → Retrying with scale={scale}")

                    time.sleep(2)
                    continue
                            
                            


            if not export_success:
                return {
                    "uc_name": uc_name,
                    "city_name": city_name,
                    "error": "1",
                    "error_msg": f"Export failed after {attempt} attempts (last scale={scale})",
                    "tile_url_template": None
            }
            
            
            with rasterio.open(local_tif, "r+") as src:
                width, height = src.width, src.height
                factors = [2, 4, 8, 16]
                valid_factors = [f for f in factors if f < min(width, height)]
                if valid_factors:
                    src.build_overviews(valid_factors, Resampling.nearest)
                    src.update_tags(ns="rio_overview", resampling="nearest")

            
            if os.path.exists(tiles_dir):
                shutil.rmtree(tiles_dir)
            os.makedirs(tiles_dir, exist_ok=True)

            with COGReader(local_tif) as cog:
                
                def scale_to_zoom(scale_m_per_pixel):
                    z = math.log2(156543.03392804097 / float(scale_m_per_pixel))
                    return int(round(z))

                target_zoom = max(0, min(18, scale_to_zoom(scale)))
                min_zoom = max(0, target_zoom - 4)
                max_zoom = min(18, target_zoom + 2)
                
                
                left, bottom, right, top = cog.bounds
                transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
                lon_left, lat_bottom = transformer.transform(left, bottom)
                lon_right, lat_top = transformer.transform(right, top)
                
                
                for z in range(min_zoom, max_zoom + 1):
                    n = 2 ** z
                    try:
                        
                        tile_list = list(mercantile.tiles(lon_left, lat_bottom, lon_right, lat_top, [z]))
                    except Exception as e:
                        print(f"Zoom {z} skipped: {e}")
                        continue

                    
                    tile_list = [t for t in tile_list if 0 <= t.x < n and 0 <= t.y < n]

                    for t in tile_list:
                        try:
                            
                            data, mask = cog.tile(t.x, t.y, t.z)
                            if data is None:
                                continue
                            img = np.moveaxis(data, 0, 2)
                            img = (img * 255).astype(np.uint8) if img.max() <= 1 else img

                            if img.shape[2] == 3:
                                alpha = np.any(img > 0, axis=2).astype(np.uint8) * 255
                                img = np.dstack((img, alpha))

                            pil_img = Image.fromarray(img, mode="RGBA")


                            tile_path = os.path.join(tiles_dir, str(z), str(t.x))
                            os.makedirs(tile_path, exist_ok=True)
                            pil_img.save(os.path.join(tile_path, f"{t.y}.png"))
                        except Exception as e:
                            print(f"Tile x={t.x}, y={t.y}, z={t.z} skipped: {e}")

           
            if area_type == "kml":
                s3_tile_prefix = f"tiles/pixelwise/shared/kml/{kml_hash}/{analysis_type}/{start_date}_{end_date}/{uc_safe}"
            else:
                s3_tile_prefix = f"tiles/pixelwise/shared/uc/{analysis_type}/{start_date}_{end_date}/{city_name_safe}/{uc_safe}"

            for root, dirs, files in os.walk(tiles_dir):
                for fname in files:
                    if fname.lower().endswith(".png"):
                        full_path = os.path.join(root, fname)
                        rel_path = os.path.relpath(full_path, tiles_dir).replace(os.sep, "/")
                        s3_key = f"{s3_tile_prefix}/{rel_path}"
                        s3_client.upload_file(full_path, bucket_name, s3_key)

            
            tile_url_template = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{s3_tile_prefix}/{{z}}/{{x}}/{{y}}.png"

            
            if os.path.exists(local_dir):
                shutil.rmtree(local_dir)


            AreaAnalysis.objects.update_or_create(
                project_id=None,
                analysis_type=analysis_type,
                start_date=start_date,
                end_date=end_date,
                area_type=area_type,
                uc_name=uc_safe,
                defaults={
                    "city_name": city_name_safe,
                    "kml_hash": kml_hash,
                    "is_pixelwise": True,
                    "tile_url_template": tile_url_template
                }
            )
            if project_id:
                AreaAnalysis.objects.update_or_create(
                    project_id=project_id,
                    analysis_type=analysis_type,
                    start_date=start_date,
                    end_date=end_date,
                    area_type=area_type,
                    uc_name=uc_safe,
                    defaults={
                        "city_name": city_name_safe,
                        "kml_hash": kml_hash,
                        "is_pixelwise": True,
                        "tile_url_template": tile_url_template
                    }
                )
            return {"uc_name": uc_name, "city_name": city_name_local, "tile_url_template": tile_url_template, "cached": False}
        
        except Exception as e:
                if os.path.exists(local_dir):
                    shutil.rmtree(local_dir)
                return {
                    "uc_name": uc_name,
                    "city_name": city_name,
                    "error": "1",
                    "error_msg": str(e),
                    "tile_url_template": None
                }
                

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(process_feature, features))

    return Response({
        "message": f"{analysis_type.upper()} pixelwise analysis performed",
        "results": results
    }, status=200)


def run_pixelwise_analysis(analysis_type, polygon, start_date, end_date):
    init_ee()

    def print_debug_info(image, analysis_type, polygon, scale):
        try:
            count = ee.Number(image.reduceRegion(
                reducer=ee.Reducer.count(),
                geometry=polygon,
                scale=scale,
                bestEffort=True
            ).values().reduce(ee.Reducer.sum())).getInfo()
            print(f"[DEBUG] {analysis_type} pixel count in polygon:", count)
        except Exception as e:
            print(f"[DEBUG] {analysis_type} pixel count failed:", str(e))
            
    fallback_palette = ["#FFFFFF", "#0000FF", "#00FF00", "#FF0000"]


    if analysis_type.lower() == "ndvi":
        
        def mask_s2_sr(image):
            qa = image.select('QA60')
            cloud = qa.bitwiseAnd(1 << 10).Or(qa.bitwiseAnd(1 << 11))
            return image.updateMask(cloud.Not())

        
        s2 = (
            ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(polygon)
            .filterDate(start_date, end_date)
            .map(mask_s2_sr)
            .select(['B8', 'B4'])
        )

        s2_size = s2.size().getInfo()
        print(f"[DEBUG] Sentinel-2 images found: {s2_size}")

        if s2_size > 0:

            
            def per_image_ndvi(img):
                ndvi = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
                return ndvi.unmask(0).copyProperties(img, ['system:time_start'])

            ndvi_images = s2.map(per_image_ndvi)

            
            image = ndvi_images.median().rename('NDVI').clip(polygon)
            scale = 10

        
        else:
            print("[DEBUG] No S2 images → Falling back to Landsat-8")

            l8 = (
                ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
                .filterBounds(polygon)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt('CLOUD_COVER', 60))
            )

            l8_size = l8.size().getInfo()
            print(f"[DEBUG] Landsat-8 images found: {l8_size}")

            if l8_size == 0:
                print("[DEBUG] No Landsat-8 images → Using constant NDVI image")
                image = ee.Image.constant(0.01).rename("NDVI").clip(polygon)
                scale = 30

            else:
                
                def per_image_ndvi_l8(img):
                    nir = img.select('SR_B5').multiply(0.0000275).add(-0.2).unmask(0)
                    red = img.select('SR_B4').multiply(0.0000275).add(-0.2).unmask(0)
                    ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
                    return ndvi.copyProperties(img, ['system:time_start'])

                ndvi_images = l8.map(per_image_ndvi_l8)

                image = ndvi_images.median().rename('NDVI').clip(polygon)
                scale = 30

        
        vis_params = {
            'min': 0,
            'max': 1,
            'palette': [
                "#ffffcc", 
                "#c2e699",  
                "#78c679",  
                "#31a354",  
                "#006837"   
            ]
        }

        print_debug_info(image, analysis_type, polygon, scale)

     
    elif analysis_type.lower() == "thermal":

        
        collection = (
            ee.ImageCollection('LANDSAT/LC09/C02/T1_L2')
            .filterBounds(polygon)
            .filterDate(start_date, end_date)
            .filter(ee.Filter.lt('CLOUD_COVER', 60))
        )

        
        if collection.size().getInfo() == 0:
            print("[THERMAL] No Landsat 9 images found. Using Landsat 8.")
            collection = (
                ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
                .filterBounds(polygon)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt('CLOUD_COVER', 60))
            )

        
        if collection.size().getInfo() == 0:
            print("[THERMAL] No Landsat images found for this date range.")
            image = ee.Image.constant(0).rename("LST").clip(polygon)
            vis_params = {
                'min': 288, 'max': 313,
                'palette': ["#00008B","#00FFFF","#00FF00","#FFFF00","#FFA500","#FF4500"]
            }
            scale = 30
            return image, vis_params, scale

        
        def per_image_lst(img):
            return img.select('ST_B10') \
                    .multiply(0.00341802).add(149.0) \
                    .rename('LST') \
                    .copyProperties(img, ['system:time_start'])

        lst_images = collection.map(per_image_lst)

        
        image = lst_images.median().rename("LST").clip(polygon)

        
        vis_params = {
            'min': 288,
            'max': 313,
            'palette': ["#00008B","#00FFFF","#00FF00","#FFFF00","#FFA500","#FF4500"]
        }

        scale = 30
        print_debug_info(image, analysis_type, polygon, scale)

    
        
    
    elif analysis_type.lower() == "aqi":
        
        
        from datetime import datetime, timedelta
        
        
        def compute_aqi_pixel(img, breakpoints):
            """Compute AQI pixelwise using breakpoints"""
            expr = ""
            for Cl, Ch, Il, Ih in breakpoints:
                expr += f"({Cl} <= b(0) && b(0) <= {Ch}) ? (({Ih}-{Il})/({Ch}-{Cl}))*(b(0)-{Cl})+{Il} : "
            expr += "0"
            return img.expression(expr)
        
       
        MONTHLY_PM25_BASELINE = {
            1: 110, 2: 75, 3: 50, 4: 63, 5: 32, 6: 29,
            7: 28, 8: 25, 9: 27, 10: 100, 11: 130, 12: 195
        }
        
        
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        date_range_days = (end_dt - start_dt).days + 1
        
        
        modis = (
            ee.ImageCollection("MODIS/061/MCD19A2_GRANULES")
            .select("Optical_Depth_047")
            .filterBounds(polygon)
            .filterDate(start_date, end_date)
        )
        aod_img = modis.median().multiply(0.001).clamp(0.1, 1.5)
        aod_factor_img = aod_img.expression("1.0 + 0.6*(b(0)-0.5)").clamp(0.7, 1.4)
        
        
        if date_range_days >= 300:
            print(f"[PIXELWISE AQI] Yearly analysis: {date_range_days} days - Using EPA daily AQI averaging")
            
            
            daily_aqi_images = []
            current_date = start_dt
            
            while current_date <= end_dt:
                month = current_date.month
                day_baseline_pm25 = MONTHLY_PM25_BASELINE.get(month, 60)
                
                
                day_of_year = current_date.timetuple().tm_yday
                variation_factor = 0.95 + (day_of_year % 21) * 0.005
                
               
                baseline_daily_img = ee.Image.constant(day_baseline_pm25 * variation_factor)
                pm25_daily = baseline_daily_img.multiply(aod_factor_img).clamp(15, 350)
                
                
                daily_aqi = compute_aqi_pixel(pm25_daily, AQI_BREAKPOINTS["PM25"])
                daily_aqi_images.append(daily_aqi)
                
                current_date += timedelta(days=1)
            
            
            aqi_collection = ee.ImageCollection(daily_aqi_images)
            overall_aqi = aqi_collection.mean().rename("AQI").clip(polygon)
            
            print(f"[PIXELWISE AQI] Computed {len(daily_aqi_images)} daily AQI images, averaged to annual AQI")
            print(f"[PIXELWISE AQI] Formula: baseline × AOD_factor × daily_variation → AQI → mean (PM2.5 only)")
            
            vis_params = {
                "min": 0,
                "max": 500,
                "palette": ["#00E400","#FFFF00","#FF7E00","#FF0000","#8F3F97","#7E0023"]
            }
            scale = 1000
            print_debug_info(overall_aqi, "AQI", polygon, scale)
            return overall_aqi, vis_params, scale
        
       
        else:
            print(f"[PIXELWISE AQI] Monthly analysis: {date_range_days} days - Using all pollutants")
            
            
            era5 = (
                ee.ImageCollection("ECMWF/ERA5/HOURLY")
                .select(["boundary_layer_height"])
                .filterBounds(polygon)
                .filterDate(start_date, end_date)
                .median()
            )
            blh_img = era5.rename("BLH").unmask(800)
            
            era5_land = (
                ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
                .select(["temperature_2m", "dewpoint_temperature_2m"])
                .filterBounds(polygon)
                .filterDate(start_date, end_date)
                .median()
            )
            temp_img = era5_land.select("temperature_2m")
            dew_img = era5_land.select("dewpoint_temperature_2m")
            
            temp_c = temp_img.subtract(273.15)
            dew_c = dew_img.subtract(273.15)
            
            rh_img = ee.Image(100).multiply(
                dew_c.multiply(17.625).divide(dew_c.add(243.04)).exp()
            ).divide(
                temp_c.multiply(17.625).divide(temp_c.add(243.04)).exp()
            ).clamp(0, 100).unmask(60).rename("RH")
            
            
            met_factor = ee.Image(1.0)
            met_factor = met_factor.where(blh_img.lt(400), met_factor.multiply(1.15))
            met_factor = met_factor.where(blh_img.gt(1800), met_factor.multiply(0.85))
            met_factor = met_factor.where(rh_img.gt(85), met_factor.multiply(1.05))
            met_factor = met_factor.where(rh_img.lt(30), met_factor.multiply(0.95))
            met_factor = met_factor.where(temp_img.subtract(273.15).lt(10), met_factor.multiply(1.05))
            met_factor = met_factor.where(temp_img.subtract(273.15).gt(40), met_factor.multiply(0.95))
            
           
            month = start_dt.month
            baseline_pm25 = MONTHLY_PM25_BASELINE.get(month, 60)
            baseline_img = ee.Image.constant(baseline_pm25)
            
            
            pm25_img = baseline_img.multiply(aod_factor_img).multiply(met_factor).clamp(15, 350)
            pm10_img = pm25_img.multiply(1.67).clamp(20, 600)
            
            
            def s5p_gas(collection_id, band, molar, scale_factor, max_cap):
                col = ee.ImageCollection(collection_id).select(band).filterBounds(polygon).filterDate(start_date, end_date)
                img = col.mean()
                ppb = img.divide(blh_img.add(1e-10)).multiply(scale_factor * 1e9 * 24.45 / molar)
                
                
                month_ee = ee.Number(ee.Date(start_date).get('month'))
                ppb = ppb.where(month_ee.gte(6).And(month_ee.lte(8)), ppb.multiply(0.5))
                ppb = ppb.where(month_ee.eq(9).Or(month_ee.eq(5)), ppb.multiply(0.65))
                ppb = ppb.where(month_ee.eq(3).Or(month_ee.eq(4)).Or(month_ee.eq(10)), ppb.multiply(0.75))
                ppb = ppb.where(month_ee.eq(11).Or(month_ee.eq(2)), ppb.multiply(0.85))
                ppb = ppb.where(month_ee.eq(12).Or(month_ee.eq(1)), ppb.multiply(0.95))
                
                return ppb.clamp(0, max_cap)
            
            no2_img = s5p_gas("COPERNICUS/S5P/NRTI/L3_NO2", "tropospheric_NO2_column_number_density", 46.0, 0.25, 2000)
            so2_img = s5p_gas("COPERNICUS/S5P/NRTI/L3_SO2", "SO2_column_number_density", 64.0, 0.15, 1000)
            
            
            month_num = ee.Number(month)
            o3_img = pm25_img.expression(
                """
                (month <= 2 || month == 12) ? 15 + b(0)*0.08 :
                (month >= 3 && month <= 4) ? 25 + b(0)*0.12 :
                (month == 5) ? 35 + b(0)*0.15 :
                (month >= 6 && month <= 9) ? 20 + b(0)*0.10 :
                (month >= 10 && month <= 11) ? 30 + b(0)*0.10 : 25 + b(0)*0.10
                """,
                {"month": month_num}
            )
            temp_c = temp_img.subtract(273.15)
            o3_img = o3_img.where(temp_c.gt(35), o3_img.multiply(1.15))
            o3_img = o3_img.where(temp_c.lt(15), o3_img.multiply(0.85))
            o3_img = o3_img.clamp(10, 80)
            
            
            pm25_img = pm25_img.rename("PM25")
            pm10_img = pm10_img.rename("PM10")
            
            
            aqi_pm25 = compute_aqi_pixel(pm25_img, AQI_BREAKPOINTS["PM25"])
            aqi_pm10 = compute_aqi_pixel(pm10_img, AQI_BREAKPOINTS["PM10"])
            aqi_no2 = compute_aqi_pixel(no2_img, AQI_BREAKPOINTS["NO2"])
            aqi_so2 = compute_aqi_pixel(so2_img, AQI_BREAKPOINTS["SO2"])
            aqi_o3 = compute_aqi_pixel(o3_img, AQI_BREAKPOINTS["O3"])
            
            # Get maximum AQI across all pollutants using pixel-wise max
            overall_aqi = (aqi_pm25.max(aqi_pm10)
                          .max(aqi_no2)
                          .max(aqi_so2)
                          .max(aqi_o3)
                          .rename("AQI")
                          .clip(polygon))
            
            vis_params = {
                "min": 0,
                "max": 500,
                "palette": ["#00E400","#FFFF00","#FF7E00","#FF0000","#8F3F97","#7E0023"]
            }
            scale = 1000
            print_debug_info(overall_aqi, "AQI", polygon, scale)
            return overall_aqi, vis_params, scale


    else:
        raise ValueError("Invalid analysis type")
    
    if "palette" not in vis_params or len(vis_params["palette"]) < 2:
        vis_params["palette"] = fallback_palette

    return image, vis_params, scale


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_pixel_value(request):
    init_ee()

    analysis_type = request.data.get("analysis_type")
    start_date = request.data.get("start_date")
    end_date = request.data.get("end_date")
    lat = request.data.get("lat")
    lng = request.data.get("lng")

    if not analysis_type or not start_date or not end_date or not lat or not lng:
        return Response({"error": "Missing required parameters"}, status=400)

    try:
        point = ee.Geometry.Point([float(lng), float(lat)])

        
        image, vis_params, scale = run_pixelwise_analysis(analysis_type, point.buffer(30), start_date, end_date)

        
        value = image.sample(region=point, scale=scale).first().toDictionary().getInfo()

        return Response({
            "lat": lat,
            "lng": lng,
            "analysis_type": analysis_type,
            "pixel_value": value
        })
    except Exception as e:
        return Response({"error": str(e)}, status=500)

from datetime import datetime

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def per_year_analysis(request):
    init_ee()
    analysis_type = request.data.get("analysis_type")
    year = request.data.get("year")
    area_type = request.data.get("area_type")
    project_id = request.data.get("project_id")
    city_name = request.data.get("city_name")
    mode = request.data.get("mode", "pixelwise") 
    if not all([analysis_type, year, area_type]):
        return Response({"error": "Missing required parameters"}, status=400)
    

    try:
        current_year = datetime.now().year
        current_month = datetime.now().strftime("%B %Y")
        selected_year = int(year)
        note = None

        
        if selected_year > current_year:
            return Response({
                "error": f"Future year {selected_year} cannot be analyzed yet.",
                "message": f"Data for {selected_year} will be available once the year begins."
            }, status=400)

        
        elif selected_year == current_year:
            note = f" Data for {selected_year} includes satellite observations available up to {current_month} only."

        project = Project.objects.get(id=project_id) if project_id else None
        results = []
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME

        
        features = []
        kml_hash = None
        if area_type == "uc" and project and project.location_name:
            uc_data = load_ucs_for_uc(project.location_name)
            if uc_data:
                features = uc_data.get("features", [])
            else:
                ucs = UnionCouncil.objects.filter(city_name__iexact=project.location_name)
                features = [
                    {"geometry": json.loads(uc.geometry.geojson),
                     "properties": {"uc_name": uc.uc_name, "city_name": uc.city_name}}
                    for uc in ucs
                ]

        elif area_type == "kml" and project and project.kml_file:
             
            if not project_id:
                return Response({"error": "project_id is required for KML analysis"}, status=400)
            
            project = Project.objects.filter(id=project_id).first()
            if not project or not project.kml_file:
                return Response({"error": "KML file not found for this project"}, status=404)

            kml_path = project.kml_file.path

            
            with open(kml_path, "rb") as f:
                kml_bytes = f.read()

            
            kml_content = kml_bytes.decode("utf-8-sig")

            
            kml_hash = hashlib.md5(kml_bytes).hexdigest()

        
            content_cache_path = os.path.join(DATA_DIR, f"{kml_hash}_kml_ucs.json")

            
            if os.path.exists(content_cache_path):
                kml_data = json.load(open(content_cache_path))
            else:
                polygon = kml_to_geosgeometry(kml_content)
                ucs = UnionCouncil.objects.filter(geometry__intersects=polygon)
                if not ucs.exists():
                    return Response({"error": "No UCs found in this area"}, status=404)

                geojson = serialize(
                    "geojson", ucs,
                    geometry_field="geometry",
                    fields=("uc_name", "city_name")
                )
                kml_data = json.loads(geojson)
                with open(content_cache_path, "w") as f:
                    json.dump(kml_data, f)

            
            features = kml_data.get("features", [])

        if not features and area_type != "custom":
            return Response({"error": "No features found for analysis"}, status=404)

        
        cached_results = YearlyAnalysis.objects.filter(
            project_id=project_id,
            analysis_type=analysis_type,
            year=selected_year,
            area_type=area_type,
            is_pixelwise=(mode == "pixelwise")
        ).order_by('uc_name')

        if cached_results.exists():
            for cached in cached_results:
                if mode == "annual_stats":
                    mean_value = cached.stats.get("mean") if cached.stats else None
                    results.append({
                        "uc_name": cached.uc_name,
                        "city_name": cached.city_name,
                        "mean_value": round(mean_value, 4) if mean_value is not None else None,
                        "color": cached.stats.get("color") if cached.stats else "#000000",
                        "area_type": area_type
                    })
                else:  
                    results.append({
                        "uc_name": cached.uc_name,
                        "city_name": cached.city_name,
                        "tile_url_template": cached.tile_url_template,
                        "error": "0"
                    })
            return Response({
                "message": f"Cached {analysis_type.upper()} {mode} analysis returned",
                "year": selected_year,
                "note": note,
                "results": results
            })

        
        if mode == "annual_stats":
            def analyze_feature_stats(feature):
                uc_name = feature["properties"].get("uc_name", "unknown_uc")
                city_name = feature["properties"].get("city_name", project.location_name if project else "unknown")

                try:
                    polygon = ee.Geometry(feature["geometry"])
                    result = perform_analysis_for_polygon(
                        analysis_type, polygon, f"{year}-01-01", f"{year}-12-31"
                    )
                    if not result or "stats" not in result:
                        raise ValueError("No stats found for this polygon")

                    mean_value = result["stats"].get("mean", 0)
                    if mean_value is None or (isinstance(mean_value, float) and math.isnan(mean_value)):
                        mean_value = 0

                    mean_value = round(mean_value, 4)
                    color = result["stats"].get("color", "#000000")

                    YearlyAnalysis.objects.update_or_create(
                        project_id=project_id,
                        analysis_type=analysis_type,
                        year=selected_year,
                        area_type=area_type,
                        uc_name=uc_name,
                        defaults={
                            "city_name": city_name,
                            "stats": {"mean": mean_value, "color": color},
                            "is_pixelwise": False,
                            "tile_url_template": None
                        }
                    )

                    return {
                        "uc_name": uc_name,
                        "city_name": city_name,
                        "mean_value": mean_value,
                        "color": color,
                        "area_type": area_type
                    }

                except Exception as e:
                    return {"uc_name": uc_name, "city_name": city_name, "error": "1", "error_msg": str(e)}

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(analyze_feature_stats, f) for f in features]
                for future in as_completed(futures):
                    results.append(future.result())

            return Response({
                "message": f"{analysis_type.upper()} annual stats analysis for {selected_year} completed",
                "year": selected_year,
                "note": note,
                "results": results
            })

        
        elif mode == "pixelwise":
            def process_feature(feature):
                uc_name = feature["properties"].get("uc_name", "custom_uc")
                city_name = feature["properties"].get("city_name", project.location_name if project else "unknown")
                def normalize_name(name):
                    return re.sub(r"[^\w\-]", "_", name.strip().lower())

                

                uc_safe = normalize_name(uc_name)
                city_safe = normalize_name(city_name)

                shared_filter = {
                    "project_id__isnull": True,
                    "analysis_type": analysis_type,
                    "year": selected_year,
                    "area_type": area_type,
                    
                }
                if area_type == "uc":
                    shared_filter["city_name"] = city_safe
                    shared_filter["uc_name"] = uc_safe

                
                elif area_type == "kml":
                    if kml_hash:
                        
                        shared_filter.update({
                            "kml_hash": kml_hash,
                            "year": int(selected_year),
                            "uc_name": uc_safe,          
                            "city_name": city_safe 
                        })
                    else:
                        return {
                            "uc_name": uc_name,
                            "city_name": city_name,
                            "error": "1",
                            "error_msg": "KML hash missing for caching.",
                            "tile_url_before": None,
                            "tile_url_after": None
                        }
                        


                shared_cache = YearlyAnalysis.objects.filter(**shared_filter).first()
                if shared_cache and shared_cache.tile_url_template:
                    
                    if project_id:
                        YearlyAnalysis.objects.update_or_create(
                            project_id=project_id,
                            analysis_type=analysis_type,
                            year=selected_year,
                            area_type=area_type,
                            uc_name=uc_safe,
                            defaults={
                                "city_name": city_name,
                                "kml_hash": kml_hash,
                                "is_pixelwise": True,
                                "tile_url_template": shared_cache.tile_url_template
                            }
                        )
                    return {
                        "uc_name": uc_name,
                        "city_name": city_name,
                        "tile_url_template": shared_cache.tile_url_template,
                        "cached": True
                    }
                local_dir = os.path.join(settings.MEDIA_ROOT, "temp_exports", "yearly_pixelwise", str(project_id), uc_safe)
                os.makedirs(local_dir, exist_ok=True)
                local_tif = os.path.join(local_dir, f"{analysis_type}_{selected_year}.tif")
                tiles_dir = os.path.join(local_dir, "tiles")

                try:
                    
                    polygon = ee.Geometry(feature["geometry"])
                    polygon = polygon.simplify(30)
                    area_sq_m = polygon.area().getInfo()
                    if area_sq_m > 2e8:
                        polygon = polygon.simplify(100)  
                    elif area_sq_m > 5e7:
                        polygon = polygon.simplify(50)
                    else:
                        polygon = polygon.simplify(30)
                        
                    if area_sq_m > 2e8:
                        base_scale = 50
                    elif area_sq_m > 5e7:
                        base_scale = 30
                    else:
                        base_scale = 10


                    
                

                    if analysis_type.lower() == "aqi":
                        image, vis_params, scale = run_pixelwise_analysis(
                        analysis_type, polygon, f"{selected_year}-01-01", f"{selected_year}-12-31"
                        )
                        

                    else:
                        image, vis_params,scale = run_pixelwise_analysis(
                        analysis_type, polygon, f"{selected_year}-01-01", f"{selected_year}-12-31"
                        )


                    
                    pixel_count = image.reduceRegion(
                        reducer=ee.Reducer.count(),
                        geometry=polygon,
                        scale=scale,
                        maxPixels=1e13
                    ).getInfo()
                    
                    if not pixel_count or all(v == 0 for v in pixel_count.values()):
                        print(f"Empty pixels for {uc_name}, trying larger buffer")
                        polygon = polygon.buffer(50)  
                        scale = 5  

                    if not pixel_count or all(v == 0 for v in pixel_count.values()):
                        return {
                            "uc_name": uc_name,
                            "city_name": city_name,
                            "error": "1",
                            "error_msg": "Export failed: No valid pixels found.",
                            "tile_url_template": None
                        }

                    vis_image = image.visualize(
                        min=vis_params.get("min"),
                        max=vis_params.get("max"),
                        palette=vis_params.get("palette")
                    )

                    
                    export_success = False
                    attempt = 0
                    max_attempts = 4
                    while not export_success and attempt < max_attempts:
                        try:
                            attempt += 1
                            print(f"Export attempt {attempt} for {uc_name} at scale={scale}")
                            geemap.ee_export_image(
                                vis_image,
                                filename=local_tif,
                                scale=scale,
                                file_per_band=False,
                                crs="EPSG:3857"
                            )
                            if os.path.exists(local_tif) and os.path.getsize(local_tif) > 0:
                                export_success = True
                            else:
                                raise Exception("Export produced empty or missing file")
                        except Exception as e:
                            error_msg = str(e)
                            scale = min(int(scale * 2), 200)
                            print(f"[EXPORT ERROR] {error_msg} → Retrying with scale={scale}")

                            time.sleep(2)
                            continue
                            
                            

                    if not export_success:
                        return {
                            "uc_name": uc_name,
                            "city_name": city_name,
                            "error": "1",
                            "error_msg": f"Export failed after {attempt} attempts.",
                            "tile_url_template": None
                        }

                    
                    with rasterio.open(local_tif, "r+") as src:
                        factors = [2, 4, 8, 16]
                        valid_factors = [f for f in factors if f < min(src.width, src.height)]
                        if valid_factors:
                            src.build_overviews(valid_factors, Resampling.nearest)
                            src.update_tags(ns="rio_overview", resampling="nearest")

                    
                    if os.path.exists(tiles_dir):
                        shutil.rmtree(tiles_dir)
                    os.makedirs(tiles_dir, exist_ok=True)

                    
                    with COGReader(local_tif) as cog:
                        def scale_to_zoom(scale_m_per_pixel):
                            z = math.log2(156543.03392804097 / float(scale_m_per_pixel))
                            return int(round(z))

                        target_zoom = max(0, min(18, scale_to_zoom(scale)))
                        min_zoom = max(0, target_zoom - 4)
                        max_zoom = min(18, target_zoom + 2)

                        left, bottom, right, top = cog.bounds
                        transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
                        lon_left, lat_bottom = transformer.transform(left, bottom)
                        lon_right, lat_top = transformer.transform(right, top)

                        for z in range(min_zoom, max_zoom + 1):
                            try:
                                tile_list = list(mercantile.tiles(lon_left, lat_bottom, lon_right, lat_top, [z]))
                                for t in tile_list:
                                    data, mask = cog.tile(t.x, t.y, t.z)
                                    if data is None:
                                        continue
                                    img = np.moveaxis(data, 0, 2)
                                    img = (img * 255).astype(np.uint8) if img.max() <= 1 else img

                                    if img.shape[2] == 3:
                                        alpha = np.any(img > 0, axis=2).astype(np.uint8) * 255
                                        img = np.dstack((img, alpha))

                                    pil_img = Image.fromarray(img, mode="RGBA")
                                    tile_path = os.path.join(tiles_dir, str(z), str(t.x))
                                    os.makedirs(tile_path, exist_ok=True)
                                    pil_img.save(os.path.join(tile_path, f"{t.y}.png"))
                            except Exception as e:
                                print(f"Zoom {z} skipped: {e}")

                    if area_type == "kml":
                        s3_prefix = f"tiles/yearly_pixelwise/shared/kml/{kml_hash}/{analysis_type}/{year}/{uc_safe}"
                    else:
                        s3_prefix = f"tiles/yearly_pixelwise/shared/uc/{analysis_type}/{year}/{city_safe}/{uc_safe}"
                    for root, dirs, files in os.walk(tiles_dir):
                        for fname in files:
                            if fname.lower().endswith(".png"):
                                full_path = os.path.join(root, fname)
                                rel_path = os.path.relpath(full_path, tiles_dir).replace(os.sep, "/")
                                s3_key = f"{s3_prefix}/{rel_path}"
                                s3_client.upload_file(full_path, bucket_name, s3_key)

                    tile_url_template = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{s3_prefix}/{{z}}/{{x}}/{{y}}.png"

                    
                    if os.path.exists(local_dir):
                        shutil.rmtree(local_dir)

                    
                    shared_defaults = {
                        "city_name": city_safe,
                        "is_pixelwise": True,
                        "tile_url_template": tile_url_template
                    }

                    if area_type == "kml" and kml_hash:
                        shared_defaults["kml_hash"] = kml_hash

                    YearlyAnalysis.objects.update_or_create(
                        project_id=None,
                        analysis_type=analysis_type,
                        year=selected_year,
                        area_type=area_type,
                        uc_name=uc_safe,
                        defaults=shared_defaults
                    )

                    if project_id:
                        YearlyAnalysis.objects.update_or_create(
                            project_id=project_id,
                            analysis_type=analysis_type,
                            year=selected_year,
                            area_type=area_type,
                            uc_name=uc_safe,
                            defaults={
                                "city_name": city_name,
                                "is_pixelwise": True,
                                "tile_url_template": tile_url_template
                            }
                        )

                    return {
                        "uc_name": uc_name,
                        "city_name": city_name,
                        "error": "0",
                        "tile_url_template": tile_url_template
                    }

                except Exception as e:
                    if os.path.exists(local_dir):
                        shutil.rmtree(local_dir)
                    return {
                        "uc_name": uc_name,
                        "city_name": city_name,
                        "error": "1",
                        "error_msg": str(e)
                    }

            
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(process_feature, f) for f in features]
                for future in as_completed(futures):
                    results.append(future.result())

            return Response({
                "message": f"{analysis_type.upper()} pixelwise yearly analysis for {selected_year} performed",
                "year": selected_year,
                "note": note,
                "results": results
            })

        else:
            return Response({"error": "Invalid mode"}, status=400)

    except Exception as e:
        return Response({"error": str(e)}, status=500)




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_yearly_pixel_value(request):
    try:
        
        analysis_type = request.data.get("analysis_type")
        year = request.data.get("year")
        lat = request.data.get("lat")
        lng = request.data.get("lng")
        project_id = request.data.get("project_id")  

        if not all([analysis_type, year, lat, lng]):
            return Response({"error": "Missing required parameters"}, status=400)

        year = int(year)
        lat = float(lat)
        lng = float(lng)

        
        pixel_record = YearlyPixelValue.objects.filter(
            project_id=project_id,
            analysis_type=analysis_type,
            year=year,
            lat=lat,
            lng=lng
        ).first()

        if pixel_record:
            return Response({
                "lat": lat,
                "lng": lng,
                "analysis_type": analysis_type,
                "year": year,
                "pixel_value": pixel_record.pixel_value
            })

        
        init_ee()

        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        point = ee.Geometry.Point([lng, lat])

        
        if analysis_type.lower() == "ndvi":
            collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
                         .filterBounds(point) \
                         .filterDate(start_date, end_date) \
                         .select(['B8', 'B4'])
            image = collection.median().normalizedDifference(['B8', 'B4']).rename('NDVI')

        elif analysis_type.lower() == "thermal":
            collection = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2') \
                         .filterBounds(point) \
                         .filterDate(start_date, end_date) \
                         .filter(ee.Filter.lt('CLOUD_COVER', 60))
            if collection.size().getInfo() == 0:
                collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
                             .filterBounds(point) \
                             .filterDate(start_date, end_date) \
                             .filter(ee.Filter.lt('CLOUD_COVER', 60))
            composite = collection.median()
            image = composite.select('ST_B10').multiply(0.00341802).add(149.0).rename('THERMAL')

        elif analysis_type.lower() == "aqi":
            collection = ee.ImageCollection('COPERNICUS/S5P/NRTI/L3_NO2') \
                         .filterBounds(point) \
                         .filterDate(start_date, end_date)
            image = collection.median().select('NO2_column_number_density').multiply(1e5).rename('AQI')

        else:
            return Response({"error": "Unsupported analysis type"}, status=400)

        
        sample = image.sample(region=point, scale=30).first()

        if not sample:
            pixel_value = {analysis_type.upper(): None}
        else:
            pixel_dict = sample.toDictionary().getInfo()
            band_name = list(pixel_dict.keys())[0]
            pixel_value = {analysis_type.upper(): pixel_dict.get(band_name, None)}

        
        YearlyPixelValue.objects.update_or_create(
            project_id=project_id,
            analysis_type=analysis_type,
            year=year,
            lat=lat,
            lng=lng,
            defaults={"pixel_value": pixel_value}
        )

        return Response({
            "lat": lat,
            "lng": lng,
            "analysis_type": analysis_type,
            "year": year,
            "pixel_value": pixel_value
        })

    except Exception as e:
        return Response({"error": str(e)}, status=500)
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def before_after_comparison_stats(request):
    
    init_ee()

    data = request.data
    project_id = data.get("project_id")
    analysis_type = data.get("analysis_type")
    area_type = data.get("area_type")
    before_year = data.get("before_year")
    after_year = data.get("after_year")

    if not all([project_id, analysis_type, area_type, before_year, after_year]):
        return Response({"error": "All fields are required."}, status=400)

    project = Project.objects.filter(id=project_id).first()
    if not project:
        return Response({"error": "Project not found."}, status=404)

    city_name = project.location_name
    results = []

    
    features = []
    if area_type == "uc":
        uc_data = load_ucs_for_uc(city_name)
        if not uc_data:
            db_ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)
            features = [
                {"uc_name": uc.uc_name, "city_name": uc.city_name, "geometry": json.loads(uc.geometry.geojson)}
                for uc in db_ucs
            ]
        else:
            features = [
                {"uc_name": f["properties"].get("uc_name"),
                 "city_name": f["properties"].get("city_name"),
                 "geometry": f["geometry"]}
                for f in uc_data.get("features", [])
            ]
    elif area_type == "kml":
        kml_data = load_ucs_for_kml(project.id)
        if not kml_data and project.kml_file:
            features = [{"uc_name": None, "city_name": None, "geometry": None}]
        else:
            features = [
                {"uc_name": f["properties"].get("uc_name"),
                 "city_name": f["properties"].get("city_name"),
                 "geometry": f["geometry"]}
                for f in kml_data.get("features", [])
            ]
    else:
        return Response({"error": "Invalid area_type"}, status=400)

   
    cached_data = BeforeAfterAnalysis.objects.filter(
        project_id=project_id,
        analysis_type=analysis_type,
        area_type=area_type,
        before_year=before_year,
        after_year=after_year
    )

    cached_map = {c.uc_name: c for c in cached_data}

    
    def process_feature(feature):
        uc_name = feature.get("uc_name")
        city_name = feature.get("city_name")

        if uc_name in cached_map:
            c = cached_map[uc_name]
            comp = c.comparison or {}
            before_mean = comp.get("before_mean")
            after_mean = comp.get("after_mean")
            status = comp.get("status")

            return {
                "uc_name": uc_name,
                "city_name": city_name,
                "before_mean": before_mean,
                "after_mean": after_mean,
                "status": status,
                "area_type": area_type
            }

        try:
            polygon = ee.Geometry(feature.get("geometry"))
            start_before, end_before = f"{before_year}-01-01", f"{before_year}-12-31"
            start_after, end_after = f"{after_year}-01-01", f"{after_year}-12-31"

            before_result = perform_analysis_for_polygon(analysis_type, polygon, start_before, end_before)
            after_result = perform_analysis_for_polygon(analysis_type, polygon, start_after, end_after)

            before_mean = before_result.get("stats", {}).get("mean")
            after_mean = after_result.get("stats", {}).get("mean")

            
            if before_mean is None or after_mean is None:
                status = "no_data"
            elif after_mean > before_mean:
                status = "increase"
            elif after_mean < before_mean:
                status = "decrease"
            else:
                status = "no_change"

            BeforeAfterAnalysis.objects.update_or_create(
                project_id=project_id,
                analysis_type=analysis_type,
                area_type=area_type,
                uc_name=uc_name,
                before_year=before_year,
                after_year=after_year,
                defaults={
                    "city_name": city_name,
                    "stats_before": {"mean": before_mean},
                    "stats_after": {"mean": after_mean},
                    "comparison": {
                        "status": status,
                        "before_mean": before_mean,
                        "after_mean": after_mean
                    }
                }
            )

            return {
                "uc_name": uc_name,
                "city_name": city_name,
                "before_mean": before_mean,
                "after_mean": after_mean,
                "status": status,
                "area_type": area_type
            }

        except Exception as e:
            return {
                "uc_name": uc_name,
                "city_name": city_name,
                "before_mean": None,
                "after_mean": None,
                "status": "error",
                "error_msg": str(e),
                "area_type": area_type
            }

    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_feature, f) for f in features]
        for future in as_completed(futures):
            results.append(future.result())

    
    before_vals = [r["before_mean"] for r in results if r["before_mean"] is not None]
    after_vals = [r["after_mean"] for r in results if r["after_mean"] is not None]
    change_counts = {"increase": 0, "decrease": 0, "no_change": 0}
    for r in results:
        if r["status"] in change_counts:
            change_counts[r["status"]] += 1

    summary_stats = {
        "before": {
            "mean": round(sum(before_vals) / len(before_vals), 4) if before_vals else None,
            "min": round(min(before_vals), 4) if before_vals else None,
            "max": round(max(before_vals), 4) if before_vals else None,
        },
        "after": {
            "mean": round(sum(after_vals) / len(after_vals), 4) if after_vals else None,
            "min": round(min(after_vals), 4) if after_vals else None,
            "max": round(max(after_vals), 4) if after_vals else None,
        },
        "changes": change_counts,
        "total": len(results)
    }

    return Response({
        "message": f"{analysis_type.upper()} before-after comparison completed",
        "analysis_type": analysis_type,
        "before_year": before_year,
        "after_year": after_year,
        "results": results,
        "summary_stats": summary_stats
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def before_after_comparison_pixelwise(request):
    init_ee()
    data = request.data
    project_id = data.get("project_id")
    analysis_type = data.get("analysis_type")
    area_type = data.get("area_type")
    before_year = data.get("before_year")
    after_year = data.get("after_year")

    if not all([project_id, analysis_type, area_type, before_year, after_year]):
        return Response({"error": "All fields are required."}, status=400)

    project = Project.objects.filter(id=project_id).first()
    if not project:
        return Response({"error": "Project not found."}, status=404)
    city_name = project.location_name

    
    features = []
    kml_hash = None
    if area_type == "uc":
        uc_data = load_ucs_for_uc(city_name)
        if not uc_data:
            db_ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)
            features = [
                {"uc_name": uc.uc_name, "city_name": uc.city_name, "geometry": json.loads(uc.geometry.geojson)}
                for uc in db_ucs
            ]
        else:
            features = [
                {"uc_name": f["properties"].get("uc_name"),
                 "city_name": f["properties"].get("city_name"),
                 "geometry": f["geometry"]}
                for f in uc_data.get("features", [])
            ]
    elif area_type == "kml":
        if not project_id:
            return Response({"error": "project_id is required for KML analysis"}, status=400)
        if not project or not project.kml_file:
            return Response({"error": "KML file not found for this project"}, status=404)

        kml_path = project.kml_file.path

        
        with open(kml_path, "rb") as f:
            kml_bytes = f.read()

        
        kml_content = kml_bytes.decode("utf-8-sig")

        
        kml_hash = hashlib.md5(kml_bytes).hexdigest()

    
        content_cache_path = os.path.join(DATA_DIR, f"{kml_hash}_kml_ucs.json")

        
        if os.path.exists(content_cache_path):
            kml_data = json.load(open(content_cache_path))
        else:
            polygon = kml_to_geosgeometry(kml_content)
            ucs = UnionCouncil.objects.filter(geometry__intersects=polygon)
            if not ucs.exists():
                return Response({"error": "No UCs found in this area"}, status=404)

            geojson = serialize(
                "geojson", ucs,
                geometry_field="geometry",
                fields=("uc_name", "city_name")
            )
            kml_data = json.loads(geojson)
            with open(content_cache_path, "w") as f:
                json.dump(kml_data, f)

        features = [
            {
                "uc_name": f["properties"].get("uc_name"),
                "city_name": f["properties"].get("city_name"),
                "geometry": f["geometry"]
            }
            for f in kml_data.get("features", [])
        ]

    else:
        return Response({"error": "Invalid area_type"}, status=400)

    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    s3_domain = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}"
    before_year = int(before_year)
    after_year = int(after_year)
    def normalize_name(name):
            if not name:
                return "custom"    
            return re.sub(r"[^\w\-]", "_", name.strip().lower())
        
    def process_feature(feature):
        uc_name = feature.get("uc_name")
        city_name = feature.get("city_name")
        geometry = feature.get("geometry")

        uc_safe = normalize_name(uc_name)
        city_safe = normalize_name(city_name)
        
        cached = BeforeAfterPixelwise.objects.filter(
            project_id=project_id,
            analysis_type=analysis_type,
            area_type=area_type,
            uc_name=uc_safe,
            before_year=before_year,
            after_year=after_year
        ).first()

        if cached and cached.tile_url_before and cached.tile_url_after:
            return {
                "uc_name": uc_name,
                "city_name": city_name,
                "tile_url_before": cached.tile_url_before,
                "tile_url_after": cached.tile_url_after,
                "error": "0"
            }
            
        shared_filter = {
            "project_id__isnull": True,
            "analysis_type": analysis_type,
            "before_year": before_year,
            "after_year": after_year,
            "area_type": area_type
        }

        if area_type == "uc":
            shared_filter["uc_name"] = uc_safe
            shared_filter["city_name"] = city_safe
        elif area_type == "kml":
            if kml_hash:
                
                shared_filter.update({
                    "kml_hash": kml_hash,
                    "before_year": int(before_year),
                    "after_year": int(after_year),
                    "uc_name": uc_safe,          
                    "city_name": city_safe 
                })
            else:
                return {
                    "uc_name": uc_name,
                    "city_name": city_name,
                    "error": "1",
                    "error_msg": "KML hash missing for caching.",
                    "tile_url_before": None,
                    "tile_url_after": None
                }
            



        shared_cache = BeforeAfterPixelwise.objects.filter(**shared_filter).first()
        if shared_cache:
            
            if project_id:
                
                BeforeAfterPixelwise.objects.update_or_create(
                    project_id=project_id,
                    analysis_type=analysis_type,
                    before_year=before_year,
                    after_year=after_year,
                    area_type=area_type,
                    uc_name=uc_safe,
                    defaults={
                        "city_name": city_name,
                        "kml_hash": kml_hash,
                        "tile_url_before": shared_cache.tile_url_before,
                        "tile_url_after": shared_cache.tile_url_after
                    }
                )
            return {
                "uc_name": uc_name,
                "city_name": city_name,
                "tile_url_before": shared_cache.tile_url_before,
                "tile_url_after": shared_cache.tile_url_after,
                "cached": True
            }

        try:
            polygon = ee.Geometry(feature.get("geometry"))
            polygon = polygon.simplify(30)
            area_sq_m = polygon.area().getInfo()
            if area_sq_m > 2e8:
                polygon = polygon.simplify(100)  
            elif area_sq_m > 5e7:
                polygon = polygon.simplify(50)
            else:
                polygon = polygon.simplify(30)
                
            if area_sq_m > 2e8:
                base_scale = 50
            elif area_sq_m > 5e7:
                base_scale = 30
            else:
                base_scale = 10

            
            if analysis_type.lower() == "aqi":
                before_image, before_vis, before_scale = run_pixelwise_analysis(
                analysis_type, polygon, f"{before_year}-01-01", f"{before_year}-12-31"
                )
                after_image, after_vis, after_scale = run_pixelwise_analysis(
                    analysis_type, polygon, f"{after_year}-01-01", f"{after_year}-12-31"
                )

            else:
                before_image, before_vis,before_scale = run_pixelwise_analysis(
                analysis_type, polygon, f"{before_year}-01-01", f"{before_year}-12-31"
                )
                after_image, after_vis, after_scale = run_pixelwise_analysis(
                    analysis_type, polygon, f"{after_year}-01-01", f"{after_year}-12-31"
                )

            
            def export_to_s3(image, vis_params, year_label, scale, poly):
                local_dir = os.path.join(
                    settings.MEDIA_ROOT, "temp_exports", "before_after_pixelwise",
                    "kml" if kml_hash else "uc",
                    kml_hash if kml_hash else str(project_id),
                    uc_safe,str(year_label)
                )
                os.makedirs(local_dir, exist_ok=True)
                local_tif = os.path.join(local_dir, f"{analysis_type}_{year_label}.tif")
                tiles_dir = os.path.join(local_dir, "tiles")
                os.makedirs(tiles_dir, exist_ok=True)

                
                pixel_count = image.reduceRegion(
                    reducer=ee.Reducer.count(),
                    geometry=poly,
                    scale=scale,
                    maxPixels=1e13
                ).getInfo()
                if not pixel_count or all(v == 0 for v in pixel_count.values()):
                    print(f"Empty pixels for {uc_name}, trying larger buffer")
                    poly = poly.buffer(60)
                    scale = 10
                    
                    pixel_count = image.reduceRegion(
                        reducer=ee.Reducer.count(),
                        geometry=poly,
                        scale=scale,
                        maxPixels=1e13
                    ).getInfo()
                    if not pixel_count or all(v == 0 for v in pixel_count.values()):
                        raise Exception("Export failed: No valid pixels found even after buffering.")

                vis_image = image.visualize(
                    min=vis_params.get("min"),
                    max=vis_params.get("max"),
                    palette=vis_params.get("palette")
                )

                
                export_success = False
                attempt = 0
                max_attempts = 4
                while not export_success and attempt < max_attempts:
                    try:
                        attempt += 1
                        print(f"Export attempt {attempt} for {uc_name or 'custom'} - {year_label} at scale={scale}")
                        geemap.ee_export_image(
                            vis_image,
                            filename=local_tif,
                            scale=scale,
                            file_per_band=False,
                            crs="EPSG:3857"
                        )
                        if os.path.exists(local_tif) and os.path.getsize(local_tif) > 0:
                            export_success = True
                        else:
                            raise Exception("Empty or missing export")
                    except Exception as e:
                        err = str(e)
                        if "Empty or missing export" in err or "No valid pixels" in err:
                            scale = min(int(scale * 2), 200)
                            print(f"[INFO] Retrying export with larger scale={scale} due to empty result.")
                            time.sleep(2)
                        elif "memory" in err.lower() or "limit exceeded" in err.lower():
                            scale = min(int(scale * 2), 200)
                            print(f"[INFO] Retrying due to memory limit exceeded, new scale={scale}")
                            time.sleep(2)
                        elif "Total request size" in err or "50331648 bytes" in err:
                            scale = min(int(scale * 2), 200)
                            print(f"Retrying with larger scale={scale}")
                        elif "Network" in err or "getaddrinfo" in err:
                            time.sleep(5)
                        else:
                            print(f"Export failed: {err}")
                            break

                if not export_success:
                    raise Exception(f"Export failed after {attempt} attempts")

                
                with rasterio.open(local_tif, "r+") as src:
                    factors = [2, 4, 8, 16]
                    valid_factors = [f for f in factors if f < min(src.width, src.height)]
                    if valid_factors:
                        src.build_overviews(valid_factors, Resampling.nearest)
                        src.update_tags(ns="rio_overview", resampling="nearest")

                if os.path.exists(tiles_dir):
                    shutil.rmtree(tiles_dir)
                os.makedirs(tiles_dir, exist_ok=True)

                
                with COGReader(local_tif) as cog:
                    def scale_to_zoom(scale_m_per_pixel):
                        z = math.log2(156543.03392804097 / float(scale_m_per_pixel))
                        return int(round(z))

                    target_zoom = max(0, min(18, scale_to_zoom(scale)))
                    min_zoom = max(0, target_zoom - 4)
                    max_zoom = min(18, target_zoom + 2)

                    left, bottom, right, top = cog.bounds
                    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
                    lon_left, lat_bottom = transformer.transform(left, bottom)
                    lon_right, lat_top = transformer.transform(right, top)

                    for z in range(min_zoom, max_zoom + 1):
                        try:
                            tile_list = list(mercantile.tiles(lon_left, lat_bottom, lon_right, lat_top, [z]))
                            for t in tile_list:
                                data, mask = cog.tile(t.x, t.y, t.z)
                                if data is None:
                                    continue
                                img = np.moveaxis(data, 0, 2)
                                img = (img * 255).astype(np.uint8) if img.max() <= 1 else img
                                if img.shape[2] == 3:
                                    alpha = np.any(img > 0, axis=2).astype(np.uint8) * 255
                                    img = np.dstack((img, alpha))
                                pil_img = Image.fromarray(img, mode="RGBA")
                                tile_path = os.path.join(tiles_dir, str(z), str(t.x))
                                try:
                                    os.makedirs(tile_path, exist_ok=True)
                                    save_path = os.path.join(tile_path, f"{t.y}.png")
                                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                                    pil_img.save(save_path)
                                except FileNotFoundError as e:
                                    print(f"[WARN] Skipped tile ({z}/{t.x}/{t.y}) — folder missing: {e}")
                                except Exception as e:
                                    print(f"[WARN] Failed to save tile ({z}/{t.x}/{t.y}): {e}")

                                
                        except Exception as e:
                            print(f"Zoom {z} skipped: {e}")

                if area_type == "kml":
                    s3_prefix = f"tiles/2-year comparison/shared/kml/{kml_hash}/{analysis_type}/{year_label}/{uc_safe}"
                else:
                    s3_prefix = f"tiles/2-year comparison/shared/uc/{analysis_type}/{year_label}/{city_safe}/{uc_safe}"
                for root, dirs, files in os.walk(tiles_dir):
                    for fname in files:
                        if fname.lower().endswith(".png"):
                            full_path = os.path.join(root, fname)
                            rel_path = os.path.relpath(full_path, tiles_dir).replace(os.sep, "/")
                            s3_key = f"{s3_prefix}/{rel_path}"
                            s3_client.upload_file(full_path, bucket_name, s3_key)

                
                
                if os.path.exists(tiles_dir):
                    shutil.rmtree(tiles_dir)
                os.makedirs(tiles_dir, exist_ok=True)


                return f"{s3_domain}/{s3_prefix}/{{z}}/{{x}}/{{y}}.png"

            
            tile_url_before = export_to_s3(before_image, before_vis, before_year, before_scale, polygon)
            tile_url_after = export_to_s3(after_image, after_vis, after_year, after_scale, polygon)

            BeforeAfterPixelwise.objects.update_or_create(
                project_id=None,
                analysis_type=analysis_type,
                before_year=before_year,
                after_year=after_year,
                area_type=area_type,
                uc_name=uc_safe,
                defaults={
                    "city_name": city_safe,
                    "kml_hash": kml_hash,
                    "tile_url_before": tile_url_before,
                    "tile_url_after": tile_url_after
                }
            )
            if project_id:
               
                BeforeAfterPixelwise.objects.update_or_create(
                    project_id=project_id,
                    analysis_type=analysis_type,
                    area_type=area_type,
                    uc_name=uc_safe,
                    before_year=before_year,
                    after_year=after_year,
                    defaults={
                        "city_name": city_name,
                        "kml_hash": kml_hash,
                        "tile_url_before": tile_url_before,
                        "tile_url_after": tile_url_after
                    }
                )

                return {
                    "uc_name": uc_name,
                    "city_name": city_name,
                    "tile_url_before": tile_url_before,
                    "tile_url_after": tile_url_after,
                    "error": "0",
                    "cached": False
                }

        except Exception as e:
            print(f"Error processing {uc_name}: {e}")
            return {
                "uc_name": uc_name,
                "city_name": city_name,
                "error": "1",
                "error_msg": str(e),
                "tile_url_before": None,
                "tile_url_after": None
            }

    
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_feature, f) for f in features]
        for future in as_completed(futures):
            results.append(future.result())

    return Response({
        "mode": "before_after_comparison_pixelwise",
        "analysis_type": analysis_type,
        "before_year": before_year,
        "after_year": after_year,
        "results": results
    })
