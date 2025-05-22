from django.http import JsonResponse
from django.contrib.gis.geos import GEOSGeometry
from urbananalytics.models import UnionCouncil
from django.core.serializers import serialize
from django.contrib.gis.serializers import geojson
from django.http import HttpResponse
import ee
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from urbananalytics.models import AreaAnalysis
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from concurrent.futures import ThreadPoolExecutor
import json



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_ucs_by_city(request, city_name):
    ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)

    geojson = serialize('geojson', ucs, geometry_field='geometry', fields=('uc_name', 'city_name'))

    return Response(json.loads(geojson))


service_account_key_path = r'C:\Users\User\Documents\urbananalytics-460415-f557e7903d83.json'
credentials = ee.ServiceAccountCredentials(
    email='gee-service-account@urbananalytics-460415.iam.gserviceaccount.com',
    key_file=service_account_key_path
)
ee.Initialize(credentials, project='urbananalytics-460415')

@api_view(['POST'])
def perform_gee_analysis(request):
    analysis_type = request.data.get("analysis_type")
    start_date = request.data.get("start_date")
    end_date = request.data.get("end_date")
    area_type = request.data.get("area_type")
    city_name = request.data.get("city_name")
    geometry_data = request.data.get("geometry")

    if not analysis_type or not start_date or not end_date or not area_type:
        return Response({"error": "Missing required parameters"}, status=400)

    try:
        results = []

        
        if area_type == "uc":
            if not city_name:
                return Response({"error": "city_name is required for UC analysis"}, status=400)

            ucs = UnionCouncil.objects.filter(city_name=city_name)
            if not ucs.exists():
                return Response({"error": "No Union Councils found for the selected city"}, status=404)

            def process_uc(uc):
                try:
                    geojson_dict = json.loads(uc.geometry.geojson)
                    polygon = ee.Geometry(geojson_dict)
                    result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)

                    return {
                        "uc_name": uc.uc_name,
                        "city_name": uc.city_name,
                        "error": "0",
                        "map_layer": result.get("map_layer"),
                        "stats": result.get("stats")
                    }
                except Exception as e:
                    return {
                        "uc_name": uc.uc_name,
                        "city_name": uc.city_name,
                        "error": "1",
                        "error_msg": str(e)
                    }

            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(process_uc, ucs))

        
        elif area_type in ("custom", "kml"):
            if not geometry_data:
                return Response({"error": "geometry data is required for custom/kml analysis"}, status=400)

            try:
                geom_json = geometry_data if isinstance(geometry_data, dict) else json.loads(geometry_data)
                polygon = ee.Geometry(geom_json)
                result = perform_analysis_for_polygon(analysis_type, polygon, start_date, end_date)
                results.append(result)
            except Exception as e:
                return Response({"error": "Invalid geometry data", "details": str(e)}, status=400)

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
        image = collection.normalizedDifference(['B8', 'B4']).rename('NDVI')
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

        image = composite.select('ST_B10').multiply(0.00341802).add(149.0).rename('Thermal')
        vis_params = {'min': 290, 'max': 320, 'palette': ['blue', 'green', 'red']}
        band_name = 'Thermal'
        scale = 100

    elif analysis_type.lower() == "aqi":
        collection = ee.ImageCollection('COPERNICUS/S5P/NRTI/L3_NO2') \
            .filterBounds(polygon) \
            .filterDate(start_date, end_date) \
            .mean()
        image = collection.select('NO2_column_number_density').rename('AQI')
        vis_params = {'min': 0, 'max': 0.0003, 'palette': ['green', 'yellow', 'red']}
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
