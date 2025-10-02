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
from urbananalytics.models import AreaAnalysis, Project, YearlyAnalysis ,YearlyPixelValue,YearlyComparisonAnalysis
from rest_framework.decorators import api_view
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
    if ee.data._initialized:  # Skip if already initialized
        return

    service_account_key_path = r'C:\Users\Maryam Afzal\Downloads\urbananalytics-460415-f557e7903d83.json'
    credentials = ee.ServiceAccountCredentials(
        email='gee-service-account@urbananalytics-460415.iam.gserviceaccount.com',
        key_file=service_account_key_path
    )
    try:
        ee.Initialize(credentials, project='urbananalytics-460415')
        print("Earth Engine initialized successfully!")
    except Exception as e:
        print("Failed to initialize Earth Engine:", e)
        raise RuntimeError("Earth Engine initialization failed. Check credentials.")


# def init_ee():
#     """Initialize Earth Engine lazily when needed."""
#     service_account_key_path = r'C:\Users\Maryam Afzal\Downloads\urbananalytics-460415-f557e7903d83.json'
#     # service_account_key_path = r'C:\Users\User\Documents\urbananalytics-460415-f557e7903d83.json'
#     credentials = ee.ServiceAccountCredentials(
#         email='gee-service-account@urbananalytics-460415.iam.gserviceaccount.com',
#         key_file=service_account_key_path
#     )
#     try:
#         ee.Initialize(credentials, project='urbananalytics-460415')
#         print("Earth Engine initialized successfully!")
#     except Exception as e:
#         print("Failed to initialize Earth Engine:", e)
#         raise RuntimeError("Earth Engine initialization failed. Check credentials.")



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

        # Check cache first if project_id exists
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
                    map_layer = None
                    if cached.map_layer_path and os.path.exists(cached.map_layer_path):
                        with open(cached.map_layer_path, "r") as f:
                            map_layer = json.load(f)

                    results.append({
                        "uc_name": cached.uc_name,
                        "city_name": cached.city_name,
                        "map_layer": map_layer,
                        "stats": cached.stats,
                        "area_type": cached.area_type
                    })

                return Response({
                    "message": f"Cached {analysis_type.upper()} analysis returned",
                    "results": results
                })

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

            def process_uc(feature):
                try:
                    geojson_dict = feature["geometry"]
                    polygon = ee.Geometry(geojson_dict)
                    result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)
                    return {
                        "uc_name": feature["properties"]["uc_name"],
                        "city_name": feature["properties"]["city_name"],
                        "error": "0",
                        "map_layer": result.get("map_layer"),
                        "stats": result.get("stats") or {}   
                    }
                except Exception as e:
                    return {
                        "uc_name": feature["properties"]["uc_name"],
                        "city_name": feature["properties"]["city_name"],
                        "error": "1",
                        "error_msg": str(e),
                        "map_layer": None,
                        "stats": {}   
                    }

            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(process_uc, features))

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

            def process_uc(feature):
                try:
                    geojson_dict = feature["geometry"]
                    polygon = ee.Geometry(geojson_dict)
                    result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)
                    return {
                        "uc_name": feature["properties"]["uc_name"],
                        "city_name": feature["properties"]["city_name"],
                        "error": "0",
                        "map_layer": result.get("map_layer"),
                        "stats": result.get("stats") or {}
                    }
                except Exception as e:
                    return {
                        "uc_name": feature["properties"]["uc_name"],
                        "city_name": feature["properties"]["city_name"],
                        "error": "1",
                        "error_msg": str(e),
                        "map_layer": None,
                        "stats": {}
                    }

            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(process_uc, features))

        elif area_type == "custom":
            if not geometry_data:
                return Response({"error": "geometry data is required for custom analysis"}, status=400)

            geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
            polygon = ee.Geometry(geom_json)
            result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)
            results.append({
                "uc_name": None,
                "city_name": None,
                "map_layer": result.get("map_layer"),
                "stats": result.get("stats"),
                "area_type": "custom"
            })

        else:
            return Response({"error": "Invalid area_type"}, status=400)

        if project_id and results and area_type in ["uc", "kml"]:
            for res in results:
                layer_content = res.get("map_layer")
                stats = res.get("stats")
                uc_name = res.get("uc_name")
                city_name = res.get("city_name")

                file_name = f"{project_id}{analysis_type}{start_date}{end_date}{area_type}_{uc_name}.json"
                file_path = os.path.join(settings.MEDIA_ROOT, "map_layers", file_name)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w") as f:
                    json.dump(layer_content, f)

                AreaAnalysis.objects.update_or_create(
                    project_id=project_id,
                    analysis_type=analysis_type,
                    start_date=start_date,
                    end_date=end_date,
                    area_type=area_type,
                    uc_name=uc_name,
                    defaults={
                        "city_name": city_name,
                        "stats": stats,
                        "is_pixelwise": False,
                        "map_layer_path": file_path
                    }
                )

        return Response({
            "message": f"{analysis_type.upper()} analysis performed",
            "results": results
        })

    except Exception as e:
        return Response({"error": "Failed to perform analysis", "details": str(e)}, status=500)


def perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date):
    init_ee()
    scale = 10

    if analysis_type.lower() == "ndvi":
        collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
            .filterBounds(polygon) \
            .filterDate(start_date, end_date) \
            .select(['B8', 'B4']) \
            .median()
        image = collection.normalizedDifference(['B8', 'B4']).rename('NDVI').clip(polygon)
        vis_params = {'min': 0, 'max': 1, 'palette': ['white', 'green']}
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
        vis_params = {'min': 290, 'max': 320, 'palette': ['blue', 'green', 'red']}
        band_name = 'Thermal'
        scale = 100

    elif analysis_type.lower() == "aqi":
        
        collection = ee.ImageCollection('COPERNICUS/S5P/NRTI/L3_NO2') \
            .filterBounds(polygon) \
            .filterDate(start_date, end_date) \
            .median()
        image = collection.select('NO2_column_number_density').rename('AQI').multiply(1e5).clip(polygon)
        vis_params = {'min': 0, 'max': 30, 'palette': ['green', 'yellow', 'red']}
        band_name = 'AQI'
        scale = 1000
       


    else:
        raise ValueError("Invalid analysis type")

    
    stats = image.reduceRegion(
        reducer=ee.Reducer.mean().combine(
            reducer2=ee.Reducer.minMax(), sharedInputs=True
        ).combine(
            reducer2=ee.Reducer.stdDev(), sharedInputs=True
        ),
        geometry=polygon,
        scale=scale,
        maxPixels=1e9
    ).getInfo()

    
    try:
        vis_image = image.visualize(**vis_params)
        map_data = vis_image.getMapId()
        url_format = map_data["tile_fetcher"].url_format
        mapid = map_data["mapid"]
        token = map_data["token"]
    except Exception as e:
        raise ValueError(f"Failed to generate map layer: {str(e)}")

    return {
        "map_layer": {
            "urlFormat": url_format,
            "mapid": mapid,
            "token": token
        },
        "stats": {
            "mean": stats.get(f"{band_name}_mean"),
            "min": stats.get(f"{band_name}_min"),
            "max": stats.get(f"{band_name}_max"),
            "std_dev": stats.get(f"{band_name}_stdDev")
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
                    map_layer = None
                    if cached.map_layer_path and os.path.exists(cached.map_layer_path):
                        with open(cached.map_layer_path, "r") as f:
                            map_layer = json.load(f)

                    results.append({
                        "uc_name": cached.uc_name,
                        "city_name": cached.city_name,
                        "map_layer": map_layer,
                        "palette_used": map_layer.get("palette") if map_layer else None,
                        "area_type": cached.area_type
                    })

                return Response({
                    "message": f"Cached {analysis_type.upper()} pixelwise analysis returned",
                    "results": results
                })

        
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

            def process_uc(feature):
                try:
                    geojson_dict = feature["geometry"]
                    polygon = ee.Geometry(geojson_dict)
                    image, vis_params = run_pixelwise_analysis(analysis_type, polygon, start_date, end_date)
                    map_id = image.getMapId(vis_params)

                    return {
                        "uc_name": feature["properties"]["uc_name"],
                        "city_name": feature["properties"]["city_name"],
                        "error": "0",
                        "map_layer": {
                            "urlFormat": map_id["tile_fetcher"].url_format,
                            "mapid": map_id["mapid"],
                            "token": map_id["token"],
                            "palette": vis_params["palette"]
                        }
                    }
                except Exception as e:
                    return {
                        "uc_name": feature["properties"]["uc_name"],
                        "city_name": feature["properties"]["city_name"],
                        "error": "1",
                        "error_msg": str(e),
                        "map_layer": None
                    }

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

            def process_uc(feature):
                try:
                    geojson_dict = feature["geometry"]
                    polygon = ee.Geometry(geojson_dict)
                    image, vis_params = run_pixelwise_analysis(analysis_type, polygon, start_date, end_date)
                    map_id = image.getMapId(vis_params)

                    return {
                        "uc_name": feature["properties"]["uc_name"],
                        "city_name": feature["properties"]["city_name"],
                        "error": "0",
                        "map_layer": {
                            "urlFormat": map_id["tile_fetcher"].url_format,
                            "mapid": map_id["mapid"],
                            "token": map_id["token"],
                            "palette": vis_params["palette"]
                        }
                    }
                except Exception as e:
                    return {
                        "uc_name": feature["properties"]["uc_name"],
                        "city_name": feature["properties"]["city_name"],
                        "error": "1",
                        "error_msg": str(e),
                        "map_layer": None
                    }

            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(process_uc, features))

        elif area_type == "custom":
            if not geometry_data:
                return Response({"error": "geometry data is required for custom analysis"}, status=400)

            geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
            polygon = ee.Geometry(geom_json)
            image, vis_params = run_pixelwise_analysis(analysis_type, polygon, start_date, end_date)
            map_id = image.getMapId(vis_params)

            results.append({
                "uc_name": None,
                "city_name": None,
                "map_layer": {
                    "urlFormat": map_id["tile_fetcher"].url_format,
                    "mapid": map_id["mapid"],
                    "token": map_id["token"],
                    "palette": vis_params["palette"]
                },
                "area_type": "custom"
            })

        else:
            return Response({"error": "Invalid area_type"}, status=400)

        
        if project_id and results and area_type in ["uc", "kml"]:
            for res in results:
                layer_content = res.get("map_layer")
                uc_name = res.get("uc_name")
                city_name = res.get("city_name")

                file_name = f"{project_id}{analysis_type}{start_date}{end_date}{area_type}_{uc_name}.json"
                file_path = os.path.join(settings.MEDIA_ROOT, "map_layers", file_name)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "w") as f:
                    json.dump(layer_content, f)

                AreaAnalysis.objects.update_or_create(
                    project_id=project_id,
                    analysis_type=analysis_type,
                    start_date=start_date,
                    end_date=end_date,
                    area_type=area_type,
                    uc_name=uc_name,
                    defaults={
                        "city_name": city_name,
                        "stats": {},  
                        "map_layer_path": file_path,
                        "is_pixelwise": True
                    }
                )

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
            'min': -0.5, 'max': 1,
            'palette': ['#654321', '#FFA07A', '#FFFF66', '#ADFF2F', '#008000', '#004B23']
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
            'palette': ['#0000FF', '#00BFFF', '#7FFFD4', '#FFFF66', '#FF8C00', '#B22222']
        }

    elif analysis_type.lower() == "aqi":
        collection = ee.ImageCollection('COPERNICUS/S5P/NRTI/L3_NO2') \
            .filterBounds(polygon).filterDate(start_date, end_date)
        image = collection.median().select('NO2_column_number_density').multiply(1e5).rename('AQI').clip(polygon)
        
        vis_params = {
            'min': 0, 'max': 50,
            'palette': ['#00E400', '#FFFF00', '#FF7E00', '#FF0000', '#8F3F97', '#7E0023']
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


<<<<<<< Updated upstream
=======
def get_yearly_analysis_from_db(project_id, analysis_type, year, area_type, uc_name=None, is_pixelwise=False):
    try:
        record = YearlyAnalysis.objects.get(
            project_id=project_id,
            analysis_type=analysis_type,
            year=year,
            area_type=area_type,
            uc_name=uc_name,
            is_pixelwise=is_pixelwise
        )

        # Prefer DB field if available
        map_layer = record.map_layer  

        # Fallback: load from file if DB field is empty
        if not map_layer and record.map_layer_path and os.path.exists(record.map_layer_path):
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
    file_name = f"{project_id}_{analysis_type}_{year}_{area_type}_{uc_name or 'custom'}_{'pixel' if is_pixelwise else 'annual'}.json"
    file_path = os.path.join(settings.MEDIA_ROOT, "yearly_map_layers", file_name)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # Save to JSON file
    with open(file_path, "w") as f:
        json.dump(map_layer, f)

    # Save or update DB record (store both)
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
            "map_layer_path": file_path,
            "map_layer": map_layer   # 👈 store JSON directly in DB
        }
    )

>>>>>>> Stashed changes
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def per_year_analysis(request):
    init_ee()  # Initialize Earth Engine

    analysis_type = request.data.get("analysis_type")
    year = request.data.get("year")
    area_type = request.data.get("area_type")
    geometry_data = request.data.get("geometry")
    project_id = request.data.get("project_id")
    mode = request.data.get("mode", "annual_stats")  # "annual_stats" or "pixelwise"

    if not analysis_type or not year or not area_type:
        return Response({"error": "Missing required parameters"}, status=400)

    try:
        year = int(year)
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        results = []

        # --- Helper function to save result in DB ---
        def save_yearly_analysis(uc_name, city_name, stats, map_layer, is_pixelwise):
            # Save map layer to a JSON file
            file_name = f"{project_id}{analysis_type}{year}{area_type}{uc_name or 'ALL'}_{ 'pixel' if is_pixelwise else 'annual' }.json"
            file_path = os.path.join(settings.MEDIA_ROOT, "map_layers", file_name)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                json.dump(map_layer, f)

            # Create DB entry
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

        # --- UC or KML Areas ---
        if area_type in ["uc", "kml"]:
            if not project_id:
                return Response({"error": "project_id is required for UC/KML analysis"}, status=400)

            project = Project.objects.filter(id=project_id).first()
            if not project:
                return Response({"error": "Project not found"}, status=404)
            city_name = project.location_name

            # Load features
            if area_type == "uc":
                uc_data = load_ucs_for_uc(city_name)
                if not uc_data:
                    db_ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)
                    features = [
                        {
                            "geometry": json.loads(uc.geometry.geojson),
                            "properties": {"uc_name": uc.uc_name, "city_name": uc.city_name}
                        } for uc in db_ucs
                    ]
                else:
                    features = uc_data.get("features", [])
            else:  # kml
                local_kml_file = os.path.join(settings.DATA_DIR, f"project_{project_id}_kml_ucs.json")
                if os.path.exists(local_kml_file):
                    with open(local_kml_file, "r") as f:
                        kml_data = json.load(f)
                    features = kml_data.get("features", [])
                else:
                    db_ucs = UnionCouncil.objects.all()
                    features = [
                        {
                            "geometry": json.loads(uc.geometry.geojson),
                            "properties": {"uc_name": uc.uc_name, "city_name": uc.city_name}
                        } for uc in db_ucs
                    ]

            # --- Process each feature ---
            def process_uc(feature):
                uc_name = feature["properties"]["uc_name"]

                # --- Check DB first ---
                existing = YearlyAnalysis.objects.filter(
                    project_id=project_id,
                    analysis_type=analysis_type,
                    year=year,
                    area_type=area_type,
                    uc_name=uc_name,
                    is_pixelwise=(mode=="pixelwise")
                ).first()

                if existing:
                    # Return cached data
                    map_layer = json.load(open(existing.map_layer_path)) if existing.map_layer_path else None
                    return {
                        "uc_name": existing.uc_name,
                        "city_name": existing.city_name,
                        "mode": mode,
                        "map_layer": map_layer,
                        "stats": existing.stats
                    }

                try:
                    polygon = ee.Geometry(feature["geometry"])

                    if mode == "annual_stats":
                        result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)
                        stats = result.get("stats")
                        map_layer = result.get("map_layer")
                        save_yearly_analysis(uc_name, feature["properties"]["city_name"], stats, map_layer, False)

                        return {
                            "uc_name": uc_name,
                            "city_name": feature["properties"]["city_name"],
                            "mode": "annual_stats",
                            "map_layer": map_layer,
                            "stats": stats
                        }

                    else:  # pixelwise
                        image, vis_params = run_pixelwise_analysis(analysis_type, polygon, start_date, end_date)
                        map_id = image.getMapId(vis_params)
                        map_layer = {
                            "urlFormat": map_id["tile_fetcher"].url_format,
                            "mapid": map_id["mapid"],
                            "token": map_id["token"],
                            "palette": vis_params["palette"]
                        }
                        save_yearly_analysis(uc_name, feature["properties"]["city_name"], {}, map_layer, True)

                        return {
                            "uc_name": uc_name,
                            "city_name": feature["properties"]["city_name"],
                            "mode": "pixelwise",
                            "map_layer": map_layer
                        }
                except Exception as e:
                    return {
                        "uc_name": uc_name,
                        "city_name": feature["properties"]["city_name"],
                        "error": "1",
                        "error_msg": str(e)
                    }

            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(process_uc, features))

        # --- Custom Area ---
        elif area_type == "custom":
            if not geometry_data:
                return Response({"error": "geometry is required for custom analysis"}, status=400)
            geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
            polygon = ee.Geometry(geom_json)

            existing = YearlyAnalysis.objects.filter(
                project_id=project_id,
                analysis_type=analysis_type,
                year=year,
                area_type=area_type,
                uc_name=None,
                is_pixelwise=(mode=="pixelwise")
            ).first()

            if existing:
                map_layer = json.load(open(existing.map_layer_path)) if existing.map_layer_path else None
                results.append({
                    "uc_name": None,
                    "city_name": None,
                    "mode": mode,
                    "map_layer": map_layer,
                    "stats": existing.stats
                })
            else:
                if mode == "annual_stats":
                    result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)
                    stats = result.get("stats")
                    map_layer = result.get("map_layer")
                    save_yearly_analysis(None, None, stats, map_layer, False)
                    results.append({
                        "uc_name": None,
                        "city_name": None,
                        "mode": "annual_stats",
                        "map_layer": map_layer,
                        "stats": stats
                    })
                else:
                    image, vis_params = run_pixelwise_analysis(analysis_type, polygon, start_date, end_date)
                    map_id = image.getMapId(vis_params)
                    map_layer = {
                        "urlFormat": map_id["tile_fetcher"].url_format,
                        "mapid": map_id["mapid"],
                        "token": map_id["token"],
                        "palette": vis_params["palette"]
                    }
                    save_yearly_analysis(None, None, {}, map_layer, True)
                    results.append({
                        "uc_name": None,
                        "city_name": None,
                        "mode": "pixelwise",
                        "map_layer": map_layer
                    })
        else:
            return Response({"error": "Invalid area_type"}, status=400)

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

<<<<<<< Updated upstream
=======

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


# ---------------- Main API ---------------- #
>>>>>>> Stashed changes
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def yearly_comparison(request):
    """
    Pairwise yearly comparison API using polygon/vector logic.
    Checks DB first; computes only if missing.
    Stores results in YearlyComparisonAnalysis.stats as:
    {
      "2025_vs_2024": {"baseline_mean": 0.56, "comparison_mean": 0.48, "status": "increase"},
      "2025_vs_2023": {"baseline_mean": 0.56, "comparison_mean": 0.62, "status": "decrease"}
    }
    """
    try:
        init_ee()

        start_year = int(request.data.get("start_year"))
        comparison_years = int(request.data.get("comparison_years", 3))
        analysis_type = request.data.get("analysis_type")
        area_type = request.data.get("area_type")
        project_id = request.data.get("project_id")
        city_name = request.data.get("city_name")
        geometry_data = request.data.get("geometry")

        if comparison_years not in (1, 2, 3):
            return Response({"error": "comparison_years must be 1,2,3"}, status=400)
        if analysis_type not in ("ndvi", "thermal", "aqi"):
            return Response({"error": "analysis_type invalid"}, status=400)
        if area_type not in ("uc", "kml", "custom"):
            return Response({"error": "area_type invalid"}, status=400)

        prev_years = [start_year - i for i in range(1, comparison_years + 1)]
        results = []

        def mean_for_year(polygon_ee, year_int):
            start = f"{year_int}-01-01"
            end = f"{year_int+1}-01-01"
            res = perform_analysis_for_polygon(analysis_type, polygon_ee, start, end)
            return res.get("stats", {}).get("mean")

<<<<<<< Updated upstream
        # --- Helper to process a polygon/UC ---
        def process_polygon(uc_name, uc_city, polygon):
            # Check DB first
            existing = YearlyComparisonAnalysis.objects.filter(
=======
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
            # Run GEE analysis
            res = run_before_after_analysis(
                project_id, analysis_type, before_year, after_year, area_type, [feature]
            )[0]

            # Save to DB (only stats, no layers)
            BeforeAfterAnalysis.objects.update_or_create(
>>>>>>> Stashed changes
                project_id=project_id,
                analysis_type=analysis_type,
                baseline_year=start_year,
                area_type=area_type,
<<<<<<< Updated upstream
                uc_name=uc_name
            ).first()

            if existing:
                return {
                    "uc_name": uc_name,
                    "city_name": uc_city,
                    "stats": existing.stats,
                    "cached": True
=======
                uc_name=uc_name,
                before_year=before_year,
                after_year=after_year,
                defaults={
                    "city_name": res.get("city_name"),
                    "stats_before": {"mean": res["comparison"].get("before_mean")},
                    "stats_after": {"mean": res["comparison"].get("after_mean")},
                    "comparison": res["comparison"]
>>>>>>> Stashed changes
                }

            baseline_mean = mean_for_year(polygon, start_year)
            stats = {}
            for y in prev_years:
                comparison_mean = mean_for_year(polygon, y)
                status = "no_data"
                if baseline_mean is not None and comparison_mean is not None:
                    diff = baseline_mean - comparison_mean
                    if diff > 0:
                        status = "increase"
                    elif diff < 0:
                        status = "decrease"
                    else:
                        status = "no_change"

                stats[f"{start_year}_vs_{y}"] = {
                    "baseline_mean": baseline_mean,
                    "comparison_mean": comparison_mean,
                    "status": status
                }

            # Save to DB
            if project_id:
                YearlyComparisonAnalysis.objects.update_or_create(
                    project_id=project_id,
                    analysis_type=analysis_type,
                    baseline_year=start_year,
                    area_type=area_type,
                    uc_name=uc_name,
                    defaults={
                        "city_name": uc_city,
                        "comparison_years": prev_years,
                        "stats": stats
                    }
                )

<<<<<<< Updated upstream
=======
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
>>>>>>> Stashed changes
            return {
                "uc_name": uc_name,
                "city_name": uc_city,
                "stats": stats,
                "cached": False
            }

        # --- UC polygons ---
        if area_type == "uc":
            if not project_id and not city_name:
                return Response({"error": "project_id or city_name required for uc"}, status=400)
            if project_id:
                proj = Project.objects.filter(id=project_id).first()
                if proj and proj.location_name:
                    city_name = proj.location_name
            if not city_name:
                return Response({"error": "city_name resolved to None"}, status=400)

            ucs_data = load_ucs_for_uc(city_name)
            if ucs_data:
                features = ucs_data.get("features", [])
            else:
                db_ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)
                features = [
                    {"geometry": json.loads(uc.geometry.geojson),
                     "properties": {"uc_name": uc.uc_name, "city_name": uc.city_name}}
                    for uc in db_ucs
                ]

            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(lambda f: process_polygon(
                    f["properties"].get("uc_name"),
                    f["properties"].get("city_name"),
                    ee.Geometry(f["geometry"])
                ), features))

        # --- KML polygons ---
        elif area_type == "kml":
            if not project_id:
                return Response({"error": "project_id required for kml"}, status=400)
            try:
                project = Project.objects.get(id=project_id)
            except Project.DoesNotExist:
                return Response({"error": "Project not found"}, status=404)
            if not project.kml_file:
                return Response({"error": "KML file missing"}, status=400)

            from django.contrib.gis.gdal import DataSource
            ds = DataSource(project.kml_file.path)
            layer = ds[0]
            kml_geom = None
            for feat in layer:
                geom = feat.geom.geos
                kml_geom = geom if kml_geom is None else kml_geom.union(geom)

            ucs = UnionCouncil.objects.filter(geometry__intersects=kml_geom)
            if not ucs.exists():
                return Response({"error": "No UCs intersect KML area"}, status=404)

            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(lambda uc: process_polygon(
                    uc.uc_name,
                    uc.city_name,
                    ee.Geometry(json.loads(uc.geometry.geojson))
                ), ucs))

        # --- Custom polygon ---
        elif area_type == "custom":
            if not geometry_data:
                return Response({"error": "geometry required for custom"}, status=400)
            geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
            polygon = ee.Geometry(geom_json)
            results.append(process_polygon(None, None, polygon))

        return Response({
            "mode": "yearly_comparison",
            "analysis_type": analysis_type,
            "baseline_year": start_year,
            "compared_years": prev_years,
            "results": results
        })

    except Exception as e:
        return Response({"error": "Failed yearly comparison", "details": str(e)}, status=500)

