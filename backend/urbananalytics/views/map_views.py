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
from urbananalytics.models import AreaAnalysis, Project, YearlyComparisonAnalysis
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

    # Convert Shapely Polygon to WKT
    shapely_poly = ShapelyPolygon(coords)
    wkt = shapely_poly.wkt  # "POLYGON((...))"
    
    return GEOSGeometry(wkt)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_ucs(request):
    project_id = request.query_params.get("project_id")
    if not project_id:
        return Response({"error": "project_id required"}, status=400)

    try:
        project = Project.objects.get(id=project_id)

        # -------------------- UCS type --------------------
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

        # -------------------- KML type --------------------
        elif project.kml_file:
            kml_path = project.kml_file.path
            cache_file_path = os.path.join(DATA_DIR, f"project_{project.id}_kml_ucs.json")

            # If cached file exists, return it
            if os.path.exists(cache_file_path):
                with open(cache_file_path, "r") as f:
                    return Response(json.load(f))

            # Otherwise, parse KML
            with open(kml_path, "r") as f:
                kml_content = f.read()

            polygon = kml_to_geosgeometry(kml_content)


            # Query UCs intersecting the polygon
            ucs = UnionCouncil.objects.filter(geometry__intersects=polygon)
            if not ucs.exists():
                return Response({"error": "No UCs found in this area"}, status=404)

            geojson = serialize(
                "geojson", ucs,
                geometry_field="geometry",
                fields=("uc_name", "city_name")
            )
            geojson_data = json.loads(geojson)

            # Save GeoJSON locally for caching
            with open(cache_file_path, "w") as f:
                json.dump(geojson_data, f)

            return Response(geojson_data)

        else:
            return Response({"error": "Project has neither location_name nor KML file"}, status=400)

    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=404)



# import ee

# def init_ee():
#     """Initialize Earth Engine lazily when needed."""
#     service_account_key_path = r'C:\Users\User\Documents\urbananalytics-460415-f557e7903d83.json'
#     credentials = ee.ServiceAccountCredentials(
#         email='gee-service-account@urbananalytics-460415.iam.gserviceaccount.com',
#         key_file=service_account_key_path
#     )
#     try:
#         ee.Initialize(credentials, project='urbananalytics-460415')
#     except Exception as e:
#         print("Error initializing Earth Engine:", e)
        
import ee

# def init_ee():
#     """Initialize Earth Engine lazily using service account."""
#     service_account_key_path = r'C:\Users\User\Documents\urbananalytics-460415-f557e7903d83.json'
#     credentials = ee.ServiceAccountCredentials(
#         email='gee-service-account@urbananalytics-460415.iam.gserviceaccount.com',
#         key_file=service_account_key_path
#     )
#     try:
#         # Check if already initialized
#         ee.Initialize()
#     except Exception:
#         try:
#             ee.Initialize(credentials, project='urbananalytics-460415')
#             print("Earth Engine initialized with service account.")
#         except Exception as e:
#             print("Failed to initialize Earth Engine:", e)
#             raise RuntimeError("Earth Engine initialization failed. Check credentials.")
import os
import certifi
import ee

# Force requests / Google API to use certifi CA bundle
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
os.environ['SSL_CERT_FILE'] = certifi.where()

def init_ee():
    """Initialize Earth Engine lazily when needed."""
    service_account_key_path = r'C:\Users\User\Documents\urbananalytics-460415-f557e7903d83.json'
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

# @api_view(['POST'])
# def perform_gee_analysis(request):
#     init_ee()

#     analysis_type = request.data.get("analysis_type")
#     start_date = request.data.get("start_date")
#     end_date = request.data.get("end_date")
#     area_type = request.data.get("area_type")
#     city_name = request.data.get("city_name")
#     geometry_data = request.data.get("geometry")
#     project_id = request.data.get("project_id")

#     if not analysis_type or not start_date or not end_date or not area_type:
#         return Response({"error": "Missing required parameters"}, status=400)

#     try:
        
#         if project_id and area_type in ["uc", "kml"]:
#             cached_results = AreaAnalysis.objects.filter(
#                 project_id=project_id,
#                 analysis_type=analysis_type,
#                 start_date=start_date,
#                 end_date=end_date,
#                 area_type=area_type
#             ).order_by('uc_name')  

#             if cached_results.exists():
#                 results = []
#                 for cached in cached_results:
#                     map_layer = None
#                     if cached.map_layer_path and os.path.exists(cached.map_layer_path):
#                         with open(cached.map_layer_path, "r") as f:
#                             map_layer = json.load(f)

#                     results.append({
#                         "uc_name": cached.uc_name,
#                         "city_name": cached.city_name,
#                         "map_layer": map_layer,
#                         "stats": cached.stats,
#                         "area_type": cached.area_type
#                     })

#                 return Response({
#                     "message": f"Cached {analysis_type.upper()} analysis returned",
#                     "results": results
#                 })

#         results = []

#         if area_type == "uc":
#             if not city_name:
#                 return Response({"error": "city_name is required for UC analysis"}, status=400)

#             uc_data = load_ucs_for_uc(city_name)
#             if not uc_data:
#                 return Response({"error": f"No local UC data found for {city_name}"}, status=404)

#             features = uc_data.get("features", [])
#             if not features:
#                 return Response({"error": "No Union Councils found in local file"}, status=404)
            
#             def process_uc(feature):
#                 try:
#                     geojson_dict = feature["geometry"]
#                     polygon = ee.Geometry(geojson_dict)
#                     result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)
#                     return {
#                         "uc_name": feature["properties"]["uc_name"],
#                         "city_name": feature["properties"]["city_name"],
#                         "error": "0",
#                         "map_layer": result.get("map_layer"),
#                         "stats": result.get("stats") or {}   
#                     }
#                 except Exception as e:
#                     return {
#                         "uc_name": feature["properties"]["uc_name"],
#                         "city_name": feature["properties"]["city_name"],
#                         "error": "1",
#                         "error_msg": str(e),
#                         "map_layer": None,
#                         "stats": {}   
#                     }


#             with ThreadPoolExecutor(max_workers=5) as executor:
#                 results = list(executor.map(process_uc, features))

#         elif area_type == "kml":
#             if not project_id:
#                 return Response({"error": "project_id is required for KML analysis"}, status=400)

#             try:
#                 project = Project.objects.get(id=project_id)
#             except Project.DoesNotExist:
#                 return Response({"error": "Project not found"}, status=404)

#             if not project.kml_file:
#                 return Response({"error": "No KML file found for this project"}, status=404)

#             file_name = os.path.splitext(os.path.basename(project.kml_file.name))[0]
#             city_name = file_name.split("_")[0].capitalize()

#             uc_data = load_ucs_for_uc(city_name)
#             if not uc_data:
#                 return Response({"error": f"No local UC data found for {city_name}"}, status=404)

#             features = uc_data.get("features", [])
#             if not features:
#                 return Response({"error": "No Union Councils found in local file"}, status=404)

#             def process_uc(feature):
#                 try:
#                     geojson_dict = feature["geometry"]
#                     polygon = ee.Geometry(geojson_dict)
#                     result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)
#                     return {
#                         "uc_name": feature["properties"]["uc_name"],
#                         "city_name": feature["properties"]["city_name"],
#                         "error": "0",
#                         "map_layer": result.get("map_layer"),
#                         "stats": result.get("stats")
#                     }
#                 except Exception as e:
#                     return {
#                         "uc_name": feature["properties"]["uc_name"],
#                         "city_name": feature["properties"]["city_name"],
#                         "error": "1",
#                         "error_msg": str(e)
#                     }

#             with ThreadPoolExecutor(max_workers=5) as executor:
#                 results = list(executor.map(process_uc, features))

#         elif area_type == "custom":
#             if not geometry_data:
#                 return Response({"error": "geometry data is required for custom analysis"}, status=400)

#             geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
#             polygon = ee.Geometry(geom_json)
#             result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)
#             results.append({
#                 "uc_name": None,
#                 "city_name": None,
#                 "map_layer": result.get("map_layer"),
#                 "stats": result.get("stats"),
#                 "area_type": "custom"
#             })

#         else:
#             return Response({"error": "Invalid area_type"}, status=400)

#         if project_id and results and area_type in ["uc", "kml"]:
#             for res in results:
#                 layer_content = res.get("map_layer")
#                 stats = res.get("stats")
#                 uc_name = res.get("uc_name")
#                 city_name = res.get("city_name")

                
#                 file_name = f"{project_id}_{analysis_type}_{start_date}_{end_date}_{area_type}_{uc_name}.json"
#                 file_path = os.path.join(settings.MEDIA_ROOT, "map_layers", file_name)
#                 os.makedirs(os.path.dirname(file_path), exist_ok=True)
#                 with open(file_path, "w") as f:
#                     json.dump(layer_content, f)

                
#                 AreaAnalysis.objects.update_or_create(
#                     project_id=project_id,
#                     analysis_type=analysis_type,
#                     start_date=start_date,
#                     end_date=end_date,
#                     area_type=area_type,
#                     uc_name=uc_name,
#                     defaults={
#                         "city_name": city_name,
#                         "stats": stats,
#                         "map_layer_path": file_path
#                     }
#                 )

#         return Response({
#             "message": f"{analysis_type.upper()} analysis performed",
#             "results": results
#         })

#     except Exception as e:
#         return Response({"error": "Failed to perform analysis", "details": str(e)}, status=500)
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
                area_type=area_type
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

        # ---------------- UC Analysis (local only, unchanged) ----------------
        if area_type == "uc":
            if not city_name:
                return Response({"error": "city_name is required for UC analysis"}, status=400)

            uc_data = load_ucs_for_uc(city_name)

            # If local UC not found, fall back to database
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

        # ---------------- KML Analysis (local → DB fallback) ----------------
        elif area_type == "kml":
            if not project_id:
                return Response({"error": "project_id is required for KML analysis"}, status=400)

            # First try to load local JSON for KML
            local_kml_file = os.path.join(
                DATA_DIR, f"project_{project_id}_kml_ucs.json"
            )
            if os.path.exists(local_kml_file):
                with open(local_kml_file, "r") as f:
                    kml_data = json.load(f)
                features = kml_data.get("features", [])
            else:
                # Fall back to database
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
                        "stats": result.get("stats")
                    }
                except Exception as e:
                    return {
                        "uc_name": feature["properties"]["uc_name"],
                        "city_name": feature["properties"]["city_name"],
                        "error": "1",
                        "error_msg": str(e)
                    }

            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(process_uc, features))

        # ---------------- Custom Polygon Analysis ----------------
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

        # ---------------- Save results to DB if project_id ----------------
        if project_id and results and area_type in ["uc", "kml"]:
            for res in results:
                layer_content = res.get("map_layer")
                stats = res.get("stats")
                uc_name = res.get("uc_name")
                city_name = res.get("city_name")

                file_name = f"{project_id}_{analysis_type}_{start_date}_{end_date}_{area_type}_{uc_name}.json"
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
def yearly_comparison_analysis(request):
    # Initialize GEE
    init_ee()

    start_year = request.data.get("start_year")
    area_type = request.data.get("area_type")
    city_name = request.data.get("city_name")
    project_id = request.data.get("project_id")
    comparison_years = int(request.data.get("comparison_years", 3))
    analysis_type = request.data.get("analysis_type")  # ndvi, thermal, aqi

    # Validate inputs
    if not start_year:
        return Response({"error": "start_year is required"}, status=400)
    try:
        start_year = int(start_year)
    except ValueError:
        return Response({"error": "start_year must be an integer"}, status=400)

    if comparison_years not in (1, 2, 3):
        return Response({"error": "comparison_years must be 1, 2, or 3"}, status=400)

    if analysis_type not in ("ndvi", "thermal", "aqi"):
        return Response({"error": "analysis_type must be one of 'ndvi', 'thermal', or 'aqi'"}, status=400)

    prev_years = [start_year - i for i in range(1, comparison_years + 1)]

    # Check for cached results first
    if project_id:
        cached = YearlyComparisonAnalysis.objects.filter(
            project_id=project_id,
            analysis_type=analysis_type,
            baseline_year=start_year,
            area_type=area_type
        )
        if cached.exists():
            results = []
            for c in cached:
                results.append({
                    "uc_name": c.uc_name,
                    "city_name": c.city_name,
                    "analysis": {
                        "baseline_year": c.baseline_year,
                        "comparison_years": c.comparison_years,
                        "baseline_mean": c.baseline_mean,
                        "avg_prev_mean": c.avg_prev_mean,
                        "status": c.status
                    }
                })
            return Response({
                "mode": "yearly_comparison",
                "analysis_type": analysis_type,
                "baseline_year": start_year,
                "compared_years": prev_years,
                "results": results,
                "cached": True
            })

    results = []

    try:
        if area_type == "uc":
            if not city_name:
                return Response({"error": "city_name is required for area_type 'uc'."}, status=400)

            # Load UCs from local JSON
            ucs_data = load_ucs_for_uc(city_name)
            if not ucs_data:
                return Response({"error": f"No UC data found for city {city_name}"}, status=404)

            features = ucs_data.get("features", [])
            if not features:
                return Response({"error": "No Union Councils found in local file"}, status=404)

            def process_uc(feature):
                uc_name = feature["properties"].get("uc_name") or "UNKNOWN_UC"
                uc_city = feature["properties"].get("city_name") or city_name
                uc_polygon = ee.Geometry(feature["geometry"])
                uc_result = {"uc_name": uc_name, "city_name": uc_city, "area_type": "uc"}

                # Baseline year
                baseline_start = f"{start_year}-01-01"
                baseline_end = f"{start_year+1}-01-01"
                res = perform_analysis_for_polygon(analysis_type, uc_polygon, baseline_start, baseline_end)
                baseline_mean = res.get("stats", {}).get("mean")

                # Previous years
                prev_means = []
                for year in prev_years:
                    year_start = f"{year}-01-01"
                    year_end = f"{year+1}-01-01"
                    prev_res = perform_analysis_for_polygon(analysis_type, uc_polygon, year_start, year_end)
                    prev_mean = prev_res.get("stats", {}).get("mean")
                    if prev_mean is not None:
                        prev_means.append(prev_mean)
                avg_prev_mean = sum(prev_means) / len(prev_means) if prev_means else None

                # Status logic
                if avg_prev_mean is None or baseline_mean is None:
                    status = "no_data"
                elif baseline_mean > avg_prev_mean:
                    status = "increase"
                elif baseline_mean < avg_prev_mean:
                    status = "decrease"
                else:
                    status = "no_change"

                uc_result["analysis"] = {
                    "baseline_year": start_year,
                    "comparison_years": prev_years,
                    "baseline_mean": baseline_mean,
                    "avg_prev_mean": avg_prev_mean,
                    "status": status
                }

                # Save to DB for caching
                if project_id:
                    YearlyComparisonAnalysis.objects.update_or_create(
                        project_id=project_id,
                        analysis_type=analysis_type,
                        baseline_year=start_year,
                        area_type="uc",
                        uc_name=uc_name,
                        defaults={
                            "city_name": uc_city,
                            "comparison_years": prev_years,
                            "baseline_mean": baseline_mean,
                            "avg_prev_mean": avg_prev_mean,
                            "status": status
                        }
                    )

                return uc_result

            # Threaded processing
            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(process_uc, features))

        # Add similar logic for "custom" or "kml" if needed
        else:
            results.append({"area_type": area_type, "analysis": "Not implemented"})

        return Response({
            "mode": "yearly_comparison",
            "analysis_type": analysis_type,
            "baseline_year": start_year,
            "compared_years": prev_years,
            "results": results,
            "cached": False
        })

    except Exception as e:
        return Response({"error": "Failed comparison analysis", "details": str(e)}, status=500)


# @api_view(['POST'])
# def yearly_comparison_analysis(request):
#     # Initialize GEE
#     init_ee()

#     start_year = request.data.get("start_year")
#     area_type = request.data.get("area_type")
#     city_name = request.data.get("city_name")
#     geometry_data = request.data.get("geometry")
#     project_id = request.data.get("project_id")
#     comparison_years = int(request.data.get("comparison_years", 3))

#     if not start_year:
#         return Response({"error": "start_year is required"}, status=400)

#     try:
#         start_year = int(start_year)
#     except ValueError:
#         return Response({"error": "start_year must be an integer"}, status=400)

#     if comparison_years not in (1, 2, 3):
#         return Response({"error": "comparison_years must be 1, 2, or 3"}, status=400)

#     prev_years = [start_year - i for i in range(1, comparison_years + 1)]
#     analysis_types = ["ndvi", "thermal", "aqi"]
#     results = []

#     try:
#         if area_type == "uc":
#             if not city_name:
#                 return Response({"error": "city_name is required for area_type 'uc'."}, status=400)

#             # ------------------- Step 1: Load UCs from local JSON -------------------
#             ucs_data = load_ucs_from_file(city_name)
#             if not ucs_data:
#                 # fallback to DB
#                 ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)
#                 if not ucs.exists():
#                     return Response({"error": "No UCs found for given city_name"}, status=404)

#                 geojson = serialize(
#                     "geojson", ucs,
#                     geometry_field="geometry",
#                     fields=("uc_name", "city_name")
#                 )
#                 ucs_data = json.loads(geojson)

#                 file_path = os.path.join(settings.BASE_DIR, "data", f"{city_name.lower()}_ucs.json")
#                 os.makedirs(os.path.dirname(file_path), exist_ok=True)
#                 with open(file_path, "w") as f:
#                     json.dump(ucs_data, f)

#             # ------------------- Step 2: Process each UC -------------------
#             def process_uc(feature):
#                 uc_name = feature["properties"]["uc_name"]
#                 uc_city = feature["properties"]["city_name"]
#                 uc_polygon = ee.Geometry(feature["geometry"])
#                 uc_result = {"uc_name": uc_name, "city_name": uc_city, "analysis": {}}

#                 for atype in analysis_types:
#                     # ------------------- Check yearly comparison cache -------------------
#                     cached = None
#                     if project_id:
#                         cached_qs = YearlyComparisonAnalysis.objects.filter(
#                         project_id=project_id,
#                         analysis_type=atype,
#                         baseline_year=start_year,
#                         area_type="uc",
#                         uc_name=uc_name
#                     )

#                     if cached_qs.exists():
#                         uc_result["analysis"][atype] = []
#                         for cached in cached_qs:
#                             map_layer = None
#                             if cached.map_layer_path and os.path.exists(cached.map_layer_path):
#                                 with open(cached.map_layer_path, "r") as f:
#                                     map_layer = json.load(f)

#                             uc_result["analysis"][atype].append({
#                                 "baseline_year": cached.baseline_year,
#                                 "comparison_years": cached.comparison_years,
#                                 "baseline_mean": cached.baseline_mean,
#                                 "avg_prev_mean": cached.avg_prev_mean,
#                                 "map_layer": map_layer,
#                                 "status": cached.status
#                             })
#                         continue  # don’t recompute if all cached


#                     # ------------------- Run GEE analysis if not cached -------------------
#                     baseline_start = f"{start_year}-01-01"
#                     baseline_end = f"{start_year+1}-01-01"
#                     res = perform_analysis_for_polygon(atype, uc_polygon, baseline_start, baseline_end)
#                     baseline_stats = res.get("stats")
#                     baseline_mean = baseline_stats.get("mean") if baseline_stats else None
#                     map_layer = res.get("map_layer")

#                     # Previous years
#                     prev_means = []
#                     for year in prev_years:
#                         year_start = f"{year}-01-01"
#                         year_end = f"{year+1}-01-01"
#                         prev_res = perform_analysis_for_polygon(atype, uc_polygon, year_start, year_end)
#                         prev_mean = prev_res.get("stats", {}).get("mean")
#                         if prev_mean is not None:
#                             prev_means.append(prev_mean)

#                     avg_prev_mean = sum(prev_means)/len(prev_means) if prev_means else None

#                     # Decide status
#                     if avg_prev_mean is None or baseline_mean is None:
#                         status = "no_data"
#                     elif baseline_mean > avg_prev_mean:
#                         status = "increase"
#                     elif baseline_mean < avg_prev_mean:
#                         status = "decrease"
#                     else:
#                         status = "no_change"

#                     # ------------------- Save yearly comparison cache -------------------
#                     if project_id:
#                         file_name = f"{project_id}_{atype}_{start_year}_uc_{uc_name}.json"
#                         file_path = os.path.join(settings.MEDIA_ROOT, "yearly_comparison_layers", file_name)
#                         os.makedirs(os.path.dirname(file_path), exist_ok=True)
#                         with open(file_path, "w") as f:
#                             json.dump(map_layer, f)

#                         YearlyComparisonAnalysis.objects.update_or_create(
#                             project=Project.objects.get(id=project_id),
#                             analysis_type=atype,
#                             baseline_year=start_year,
#                             area_type="uc",
#                             uc_name=uc_name,
#                             defaults={
#                                 "city_name": uc_city,
#                                 "comparison_years": prev_years,
#                                 "baseline_mean": baseline_mean,
#                                 "avg_prev_mean": avg_prev_mean,
#                                 "status": status,
#                                 "stats": baseline_stats,
#                                 "map_layer_path": file_path
#                             }
#                         )

#                     uc_result["analysis"][atype] = {
#                         "baseline_year": start_year,
#                         "comparison_years": prev_years,
#                         "baseline_mean": baseline_mean,
#                         "avg_prev_mean": avg_prev_mean,
#                         "map_layer": map_layer,
#                         "status": status
#                     }

#                 return uc_result

#             # ------------------- Step 3: Use ThreadPoolExecutor -------------------
#             with ThreadPoolExecutor(max_workers=5) as executor:
#                 results = list(executor.map(process_uc, ucs_data.get("features", [])))

#         # Can handle custom/kml similarly if needed

#         return Response({
#             "mode": "yearly_comparison",
#             "baseline_year": start_year,
#             "compared_years": prev_years,
#             "results": results
#         })

#     except Exception as e:
#         return Response({"error": "Failed comparison analysis", "details": str(e)}, status=500)



# @api_view(['POST'])
# def yearly_comparison_analysis(request):
#     # Initialize GEE
#     init_ee()

#     start_year = request.data.get("start_year")
#     area_type = request.data.get("area_type")
#     city_name = request.data.get("city_name")
#     geometry_data = request.data.get("geometry")
#     project_id = request.data.get("project_id")
#     comparison_years = int(request.data.get("comparison_years", 3))

#     if not start_year:
#         return Response({"error": "start_year is required"}, status=400)

#     try:
#         start_year = int(start_year)
#     except ValueError:
#         return Response({"error": "start_year must be an integer"}, status=400)

#     if comparison_years not in (1, 2, 3):
#         return Response({"error": "comparison_years must be 1, 2, or 3"}, status=400)

#     prev_years = [start_year - i for i in range(1, comparison_years + 1)]
#     analysis_types = ["ndvi", "thermal", "aqi"]
#     results = []

#     try:
#         if area_type == "uc":
#             if not city_name:
#                 return Response({"error": "city_name is required for area_type 'uc'."}, status=400)

#             # ------------------- Step 1: Load UCs from local JSON -------------------
#             ucs_data = load_ucs_from_file(city_name)
#             if not ucs_data:
#                 # fallback to DB
#                 ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)
#                 if not ucs.exists():
#                     return Response({"error": "No UCs found for given city_name"}, status=404)

#                 geojson = serialize(
#                     "geojson", ucs,
#                     geometry_field="geometry",
#                     fields=("uc_name", "city_name")
#                 )
#                 ucs_data = json.loads(geojson)

#                 file_path = os.path.join(settings.BASE_DIR, "data", f"{city_name.lower()}_ucs.json")
#                 os.makedirs(os.path.dirname(file_path), exist_ok=True)
#                 with open(file_path, "w") as f:
#                     json.dump(ucs_data, f)

#             # ------------------- Step 2: Process each UC -------------------
#             def process_uc(feature):
#                 uc_name = feature["properties"]["uc_name"]
#                 uc_city = feature["properties"]["city_name"]
#                 uc_polygon = ee.Geometry(feature["geometry"])

#                 uc_result = {"uc_name": uc_name, "city_name": uc_city, "analysis": {}}

#                 for atype in analysis_types:
#                     # Check cache in DB first
#                     cached = None
#                     if project_id:
#                         cached = AreaAnalysis.objects.filter(
#                             project_id=project_id,
#                             analysis_type=atype,
#                             start_date=f"{start_year}-01-01",
#                             end_date=f"{start_year+1}-01-01",
#                             area_type="uc",
#                             uc_name=uc_name
#                         ).first()

#                     if cached and cached.stats and cached.map_layer_path and os.path.exists(cached.map_layer_path):
#                         # Load cached map layer
#                         with open(cached.map_layer_path, "r") as f:
#                             map_layer = json.load(f)
#                         stats = cached.stats
#                     else:
#                         # Run GEE analysis
#                         baseline_start = f"{start_year}-01-01"
#                         baseline_end = f"{start_year+1}-01-01"
#                         res = perform_analysis_for_polygon(atype, uc_polygon, baseline_start, baseline_end)
#                         map_layer = res.get("map_layer")
#                         stats = res.get("stats")

#                         # Save cache if project_id
#                         if project_id:
#                             file_name = f"{project_id}_{atype}_{start_year}_{start_year+1}_uc_{uc_name}.json"
#                             file_path = os.path.join(settings.MEDIA_ROOT, "map_layers", file_name)
#                             os.makedirs(os.path.dirname(file_path), exist_ok=True)
#                             with open(file_path, "w") as f:
#                                 json.dump(map_layer, f)

#                             AreaAnalysis.objects.update_or_create(
#                                 project_id=project_id,
#                                 analysis_type=atype,
#                                 start_date=baseline_start,
#                                 end_date=baseline_end,
#                                 area_type="uc",
#                                 uc_name=uc_name,
#                                 defaults={
#                                     "city_name": uc_city,
#                                     "stats": stats,
#                                     "map_layer_path": file_path
#                                 }
#                             )

#                     # ------------------- Previous years -------------------
#                     prev_means = []
#                     for year in prev_years:
#                         year_start = f"{year}-01-01"
#                         year_end = f"{year+1}-01-01"
#                         prev_cached = None
#                         if project_id:
#                             prev_cached = AreaAnalysis.objects.filter(
#                                 project_id=project_id,
#                                 analysis_type=atype,
#                                 start_date=year_start,
#                                 end_date=year_end,
#                                 area_type="uc",
#                                 uc_name=uc_name
#                             ).first()
#                         if prev_cached and prev_cached.stats:
#                             mean_val = prev_cached.stats.get("mean")
#                         else:
#                             prev_res = perform_analysis_for_polygon(atype, uc_polygon, year_start, year_end)
#                             mean_val = prev_res.get("stats", {}).get("mean")
#                             if project_id and prev_res.get("stats"):
#                                 # cache previous year
#                                 file_name = f"{project_id}_{atype}_{year}_{year+1}_uc_{uc_name}.json"
#                                 file_path = os.path.join(settings.MEDIA_ROOT, "map_layers", file_name)
#                                 os.makedirs(os.path.dirname(file_path), exist_ok=True)
#                                 with open(file_path, "w") as f:
#                                     json.dump(prev_res.get("map_layer"), f)

#                                 AreaAnalysis.objects.update_or_create(
#                                     project_id=project_id,
#                                     analysis_type=atype,
#                                     start_date=year_start,
#                                     end_date=year_end,
#                                     area_type="uc",
#                                     uc_name=uc_name,
#                                     defaults={
#                                         "city_name": uc_city,
#                                         "stats": prev_res.get("stats"),
#                                         "map_layer_path": file_path
#                                     }
#                                 )
#                         if mean_val is not None:
#                             prev_means.append(mean_val)

#                     avg_prev_mean = sum(prev_means)/len(prev_means) if prev_means else None

#                     # Decide status
#                     if avg_prev_mean is None or stats.get("mean") is None:
#                         status = "no_data"
#                     elif stats.get("mean") > avg_prev_mean:
#                         status = "increase"
#                     elif stats.get("mean") < avg_prev_mean:
#                         status = "decrease"
#                     else:
#                         status = "no_change"

#                     uc_result["analysis"][atype] = {
#                         "baseline_year": start_year,
#                         "comparison_years": prev_years,
#                         "baseline_mean": stats.get("mean"),
#                         "avg_prev_mean": avg_prev_mean,
#                         "map_layer": map_layer,
#                         "status": status
#                     }

#                 return uc_result

#             # ------------------- Step 3: Use ThreadPoolExecutor -------------------
#             with ThreadPoolExecutor(max_workers=5) as executor:
#                 results = list(executor.map(process_uc, ucs_data.get("features", [])))

#         # Can handle custom/kml similarly if needed

#         return Response({
#             "mode": "yearly_comparison",
#             "baseline_year": start_year,
#             "compared_years": prev_years,
#             "results": results
#         })

#     except Exception as e:
#         return Response({"error": "Failed comparison analysis", "details": str(e)}, status=500)


# @api_view(['POST'])
# def yearly_comparison_analysis(request):
#     # Ensure Earth Engine is initialized
#     init_ee()

#     start_year = request.data.get("start_year")
#     area_type = request.data.get("area_type")       # uc/custom/kml
#     city_name = request.data.get("city_name")       # used for uc
#     geometry_data = request.data.get("geometry")    # used for custom
#     project_id = request.data.get("project_id")     # optional
#     comparison_years = request.data.get("comparison_years", 3)  # 1|2|3

#     if not start_year:
#         return Response({"error": "start_year is required"}, status=400)

#     try:
#         start_year = int(start_year)
#     except ValueError:
#         return Response({"error": "start_year must be an integer"}, status=400)

#     # validate comparison_years
#     try:
#         comparison_years = int(comparison_years)
#         if comparison_years not in (1, 2, 3):
#             return Response({"error": "comparison_years must be 1, 2, or 3"}, status=400)
#     except ValueError:
#         return Response({"error": "comparison_years must be integer 1/2/3"}, status=400)

#     prev_years = [start_year - i for i in range(1, comparison_years + 1)]
#     analysis_types = ["ndvi", "thermal", "aqi"]
#     results = []

#     try:
#         if area_type == "uc":
#             if not city_name:
#                 return Response({"error": "city_name is required for area_type 'uc'."}, status=400)

#             # Load UC data from local file
#             ucs_data = load_ucs_from_file(city_name)
#             if not ucs_data:
#                 # If file not exists, fetch from DB and save locally
#                 ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)
#                 if not ucs.exists():
#                     return Response({"error": "No UCs found for given city_name"}, status=404)

#                 geojson = serialize(
#                     "geojson", ucs,
#                     geometry_field="geometry",
#                     fields=("uc_name", "city_name")
#                 )
#                 ucs_data = json.loads(geojson)

#                 file_path = os.path.join(DATA_DIR, f"{city_name.lower()}_ucs.json")
#                 os.makedirs(DATA_DIR, exist_ok=True)
#                 with open(file_path, "w") as f:
#                     json.dump(ucs_data, f)

#             # Run GEE analysis per UC
#             for feature in ucs_data.get("features", []):
#                 uc_name = feature["properties"]["uc_name"]
#                 uc_city = feature["properties"]["city_name"]
#                 uc_polygon = ee.Geometry(feature["geometry"])  # directly from GeoJSON

#                 uc_result = {"uc_name": uc_name, "city_name": uc_city, "analysis": {}}

#                 for atype in analysis_types:
#                     # baseline stats for current year
#                     baseline_start = f"{start_year}-01-01"
#                     baseline_end = f"{start_year+1}-01-01"

#                     # Check if cached result exists
#                     cached = None
#                     if project_id:
#                         cached = AreaAnalysis.objects.filter(
#                             project_id=project_id,
#                             analysis_type=atype,
#                             start_date=baseline_start,
#                             end_date=baseline_end,
#                             area_type="uc",
#                             uc_name=uc_name
#                         ).first()

#                     if cached and cached.stats and cached.map_layer_path and os.path.exists(cached.map_layer_path):
#                         # Load from cache
#                         with open(cached.map_layer_path, "r") as f:
#                             map_layer = json.load(f)
#                         stats = cached.stats
#                     else:
#                         # Run new analysis
#                         res = perform_analysis_for_polygon(atype, uc_polygon, baseline_start, baseline_end)
#                         stats = res.get("stats")
#                         map_layer = res.get("map_layer")

#                         # Save cache if project_id
#                         if project_id:
#                             file_name = f"{project_id}_{atype}_{start_year}_{start_year+1}_uc_{uc_name}.json"
#                             file_path = os.path.join(settings.MEDIA_ROOT, "map_layers", file_name)
#                             os.makedirs(os.path.dirname(file_path), exist_ok=True)
#                             with open(file_path, "w") as f:
#                                 json.dump(map_layer, f)

#                             AreaAnalysis.objects.update_or_create(
#                                 project_id=project_id,
#                                 analysis_type=atype,
#                                 start_date=baseline_start,
#                                 end_date=baseline_end,
#                                 area_type="uc",
#                                 uc_name=uc_name,
#                                 defaults={
#                                     "city_name": uc_city,
#                                     "stats": stats,
#                                     "map_layer_path": file_path
#                                 }
#                             )

#                     # previous years comparison
#                     prev_means = []
#                     for year in prev_years:
#                         year_start = f"{year}-01-01"
#                         year_end = f"{year+1}-01-01"
#                         # Check cache for previous years
#                         prev_cached = None
#                         if project_id:
#                             prev_cached = AreaAnalysis.objects.filter(
#                                 project_id=project_id,
#                                 analysis_type=atype,
#                                 start_date=year_start,
#                                 end_date=year_end,
#                                 area_type="uc",
#                                 uc_name=uc_name
#                             ).first()

#                         if prev_cached and prev_cached.stats:
#                             prev_mean = prev_cached.stats.get("mean")
#                         else:
#                             prev_res = perform_analysis_for_polygon(atype, uc_polygon, year_start, year_end)
#                             prev_mean = prev_res["stats"].get("mean") if prev_res.get("stats") else None

#                         if prev_mean is not None:
#                             prev_means.append(prev_mean)

#                     avg_prev_mean = sum(prev_means)/len(prev_means) if prev_means else None

#                     # decide status
#                     if avg_prev_mean is None or stats.get("mean") is None:
#                         status = "no_data"
#                     elif stats["mean"] > avg_prev_mean:
#                         status = "increase"
#                     elif stats["mean"] < avg_prev_mean:
#                         status = "decrease"
#                     else:
#                         status = "no_change"

#                     uc_result["analysis"][atype] = {
#                         "baseline_year": start_year,
#                         "comparison_years": prev_years,
#                         "baseline_mean": stats.get("mean") if stats else None,
#                         "avg_prev_mean": avg_prev_mean,
#                         "map_layer": map_layer,
#                         "status": status
#                     }

#                 results.append(uc_result)

#         # Similarly, you can handle 'custom' and 'kml' if required

#         return Response({
#             "mode": "yearly_comparison",
#             "baseline_year": start_year,
#             "compared_years": prev_years,
#             "results": results
#         })

#     except Exception as e:
#         return Response({"error": "Failed comparison analysis", "details": str(e)}, status=500)


# @api_view(['POST'])
# def yearly_comparison_analysis(request):
#     init_ee()  # Ensure EE initialized

#     start_year = request.data.get("start_year")
#     area_type = request.data.get("area_type")
#     city_name = request.data.get("city_name")
#     geometry_data = request.data.get("geometry")
#     project_id = request.data.get("project_id")
#     comparison_years = request.data.get("comparison_years", 3)

#     # ------------------- Validate inputs -------------------
#     if not start_year:
#         return Response({"error": "start_year is required"}, status=400)
#     try:
#         start_year = int(start_year)
#     except ValueError:
#         return Response({"error": "start_year must be integer"}, status=400)

#     try:
#         comparison_years = int(comparison_years)
#         if comparison_years not in (1, 2, 3):
#             return Response({"error": "comparison_years must be 1, 2, or 3"}, status=400)
#     except ValueError:
#         return Response({"error": "comparison_years must be integer 1/2/3"}, status=400)

#     prev_years = [start_year - i for i in range(1, comparison_years + 1)]
#     analysis_types = ["ndvi", "thermal", "aqi"]
#     results = []

#     try:
#         if area_type == "uc":
#             if not city_name:
#                 return Response({"error": "city_name required for UC analysis"}, status=400)

#             # ------------------- Step 1: Check cache -------------------
#             if project_id:
#                 cached_results = YearlyComparisonAnalysis.objects.filter(
#                     project_id=project_id,
#                     start_year=start_year,
#                     comparison_years=comparison_years,
#                     area_type="uc",
#                     city_name__iexact=city_name
#                 ).order_by("uc_name")

#                 if cached_results.exists():
#                     results = []
#                     for cached in cached_results:
#                         map_layer = None
#                         if cached.map_layer_path and os.path.exists(cached.map_layer_path):
#                             with open(cached.map_layer_path, "r") as f:
#                                 map_layer = json.load(f)

#                         results.append({
#                             "uc_name": cached.uc_name,
#                             "city_name": cached.city_name,
#                             "analysis_type": cached.analysis_type,
#                             "baseline_year": cached.start_year,
#                             "comparison_years": cached.comparison_years,
#                             "baseline_mean": cached.baseline_mean,
#                             "avg_prev_mean": cached.avg_prev_mean,
#                             "status": cached.status,
#                             "map_layer": map_layer
#                         })
#                     return Response({
#                         "message": "Cached yearly comparison returned",
#                         "baseline_year": start_year,
#                         "compared_years": prev_years,
#                         "results": results
#                     })

#             # ------------------- Step 2: Fresh analysis -------------------
#             ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)
#             if not ucs.exists():
#                 return Response({"error": "No UCs found for given city_name"}, status=404)

#             for uc in ucs:
#                 uc_polygon = ee.Geometry(json.loads(uc.geometry.geojson))
#                 uc_result = {"uc_name": uc.uc_name, "city_name": uc.city_name, "analysis": {}}

#                 for atype in analysis_types:
#                     baseline_start = f"{start_year}-01-01"
#                     baseline_end = f"{start_year + 1}-01-01"
#                     baseline_res = perform_analysis_for_polygon(atype, uc_polygon, baseline_start, baseline_end)
#                     baseline_mean = baseline_res["stats"].get("mean")

#                     prev_means = []
#                     for year in prev_years:
#                         year_start = f"{year}-01-01"
#                         year_end = f"{year + 1}-01-01"
#                         res = perform_analysis_for_polygon(atype, uc_polygon, year_start, year_end)
#                         if res["stats"].get("mean") is not None:
#                             prev_means.append(res["stats"]["mean"])

#                     avg_prev_mean = sum(prev_means) / len(prev_means) if prev_means else None

#                     if avg_prev_mean is None or baseline_mean is None:
#                         status = "no_data"
#                     elif baseline_mean > avg_prev_mean:
#                         status = "increase"
#                     elif baseline_mean < avg_prev_mean:
#                         status = "decrease"
#                     else:
#                         status = "no_change"

#                     uc_result["analysis"][atype] = {
#                         "baseline_year": start_year,
#                         "comparison_years": prev_years,
#                         "baseline_mean": baseline_mean,
#                         "avg_prev_mean": avg_prev_mean,
#                         "map_layer": baseline_res["map_layer"],
#                         "status": status
#                     }

#                     # ------------------- Save results -------------------
#                     if project_id:
#                         layer_content = baseline_res.get("map_layer")
#                         stats = baseline_res.get("stats")
#                         uc_name = uc.uc_name
#                         city_name = uc.city_name

#                         # Save map_layer JSON
#                         file_name = f"{project_id}_{atype}_{start_year}_{comparison_years}yrs_uc_{uc_name}.json"
#                         file_path = os.path.join(settings.MEDIA_ROOT, "map_layers", file_name)
#                         os.makedirs(os.path.dirname(file_path), exist_ok=True)
#                         with open(file_path, "w") as f:
#                             json.dump(layer_content, f)

#                         # Save in YearlyComparisonAnalysis table
#                         YearlyComparisonAnalysis.objects.update_or_create(
#                             project_id=project_id,
#                             analysis_type=atype,
#                             start_year=start_year,
#                             comparison_years=comparison_years,
#                             area_type="uc",
#                             uc_name=uc_name,
#                             defaults={
#                                 "city_name": city_name,
#                                 "baseline_mean": baseline_mean,
#                                 "avg_prev_mean": avg_prev_mean,
#                                 "status": status,
#                                 "map_layer_path": file_path
#                             }
#                         )

#                 results.append(uc_result)

#         return Response({
#             "message": "Yearly comparison completed",
#             "baseline_year": start_year,
#             "compared_years": prev_years,
#             "results": results
#         })

#     except Exception as e:
#         return Response({"error": "Failed comparison analysis", "details": str(e)}, status=500)


# @api_view(['POST'])
# def yearly_comparison_analysis(request):
#     # Ensure Earth Engine is initialized
#     init_ee()

#     start_year = request.data.get("start_year")     # required (int)
#     area_type = request.data.get("area_type")       # uc/custom/kml
#     city_name = request.data.get("city_name")       # used for uc
#     geometry_data = request.data.get("geometry")    # used for custom
#     project_id = request.data.get("project_id")     # used for kml (optional)
#     comparison_years = request.data.get("comparison_years", 3)  # 1|2|3 (default 3)

#     if not start_year:
#         return Response({"error": "start_year is required"}, status=400)
#     try:
#         start_year = int(start_year)
#     except ValueError:
#         return Response({"error": "start_year must be an integer"}, status=400)

#     # polygon creation
#     try:
#         if area_type == "uc":
#             if not city_name:
#                 return Response({"error": "city_name is required for area_type 'uc'."}, status=400)
#             uc = UnionCouncil.objects.filter(city_name__iexact=city_name).first()
#             if not uc:
#                 return Response({"error": "No UC found for given city_name"}, status=404)
#             polygon = ee.Geometry(json.loads(uc.geometry.geojson))

#         elif area_type == "custom":
#             if not geometry_data:
#                 return Response({"error": "geometry is required for area_type 'custom'."}, status=400)
#             geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
#             polygon = ee.Geometry(geom_json)

#         elif area_type == "kml":
#             if not project_id:
#                 return Response({"error": "project_id is required for area_type 'kml'."}, status=400)
#             try:
#                 project = Project.objects.get(id=project_id)
#             except Project.DoesNotExist:
#                 return Response({"error": "Project not found"}, status=404)
#             if not project.kml_file:
#                 return Response({"error": "No KML file found for this project"}, status=404)

#             file_name = os.path.splitext(os.path.basename(project.kml_file.name))[0]
#             city_name_from_file = file_name.split("_")[0].capitalize()
#             uc_data = load_ucs_from_file(city_name_from_file)
#             if not uc_data:
#                 return Response({"error": f"No local UC data found for {city_name_from_file}"}, status=404)

#             polygon = None  # handled later if multi-feature

#         else:
#             return Response({"error": "Invalid area_type"}, status=400)
#     except Exception as e:
#         return Response({"error": "Failed to build geometry", "details": str(e)}, status=500)

#     # validate comparison_years
#     try:
#         comparison_years = int(comparison_years)
#         if comparison_years not in (1, 2, 3):
#             return Response({"error": "comparison_years must be 1, 2, or 3"}, status=400)
#     except ValueError:
#         return Response({"error": "comparison_years must be integer 1/2/3"}, status=400)

#     prev_years = [start_year - i for i in range(1, comparison_years + 1)]
#     analysis_types = ["ndvi", "thermal", "aqi"]

#     results = {}
#     layers = {}

#     try:
#         baseline_start = f"{start_year}-01-01"
#         baseline_end = f"{start_year + 1}-01-01"

#         for atype in analysis_types:
#             # baseline stats
#             baseline_res = perform_analysis_for_polygon(atype, polygon, baseline_start, baseline_end)
#             baseline_mean = baseline_res["stats"].get("mean")

#             # collect previous year means
#             prev_means = []
#             for year in prev_years:
#                 year_start = f"{year}-01-01"
#                 year_end = f"{year + 1}-01-01"
#                 res = perform_analysis_for_polygon(atype, polygon, year_start, year_end)
#                 if res["stats"].get("mean") is not None:
#                     prev_means.append(res["stats"]["mean"])

#             avg_prev_mean = sum(prev_means) / len(prev_means) if prev_means else None

#             # decide change status
#             if avg_prev_mean is None or baseline_mean is None:
#                 status = "no_data"
#             elif baseline_mean > avg_prev_mean:
#                 status = "increase"
#             elif baseline_mean < avg_prev_mean:
#                 status = "decrease"
#             else:
#                 status = "no_change"

#             results[atype] = {
#                 "baseline_year": start_year,
#                 "comparison_years": prev_years,
#                 "baseline_mean": baseline_mean,
#                 "avg_prev_mean": avg_prev_mean,
#                 "map_layer": baseline_res["map_layer"]
#             }

#             # return 3 layers for frontend (toggle handled there)
#             layers[atype] = {
#                 "increase": {"visible": status == "increase", "color": "green"},
#                 "decrease": {"visible": status == "decrease", "color": "red"},
#                 "no_change": {"visible": status == "no_change", "color": "gray"}
#             }

#         return Response({
#             "mode": "comparison",
#             "baseline_year": start_year,
#             "compared_years": prev_years,
#             "results": results,
#             "layers": layers
#         })

#     except Exception as e:
#         return Response({"error": "Failed comparison analysis", "details": str(e)}, status=500)

# @api_view(['POST'])
# def yearly_comparison_analysis(request):
#     start_date_str = request.data.get("start_date")
#     end_date_str = request.data.get("end_date")
#     area_type = request.data.get("area_type")
#     city_name = request.data.get("city_name")
#     geometry_data = request.data.get("geometry")

#     if not start_date_str or not end_date_str:
#         return Response({"error": "start_date and end_date are required"}, status=400)

#     try:
        
#         start_date = datetime.strptime(start_date_str, "%m/%d/%Y")
#         end_date = datetime.strptime(end_date_str, "%m/%d/%Y")
#     except ValueError:
#         return Response({"error": "Invalid date format. Use MM/DD/YYYY"}, status=400)

    
#     if area_type == "uc":
#         uc = UnionCouncil.objects.filter(city_name=city_name).first()
#         if not uc:
#             return Response({"error": "No UC found"}, status=404)
#         polygon = ee.Geometry(json.loads(uc.geometry.geojson))
#     else:
#         polygon = ee.Geometry(geometry_data)

#     analysis_types = ["ndvi", "thermal", "aqi"]
#     results = {atype: [] for atype in analysis_types}

#     for atype in analysis_types:
#         for year_offset in range(0, 3):  
#             year_start = (start_date - relativedelta(years=year_offset)).strftime("%Y-%m-%d")
#             year_end = (end_date - relativedelta(years=year_offset)).strftime("%Y-%m-%d")
#             year_val = start_date.year - year_offset

#             try:
#                 analysis_result = perform_analysis_for_polygon(atype, polygon, year_start, year_end)
#                 results[atype].append({
#                     "year": year_val,
#                     "mean": analysis_result["stats"]["mean"],
#                     "min": analysis_result["stats"]["min"],
#                     "max": analysis_result["stats"]["max"]
#                 })
#             except Exception as e:
#                 results[atype].append({
#                     "year": year_val,
#                     "error": str(e)
#                 })

#     return Response(results)
