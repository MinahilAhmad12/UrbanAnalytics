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
from urbananalytics.models import AreaAnalysis, Project
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


DATA_DIR = os.path.join(settings.BASE_DIR, "local_data")
os.makedirs(DATA_DIR, exist_ok=True)

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
        elif project.kml_file:
            file_name = os.path.splitext(os.path.basename(project.kml_file.name))[0]
            city_name = file_name.split("_")[0].capitalize()
        else:
            return Response({"error": "Project has no location_name or kml_file"}, status=400)

        
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

    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=404)

# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def get_ucs_by_city(request, city_name):
#     ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)

#     geojson = serialize('geojson', ucs, geometry_field='geometry', fields=('uc_name', 'city_name'))

#     return Response(json.loads(geojson))


service_account_key_path = r'C:\Users\User\Documents\urbananalytics-460415-f557e7903d83.json'
credentials = ee.ServiceAccountCredentials(
    email='gee-service-account@urbananalytics-460415.iam.gserviceaccount.com',
    key_file=service_account_key_path
)
ee.Initialize(credentials, project='urbananalytics-460415')

# @api_view(['POST'])
# def perform_gee_analysis(request):
#     analysis_type = request.data.get("analysis_type")
#     start_date = request.data.get("start_date")
#     end_date = request.data.get("end_date")
#     area_type = request.data.get("area_type")
#     city_name = request.data.get("city_name")
#     geometry_data = request.data.get("geometry")

#     if not analysis_type or not start_date or not end_date or not area_type:
#         return Response({"error": "Missing required parameters"}, status=400)

#     try:
#         results = []

        
#         if area_type == "uc":
#             if not city_name:
#                 return Response({"error": "city_name is required for UC analysis"}, status=400)

#             ucs = UnionCouncil.objects.filter(city_name=city_name)
#             if not ucs.exists():
#                 return Response({"error": "No Union Councils found for the selected city"}, status=404)

#             def process_uc(uc):
#                 try:
#                     geojson_dict = json.loads(uc.geometry.geojson)
#                     polygon = ee.Geometry(geojson_dict)
#                     result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)

#                     return {
#                         "uc_name": uc.uc_name,
#                         "city_name": uc.city_name,
#                         "error": "0",
#                         "map_layer": result.get("map_layer"),
#                         "stats": result.get("stats")
#                     }
#                 except Exception as e:
#                     return {
#                         "uc_name": uc.uc_name,
#                         "city_name": uc.city_name,
#                         "error": "1",
#                         "error_msg": str(e)
#                     }

#             with ThreadPoolExecutor(max_workers=5) as executor:
#                 results = list(executor.map(process_uc, ucs))

        
#         elif area_type in ("custom", "kml"):
#             if not geometry_data:
#                 return Response({"error": "geometry data is required for custom/kml analysis"}, status=400)

#             try:
#                 geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
#                 polygon = ee.Geometry(geom_json)
#                 result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)
#                 results.append(result)
#             except Exception as e:
#                 return Response({"error": "Invalid geometry data", "details": str(e)}, status=400)

#         else:
#             return Response({"error": "Invalid area_type"}, status=400)

#         return Response({
#             "message": f"{analysis_type.upper()} analysis performed",
#             "results": results
#         })

#     except Exception as e:
#         return Response({"error": "Failed to perform analysis", "details": str(e)}, status=500)


# def load_ucs_from_file(city_name, bounds_polygon=None):
#     """Load UC data for a city from local JSON file, optionally filtering by bounds."""
#     file_path = os.path.join(DATA_DIR, "ucs.json")
#     if not os.path.exists(file_path):
#         return None

#     with open(file_path, "r") as f:
#         all_ucs = json.load(f)

#     # If no bounds provided, return all UCs for that city
#     if not bounds_polygon:
#         return [uc for uc in all_ucs if uc["properties"]["city_name"].lower() == city_name.lower()]

#     # Otherwise, filter only UCs intersecting bounds
#     matching_ucs = []
#     for uc in all_ucs:
#         try:
#             uc_geom = GEOSGeometry(json.dumps(uc["geometry"]))
#             if uc_geom.intersects(bounds_polygon):
#                 matching_ucs.append(uc)
#         except Exception:
#             continue

#     return matching_ucs
def load_ucs_from_file(city_name):
    """Load UC data for a city from local JSON file."""
    file_path = os.path.join(DATA_DIR, f"{city_name.lower()}_ucs.json")
    if not os.path.exists(file_path):
        return None

    with open(file_path, "r") as f:
        return json.load(f)  # already GeoJSON dict


@api_view(['POST'])
def perform_gee_analysis(request):
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

        # ---- CASE 1: UC (manual entry) ----
        if area_type == "uc":
            if not city_name:
                return Response({"error": "city_name is required for UC analysis"}, status=400)

            uc_data = load_ucs_from_file(city_name)
            if not uc_data:
                return Response({"error": f"No local UC data found for {city_name}"}, status=404)

            features = uc_data.get("features", [])
            if not features:
                return Response({"error": "No Union Councils found in local file"}, status=404)

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

        # ---- CASE 2: Custom-drawn geometry ----
        elif area_type == "custom":
            if not geometry_data:
                return Response({"error": "geometry data is required for custom analysis"}, status=400)

            geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
            polygon = ee.Geometry(geom_json)
            result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)
            results.append(result)

        # ---- CASE 3: KML Upload (get bounds → find UCs locally) ----
       # ---- CASE 3: KML Upload (use city name from file → process all UCs) ----
        elif area_type == "kml":
            if not project_id:
                return Response({"error": "project_id is required for KML analysis"}, status=400)

            try:
                project = Project.objects.get(id=project_id)
            except Project.DoesNotExist:
                return Response({"error": "Project not found"}, status=404)

            if not project.kml_file:
                return Response({"error": "No KML file found for this project"}, status=404)

            # Extract city name from KML file name
            file_name = os.path.splitext(os.path.basename(project.kml_file.name))[0]
            city_name = file_name.split("_")[0].capitalize()

            # Load local UC data for the city
            uc_data = load_ucs_from_file(city_name)
            if not uc_data:
                return Response({"error": f"No local UC data found for {city_name}"}, status=404)

            features = uc_data.get("features", [])
            if not features:
                return Response({"error": "No Union Councils found in local file"}, status=404)

            # Perform analysis for each UC
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


        else:
            return Response({"error": "Invalid area_type"}, status=400)

        return Response({
            "message": f"{analysis_type.upper()} analysis performed",
            "results": results
        })

    except Exception as e:
        return Response({"error": "Failed to perform analysis", "details": str(e)}, status=500)



def perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date):
    scale = 30

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
        scale = 7000
       


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
    start_date_str = request.data.get("start_date")
    end_date_str = request.data.get("end_date")
    area_type = request.data.get("area_type")
    city_name = request.data.get("city_name")
    geometry_data = request.data.get("geometry")

    if not start_date_str or not end_date_str:
        return Response({"error": "start_date and end_date are required"}, status=400)

    try:
        
        start_date = datetime.strptime(start_date_str, "%m/%d/%Y")
        end_date = datetime.strptime(end_date_str, "%m/%d/%Y")
    except ValueError:
        return Response({"error": "Invalid date format. Use MM/DD/YYYY"}, status=400)

    
    if area_type == "uc":
        uc = UnionCouncil.objects.filter(city_name=city_name).first()
        if not uc:
            return Response({"error": "No UC found"}, status=404)
        polygon = ee.Geometry(json.loads(uc.geometry.geojson))
    else:
        polygon = ee.Geometry(geometry_data)

    analysis_types = ["ndvi", "thermal", "aqi"]
    results = {atype: [] for atype in analysis_types}

    for atype in analysis_types:
        for year_offset in range(0, 3):  
            year_start = (start_date - relativedelta(years=year_offset)).strftime("%Y-%m-%d")
            year_end = (end_date - relativedelta(years=year_offset)).strftime("%Y-%m-%d")
            year_val = start_date.year - year_offset

            try:
                analysis_result = perform_analysis_for_polygon(atype, polygon, year_start, year_end)
                results[atype].append({
                    "year": year_val,
                    "mean": analysis_result["stats"]["mean"],
                    "min": analysis_result["stats"]["min"],
                    "max": analysis_result["stats"]["max"]
                })
            except Exception as e:
                results[atype].append({
                    "year": year_val,
                    "error": str(e)
                })

    return Response(results)
