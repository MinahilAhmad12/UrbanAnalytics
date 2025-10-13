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
# from dateutil.relativedelta import relativedelta
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

from rio_tiler.io import COGReader

#from rio_tiler.utils import tile_read

from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image
import mercantile
import time


DATA_DIR = os.path.join(settings.BASE_DIR, "local_data")
os.makedirs(DATA_DIR, exist_ok=True)


from django.contrib.gis.geos import GEOSGeometry
from shapely.geometry import Polygon as ShapelyPolygon
import xml.etree.ElementTree as ET

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
            cache_file_path = os.path.join(DATA_DIR, f"project_{project.id}_kml_ucs.json")

            if os.path.exists(cache_file_path):
                with open(cache_file_path, "r") as f:
                    return Response(json.load(f))

            with open(kml_path, "r", encoding="utf-8") as f:
                kml_content = f.read()

            polygon = kml_to_geosgeometry(kml_content)


            ucs = UnionCouncil.objects.filter(geometry__intersects=polygon)
            if not ucs.exists():
                return Response({"error": "No UCs found in this area"}, status=404)

            geojson = serialize(
                "geojson", ucs,
                geometry_field="geometry",
                fields=("uc_name", "city_name")
            )
            geojson_data = json.loads(geojson)

            with open(cache_file_path, "w") as f:
                json.dump(geojson_data, f)

            return Response(geojson_data)

        else:
            return Response({"error": "Project has neither location_name nor KML file"}, status=400)

    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=404)


os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
os.environ['SSL_CERT_FILE'] = certifi.where()
# def init_ee():
#     """Initialize Earth Engine lazily when needed."""
#     if ee.data._initialized:  # Skip if already initialized
#         return
#     service_account = os.path.join(settings.BASE_DIR, 'service_account.json')

#     # service_account = 'gee-service-account@urbananalytics-460415.iam.gserviceaccount.com'
#     credentials = ee.ServiceAccountCredentials(service_account, settings.SERVICE_ACCOUNT_PATH)

#     try:
#         ee.Initialize(credentials, project='urbananalytics-460415')
#         print("Earth Engine initialized successfully!")
#     except Exception as e:
#         print("Failed to initialize Earth Engine:", e)
#         raise RuntimeError("Earth Engine initialization failed. Check credentials.")

def init_ee():
    """Initialize Earth Engine lazily when needed."""
    if ee.data._initialized:  # Skip if already initialized
        return

    # Path to service_account.json at the same level as manage.py
    service_account_path = os.path.join(settings.BASE_DIR, 'service_account.json')

    # Service account email from the JSON file
    # For GEE, it should be something like 'your-service-account@your-project.iam.gserviceaccount.com'
    with open(service_account_path) as f:
        import json
        service_account_info = json.load(f)
        service_account_email = service_account_info['client_email']

    credentials = ee.ServiceAccountCredentials(service_account_email, key_file=service_account_path)

    try:
        ee.Initialize(credentials, project='urbananalytics-460415')
        print("Earth Engine initialized successfully!")
    except Exception as e:
        print("Failed to initialize Earth Engine:", e)
        raise RuntimeError("Earth Engine initialization failed. Check credentials.")


def load_ucs_for_uc(city_name):
    """Load UC data for a city from local JSON file."""
    file_path = os.path.join(DATA_DIR, f"{city_name.lower()}_ucs.json")
    if not os.path.exists(file_path):
        return None

    with open(file_path, "r") as f:
        return json.load(f) 
def load_ucs_for_kml(project_id):
    """Load UC and KML data for a project from a local JSON file."""
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
                polygon = ee.Geometry(feature["geometry"])
                result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)

                if not result or "stats" not in result:
                    raise ValueError("No stats found for this polygon")

                mean_value = result["stats"].get("mean", None)
                if mean_value is None or (isinstance(mean_value, float) and math.isnan(mean_value)):
                    mean_value = 0
                elif analysis_type.lower() == "ndvi":
                    mean_value = max(0, min(1, mean_value))
                elif analysis_type.lower() == "thermal":
                    mean_value = max(290, min(320, mean_value))  
                elif analysis_type.lower() == "aqi":
                    mean_value = max(0, min(30, mean_value))     

                
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
                    results.append(res)



        return Response({
            "message": f"{analysis_type.upper()} average analysis completed",
            "results": results
        })

    except Exception as e:
        return Response({"error": str(e)}, status=500)
            
def perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date):
    init_ee()
    scale = 10

    try:
        
        if analysis_type.lower() == "ndvi":
            
            collection = (
                ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterBounds(polygon)
                .filterDate(start_date, end_date)
                .select(['B8', 'B4'])
                .median()
            )
            image = collection.normalizedDifference(['B8', 'B4']).rename('NDVI').clip(polygon)
            band_name = 'NDVI'
            vis_params = {'min': 0, 'max': 1,
                          "palette": ["#FFFFFF", "#FFFF00", "#90EE90", "#008000", "#006400"]}
            scale = 10

            stats = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=polygon,
                scale=scale,
                maxPixels=1e9
            ).getInfo()

            mean_value = stats.get(band_name)

            
            if mean_value is None:
                collection = (
                    ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
                    .filterBounds(polygon)
                    .filterDate(start_date, end_date)
                    .filter(ee.Filter.lt('CLOUD_COVER', 60))
                )
                if collection.size().getInfo() > 0:
                    composite = collection.median()
                    nir = composite.select('SR_B5')
                    red = composite.select('SR_B4')
                    image = nir.subtract(red).divide(nir.add(red)).rename('NDVI').clip(polygon)

                    stats = image.reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=polygon,
                        scale=30,
                        maxPixels=1e9
                    ).getInfo()
                    mean_value = stats.get('NDVI')
                    scale = 30

        
        elif analysis_type.lower() == "thermal":
            collection = (
                ee.ImageCollection('LANDSAT/LC09/C02/T1_L2')
                .filterBounds(polygon)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt('CLOUD_COVER', 60))
            )

            
            if collection.size().getInfo() == 0:
                collection = (
                    ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
                    .filterBounds(polygon)
                    .filterDate(start_date, end_date)
                    .filter(ee.Filter.lt('CLOUD_COVER', 60))
                )

            composite = collection.median()
            image = composite.select('ST_B10').multiply(0.00341802).add(149.0).rename('Thermal').clip(polygon)
            band_name = 'Thermal'
            vis_params = {'min': 290, 'max': 320,
                          'palette': ["#87CEEB", "#32CD32", "#FF6347", "#FFA500", "#800080"]}
            scale = 100

        
        elif analysis_type.lower() == "aqi":
            collection = (
                ee.ImageCollection('COPERNICUS/S5P/NRTI/L3_NO2')
                .filterBounds(polygon)
                .filterDate(start_date, end_date)
                .median()
            )
            image = collection.select('NO2_column_number_density').rename('AQI').multiply(1e5).clip(polygon)
            band_name = 'AQI'
            vis_params = {'min': 0, 'max': 30,
                          'palette': ["#FFC0CB", "#FF7F50", "#FFBF00", "#FFFFE0", "#FF00FF", "#8A2BE2"]}
            scale = 1000

        else:
            raise ValueError("Invalid analysis type")

        
        if analysis_type.lower() != "ndvi" or mean_value is None:
            stats = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=polygon,
                scale=scale,
                maxPixels=1e9
            ).getInfo()
            mean_value = stats.get(band_name)

        
        if mean_value is None:
            raise ValueError("No mean value computed (even after fallback)")

        
        min_val, max_val = vis_params['min'], vis_params['max']
        palette = vis_params['palette']
        norm_val = max(0, min(1, (mean_value - min_val) / (max_val - min_val)))
        idx = int(norm_val * (len(palette) - 1))
        color = palette[idx]

        return {
            "stats": {
                "mean": round(mean_value, 4),
                "color": color,
                "status": "success",
                "source": "Sentinel-2" if scale == 10 else "Landsat-8"
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

    try:
        results = []
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        
        if project_id and area_type in ["uc", "kml"]:
            cached_results = AreaAnalysis.objects.filter(
                project_id=project_id,
                analysis_type=analysis_type,
                start_date=start_date,
                end_date=end_date,
                area_type=area_type,
                is_pixelwise=True
            ).order_by('uc_name')

            if cached_results.exists():
                for cached in cached_results:
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

        def process_uc(feature):
            uc_name = feature["properties"].get("uc_name", "unknown_uc")
            city_name = feature["properties"].get("city_name", "unknown_city")
            uc_safe = re.sub(r"[^\w\-]", "_", uc_name)
            local_dir = os.path.join(settings.MEDIA_ROOT, "temp_exports", "pixelwise", str(project_id), uc_safe)
            os.makedirs(local_dir, exist_ok=True)

            local_tif = os.path.join(local_dir, f"{analysis_type}_{start_date}_{end_date}.tif")
            tiles_dir = os.path.join(local_dir, "tiles")

            try:
                
                geojson_dict = feature.get("geometry")
                if not geojson_dict:
                    raise ValueError("Missing geometry")
                polygon = ee.Geometry(geojson_dict)

                if analysis_type.lower()!= "aqi":
                    
                    area_sq_m = polygon.area().getInfo()
                    default_scales = {"ndvi": 10, "thermal": 100}
                    scale = default_scales.get(analysis_type.lower(), 10)
                    
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
                else:
                    image, vis_params, _ = run_pixelwise_analysis(analysis_type, polygon, start_date, end_date)
                
                if not image:
                    return {"uc_name": uc_name, "city_name": city_name, "error": "1",
                            "error_msg": "No image generated", "tile_url_template": None}

                
                
                polygon_3857 = polygon.transform("EPSG:3857", maxError=1)

                
                image = image.clip(polygon_3857)
                
                try:
                    stats = image.reduceRegion(
                        reducer=ee.Reducer.percentile([5, 95]),
                        geometry=polygon,
                        scale=scale,
                        bestEffort=True,
                        maxPixels=1e13
                    ).getInfo()

                    band_name = list(stats.keys())[0]  
                    vmin = float(stats.get(f'{band_name}_p5', vis_params.get("min", 0)))
                    vmax = float(stats.get(f'{band_name}_p95', vis_params.get("max", 1)))
                    
                    if vmin == vmax:
                        vmax += 1e-3  
                except Exception:
                    vmin = vis_params.get("min", 0)
                    vmax = vis_params.get("max", 1)
                
                vis_image = image.visualize(
                    min=vmin,
                    max=vmax,
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
                    print(f" No pixel data found for {uc_name}, skipping export.")
                    return {
                        "uc_name": uc_name,
                        "city_name": city_name,
                        "error": "1",
                        "error_msg": "Export failed: No valid pixels found (empty data).",
                        "tile_url_template": None
                    }

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
                        if "Total request size" in error_msg or "50331648 bytes" in error_msg:
                            
                            scale = min(int(scale * 2), 200)
                            print(f" Export too large, retrying with scale={scale}")
                        elif "Network" in error_msg or "getaddrinfo" in error_msg:
                            print(f" Network error, retrying after 5 seconds...")
                            time.sleep(5)
                        else:
                            print(f" Export failed: {error_msg}")
                            break

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

                
                s3_tile_prefix = f"tiles/pixelwise/{project_id}/{analysis_type}/{start_date}_{end_date}/{uc_safe}"
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
                    project_id=project_id,
                    analysis_type=analysis_type,
                    start_date=start_date,
                    end_date=end_date,
                    area_type=area_type,
                    uc_name=uc_name,
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
                    "error_msg": str(e),
                    "tile_url_template": None
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


            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(process_uc, features))

        elif area_type == "kml":
            if not project_id:
                return Response({"error": "project_id is required for KML analysis"}, status=400)

            local_kml_file = os.path.join(DATA_DIR, f"project_{project_id}_kml_ucs.json")
            if os.path.exists(local_kml_file):
                with open(local_kml_file, "r") as f:
                    kml_data = json.load(f)
                features = kml_data.get("features", [])
            else:
                project = Project.objects.filter(id=project_id).first()
                if not project:
                    return Response({"error": "Project not found"}, status=404)

                db_ucs = UnionCouncil.objects.all()
                features = [
                    {
                        "geometry": json.loads(uc.geometry.geojson),
                        "properties": {"uc_name": uc.uc_name, "city_name": uc.city_name}
                    } for uc in db_ucs
                ]

            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(process_uc, features))

        elif area_type == "custom":
            if not geometry_data:
                return Response({"error": "geometry data is required for custom analysis"}, status=400)

            geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
            polygon = ee.Geometry(geom_json)
            if analysis_type.lower()!= "aqi":
                area_sq_m = polygon.area().getInfo()
                default_scales = {"ndvi": 10, "thermal": 100}
                scale = default_scales.get(analysis_type.lower(), 10)
                if area_sq_m < (scale**2):
                    scale = max(int(area_sq_m**0.5), 1)
                if analysis_type.lower() == "ndvi" and area_sq_m < 1e4:
                    scale = max(scale, 20)
                if area_sq_m < 100:
                    return {"uc_name": None, "city_name": None, "error": "1",
                            "error_msg": "Polygon too small for analysis", "tile_url_template": None}
                    
            if analysis_type.lower() == "aqi":
                image, vis_params, scale = run_pixelwise_analysis(analysis_type, polygon, start_date, end_date)
            else:
                image, vis_params, _ = run_pixelwise_analysis(analysis_type, polygon, start_date, end_date)
    
            if not image:
                return {
                    "error": "1",
                    "error_msg": "No image generated for custom area",
                    "cog_https_url": None
                }

            custom_dir = os.path.join(settings.MEDIA_ROOT, "temp_exports", "pixelwise", str(project_id))
            os.makedirs(custom_dir, exist_ok=True)

            local_tif = os.path.join(custom_dir, f"{analysis_type}_{start_date}_{end_date}.tif")
            tiles_dir = os.path.join(custom_dir, "tiles")
            polygon_3857 = polygon.transform("EPSG:3857", maxError=1)
            image = image.clip(polygon_3857)
            
            try:
                stats = image.reduceRegion(
                    reducer=ee.Reducer.percentile([5, 95]),
                    geometry=polygon,
                    scale=scale,
                    bestEffort=True,
                    maxPixels=1e13
                ).getInfo()

                band_name = list(stats.keys())[0]  
                vmin = float(stats.get(f'{band_name}_p5', vis_params.get("min", 0)))
                vmax = float(stats.get(f'{band_name}_p95', vis_params.get("max", 1)))
                
                if vmin == vmax:
                    vmax += 1e-3  
            except Exception:
                vmin = vis_params.get("min", 0)
                vmax = vis_params.get("max", 1)
            
            vis_image = image.visualize(
                min=vmin,
                max=vmax,
                palette=vis_params.get("palette")
            )

            
            data_type = "uint8"  
            vis_image = vis_image.reproject(crs="EPSG:3857", scale=scale)
            
            if analysis_type.lower() == "aqi":
                geemap.ee_export_image(
                    vis_image,
                    filename=local_tif,
                    scale=scale,
                    region=polygon.geometry().getInfo(),  
                    file_per_band=False,
                    crs="EPSG:3857"
                )
            else:
                
                geemap.ee_export_image(
                    vis_image,
                    filename=local_tif,
                    scale=scale,
                    file_per_band=False,
                    crs="EPSG:3857"
                )

            if not os.path.exists(local_tif):
                return {"uc_name": None, "city_name": None, "error": "1",
                        "error_msg": "Export failed", "tile_url_template": None}

            
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

            
                s3_tile_prefix = f"tiles/pixelwise/custom/{project_id}/{analysis_type}/{start_date}_{end_date}"
            for root, dirs, files in os.walk(tiles_dir):
                for fname in files:
                    if fname.lower().endswith(".png"):
                        full_path = os.path.join(root, fname)
                        rel_path = os.path.relpath(full_path, tiles_dir).replace(os.sep, "/")
                        s3_key = f"{s3_tile_prefix}/{rel_path}"
                        s3_client.upload_file(full_path, bucket_name, s3_key)

            
            tile_url_template = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{s3_tile_prefix}/{{z}}/{{x}}/{{y}}.png"

            
            if os.path.exists(custom_dir):
                shutil.rmtree(custom_dir)

            
            AreaAnalysis.objects.update_or_create(
                project_id=project_id,
                analysis_type=analysis_type,
                start_date=start_date,
                end_date=end_date,
                area_type=area_type,
                uc_name=None,
                defaults={
                    "city_name": None,
                    "is_pixelwise": True,
                    "tile_url_template": tile_url_template
                }
            )

            return {"uc_name": None, "city_name": None, "error": "0", "tile_url_template": tile_url_template}
        
        return Response({
            "message": f"{analysis_type.upper()} pixelwise analysis performed",
            "results": results
        }, status=200)
        
    except Exception as e:
        if 'custom_dir' in locals() and os.path.exists(custom_dir):
            shutil.rmtree(custom_dir)
        return Response({"uc_name": None, "city_name": None, "error": "1",
                "error_msg": str(e), "tile_url_template": None}, status=500)
    
    

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
        
        s2_collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterBounds(polygon) \
            .filterDate(start_date, end_date) \
            .select(['B8', 'B4'])  

        s2_size = s2_collection.size().getInfo()
        print(f"[DEBUG] Sentinel-2 collection size: {s2_size}")

        if s2_size > 0:
            image = s2_collection.median().normalizedDifference(['B8', 'B4']).rename('NDVI').clip(polygon)
            scale = 10
        else:
            print("[DEBUG] No Sentinel-2 images found, falling back to Landsat-8")
            
            l8_collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
                .filterBounds(polygon) \
                .filterDate(start_date, end_date) \
                .select(['B5', 'B4'])  

            l8_size = l8_collection.size().getInfo()
            print(f"[DEBUG] Landsat-8 collection size: {l8_size}")

            if l8_size > 0:
                image = l8_collection.median().normalizedDifference(['B5', 'B4']).rename('NDVI').clip(polygon)
                scale = 30
            else:
                print("[DEBUG] No Landsat-8 images found, creating constant NDVI image")
                image = ee.Image.constant(0.01).rename("NDVI").clip(polygon)
                scale = 30

        
        try:
            stats = image.reduceRegion(
                reducer=ee.Reducer.percentile([5, 95]),
                geometry=polygon,
                scale=scale,
                bestEffort=True,
                maxPixels=1e13
            ).getInfo()

            vmin = float(stats.get('NDVI_p5', 0))
            vmax = float(stats.get('NDVI_p95', 1))
            if vmin == vmax:
                vmax += 1e-3

            print(f"[DEBUG] NDVI min={vmin}, max={vmax}")
        except Exception as e:
            print("[DEBUG] Failed to compute NDVI min/max:", e)
            vmin, vmax = 0, 1

        vis_params = {
            'min': vmin,
            'max': vmax,
            'palette': ["#A52A2A", "#F4A460", "#9ACD32", "#90EE90", "#008000", "#006400"]
        }

        
        try:
            pixel_count = ee.Number(image.reduceRegion(
                reducer=ee.Reducer.count(),
                geometry=polygon,
                scale=scale,
                bestEffort=True,
                maxPixels=1e13
            ).get('NDVI')).getInfo()
            print(f"[DEBUG] NDVI pixel count: {pixel_count}")
        except Exception as e:
            print("[DEBUG] NDVI pixel count failed:", e)
        
        print_debug_info(image, analysis_type, polygon, scale)
     
    elif analysis_type.lower() == "thermal":
        
        collection = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2') \
            .filterBounds(polygon) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.lt('CLOUD_COVER', 60))

        if collection.size().getInfo() == 0:
            collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
                .filterBounds(polygon) \
                .filterDate(start_date, end_date) \
                .filter(ee.Filter.lt('CLOUD_COVER', 60))

        
        if collection.size().getInfo() == 0:
            image = ee.Image.constant(295).rename("Thermal").clip(polygon)
            vis_params = {'min': 290, 'max': 320,
                        'palette': ["#00008B","#008080","#40E0D0","#2E8B57","#FFFDD0","#FF8C00"]}
        else:
            
            image = collection.median().select('ST_B10') \
                .multiply(0.00341802).add(149.0).rename('Thermal').clip(polygon)

            
            stats = image.reduceRegion(
                reducer=ee.Reducer.percentile([5, 95]),
                geometry=polygon,
                scale=100,
                bestEffort=True,
                maxPixels=1e13
            ).getInfo()

            vmin = float(stats.get('ST_B10_p5', 290))
            vmax = float(stats.get('ST_B10_p95', 320))
            if vmin == vmax:
                vmax += 1e-3

            vis_params = {'min': vmin, 'max': vmax,
                        'palette': ["#00008B","#008080","#40E0D0","#2E8B57","#FFFDD0","#FF8C00"]}

        scale = 100
        print_debug_info(image, analysis_type, polygon, scale)

    
    elif analysis_type.lower() == "aqi":
       
        collection = ee.ImageCollection('COPERNICUS/S5P/NRTI/L3_NO2') \
            .filterBounds(polygon) \
            .filterDate(start_date, end_date)

        
        if collection.size().getInfo() == 0:
            print("No NO₂ data available for this date range.")
            image = ee.Image.constant(0).rename("AQI").clip(polygon)
            vis_params = {
                'min': 0, 'max': 50,
                'palette': ['#00E400', '#FFFF00', '#FF7E00',
                            '#FF0000', '#8F3F97', '#7E0023']
            }
            return image, vis_params

        
        image = collection.median() \
            .select('NO2_column_number_density') \
            .multiply(1e5).rename('AQI') \
            .clip(polygon)

        
        area_sq_m = polygon.area().getInfo()

        if area_sq_m < 5e7:       
            scale = 500
        elif area_sq_m < 1e8:      
            scale = 1000
        elif area_sq_m < 5e8:      
            scale = 2000
        else:                      
            scale = 3000

        print(f"[DEBUG] AQI scale selected = {scale} meters/pixel for area = {area_sq_m/1e6:.2f} km²")

        
        vis_params = {
            'min': 0,
            'max': 50,
            'palette': [
                '#00E400', '#FFFF00', '#FF7E00',
                '#FF0000', '#8F3F97', '#7E0023'
            ]
        }

        return image, vis_params,scale


    
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

        
        image, _ = run_pixelwise_analysis(analysis_type, point.buffer(30), start_date, end_date)

        
        value = image.sample(region=point, scale=30).first().toDictionary().getInfo()

        return Response({
            "lat": lat,
            "lng": lng,
            "analysis_type": analysis_type,
            "pixel_value": value
        })
    except Exception as e:
        return Response({"error": str(e)}, status=500)


    
# def get_yearly_analysis_from_db(project_id, analysis_type, year, area_type, uc_name=None, is_pixelwise=True):
#     try:
#         record = YearlyAnalysis.objects.get(
#             project_id=project_id,
#             analysis_type=analysis_type,
#             year=year,
#             area_type=area_type,
#             uc_name=uc_name,
#             is_pixelwise=is_pixelwise
#         )

#         return {
#             "uc_name": record.uc_name,
#             "city_name": record.city_name,
#             "tile_url_template": record.tile_url_template,  
#             "stats": record.stats,
#             "mode": "pixelwise" if is_pixelwise else "annual_stats",
#             "error": "0"
#         }

#     except YearlyAnalysis.DoesNotExist:
#         return None

def get_yearly_analysis_from_db(project_id, analysis_type, year, area_type, uc_name=None, is_pixelwise=False):
    """
    Fetch cached yearly analysis from the database for both annual stats and pixelwise modes,
    for both UC and KML area types.
    """

    if not project_id or area_type not in ["uc", "kml"]:
        return None

    filters = {
        "project_id": project_id,
        "analysis_type": analysis_type,
        "year": year,
        "area_type": area_type,
        "is_pixelwise": is_pixelwise,
    }

    # Add uc_name only if it exists (for UC-based)
    if uc_name:
        filters["uc_name"] = uc_name

    # Query all relevant cached results
    cached_results = YearlyAnalysis.objects.filter(**filters).order_by("uc_name")

    if not cached_results.exists():
        return None

    results = []
    for record in cached_results:
        results.append({
            "uc_name": record.uc_name,
            "city_name": record.city_name,
            "tile_url_template": record.tile_url_template,
            "stats": record.stats,
            "mode": "pixelwise" if record.is_pixelwise else "annual_stats",
            "error": "0"
        })

    print(f"[DEBUG] Returning {len(results)} cached {analysis_type.upper()} "
          f"{'pixelwise' if is_pixelwise else 'annual_stats'} records for {year} ({area_type})")

    return results




# def save_yearly_analysis(polygon,start_date,end_date,image,vis_params,project_id, analysis_type, year, area_type, uc_name, city_name, stats, is_pixelwise=False):
#     bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    
#     uc_safe = re.sub(r"[^\w\-]", "_", uc_name)
#     local_dir = os.path.join(settings.MEDIA_ROOT, "temp_exports", "yearly_analysis", str(project_id), uc_safe)
#     os.makedirs(local_dir, exist_ok=True)

#     local_tif = os.path.join(local_dir, f"{analysis_type}_{start_date}_{end_date}.tif")
#     tiles_dir = os.path.join(local_dir, "tiles")

#     try:
        
        
#         area_sq_m = polygon.area().getInfo()
#         default_scales = {"ndvi": 10, "thermal": 100, "aqi": 7000}
#         scale = default_scales.get(analysis_type.lower(), 10)
#         if area_sq_m < (scale**2):
#             scale = max(int(area_sq_m**0.5), 1)
#         if analysis_type.lower() == "ndvi" and area_sq_m < 1e4:
#             scale = max(scale, 20)
#         if area_sq_m < 100:
#             return {"uc_name": uc_name, "city_name": city_name, "error": "1",
#                     "error_msg": "Polygon too small for analysis", "tile_url_template": None}

        
    
#         vis_image = image.visualize(
#             min=vis_params.get("min"),
#             max=vis_params.get("max"),
#             palette=vis_params.get("palette")
#         )

        
#         geemap.ee_export_image(
#             vis_image,
#             filename=local_tif,
#             scale=scale,
#             file_per_band=False,
#             crs="EPSG:3857"
#         )

#         if not os.path.exists(local_tif):
#             return {"uc_name": uc_name, "city_name": city_name, "error": "1",
#                     "error_msg": "Export failed", "tile_url_template": None}

        
#         with rasterio.open(local_tif, "r+") as src:
#             width, height = src.width, src.height
#             factors = [2, 4, 8, 16]
#             valid_factors = [f for f in factors if f < min(width, height)]
#             if valid_factors:
#                 src.build_overviews(valid_factors, Resampling.nearest)
#                 src.update_tags(ns="rio_overview", resampling="nearest")

        
#         if os.path.exists(tiles_dir):
#             shutil.rmtree(tiles_dir)
#         os.makedirs(tiles_dir, exist_ok=True)

#         with COGReader(local_tif) as cog:
            
#             def scale_to_zoom(scale_m_per_pixel):
#                 z = math.log2(156543.03392804097 / float(scale_m_per_pixel))
#                 return int(round(z))

#             target_zoom = max(0, min(18, scale_to_zoom(scale)))
#             min_zoom = max(0, target_zoom - 4)
#             max_zoom = min(18, target_zoom + 2)
            
            
#             left, bottom, right, top = cog.bounds
#             transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
#             lon_left, lat_bottom = transformer.transform(left, bottom)
#             lon_right, lat_top = transformer.transform(right, top)
            
            
#             for z in range(min_zoom, max_zoom + 1):
#                 n = 2 ** z
#                 try:
                    
#                     tile_list = list(mercantile.tiles(lon_left, lat_bottom, lon_right, lat_top, [z]))
#                 except Exception as e:
#                     print(f"Zoom {z} skipped: {e}")
#                     continue

                
#                 tile_list = [t for t in tile_list if 0 <= t.x < n and 0 <= t.y < n]

#                 for t in tile_list:
#                     try:
                        
#                         data, mask = cog.tile(t.x, t.y, t.z)
#                         if data is None:
#                             continue
#                         img = np.moveaxis(data, 0, 2)
#                         img = (img * 255).astype(np.uint8) if img.max() <= 1 else img
#                         pil_img = Image.fromarray(img)

#                         tile_path = os.path.join(tiles_dir, str(z), str(t.x))
#                         os.makedirs(tile_path, exist_ok=True)
#                         pil_img.save(os.path.join(tile_path, f"{t.y}.png"))
#                     except Exception as e:
#                         print(f"Tile x={t.x}, y={t.y}, z={t.z} skipped: {e}")

        
#         s3_tile_prefix = f"tiles/pixelwise_yearly_analysis/{project_id}/{uc_safe}"
#         for root, dirs, files in os.walk(tiles_dir):
#             for fname in files:
#                 if fname.lower().endswith(".png"):
#                     full_path = os.path.join(root, fname)
#                     rel_path = os.path.relpath(full_path, tiles_dir).replace(os.sep, "/")
#                     s3_key = f"{s3_tile_prefix}/{rel_path}"
#                     s3_client.upload_file(full_path, bucket_name, s3_key)

        
#         tile_url_template = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{s3_tile_prefix}/{{z}}/{{x}}/{{y}}.png"

        
#         if os.path.exists(local_dir):
#             shutil.rmtree(local_dir)

#         YearlyAnalysis.objects.update_or_create(
#         project_id=project_id,
#         analysis_type=analysis_type,
#         year=year,
#         area_type=area_type,
#         uc_name=uc_name,
#         is_pixelwise=is_pixelwise,
#         defaults={
#             "city_name": city_name,
#             "stats": stats,
#             "tile_url_template": tile_url_template
#         })

#         return {
#             "uc_name": uc_name,
#             "city_name": city_name,
#             "error": "0",
#             "tile_url_template": tile_url_template
#         }

#     except Exception as e:
#         if os.path.exists(local_dir):
#             shutil.rmtree(local_dir)
#         return {
#             "uc_name": uc_name,
#             "city_name": city_name,
#             "error": "1",
#             "error_msg": str(e),
#             "tile_url_template": None
#         }

def save_yearly_analysis(
    polygon, start_date, end_date, image, vis_params,
    project_id, analysis_type, year, area_type,
    uc_name, city_name, stats, is_pixelwise=False
):
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    
    uc_safe = re.sub(r"[^\w\-]", "_", uc_name)
    local_dir = os.path.join(settings.MEDIA_ROOT, "temp_exports", "yearly_analysis", str(project_id), uc_safe)
    os.makedirs(local_dir, exist_ok=True)

    local_tif = os.path.join(local_dir, f"{analysis_type}_{start_date}_{end_date}.tif")
    tiles_dir = os.path.join(local_dir, "tiles")

    try:
        
        area_sq_m = polygon.area().getInfo()
        default_scales = {"ndvi": 10, "thermal": 100, "aqi": 7000}
        scale = default_scales.get(analysis_type.lower(), 10)
                
        

        
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
            scale = max(1, int(area_sq_m ** 0.5))
            
            
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
                if "Total request size" in error_msg or "50331648 bytes" in error_msg:
                    
                    scale = min(int(scale * 2), 200)
                    print(f"⚠️ Export too large, retrying with scale={scale}")
                else:
                    print(f"❌ Export failed: {error_msg}")
                    break

        if not export_success:
            print(f"[DEBUG] Creating placeholder tile for UC={uc_name}")
            placeholder_image = ee.Image.constant(0).visualize(min=0, max=1, palette=['000000'])
            geemap.ee_export_image(
                placeholder_image,
                filename=local_tif,
                scale=100,
                file_per_band=False,
                crs="EPSG:3857"
            )
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
                        pil_img = Image.fromarray(img)
                        tile_path = os.path.join(tiles_dir, str(z), str(t.x))
                        os.makedirs(tile_path, exist_ok=True)
                        pil_img.save(os.path.join(tile_path, f"{t.y}.png"))
                    except Exception as e:
                        print(f"Tile x={t.x}, y={t.y}, z={t.z} skipped: {e}")

        
        s3_tile_prefix = f"tiles/pixelwise_yearly_analysis/{project_id}/{uc_safe}"
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

        YearlyAnalysis.objects.update_or_create(
            project_id=project_id,
            analysis_type=analysis_type,
            year=year,
            area_type=area_type,
            uc_name=uc_name,
            is_pixelwise=is_pixelwise,
            defaults={
                "city_name": city_name,
                "stats": stats,
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
            "error_msg": str(e),
            "tile_url_template": None
        }

    
    
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def per_year_analysis(request):
    init_ee()

    analysis_type = request.data.get("analysis_type")
    year = request.data.get("year")
    area_type = request.data.get("area_type")
    project_id = request.data.get("project_id")
    mode = request.data.get("mode", "annual_stats")  
    geometry_data = request.data.get("geometry")

    if not all([analysis_type, year, area_type]):
        return Response({"error": "Missing required parameters"}, status=400)
    

    try:
        year = int(year)
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        results = []

        project = None
        city_name = None
        if area_type in ["uc", "kml"]:
            if not project_id:
                return Response({"error": "project_id is required for UC/KML analysis"}, status=400)
            project = Project.objects.filter(id=project_id).first()
            if not project:
                return Response({"error": "Project not found"}, status=404)
            city_name = project.location_name
            
        cached_results = get_yearly_analysis_from_db(
        project_id=project_id,
        analysis_type=analysis_type,
        year=year,
        area_type=area_type,
        is_pixelwise=(mode == "pixelwise")
    )

        if cached_results:
            return Response({
                "message": f"Cached {analysis_type.upper()} {mode} analysis for {year} returned",
                "year": year,
                "results": cached_results
            })

        
        features = []
        if area_type == "uc":
            uc_data = load_ucs_for_uc(city_name)
            if not uc_data:
                db_ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)
                features = [
                    {"geometry": json.loads(uc.geometry.geojson),
                     "properties": {"uc_name": uc.uc_name, "city_name": uc.city_name}}
                    for uc in db_ucs
                ]
            else:
                features = uc_data.get("features", [])
        elif area_type == "kml":
            kml_data = load_ucs_for_kml(project.id)

            if not kml_data and project.kml_file:
                with open(project.kml_file.path, "r", encoding="utf-8") as f:
                    polygon = kml_to_geosgeometry(f.read())

                db_ucs = UnionCouncil.objects.filter(geometry__intersects=polygon)

                features = [
                    {
                        "geometry": json.loads(uc.geometry.geojson),
                        "properties": {"uc_name": uc.uc_name, "city_name": uc.city_name}
                    }
                    for uc in db_ucs
                ]

            else:
                features = kml_data.get("features", [])

        elif area_type == "custom":
            if not geometry_data:
                return Response({"error": "geometry is required for custom analysis"}, status=400)
            geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
            features = [{"geometry": geom_json, "properties": {"uc_name": None, "city_name": None}}]
        else:
            return Response({"error": "Invalid area_type"}, status=400)

        
        def process_feature(feature):
            uc_name = feature["properties"].get("uc_name")
            city_name = feature["properties"].get("city_name")


            try:
                polygon = ee.Geometry(feature["geometry"])

                if mode == "annual_stats":
                    result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)
                    stats = result.get("stats")
                    
                    YearlyAnalysis.objects.update_or_create(
                    project_id=project_id,
                    analysis_type=analysis_type,
                    year=year,
                    area_type=area_type,
                    uc_name=uc_name,
                    is_pixelwise=False,
                    defaults={
                        "city_name": city_name,
                        "stats": stats,
                        "tile_url_template": None
                    })
                    return {
                        "uc_name": uc_name, "city_name": city_name, "mode": "annual_stats",
                         "stats": stats
                    }

                else:  
                    image, vis_params = run_pixelwise_analysis(analysis_type, polygon, start_date, end_date)
                    data = save_yearly_analysis(
                            polygon, start_date, end_date, image, vis_params,
                            project_id, analysis_type, year, area_type,
                            uc_name, city_name, {}, is_pixelwise=True
                        )
                    return {
                        "uc_name": uc_name, "city_name": city_name,
                        "mode": "pixelwise", "tile_url_template" : data.get("tile_url_template")
                    }

            except Exception as e:
                return {"uc_name": uc_name, "city_name": city_name,
                        "error": "1", "error_msg": str(e)}

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(process_feature, features))

        return Response({
            "message": f"{analysis_type.upper()} {mode} analysis for {year} performed",
            "year": year,
            "results": results
        })

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
    
  

def run_before_after_analysis(project_id, analysis_type, before_year, after_year, area_type, features):
    
    def process_feature(feature):
        uc_name = feature.get("uc_name")
        city_name = feature.get("city_name")
        try:
            geojson_dict = feature.get("geometry")
            polygon = ee.Geometry(geojson_dict) if geojson_dict else None

            start_before, end_before = f"{before_year}-01-01", f"{before_year}-12-31"
            start_after, end_after = f"{after_year}-01-01", f"{after_year}-12-31"

            before_result = perform_analysis_for_polygon(analysis_type, polygon, start_before, end_before) if polygon else {}
            after_result = perform_analysis_for_polygon(analysis_type, polygon, start_after, end_after) if polygon else {}

            before_mean = before_result.get("stats", {}).get("mean")
            after_mean = after_result.get("stats", {}).get("mean")
            if before_mean is not None and after_mean is not None:
                if after_mean > before_mean:
                    status = "increase"
                elif after_mean < before_mean:
                    status = "decrease"
                else:
                    status = "no_change"
            else:
                status = "no_data"

            return {
                "uc_name": uc_name,
                "city_name": city_name,
                "comparison": {
                    "status": status,
                    "before_mean": before_mean,
                    "after_mean": after_mean
                }
            }

        except Exception as e:
            return {
                "uc_name": uc_name,
                "city_name": city_name,
                "comparison": {
                    "status": "no_data",
                    "before_mean": None,
                    "after_mean": None
                },
                "error_msg": str(e)
            }

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(process_feature, features))

    return results


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

    
    results = []

    for feature in features:
        uc_name = feature.get("uc_name")

        existing = BeforeAfterAnalysis.objects.filter(
            project_id=project_id,
            analysis_type=analysis_type,
            area_type=area_type,
            uc_name=uc_name,
            before_year=before_year,
            after_year=after_year
        ).first()

        if existing:
            results.append({
                "uc_name": uc_name,
                "city_name": existing.city_name,
                "comparison": existing.comparison
            })
        else:
            
            res = run_before_after_analysis(
                project_id, analysis_type, before_year, after_year, area_type, [feature]
            )[0]

            
            BeforeAfterAnalysis.objects.update_or_create(
                project_id=project_id,
                analysis_type=analysis_type,
                area_type=area_type,
                uc_name=uc_name,
                before_year=before_year,
                after_year=after_year,
                defaults={
                    "city_name": res.get("city_name"),
                    "stats_before": {"mean": res["comparison"].get("before_mean")},
                    "stats_after": {"mean": res["comparison"].get("after_mean")},
                    "comparison": res["comparison"]
                }
            )

            results.append(res)

    
    before_values, after_values = [], []
    change_counts = {"increase": 0, "decrease": 0, "no_change": 0}

    for r in results:
        before_mean = r["comparison"].get("before_mean")
        after_mean = r["comparison"].get("after_mean")
        status = r["comparison"].get("status")
        if before_mean is not None and after_mean is not None:
            before_values.append(before_mean)
            after_values.append(after_mean)
            if status in change_counts:
                change_counts[status] += 1

    summary_stats = {
        "before": {
            "mean": round(sum(before_values)/len(before_values), 4) if before_values else None,
            "min": round(min(before_values), 4) if before_values else None,
            "max": round(max(before_values), 4) if before_values else None
        },
        "after": {
            "mean": round(sum(after_values)/len(after_values), 4) if after_values else None,
            "min": round(min(after_values), 4) if after_values else None,
            "max": round(max(after_values), 4) if after_values else None
        },
        "changes": change_counts,
        "total": len(before_values)
    }

    
    return Response({
        "mode": "before_after_comparison",
        "analysis_type": analysis_type,
        "before_year": before_year,
        "after_year": after_year,
        "results": results,
        "summary_stats": summary_stats
    })
    


def run_before_after_pixelwise(project_id, analysis_type, before_year, after_year, area_type, features):
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME

    def process_feature(feature):
        uc_name = feature.get("uc_name")
        uc_safe = re.sub(r"[^\w\-]", "_", uc_name)
        city_name = feature.get("city_name")
        geojson_dict = feature.get("geometry")
        polygon = ee.Geometry(geojson_dict) if geojson_dict else None

        cached = BeforeAfterPixelwise.objects.filter(
            project_id=project_id,
            analysis_type=analysis_type,
            area_type=area_type,
            uc_name=uc_name,
            before_year=before_year,
            after_year=after_year
        ).first()

        if cached:
            return {
                "uc_name": uc_name,
                "city_name": city_name,
                "tile_url_template_before": cached.tile_url_template_before,
                "tile_url_template_after": cached.tile_url_template_after,
            }

        try:
            if polygon:
                area_sq_m = polygon.area().getInfo()
                default_scales = {"ndvi": 10, "thermal": 100, "aqi": 7000}
                scale = default_scales.get(analysis_type.lower(), 10)
                if area_sq_m > 1e9:          
                    scale = max(scale, 60)
                elif area_sq_m > 5e8:        
                    scale = max(scale, 40)
                elif area_sq_m > 1e8:        
                    scale = max(scale, 20)              
                                                        
                if area_sq_m < (scale ** 2):
                    scale = max(int(area_sq_m ** 0.5), 1)
                if analysis_type.lower() == "ndvi" and area_sq_m < 1e4:
                    scale = max(scale, 20)
                if area_sq_m < 100:
                    return {
                        "uc_name": uc_name,
                        "city_name": city_name,
                        "error": "1",
                        "error_msg": "Polygon too small for analysis",
                        "tile_url_template_before": None
                    }

                
                local_dir1 = os.path.join(settings.MEDIA_ROOT, "temp_exports", "pixelwise", "before_year", str(project_id), uc_safe)
                os.makedirs(local_dir1, exist_ok=True)
                local_tif1 = os.path.join(local_dir1, f"{analysis_type}_{before_year}.tif")
                tiles_dir1 = os.path.join(local_dir1, "tiles")

                before_image, before_vis = run_pixelwise_analysis(
                    analysis_type, polygon, f"{before_year}-01-01", f"{before_year}-12-31"
                )

                vis_image1 = before_image.visualize(
                    min=before_vis.get("min"),
                    max=before_vis.get("max"),
                    palette=before_vis.get("palette")
                )

                export_success = False
                attempt = 0
                max_attempts = 4

                while not export_success and attempt < max_attempts:
                    try:
                        attempt += 1
                        print(f"Export attempt {attempt} at scale={scale} meters/pixel")

                        geemap.ee_export_image(
                            vis_image1,
                            filename=local_tif1,
                            scale=scale,
                            file_per_band=False,
                            crs="EPSG:3857"
                        )

                        if os.path.exists(local_tif1) and os.path.getsize(local_tif1) > 0:
                            export_success = True
                        else:
                            raise Exception("Export produced empty or missing file")

                    except Exception as e:
                        error_msg = str(e)
                        if "Total request size" in error_msg or "50331648 bytes" in error_msg:
                            
                            scale = min(int(scale * 2), 200)
                            print(f"⚠️ Export too large, retrying with scale={scale}")
                        else:
                            print(f"❌ Export failed: {error_msg}")
                            break

                if not export_success:
                    return {
                        "uc_name": uc_name,
                        "city_name": city_name,
                        "error": "1",
                        "error_msg": f"Export failed after {attempt} attempts (last scale={scale})",
                        "tile_url_template": None
                    }

                with rasterio.open(local_tif1, "r+") as src:
                    width, height = src.width, src.height
                    factors = [2, 4, 8, 16]
                    valid_factors = [f for f in factors if f < min(width, height)]
                    if valid_factors:
                        src.build_overviews(valid_factors, Resampling.nearest)
                        src.update_tags(ns="rio_overview", resampling="nearest")

                if os.path.exists(tiles_dir1):
                    shutil.rmtree(tiles_dir1)
                os.makedirs(tiles_dir1, exist_ok=True)

                with COGReader(local_tif1) as cog:
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
                                pil_img = Image.fromarray(img)

                                tile_path = os.path.join(tiles_dir1, str(z), str(t.x))
                                os.makedirs(tile_path, exist_ok=True)
                                pil_img.save(os.path.join(tile_path, f"{t.y}.png"))
                            except Exception as e:
                                print(f"Tile x={t.x}, y={t.y}, z={t.z} skipped: {e}")

                s3_tile_prefix = f"tiles/pixelwise_comparison/before_year/{project_id}/{uc_safe}"
                for root, _, files in os.walk(tiles_dir1):
                    for fname in files:
                        if fname.lower().endswith(".png"):
                            full_path = os.path.join(root, fname)
                            rel_path = os.path.relpath(full_path, tiles_dir1).replace(os.sep, "/")
                            s3_key = f"{s3_tile_prefix}/{rel_path}"
                            s3_client.upload_file(full_path, bucket_name, s3_key)

                tile_url_template_before = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{s3_tile_prefix}/{{z}}/{{x}}/{{y}}.png"

                if os.path.exists(local_dir1):
                    shutil.rmtree(local_dir1)

                
                local_dir2 = os.path.join(settings.MEDIA_ROOT, "temp_exports", "pixelwise", "after_year", str(project_id), uc_safe)
                os.makedirs(local_dir2, exist_ok=True)
                local_tif2 = os.path.join(local_dir2, f"{analysis_type}_{after_year}.tif")
                tiles_dir2 = os.path.join(local_dir2, "tiles")

                after_image, after_vis = run_pixelwise_analysis(
                    analysis_type, polygon, f"{after_year}-01-01", f"{after_year}-12-31"
                )

                vis_image2 = after_image.visualize(
                    min=after_vis.get("min"),
                    max=after_vis.get("max"),
                    palette=after_vis.get("palette")
                )
                
                export_success = False
                attempt = 0
                max_attempts = 4

                while not export_success and attempt < max_attempts:
                    try:
                        attempt += 1
                        print(f"Export attempt {attempt} at scale={scale} meters/pixel")

                        geemap.ee_export_image(
                            vis_image2,
                            filename=local_tif2,
                            scale=scale,
                            file_per_band=False,
                            crs="EPSG:3857"
                        )

                        if os.path.exists(local_tif2) and os.path.getsize(local_tif2) > 0:
                            export_success = True
                        else:
                            raise Exception("Export produced empty or missing file")

                    except Exception as e:
                        error_msg = str(e)
                        if "Total request size" in error_msg or "50331648 bytes" in error_msg:
                            
                            scale = min(int(scale * 2), 200)
                            print(f"⚠️ Export too large, retrying with scale={scale}")
                        else:
                            print(f"❌ Export failed: {error_msg}")
                            break

                if not export_success:
                    return {
                        "uc_name": uc_name,
                        "city_name": city_name,
                        "error": "1",
                        "error_msg": f"Export failed after {attempt} attempts (last scale={scale})",
                        "tile_url_template": None
                    }


                with rasterio.open(local_tif2, "r+") as src:
                    width, height = src.width, src.height
                    factors = [2, 4, 8, 16]
                    valid_factors = [f for f in factors if f < min(width, height)]
                    if valid_factors:
                        src.build_overviews(valid_factors, Resampling.nearest)
                        src.update_tags(ns="rio_overview", resampling="nearest")

                if os.path.exists(tiles_dir2):
                    shutil.rmtree(tiles_dir2)
                os.makedirs(tiles_dir2, exist_ok=True)

                with COGReader(local_tif2) as cog:
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
                                pil_img = Image.fromarray(img)

                                tile_path = os.path.join(tiles_dir2, str(z), str(t.x))
                                os.makedirs(tile_path, exist_ok=True)
                                pil_img.save(os.path.join(tile_path, f"{t.y}.png"))
                            except Exception as e:
                                print(f"Tile x={t.x}, y={t.y}, z={t.z} skipped: {e}")

                s3_tile_prefix = f"tiles/pixelwise_comparison/after_year/{project_id}/{uc_safe}"
                for root, _, files in os.walk(tiles_dir2):
                    for fname in files:
                        if fname.lower().endswith(".png"):
                            full_path = os.path.join(root, fname)
                            rel_path = os.path.relpath(full_path, tiles_dir2).replace(os.sep, "/")
                            s3_key = f"{s3_tile_prefix}/{rel_path}"
                            s3_client.upload_file(full_path, bucket_name, s3_key)

                tile_url_template_after = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{s3_tile_prefix}/{{z}}/{{x}}/{{y}}.png"

                if os.path.exists(local_dir2):
                    shutil.rmtree(local_dir2)

                
                BeforeAfterPixelwise.objects.update_or_create(
                    project_id=project_id,
                    analysis_type=analysis_type,
                    area_type=area_type,
                    uc_name=uc_name,
                    before_year=before_year,
                    after_year=after_year,
                    defaults={
                        "city_name": city_name,
                        "tile_url_template_before": tile_url_template_before,
                        "tile_url_template_after": tile_url_template_after
                    }
                )

                return {
                    "uc_name": uc_name,
                    "city_name": city_name,
                    "tile_url_template_before": tile_url_template_before,
                    "tile_url_template_after": tile_url_template_after
                }

        except Exception as e:
            return {
                "uc_name": uc_name,
                "city_name": city_name,
                "error": "1",
                "error_msg": str(e),
                "tile_url_template_before": None,
                "tile_url_template_after": None
            }

    
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(process_feature, features))

    return results


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

    results = run_before_after_pixelwise(
        project_id, analysis_type, before_year, after_year, area_type, features
    )

    return Response({
        "mode": "before_after_comparison_pixelwise",
        "analysis_type": analysis_type,
        "before_year": before_year,
        "after_year": after_year,
        "results": results
    })