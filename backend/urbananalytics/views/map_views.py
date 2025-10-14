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

# from rio_tiler.utils import tile_read

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

def init_ee():
    """Initialize Earth Engine lazily when needed."""
    if ee.data._initialized:
        return

    # Use .env path first (recommended)
    service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if not service_account_path or not os.path.exists(service_account_path):
        # Fallback to local file if env variable not found
        service_account_path = os.path.join(settings.BASE_DIR, "service_account.json")

    # Read service account info/
    with open(service_account_path) as f:
        import json
        service_account_info = json.load(f)
        service_account_email = service_account_info["client_email"]

    credentials = ee.ServiceAccountCredentials(service_account_email, key_file=service_account_path)

    try:
        ee.Initialize(credentials, project="urbananalytics-460415")
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
                          "palette": ["#E7E0E0", "#FFFF00", "#90EE90", "#008000", "#006400"]}
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
        if analysis_type.lower() == "thermal":
            if mean_value < 295:
                color = "#87CEEB"  
            elif 295 <= mean_value < 300:
                color = "#32CD32"  
            elif 300 <= mean_value < 305:
                color = "#FF6347"  
            elif 305 <= mean_value < 310:
                color = "#FFA500"  
            else:
                color = "#800080"  
        elif analysis_type.lower() == "aqi":
            if mean_value < 5:
                color = "#FFC0CB"  
            elif mean_value < 10:
                color = "#FF7F50"  
            elif mean_value < 15:
                color = "#FFBF00"  
            elif mean_value < 20:
                color = "#FFFFE0"  
            elif mean_value < 25:
                color = "#FF00FF"  
            else:
                color = "#8A2BE2"  
        elif analysis_type.lower() == "ndvi":
            
            if mean_value < 0.2:
                color = "#E7E0E0"
            elif mean_value < 0.4:
                color = "#FFFF00"  
            elif mean_value < 0.6:
                color = "#90EE90"  
            elif mean_value < 0.8:
                color = "#008000"  
            else:
                color = "#006400"  
        else:
            
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

            local_tif = os.path.join(local_dir, f"{analysis_type}{start_date}{end_date}.tif")
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

            local_tif = os.path.join(custom_dir, f"{analysis_type}{start_date}{end_date}.tif")
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
    mode = request.data.get("mode", "pixelwise")  # default: pixelwise

    # -------------------------
    # Basic input validation
    # -------------------------
    if not all([analysis_type, year, area_type]):
        return Response({"error": "Missing required parameters"}, status=400)
    

    try:
        current_year = datetime.now().year
        current_month = datetime.now().strftime("%B %Y")
        selected_year = int(year)
        note = None

        # ⚠️ Block future years
        if selected_year > current_year:
            return Response({
                "error": f"Future year {selected_year} cannot be analyzed yet.",
                "message": f"Data for {selected_year} will be available once the year begins."
            }, status=400)

        # ⚠️ Add note for ongoing year
        elif selected_year == current_year:
            note = f"⚠️ Data for {selected_year} includes satellite observations available up to {current_month} only."

        project = Project.objects.get(id=project_id) if project_id else None
        results = []
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME

        # -------------------------
        # Load features (UCs / KML)
        # -------------------------
        features = []
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
            cache_file = os.path.join(settings.BASE_DIR, "local_data", f"project_{project.id}_kml_ucs.json")
            if os.path.exists(cache_file):
                with open(cache_file, "r") as f:
                    kml_data = json.load(f)
                features = kml_data.get("features", [])

        if not features and area_type != "custom":
            return Response({"error": "No features found for analysis"}, status=404)

        # -------------------------
        # Cached results check
        # -------------------------
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
                else:  # pixelwise
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

        # -------------------------
        # Annual Stats Mode
        # -------------------------
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

                    if analysis_type.lower() == "ndvi":
                        mean_value = max(0, min(1, mean_value))
                    elif analysis_type.lower() == "thermal":
                        mean_value = max(290, min(320, mean_value))
                    elif analysis_type.lower() == "aqi":
                        mean_value = max(0, min(30, mean_value))

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

        # -------------------------
        # Pixelwise Mode
        # -------------------------
        elif mode == "pixelwise":
            def process_feature(feature):
                uc_name = feature["properties"].get("uc_name", "custom_uc")
                city_name = feature["properties"].get("city_name", project.location_name if project else "unknown")
                uc_safe = re.sub(r"[^\w\-]", "_", uc_name)
                local_dir = os.path.join(settings.MEDIA_ROOT, "temp_exports", "pixelwise", str(project_id), uc_safe)
                os.makedirs(local_dir, exist_ok=True)
                local_tif = os.path.join(local_dir, f"{analysis_type}_{selected_year}.tif")
                tiles_dir = os.path.join(local_dir, "tiles")

                try:
                    # 🔹 Check for cached result first
                    cached_pixel = YearlyAnalysis.objects.filter(
                        project_id=project_id,
                        analysis_type=analysis_type,
                        year=selected_year,
                        area_type=area_type,
                        uc_name=uc_name,
                        is_pixelwise=True
                    ).first()
                    if cached_pixel and cached_pixel.tile_url_template:
                        return {
                            "uc_name": uc_name,
                            "city_name": city_name,
                            "tile_url_template": cached_pixel.tile_url_template,
                            "error": "0"
                        }

                    polygon = ee.Geometry(feature["geometry"])

                    # 🔹 Run main GEE analysis
                    image, vis_params, scale = run_pixelwise_analysis(
                        analysis_type, polygon, f"{selected_year}-01-01", f"{selected_year}-12-31"
                    )
                    if not image:
                        raise ValueError("No image generated")

                    # 🔹 Check if there are valid pixels before export
                    pixel_count = image.reduceRegion(
                        reducer=ee.Reducer.count(),
                        geometry=polygon,
                        scale=scale,
                        maxPixels=1e13
                    ).getInfo()
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

                    # 🔹 Retry export if it fails
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
                            if "Total request size" in error_msg or "50331648 bytes" in error_msg:
                                scale = min(int(scale * 2), 200)
                                print(f"Export too large, retrying with scale={scale}")
                            elif "Network" in error_msg or "getaddrinfo" in error_msg:
                                print(f"Network issue — retrying after 5s...")
                                time.sleep(5)
                            else:
                                print(f"Export failed: {error_msg}")
                                break

                    if not export_success:
                        return {
                            "uc_name": uc_name,
                            "city_name": city_name,
                            "error": "1",
                            "error_msg": f"Export failed after {attempt} attempts.",
                            "tile_url_template": None
                        }

                    # 🔹 Build overviews for efficient tiling
                    with rasterio.open(local_tif, "r+") as src:
                        factors = [2, 4, 8, 16]
                        valid_factors = [f for f in factors if f < min(src.width, src.height)]
                        if valid_factors:
                            src.build_overviews(valid_factors, Resampling.nearest)
                            src.update_tags(ns="rio_overview", resampling="nearest")

                    # 🔹 Prepare tile directory
                    if os.path.exists(tiles_dir):
                        shutil.rmtree(tiles_dir)
                    os.makedirs(tiles_dir, exist_ok=True)

                    # 🔹 Dynamic zoom based on scale
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

                    # 🔹 Upload to S3
                    s3_prefix = f"tiles/yearly_pixelwise/{project_id}/{analysis_type}/{year}/{uc_safe}"
                    for root, dirs, files in os.walk(tiles_dir):
                        for fname in files:
                            if fname.lower().endswith(".png"):
                                full_path = os.path.join(root, fname)
                                rel_path = os.path.relpath(full_path, tiles_dir).replace(os.sep, "/")
                                s3_key = f"{s3_prefix}/{rel_path}"
                                s3_client.upload_file(full_path, bucket_name, s3_key)

                    tile_url_template = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{s3_prefix}/{{z}}/{{x}}/{{y}}.png"

                    # 🔹 Clean up
                    if os.path.exists(local_dir):
                        shutil.rmtree(local_dir)

                    # 🔹 Save in DB
                    YearlyAnalysis.objects.update_or_create(
                        project_id=project_id,
                        analysis_type=analysis_type,
                        year=selected_year,
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
                        "error_msg": str(e)
                    }

            # Run analysis in parallel
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

    # ---------------- Determine features ---------------- #
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

    # ---------------- Check cached data ---------------- #
    cached_data = BeforeAfterAnalysis.objects.filter(
        project_id=project_id,
        analysis_type=analysis_type,
        area_type=area_type,
        before_year=before_year,
        after_year=after_year
    )

    cached_map = {c.uc_name: c for c in cached_data}

    # ---------------- Main computation ---------------- #
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

            # Clamp values for safety
            if analysis_type.lower() == "ndvi":
                before_mean = max(0, min(1, before_mean or 0))
                after_mean = max(0, min(1, after_mean or 0))
            elif analysis_type.lower() == "thermal":
                before_mean = max(290, min(320, before_mean or 290))
                after_mean = max(290, min(320, after_mean or 290))
            elif analysis_type.lower() == "aqi":
                before_mean = max(0, min(30, before_mean or 0))
                after_mean = max(0, min(30, after_mean or 0))

            # Determine change status
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

    # ---------------- Run multithreaded ---------------- #
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_feature, f) for f in features]
        for future in as_completed(futures):
            results.append(future.result())

    # ---------------- Summary stats ---------------- #
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
    """
    Pixelwise before-after comparison (NDVI / Thermal / AQI).
    For each UC/KML feature:
      - runs GEE analysis for both years,
      - generates PNG tiles,
      - uploads to S3,
      - caches results in BeforeAfterPixelwise.
    """
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

    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    s3_domain = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}"

    # ---------------- Helper: process one feature ---------------- #
    def process_feature(feature):
        uc_name = feature.get("uc_name")
        uc_safe = re.sub(r"[^\w\-]", "_", uc_name)
        city_name = feature.get("city_name")
        uc_safe = re.sub(r"[^\w\-]", "_", uc_name or "custom")

        # Check DB cache
        cached = BeforeAfterPixelwise.objects.filter(
            project_id=project_id,
            analysis_type=analysis_type,
            area_type=area_type,
            uc_name=uc_name,
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

        try:
            polygon = ee.Geometry(feature.get("geometry"))

            # Run pixelwise analysis for both years
            before_image, before_vis, before_scale = run_pixelwise_analysis(
                analysis_type, polygon, f"{before_year}-01-01", f"{before_year}-12-31"
            )
            after_image, after_vis, after_scale = run_pixelwise_analysis(
                analysis_type, polygon, f"{after_year}-01-01", f"{after_year}-12-31"
            )

            # Helper for exporting each year's image
            def export_to_s3(image, vis_params, year_label, scale):
                local_dir = os.path.join(
                    settings.MEDIA_ROOT, "temp_exports", "before_after_pixelwise",
                    str(project_id), uc_safe, str(year_label)
                )
                os.makedirs(local_dir, exist_ok=True)
                local_tif = os.path.join(local_dir, f"{analysis_type}_{year_label}.tif")
                tiles_dir = os.path.join(local_dir, "tiles")

                # Check valid pixels
                pixel_count = image.reduceRegion(
                    reducer=ee.Reducer.count(),
                    geometry=polygon,
                    scale=scale,
                    maxPixels=1e13
                ).getInfo()
                if not pixel_count or all(v == 0 for v in pixel_count.values()):
                    raise Exception("Export failed: No valid pixels found.")

                vis_image = image.visualize(
                    min=vis_params.get("min"),
                    max=vis_params.get("max"),
                    palette=vis_params.get("palette")
                )

                # Retry export
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
                        if "Total request size" in err or "50331648 bytes" in err:
                            scale = min(int(scale * 2), 200)
                            print(f"Retrying with larger scale={scale}")
                        elif "Network" in err or "getaddrinfo" in err:
                            time.sleep(5)
                        else:
                            print(f"Export failed: {err}")
                            break

                if not export_success:
                    raise Exception(f"Export failed after {attempt} attempts")

                # Build overviews
                with rasterio.open(local_tif, "r+") as src:
                    factors = [2, 4, 8, 16]
                    valid_factors = [f for f in factors if f < min(src.width, src.height)]
                    if valid_factors:
                        src.build_overviews(valid_factors, Resampling.nearest)
                        src.update_tags(ns="rio_overview", resampling="nearest")

                if os.path.exists(tiles_dir):
                    shutil.rmtree(tiles_dir)
                os.makedirs(tiles_dir, exist_ok=True)

                # Generate PNG tiles
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

                # Upload PNG tiles to S3
                s3_prefix = f"tiles/2-year comparison/{project_id}/{analysis_type}/{year_label}/{uc_safe}"
                for root, dirs, files in os.walk(tiles_dir):
                    for fname in files:
                        if fname.lower().endswith(".png"):
                            full_path = os.path.join(root, fname)
                            rel_path = os.path.relpath(full_path, tiles_dir).replace(os.sep, "/")
                            s3_key = f"{s3_prefix}/{rel_path}"
                            s3_client.upload_file(full_path, bucket_name, s3_key)

                # Cleanup local
                if os.path.exists(local_dir):
                    shutil.rmtree(local_dir)

                return f"{s3_domain}/{s3_prefix}/{{z}}/{{x}}/{{y}}.png"

            # Export both years
            tile_url_before = export_to_s3(before_image, before_vis, before_year, before_scale)
            tile_url_after = export_to_s3(after_image, after_vis, after_year, after_scale)

            # Save to DB
            BeforeAfterPixelwise.objects.update_or_create(
                project_id=project_id,
                analysis_type=analysis_type,
                area_type=area_type,
                uc_name=uc_name,
                before_year=before_year,
                after_year=after_year,
                defaults={
                    "city_name": city_name,
                    "tile_url_before": tile_url_before,
                    "tile_url_after": tile_url_after
                }
            )

            return {
                "uc_name": uc_name,
                "city_name": city_name,
                "tile_url_before": tile_url_before,
                "tile_url_after": tile_url_after,
                "error": "0"
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

    # ---------------- Run multithreaded ---------------- #
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
