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

import ee

def init_ee():
    """Initialize Earth Engine lazily when needed."""
    service_account_key_path = r'C:\Users\User\Documents\urbananalytics-460415-f557e7903d83.json'
    credentials = ee.ServiceAccountCredentials(
        email='gee-service-account@urbananalytics-460415.iam.gserviceaccount.com',
        key_file=service_account_key_path
    )
    try:
        ee.Initialize(credentials, project='urbananalytics-460415')
    except Exception as e:
        print("Error initializing Earth Engine:", e)
        


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
        
        if project_id and area_type in ["uc", "kml"]:
            cached_results = AreaAnalysis.objects.filter(
                project_id=project_id,
                analysis_type=analysis_type,
                start_date=start_date,
                end_date=end_date,
                area_type=area_type
            ).order_by('uc_name')  

            if cached_results.exists():
                results = []
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

        results = []

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

            try:
                project = Project.objects.get(id=project_id)
            except Project.DoesNotExist:
                return Response({"error": "Project not found"}, status=404)

            if not project.kml_file:
                return Response({"error": "No KML file found for this project"}, status=404)

            file_name = os.path.splitext(os.path.basename(project.kml_file.name))[0]
            city_name = file_name.split("_")[0].capitalize()

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
    # Ensure Earth Engine is initialized
    init_ee()

    start_year = request.data.get("start_year")     # required (int)
    area_type = request.data.get("area_type")       # uc/custom/kml
    city_name = request.data.get("city_name")       # used for uc
    geometry_data = request.data.get("geometry")    # used for custom
    project_id = request.data.get("project_id")     # used for kml (optional)
    comparison_years = request.data.get("comparison_years", 3)  # 1|2|3 (default 3)

    if not start_year:
        return Response({"error": "start_year is required"}, status=400)
    try:
        start_year = int(start_year)
    except ValueError:
        return Response({"error": "start_year must be an integer"}, status=400)

    # polygon creation
    try:
        if area_type == "uc":
            if not city_name:
                return Response({"error": "city_name is required for area_type 'uc'."}, status=400)
            uc = UnionCouncil.objects.filter(city_name__iexact=city_name).first()
            if not uc:
                return Response({"error": "No UC found for given city_name"}, status=404)
            polygon = ee.Geometry(json.loads(uc.geometry.geojson))

        elif area_type == "custom":
            if not geometry_data:
                return Response({"error": "geometry is required for area_type 'custom'."}, status=400)
            geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
            polygon = ee.Geometry(geom_json)

        elif area_type == "kml":
            if not project_id:
                return Response({"error": "project_id is required for area_type 'kml'."}, status=400)
            try:
                project = Project.objects.get(id=project_id)
            except Project.DoesNotExist:
                return Response({"error": "Project not found"}, status=404)
            if not project.kml_file:
                return Response({"error": "No KML file found for this project"}, status=404)

            file_name = os.path.splitext(os.path.basename(project.kml_file.name))[0]
            city_name_from_file = file_name.split("_")[0].capitalize()
            uc_data = load_ucs_from_file(city_name_from_file)
            if not uc_data:
                return Response({"error": f"No local UC data found for {city_name_from_file}"}, status=404)

            polygon = None  # handled later if multi-feature

        else:
            return Response({"error": "Invalid area_type"}, status=400)
    except Exception as e:
        return Response({"error": "Failed to build geometry", "details": str(e)}, status=500)

    # validate comparison_years
    try:
        comparison_years = int(comparison_years)
        if comparison_years not in (1, 2, 3):
            return Response({"error": "comparison_years must be 1, 2, or 3"}, status=400)
    except ValueError:
        return Response({"error": "comparison_years must be integer 1/2/3"}, status=400)

    prev_years = [start_year - i for i in range(1, comparison_years + 1)]
    analysis_types = ["ndvi", "thermal", "aqi"]

    results = {}
    layers = {}

    try:
        baseline_start = f"{start_year}-01-01"
        baseline_end = f"{start_year + 1}-01-01"

        for atype in analysis_types:
            # baseline stats
            baseline_res = perform_analysis_for_polygon(atype, polygon, baseline_start, baseline_end)
            baseline_mean = baseline_res["stats"].get("mean")

            # collect previous year means
            prev_means = []
            for year in prev_years:
                year_start = f"{year}-01-01"
                year_end = f"{year + 1}-01-01"
                res = perform_analysis_for_polygon(atype, polygon, year_start, year_end)
                if res["stats"].get("mean") is not None:
                    prev_means.append(res["stats"]["mean"])

            avg_prev_mean = sum(prev_means) / len(prev_means) if prev_means else None

            # decide change status
            if avg_prev_mean is None or baseline_mean is None:
                status = "no_data"
            elif baseline_mean > avg_prev_mean:
                status = "increase"
            elif baseline_mean < avg_prev_mean:
                status = "decrease"
            else:
                status = "no_change"

            results[atype] = {
                "baseline_year": start_year,
                "comparison_years": prev_years,
                "baseline_mean": baseline_mean,
                "avg_prev_mean": avg_prev_mean,
                "map_layer": baseline_res["map_layer"]
            }

            # return 3 layers for frontend (toggle handled there)
            layers[atype] = {
                "increase": {"visible": status == "increase", "color": "green"},
                "decrease": {"visible": status == "decrease", "color": "red"},
                "no_change": {"visible": status == "no_change", "color": "gray"}
            }

        return Response({
            "mode": "comparison",
            "baseline_year": start_year,
            "compared_years": prev_years,
            "results": results,
            "layers": layers
        })

    except Exception as e:
        return Response({"error": "Failed comparison analysis", "details": str(e)}, status=500)

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
