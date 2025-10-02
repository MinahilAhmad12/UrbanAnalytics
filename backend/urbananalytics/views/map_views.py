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
from urbananalytics.utils import extract_bounds_from_kml
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
from dateutil.relativedelta import relativedelta
import fastkml
from shapely.geometry import shape, mapping
import os
from django.conf import settings
from urbananalytics.utils import extract_bounds_from_kml
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
def perform_gee_analysis(request):
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
                is_pixelwise=False
            ).order_by('uc_name')  

            if cached_results.exists():
                for cached in cached_results:

                    results.append({
                        "uc_name": cached.uc_name,
                        "city_name": cached.city_name,
                        "cog_https_url": cached.cog_https_url,
                        "stats": cached.stats,
                        "area_type": cached.area_type
                    })

                return Response({
                    "message": f"Cached {analysis_type.upper()} analysis returned",
                    "results": results
                })
        
        def process_uc(feature, project_id, analysis_type, start_date, end_date, bucket_name):
            uc_name = feature["properties"].get("uc_name", "unknown_uc")
            city_name = feature["properties"].get("city_name", "unknown_city")

            uc_name_safe = re.sub(r"[^\w\-]", "_", uc_name)
            local_dir = os.path.join(settings.MEDIA_ROOT, "temp_exports", "average", str(project_id), uc_name_safe)
            os.makedirs(local_dir, exist_ok=True)
            
            
            local_tif = os.path.join(local_dir, f"{analysis_type}_{start_date}_{end_date}.tif")
            local_cog = os.path.join(local_dir, f"{analysis_type}_{start_date}_{end_date}_cog.tif")

            try:
                polygon = ee.Geometry(feature["geometry"])
                result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)

                if not result or "image" not in result or result["image"] is None:
                    return {
                        "uc_name": uc_name,
                        "city_name": city_name,
                        "error": "1",
                        "error_msg": "No image generated for this UC",
                        "cog_https_url": None,
                        "stats": {}
                    }

                area_sq_m = polygon.area().getInfo()
                base_scale = result.get("scale", 10)
                scale = base_scale * 5 if area_sq_m > 1e8 else base_scale * 3 if area_sq_m > 5e7 else base_scale

                
                geemap.ee_export_image(
                    result["image"],
                    filename=local_tif,
                    scale=scale,
                    file_per_band=False,
                    crs="EPSG:3857"
                )

                profile = cog_profiles.get("deflate")  

                dst_kwargs = profile.copy()
                dst_kwargs.update({
                    "blockxsize": 512,
                    "blockysize": 512,
                    "tiled": True,
                    "compress": "deflate",
                    "resampling": Resampling.nearest
                })

                with rasterio.open(local_tif, "r+") as src:
                    factors = [2, 4, 8, 16]
                    src.build_overviews(factors, Resampling.nearest)
                    src.update_tags(ns="rio_overview", resampling="nearest")

                
                cog_translate(
                    local_tif,
                    local_cog,
                    dst_kwargs=dst_kwargs,
                    in_memory=False,
                    quiet=False
                )
                            

            
                s3_file_key = f"average/{project_id}/{uc_name_safe}/{analysis_type}_{start_date}_{end_date}.tif"
                s3_client.upload_file(local_cog, settings.AWS_STORAGE_BUCKET_NAME, s3_file_key)
                cog_https_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{s3_file_key}"

                
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
                        "stats": result.get("stats") or {},
                        "is_pixelwise": False,
                        "cog_https_url": cog_https_url
                    }
                )

                return {
                    "uc_name": uc_name,
                    "city_name": city_name,
                    "error": "0",
                    "cog_https_url": cog_https_url,
                    "stats": result.get("stats") or {}
                }

            except Exception as e:
                if os.path.exists(local_dir):
                    shutil.rmtree(local_dir)
                return {
                    "uc_name": uc_name,
                    "city_name": city_name,
                    "error": "1",
                    "error_msg": str(e),
                    "cog_https_url": None,
                    "stats": {}
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

            results = []
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [
                    executor.submit(process_uc, f, project_id, analysis_type, start_date, end_date, bucket_name)
                    for f in features
                ]
                for future in futures:
                    results.append(future.result())

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
            results = []
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [
                    executor.submit(process_uc, f, project_id, analysis_type, start_date, end_date, bucket_name)
                    for f in features
                ]
                for future in futures:
                    results.append(future.result())

        elif area_type == "custom":
            if not geometry_data:
                return Response({"error": "geometry data is required for custom analysis"}, status=400)

            geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
            polygon = ee.Geometry(geom_json)
            result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)
            if not result or "image" not in result or result["image"] is None:
                    return Response({
                        "error": "No image generated for custom geometry"
                    }, status=400)

            local_dir = os.path.join(settings.MEDIA_ROOT, "temp_exports", "average", str(project_id), "custom")
            os.makedirs(local_dir, exist_ok=True)

            local_tif = os.path.join(local_dir, f"{analysis_type}_{start_date}_{end_date}.tif")
            local_cog = os.path.join(local_dir, f"{analysis_type}_{start_date}_{end_date}_cog.tif")

            
            geemap.ee_export_image(
                result["image"],
                filename=local_tif,
                scale=result.get("scale", 10),
                file_per_band=False,
                crs="EPSG:3857"
            )

            
            with rasterio.open(local_tif, "r+") as src:
                factors = [2, 4, 8, 16]
                src.build_overviews(factors, Resampling.nearest)
                src.update_tags(ns="rio_overview", resampling="nearest")

            
            profile = cog_profiles.get("deflate")
            dst_kwargs = profile.copy()
            dst_kwargs.update({
                "blockxsize": 512,
                "blockysize": 512,
                "tiled": True,
                "compress": "deflate",
                "resampling": Resampling.nearest
            })

            cog_translate(
                local_tif,
                local_cog,
                dst_kwargs=dst_kwargs,
                in_memory=False,
                quiet=False
            )

            s3_key = f"average/{project_id}/custom/{analysis_type}_{start_date}_{end_date}.tif"
            s3_client.upload_file(local_cog, bucket_name, s3_key)
            cog_https_url = f"https://{bucket_name}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{s3_key}"

            
            if os.path.exists(local_dir):
                shutil.rmtree(local_dir)

            
            AreaAnalysis.objects.update_or_create(
                project_id=project_id,
                analysis_type=analysis_type,
                start_date=start_date,
                end_date=end_date,
                area_type="custom",
                uc_name=None,
                defaults={
                    "city_name": None,
                    "stats": result.get("stats"),
                    "is_pixelwise": False,
                    "cog_https_url": cog_https_url
                }
            )

            results.append({
                "uc_name": None,
                "city_name": None,
                "cog_https_url": cog_https_url,
                "stats": result.get("stats"),
                "area_type": "custom",
                "error": "0"
            })
        return Response({
            "message": f"{analysis_type.upper()} analysis performed",
            "results": results
        })   
    except Exception as e:
        return Response({"error": "Failed to perform analysis", "details": str(e)}, status=500)


def perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date):
    init_ee()
    scale = 10
    try:
        
        if analysis_type.lower() == "ndvi":
            collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
                .filterBounds(polygon) \
                .filterDate(start_date, end_date) \
                .select(['B8', 'B4']) \
                .median()
            image = collection.normalizedDifference(['B8', 'B4']).rename('NDVI').clip(polygon)
            vis_params = {'min': 0, 'max': 1, "palette": ["white", "yellow", "lightgreen", "green", "darkgreen"]
    }
            band_name = 'NDVI'

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
                raise ValueError("No Landsat 8 or 9 images available for the selected date range and area")

            composite = collection.median()
            bands = composite.bandNames().getInfo()
            if 'ST_B10' not in bands:
                raise ValueError(f"Thermal band 'ST_B10' not found in image bands: {bands}")

            image = composite.select('ST_B10').multiply(0.00341802).add(149.0).rename('Thermal').clip(polygon)
            vis_params = {'min': 290, 'max': 320, "palette": ["Sky Blue", "Lime Green", "Tomato Red", "Orange", "Dark Purple"]
    }
            band_name = 'Thermal'
            scale = 100

        elif analysis_type.lower() == "aqi":
            
            collection = ee.ImageCollection('COPERNICUS/S5P/NRTI/L3_NO2') \
                .filterBounds(polygon) \
                .filterDate(start_date, end_date) \
                .median()
            image = collection.select('NO2_column_number_density').rename('AQI').multiply(1e5).clip(polygon)
            vis_params = {'min': 0, 'max': 30, "palette": ["Pink", "Coral", "Amber", "Light Yellow", "Magenta", "Violet"]
    }
            band_name = 'AQI'
            scale = 1000
        


        else:
            raise ValueError("Invalid analysis type")

        
        stats = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=polygon,
            scale=scale,
            maxPixels=1e9
        ).getInfo()

        mean_value = stats.get(band_name)

        if mean_value is not None:
            avg_image = ee.Image.constant(mean_value).clip(polygon).rename(band_name)
            vis_image = avg_image.visualize(**vis_params)
            status = "success"
        else:
            avg_image = ee.Image.constant(0).clip(polygon).rename("NoData")
            vis_image = avg_image.visualize(min=0, max=1, palette=["black"]) 
            status = "nodata"


        
        return {
            "image": vis_image,
            "raw_image": avg_image,
            "scale": scale,
            "stats": {
                "mean": mean_value,
                "status": status
    
            }
        }

    except Exception as e:
        
        avg_image = ee.Image.constant(0).clip(polygon).rename("NoData")
        vis_image = avg_image.visualize(min=0, max=1, palette=["black"])
        return {
            "image": vis_image,
            "raw_image": avg_image,
            "scale": scale,
            "stats": {
                "mean": None,
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
                        "cog_https_url": cached.cog_https_url,
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
            local_cog = os.path.join(local_dir, f"{analysis_type}_{start_date}_{end_date}_cog.tif")
            
            
            try:
                try:
                    geojson_dict = feature.get("geometry")
                    if not geojson_dict:
                        raise ValueError("Missing geometry")
                    polygon = ee.Geometry(geojson_dict)
                except Exception as e:
                    return {
                        "uc_name": uc_name,
                        "city_name": city_name,
                        "error": "1",
                        "error_msg": f"Invalid geometry: {str(e)}",
                        "cog_https_url": None
                    }
                image, vis_params = run_pixelwise_analysis(analysis_type, polygon, start_date, end_date)
                
                if not image:
                    return {
                        "uc_name": uc_name,
                        "city_name": city_name,
                        "error": "1",
                        "error_msg": "No image generated for this UC",
                        "cog_https_url": None
                    }

                
                area_sq_m = polygon.area().getInfo()
                scale = 10  
                if area_sq_m > 1e8:
                    scale *= 5
                elif area_sq_m > 5e7:
                    scale *= 3
                    
                print(f"Exporting UC: {uc_name}, Area: {area_sq_m:.0f} m², Scale: {scale}")
                
                vis_image = image.visualize(
                    min=vis_params.get("min"),
                    max=vis_params.get("max"),
                    palette=vis_params.get("palette")
                )
                try:
                    geemap.ee_export_image(
                        vis_image,
                        filename=local_tif,
                        scale=scale,
                        file_per_band=False,
                        crs="EPSG:3857"
                    )
                except Exception as e:
                    print(f"⚠️ First export failed for {uc_name}: {str(e)}. Retrying with coarser scale...")

                fallback_scale = max(50, scale * 5)
                geemap.ee_export_image(
                    vis_image,
                    filename=local_tif,
                    scale=fallback_scale,
                    file_per_band=False,
                    crs="EPSG:3857"
                )
                geemap.ee_export_image(
                    vis_image,
                    filename=local_tif,
                    scale=scale,
                    file_per_band=False,
                    crs="EPSG:3857"
                )
                with rasterio.open(local_tif, "r+") as src:
                    factors = [2, 4, 8, 16]
                    src.build_overviews(factors, Resampling.nearest)
                    src.update_tags(ns="rio_overview", resampling="nearest")

                profile = cog_profiles.get("deflate")
                dst_kwargs = profile.copy()
                dst_kwargs.update({
                    "blockxsize": 512,
                    "blockysize": 512,
                    "tiled": True,
                    "compress": "deflate",
                    "resampling": Resampling.nearest
                })

                cog_translate(local_tif, local_cog, dst_kwargs=dst_kwargs, in_memory=False, quiet=False)

                s3_file_key = f"pixelwise/{project_id}/{uc_safe}/{analysis_type}_{start_date}_{end_date}.tif"
                s3_client.upload_file(local_cog, bucket_name, s3_file_key)
                cog_https_url = f"https://{bucket_name}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{s3_file_key}"
                

                
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
                        "cog_https_url": cog_https_url,
                        "is_pixelwise": True
                    }
                )

                return {
                    "uc_name": uc_name,
                    "city_name": city_name,
                    "error": "0",
                    "cog_https_url": cog_https_url,
                }

            except Exception as e:
                if os.path.exists(local_dir):
                    shutil.rmtree(local_dir)
                return {
                    "uc_name": uc_name,
                    "city_name": city_name,
                    "error": "1",
                    "error_msg": str(e),
                    "cog_https_url": None
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
            image, vis_params = run_pixelwise_analysis(analysis_type, polygon, start_date, end_date)
            if not image:
                return Response({
                    "error": "1",
                    "error_msg": "No image generated for custom area",
                    "cog_https_url": None
                }, status=500)

            custom_dir = os.path.join(settings.MEDIA_ROOT, "temp_exports", "pixelwise", str(project_id))
            os.makedirs(custom_dir, exist_ok=True)
            local_tif = os.path.join(custom_dir, f"{analysis_type}_{start_date}_{end_date}.tif")
            local_cog = os.path.join(custom_dir, f"{analysis_type}_{start_date}_{end_date}_cog.tif")

            vis_image = image.visualize(
                    min=vis_params.get("min"),
                    max=vis_params.get("max"),
                    palette=vis_params.get("palette")
                )
            geemap.ee_export_image(
                vis_image,
                filename=local_tif,
                scale=10,
                file_per_band=False,
                crs="EPSG:3857"
            )
            with rasterio.open(local_tif, "r+") as src:
                factors = [2, 4, 8, 16]
                src.build_overviews(factors, Resampling.nearest)
                src.update_tags(ns="rio_overview", resampling="nearest")

            profile = cog_profiles.get("deflate")
            dst_kwargs = profile.copy()
            dst_kwargs.update({
                "blockxsize": 512,
                "blockysize": 512,
                "tiled": True,
                "compress": "deflate",
                "resampling": Resampling.nearest
            })

            cog_translate(local_tif, local_cog, dst_kwargs=dst_kwargs, in_memory=False, quiet=False)
            s3_file_key = f"pixelwise/{project_id}/custom/{analysis_type}_{start_date}_{end_date}.tif"
            s3_client.upload_file(local_cog, bucket_name, s3_file_key)
            cog_https_url = f"https://{bucket_name}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{s3_file_key}"
                
            
            if os.path.exists(custom_dir):
                shutil.rmtree(custom_dir)

            AreaAnalysis.objects.update_or_create(
                project_id=project_id,
                analysis_type=analysis_type,
                start_date=start_date,
                end_date=end_date,
                area_type="custom",
                defaults={
                    "city_name": None,
                    "cog_https_url": cog_https_url,
                    "is_pixelwise": True
                }
            )

            results.append({
                "uc_name": None,
                "city_name": None,
                "error": "0",
                "cog_https_url": cog_https_url,
                "area_type": "custom"
            })
            
            

        else:
            return Response({"error": "Invalid area_type"}, status=400)

        
        return Response({
            "message": f"{analysis_type.upper()} pixelwise analysis performed",
            "results": results
        })

    except Exception as e:
        return Response(
            {"error": "Failed to perform pixelwise analysis", "details": str(e)},
            status=500
        )

def run_pixelwise_analysis(analysis_type, polygon, start_date, end_date):
    init_ee()

    if analysis_type.lower() == "ndvi":
        collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterBounds(polygon).filterDate(start_date, end_date).select(['B8', 'B4'])
        image = collection.median().normalizedDifference(['B8', 'B4']).rename('NDVI').clip(polygon)
        
        vis_params = {
        'min': 0, 'max': 1,
        'palette': [
                "#A52A2A",  
                "#F4A460", 
                "#9ACD32",  
                "#90EE90",  
                "#008000",  
                "#006400"   
            ]
    }

    elif analysis_type.lower() == "thermal":
        collection = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2') \
            .filterBounds(polygon).filterDate(start_date, end_date).filter(ee.Filter.lt('CLOUD_COVER', 60))
        if collection.size().getInfo() == 0:
            collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
                .filterBounds(polygon).filterDate(start_date, end_date).filter(ee.Filter.lt('CLOUD_COVER', 60))
        composite = collection.median()
        image = composite.select('ST_B10').multiply(0.00341802).add(149.0).rename('Thermal').clip(polygon)
        
        vis_params = {
            'min': 290, 'max': 320,
            'palette': [
                "#00008B",  
                "#008080",  
                "#40E0D0",  
                "#2E8B57",  
                "#FFFDD0",  
                "#FF8C00"   
            ]
        }

    elif analysis_type.lower() == "aqi":
        collection = ee.ImageCollection('COPERNICUS/S5P/NRTI/L3_NO2') \
            .filterBounds(polygon).filterDate(start_date, end_date)
        image = collection.median().select('NO2_column_number_density').multiply(1e5).rename('AQI').clip(polygon)
        
        vis_params = {
            'min': 0, 'max': 50,
            'palette': [
                "#FFB6C1",  
                "#C8A2C8",  
                "#AFEEEE",  
                "#FA8072",  
                "#FFFFE0",  
                "#FFDAB9"   
            ]
        }

    else:
        raise ValueError("Invalid analysis type")

    return image, vis_params
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


    
def get_yearly_analysis_from_db(project_id, analysis_type, year, area_type, uc_name=None, is_pixelwise=False):
    """
    Fetch saved yearly analysis from DB + file storage if exists.
    """
    try:
        record = YearlyAnalysis.objects.get(
            project_id=project_id,
            analysis_type=analysis_type,
            year=year,
            area_type=area_type,
            uc_name=uc_name,
            is_pixelwise=is_pixelwise
        )

        map_layer = None
        if record.map_layer_path and os.path.exists(record.map_layer_path):
            with open(record.map_layer_path, "r") as f:
                map_layer = json.load(f)

        return {
            "uc_name": record.uc_name,
            "city_name": record.city_name,
            "map_layer": map_layer,
            "stats": record.stats,
            "mode": "pixelwise" if is_pixelwise else "annual_stats",
            "error": "0"
        }

    except YearlyAnalysis.DoesNotExist:
        return None


def save_yearly_analysis(project_id, analysis_type, year, area_type, uc_name, city_name, map_layer, stats, is_pixelwise=False):
    """
    Save yearly analysis result (stats + map_layer) into DB and JSON file.
    """
    file_name = f"{project_id}_{analysis_type}_{year}_{area_type}_{uc_name or 'custom'}_{'pixel' if is_pixelwise else 'annual'}.json"
    file_path = os.path.join(settings.MEDIA_ROOT, "yearly_map_layers", file_name)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # Save map layer to JSON file
    with open(file_path, "w") as f:
        json.dump(map_layer, f)

    # Save or update DB record
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
            "map_layer_path": file_path
        }
    )
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def per_year_analysis(request):
    init_ee()

    analysis_type = request.data.get("analysis_type")
    year = request.data.get("year")
    area_type = request.data.get("area_type")
    project_id = request.data.get("project_id")
    mode = request.data.get("mode", "annual_stats")  # "annual_stats" or "pixelwise"
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

        # --- Determine features ---
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
                features = [{"geometry": json.loads(polygon.geojson),
                             "properties": {"uc_name": None, "city_name": None}}]
            else:
                features = kml_data.get("features", [])
        elif area_type == "custom":
            if not geometry_data:
                return Response({"error": "geometry is required for custom analysis"}, status=400)
            geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
            features = [{"geometry": geom_json, "properties": {"uc_name": None, "city_name": None}}]
        else:
            return Response({"error": "Invalid area_type"}, status=400)

        # --- Process each feature ---
        def process_feature(feature):
            uc_name = feature["properties"].get("uc_name")
            city_name = feature["properties"].get("city_name")

            # --- Check DB cache ---
            existing = get_yearly_analysis_from_db(
                project_id, analysis_type, year, area_type,
                uc_name, is_pixelwise=(mode == "pixelwise")
            )
            if existing:
                return existing

            try:
                polygon = ee.Geometry(feature["geometry"])

                if mode == "annual_stats":
                    result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)
                    stats = result.get("stats")
                    map_layer = result.get("map_layer")

                    save_yearly_analysis(
                        project_id, analysis_type, year, area_type,
                        uc_name, city_name, map_layer, stats, is_pixelwise=False
                    )
                    return {
                        "uc_name": uc_name, "city_name": city_name, "mode": "annual_stats",
                        "map_layer": map_layer, "stats": stats
                    }

                else:  # pixelwise
                    image, vis_params = run_pixelwise_analysis(analysis_type, polygon, start_date, end_date)
                    map_id = image.getMapId(vis_params)
                    map_layer = {
                        "urlFormat": map_id["tile_fetcher"].url_format,
                        "mapid": map_id["mapid"],
                        "token": map_id["token"],
                        "palette": vis_params.get("palette")
                    }

                    save_yearly_analysis(
                        project_id, analysis_type, year, area_type,
                        uc_name, city_name, map_layer, {}, is_pixelwise=True
                    )
                    return {
                        "uc_name": uc_name, "city_name": city_name,
                        "mode": "pixelwise", "map_layer": map_layer
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
        # --- Get parameters ---
        analysis_type = request.data.get("analysis_type")
        year = request.data.get("year")
        lat = request.data.get("lat")
        lng = request.data.get("lng")
        project_id = request.data.get("project_id")  # optional

        if not all([analysis_type, year, lat, lng]):
            return Response({"error": "Missing required parameters"}, status=400)

        year = int(year)
        lat = float(lat)
        lng = float(lng)

        # --- Check if value already exists in DB ---
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

        # --- Initialize Earth Engine ---
        init_ee()

        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        point = ee.Geometry.Point([lng, lat])

        # --- Select dataset ---
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

        # --- Sample pixel ---
        sample = image.sample(region=point, scale=30).first()

        if not sample:
            pixel_value = {analysis_type.upper(): None}
        else:
            pixel_dict = sample.toDictionary().getInfo()
            band_name = list(pixel_dict.keys())[0]
            pixel_value = {analysis_type.upper(): pixel_dict.get(band_name, None)}

        # --- Save in DB ---
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
    


# ---------------- Helper: Run GEE before-after analysis ---------------- #
def run_before_after_analysis(project_id, analysis_type, before_year, after_year, area_type, features):
    """
    Runs GEE analysis independently for both years for all features
    """
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
                "comparison": {"status": status, "before_mean": before_mean, "after_mean": after_mean},
                "map_layer_before": before_result.get("map_layer", {}),
                "map_layer_after": after_result.get("map_layer", {})
            }

        except Exception as e:
            return {
                "uc_name": uc_name,
                "city_name": city_name,
                "comparison": {"status": "no_data", "before_mean": None, "after_mean": None},
                "map_layer_before": {},
                "map_layer_after": {},
                "error_msg": str(e)
            }

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(process_feature, features))

    return results


# ---------------- Main API ---------------- #
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

    # ---------------- Run or load before-after analysis ---------------- #
    results = []

    for feature in features:
        uc_name = feature.get("uc_name")

        # Check if result already exists in DB
        existing = BeforeAfterAnalysis.objects.filter(
            project_id=project_id,
            analysis_type=analysis_type,
            area_type=area_type,
            uc_name=uc_name,
            before_year=before_year,
            after_year=after_year
        ).first()

        if existing:
            # Load map layers from file
            try:
                with open(existing.map_layer_before_path, "r") as f:
                    map_layer_before = json.load(f)
            except:
                map_layer_before = {}

            try:
                with open(existing.map_layer_after_path, "r") as f:
                    map_layer_after = json.load(f)
            except:
                map_layer_after = {}

            results.append({
                "uc_name": uc_name,
                "city_name": existing.city_name,
                "comparison": existing.comparison,
                "map_layer_before": map_layer_before,
                "map_layer_after": map_layer_after
            })
        else:
            # Run GEE analysis
            res = run_before_after_analysis(project_id, analysis_type, before_year, after_year, area_type, [feature])[0]

            # Save map layers locally
            before_path = os.path.join(settings.MEDIA_ROOT, "before_after_map_layers",
                                       f"{project_id}{analysis_type}{before_year}_{uc_name or 'custom'}_before.json")
            after_path = os.path.join(settings.MEDIA_ROOT, "before_after_map_layers",
                                      f"{project_id}{analysis_type}{after_year}_{uc_name or 'custom'}_after.json")
            os.makedirs(os.path.dirname(before_path), exist_ok=True)
            with open(before_path, "w") as f:
                json.dump(res.get("map_layer_before", {}), f)
            os.makedirs(os.path.dirname(after_path), exist_ok=True)
            with open(after_path, "w") as f:
                json.dump(res.get("map_layer_after", {}), f)

            # Save to DB
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
                    "comparison": res["comparison"],
                    "map_layer_before_path": before_path,
                    "map_layer_after_path": after_path,
                }
            )

            results.append(res)

    # ---------------- Calculate summary ---------------- #
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

    # ---------------- Return response ---------------- #
    return Response({
        "mode": "before_after_comparison",
        "analysis_type": analysis_type,
        "before_year": before_year,
        "after_year": after_year,
        "results": results,
        "summary_stats": summary_stats
    })
    



# ---------------- Helper: Run pixelwise before-after GEE analysis ---------------- #
def run_before_after_pixelwise(project_id, analysis_type, before_year, after_year, area_type, features):
    """
    Run pixelwise GEE analysis for before and after year per feature
    """
    def load_cached_layer(path):
        """Load cached JSON map layer, return empty dict if not exists"""
        if path and os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return {}

    def process_feature(feature):
        uc_name = feature.get("uc_name")
        city_name = feature.get("city_name")
        geojson_dict = feature.get("geometry")
        polygon = ee.Geometry(geojson_dict) if geojson_dict else None

        # ---------------- Check DB cache first ---------------- #
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
                "map_layer_before": load_cached_layer(cached.map_layer_before_path),
                "map_layer_after": load_cached_layer(cached.map_layer_after_path),
            }

        # ---------------- Run GEE if not cached ---------------- #
        before_result = {}
        after_result = {}

        if polygon:
            # Use run_pixelwise_analysis to get correct palette per type
            before_image, before_vis = run_pixelwise_analysis(
                analysis_type, polygon, f"{before_year}-01-01", f"{before_year}-12-31"
            )
            before_map = before_image.getMapId(before_vis)
            before_result = {
                "map_layer": {
                    "urlFormat": before_map["tile_fetcher"].url_format,
                    "mapid": before_map["mapid"],
                    "token": before_map["token"],
                    "palette": before_vis["palette"]
                }
            }

            after_image, after_vis = run_pixelwise_analysis(
                analysis_type, polygon, f"{after_year}-01-01", f"{after_year}-12-31"
            )
            after_map = after_image.getMapId(after_vis)
            after_result = {
                "map_layer": {
                    "urlFormat": after_map["tile_fetcher"].url_format,
                    "mapid": after_map["mapid"],
                    "token": after_map["token"],
                    "palette": after_vis["palette"]
                }
            }

        # ---------------- Save JSON ---------------- #
        folder = os.path.join(settings.MEDIA_ROOT, "before_after_pixelwise")
        os.makedirs(folder, exist_ok=True)
        before_path = os.path.join(folder, f"{project_id}{analysis_type}{before_year}_{uc_name or 'custom'}_before.json")
        after_path = os.path.join(folder, f"{project_id}{analysis_type}{after_year}_{uc_name or 'custom'}_after.json")

        if before_result.get("map_layer"):
            with open(before_path, "w") as f:
                json.dump(before_result["map_layer"], f)
        if after_result.get("map_layer"):
            with open(after_path, "w") as f:
                json.dump(after_result["map_layer"], f)

        # ---------------- Save to DB ---------------- #
        BeforeAfterPixelwise.objects.update_or_create(
            project_id=project_id,
            analysis_type=analysis_type,
            area_type=area_type,
            uc_name=uc_name,
            before_year=before_year,
            after_year=after_year,
            defaults={
                "city_name": city_name,
                "map_layer_before_path": before_path,
                "map_layer_after_path": after_path
            }
        )

        return {
            "uc_name": uc_name,
            "city_name": city_name,
            "map_layer_before": before_result.get("map_layer", {}),
            "map_layer_after": after_result.get("map_layer", {}),
        }

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(process_feature, features))

    return results

# ---------------- API ---------------- #
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