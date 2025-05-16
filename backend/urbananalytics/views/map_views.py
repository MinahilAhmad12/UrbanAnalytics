from django.http import JsonResponse
from django.contrib.gis.geos import GEOSGeometry
from urbananalytics.models import UnionCouncil
from django.core.serializers import serialize
from django.contrib.gis.serializers import geojson
from django.http import HttpResponse
import ee
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.decorators import api_view
from rest_framework.response import Response
from urbananalytics.models import AreaAnalysis
from rest_framework.decorators import api_view
from rest_framework.response import Response



def get_ucs_by_city(request, city_name):
    ucs = UnionCouncil.objects.filter(city_name__iexact=city_name)

    geojson = serialize('geojson', ucs, geometry_field='geometry', fields=('uc_name', 'city_name'))

    return HttpResponse(geojson, content_type='application/json')



# ee.Initialize()

# @api_view(['POST'])
# def perform_gee_analysis(request):
#     geometry_data = request.data.get("geometry")
#     analysis_type = request.data.get("analysis_type")
#     start_date = request.data.get("start_date")
#     end_date = request.data.get("end_date")

#     if not geometry_data or not analysis_type or not start_date or not end_date:
#         return Response({"error": "Missing required parameters"}, status=400)

#     try:
#         geom = GEOSGeometry(str(geometry_data))  
#         polygon = ee.Geometry(geometry_data)
#     except Exception as e:
#         return Response({"error": "Invalid geometry", "details": str(e)}, status=400)

#     image = None
#     vis_params = {}

#     if analysis_type == "ndvi":
#         collection = ee.ImageCollection('COPERNICUS/S2') \
#             .filterBounds(polygon) \
#             .filterDate(start_date, end_date) \
#             .sort('CLOUD_COVER') \
#             .median()
#         image = collection.normalizedDifference(['B8', 'B4']).rename('NDVI')
#         vis_params = {'min': 0, 'max': 1, 'palette': ['white', 'green']}

#     elif analysis_type == "thermal":
#         collection = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
#             .filterBounds(polygon) \
#             .filterDate(start_date, end_date) \
#             .sort('CLOUD_COVER') \
#             .median()
#         image = collection.select('ST_B10').multiply(0.00341802).add(149.0).rename('Thermal')
#         vis_params = {'min': 290, 'max': 320, 'palette': ['blue', 'green', 'red']}

#     elif analysis_type == "aqi":
#         collection = ee.ImageCollection('COPERNICUS/S5P/NRTI/L3_NO2') \
#             .filterBounds(polygon) \
#             .filterDate(start_date, end_date) \
#             .mean()
#         image = collection.select('NO2_column_number_density').rename('AQI')
#         vis_params = {'min': 0, 'max': 0.0003, 'palette': ['green', 'yellow', 'red']}

#     else:
#         return Response({"error": "Invalid analysis type"}, status=400)

#     stats = image.reduceRegion(
#         reducer=ee.Reducer.mean().combine(
#             reducer2=ee.Reducer.minMax(), sharedInputs=True
#         ).combine(
#             reducer2=ee.Reducer.stdDev(), sharedInputs=True
#         ),
#         geometry=polygon,
#         scale=30,
#         maxPixels=1e9
#     )

#     band_name = image.bandNames().getInfo()[0]

#     map_layer = image.visualize(**vis_params).getMapId()

#     return Response({
#         "map_layer": {
#             "urlFormat": map_layer["urlFormat"],
#             "mapid": map_layer["mapid"],
#             "token": map_layer["token"]
#         },
#         "stats": {
#             "mean": stats.getInfo().get(f"{band_name}_mean"),
#             "min": stats.getInfo().get(f"{band_name}_min"),
#             "max": stats.getInfo().get(f"{band_name}_max"),
#             "std_dev": stats.getInfo().get(f"{band_name}_stdDev"),
#         }
#     })
