from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from urbananalytics.models import Project, MapState,AreaAnalysis,UnionCouncil,YearlyAnalysis,BeforeAfterAnalysis,BeforeAfterPixelwise, Report
from rest_framework.response import Response
from rest_framework import status
from urbananalytics.serializers import ProjectSerializer
import json
from fastkml import kml
from shapely.geometry import shape
import os
from urbananalytics.helpers import extract_bounds_from_kml
from django.core.exceptions import ObjectDoesNotExist
import os
from django.conf import settings
import boto3


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_project(request):
    serializer = ProjectSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    project = serializer.save(owner=request.user)

    if project.kml_file:
        kml_path = project.kml_file.path
        bounds = extract_bounds_from_kml(kml_path)
    else:
      bounds = None


    response_data = ProjectSerializer(project).data
    response_data["bounds"] = bounds  

    return Response(response_data, status=status.HTTP_201_CREATED)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_project(request):
    
    data = request.data
    project_id = data.get("project_id")
    area_type = data.get("area_type")

    if not project_id:
        return Response({"error": "project_id is required"}, status=status.HTTP_400_BAD_REQUEST)

    if not area_type:
        return Response({"error": "area_type is required"}, status=status.HTTP_400_BAD_REQUEST)


    if area_type == "uc" and not data.get("city_name"):
        return Response({"error": "city_name is required for area_type 'uc'"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except ObjectDoesNotExist:
        return Response({"error": "Project not found or you don't have permission"}, status=status.HTTP_404_NOT_FOUND)

    
    map_state_fields = {
        "selected_analysis_type": data.get("selected_analysis_type"),
        "selected_mode": data.get("selected_mode"),
        "start_date": data.get("start_date"),
        "end_date": data.get("end_date"),
        "selected_year": data.get("selected_year"),
        "before_year": data.get("before_year"),
        "after_year": data.get("after_year"),
        "map_center": data.get("map_center"),
        "zoom_level": data.get("zoom_level"),
        "area_type": area_type,
        "city_name": data.get("city_name") if area_type == "uc" else None,
    }

    
    map_state_fields = {k: v for k, v in map_state_fields.items() if v is not None}

    
    map_state, created = MapState.objects.update_or_create(
        project=project,
        defaults=map_state_fields
    )

    return Response({
        "message": "Project saved successfully",
        "created": created,
        "map_state": {
            "selected_analysis_type": map_state.selected_analysis_type,
            "selected_mode": map_state.selected_mode,
            "start_date": map_state.start_date,
            "end_date": map_state.end_date,
            "selected_year": map_state.selected_year,
            "before_year": map_state.before_year,
            "after_year": map_state.after_year,
            "map_center": map_state.map_center,
            "zoom_level": map_state.zoom_level,
            "area_type": map_state.area_type,
            "city_name": map_state.city_name,
            "updated_at": map_state.updated_at
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_user_projects(request):
   
    projects = Project.objects.filter(owner=request.user).order_by('-created_at')

    project_list = []
    for project in projects:
        if project.kml_file: 
            filename = os.path.basename(project.kml_file.name) 
            location_display = filename.split('_')[0] 
        else:  
            location_display = project.location_name

        project_list.append({
            "id": project.id,
            "project_name": project.project_name,
            "location_name": location_display,
            "created_at": project.created_at
        })

    return Response({"projects": project_list})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def view_project(request, project_id):
    
    try:
        project = Project.objects.get(id=project_id)
    except ObjectDoesNotExist:
        return Response({"error": "Project not found or you don't have permission"}, status=404)

    
    try:
        map_state = project.map_state
    except ObjectDoesNotExist:
        return Response({"error": "Map state not found for this project"}, status=404)

    results = []
    mode = map_state.selected_mode

    
    uc_pairs = []

    if mode in ["average", "pixelwise"]:
        qs = AreaAnalysis.objects.filter(
            project=project,
            analysis_type=map_state.selected_analysis_type,
            area_type=map_state.area_type,
            start_date__gte=map_state.start_date,
            end_date__lte=map_state.end_date
        )
        uc_pairs = qs.values_list("uc_name", "city_name").distinct()
    elif mode in ["per-year average", "per-year pixelwise"]:
        qs = YearlyAnalysis.objects.filter(
            project=project,
            analysis_type=map_state.selected_analysis_type,
            area_type=map_state.area_type,
            year=map_state.selected_year
        )
        uc_pairs = qs.values_list("uc_name", "city_name").distinct()
    elif mode == "before-after pixelwise":
        qs = BeforeAfterPixelwise.objects.filter(
            project=project,
            analysis_type=map_state.selected_analysis_type,
            area_type=map_state.area_type,
            before_year=map_state.before_year,
            after_year=map_state.after_year
        )
        uc_pairs = qs.values_list("uc_name", "city_name").distinct()

    
    def fetch_average(uc_name, city_name):
        objs = AreaAnalysis.objects.filter(
            project=project,
            analysis_type=map_state.selected_analysis_type,
            area_type=map_state.area_type,
            uc_name=uc_name,
            city_name=city_name,
            start_date__gte=map_state.start_date,
            end_date__lte=map_state.end_date,
            is_pixelwise=False
        )
        return [
            {
                "uc_name": o.uc_name,
                "city_name": o.city_name,
                "stats": o.stats,
                "tile_url": o.tile_url_template
            } for o in objs
        ]

    def fetch_pixelwise(uc_name, city_name):
        objs = AreaAnalysis.objects.filter(
            project=project,
            analysis_type=map_state.selected_analysis_type,
            area_type=map_state.area_type,
            uc_name=uc_name,
            city_name=city_name,
            start_date__gte=map_state.start_date,
            end_date__lte=map_state.end_date,
            is_pixelwise=True
        )
        return [
            {
                "uc_name": o.uc_name,
                "city_name": o.city_name,
                "tile_url": o.tile_url_template
            } for o in objs
        ]

    def fetch_yearly_average(uc_name, city_name):
        objs = YearlyAnalysis.objects.filter(
            project=project,
            analysis_type=map_state.selected_analysis_type,
            area_type=map_state.area_type,
            uc_name=uc_name,
            city_name=city_name,
            year=map_state.selected_year,
            is_pixelwise=False
        )
        return [
            {
                "uc_name": o.uc_name,
                "city_name": o.city_name,
                "stats": o.stats,
                "tile_url": o.tile_url_template
            } for o in objs
        ]

    def fetch_yearly_pixelwise(uc_name, city_name):
        objs = YearlyAnalysis.objects.filter(
            project=project,
            analysis_type=map_state.selected_analysis_type,
            area_type=map_state.area_type,
            uc_name=uc_name,
            city_name=city_name,
            year=map_state.selected_year,
            is_pixelwise=True
        )
        return [
            {
                "uc_name": o.uc_name,
                "city_name": o.city_name,
                "tile_url": o.tile_url_template
            } for o in objs
        ]

    def fetch_before_after_pixelwise(uc_name, city_name):
        ba_stats = BeforeAfterAnalysis.objects.filter(
            project=project,
            analysis_type=map_state.selected_analysis_type,
            area_type=map_state.area_type,
            uc_name=uc_name,
            city_name=city_name,
            before_year=map_state.before_year,
            after_year=map_state.after_year
        ).first()
        ba_pixelwise = BeforeAfterPixelwise.objects.filter(
            project=project,
            analysis_type=map_state.selected_analysis_type,
            area_type=map_state.area_type,
            uc_name=uc_name,
            city_name=city_name,
            before_year=map_state.before_year,
            after_year=map_state.after_year
        ).first()
        return {
            "uc_name": uc_name,
            "city_name": city_name,
            "before_stats": ba_stats.stats_before if ba_stats else None,
            "after_stats": ba_stats.stats_after if ba_stats else None,
            "comparison": ba_stats.comparison if ba_stats else None,
            "tile_url_before": ba_pixelwise.tile_url_before if ba_pixelwise else None,
            "tile_url_after": ba_pixelwise.tile_url_after if ba_pixelwise else None
        }


    for uc_name, city_name in uc_pairs:
        if mode == "average":
            results.extend(fetch_average(uc_name, city_name))
        elif mode == "pixelwise":
            results.extend(fetch_pixelwise(uc_name, city_name))
        elif mode == "per-year average":
            results.extend(fetch_yearly_average(uc_name, city_name))
        elif mode == "per-year pixelwise":
            results.extend(fetch_yearly_pixelwise(uc_name, city_name))
        elif mode == "before-after pixelwise":
            results.append(fetch_before_after_pixelwise(uc_name, city_name))

    return Response({
        "project": {
            "id": project.id,
            "project_name": project.project_name,
            "location_name": project.location_name,
            "created_at": project.created_at
        },
        "map_state": {
            "selected_analysis_type": map_state.selected_analysis_type,
            "selected_mode": map_state.selected_mode,
            "start_date": map_state.start_date,
            "end_date": map_state.end_date,
            "selected_year": map_state.selected_year,
            "before_year": map_state.before_year,
            "after_year": map_state.after_year,
            "map_center": map_state.map_center,
            "zoom_level": map_state.zoom_level,
            "area_type": map_state.area_type,
            "city_name": map_state.city_name,
            "updated_at": map_state.updated_at
        },
        "uc_layers": results
    })



@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_project(request, project_id):
    
    try:
        
        project = Project.objects.get(id=project_id, owner=request.user)
    except ObjectDoesNotExist:
        return Response({"error": "Project not found or you don't have permission"}, status=404)

    project.delete()

    return Response({"success": f"Project '{project.project_name}' has been deleted successfully."})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_project_reports(request, project_id):
    
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except ObjectDoesNotExist:
        return Response({"error": "Project not found or you don't have permission"}, status=404)

    reports = Report.objects.filter(project=project).order_by('-created_at')

    report_list = []
    for report in reports:
        
        if report.before_year and report.after_year:
            period = f"{report.before_year}→{report.after_year}"
        elif report.year:
            period = f"Year {report.year}"
        else:
            period = f"{report.start_date}→{report.end_date}" if report.start_date and report.end_date else None

        report_list.append({
            "id": report.id,
            "analysis_type": report.analysis_type,
            "report_type": report.report_type,
            "area_type": report.area_type,
            "period": period,
            "message": report.message,
            "created_by": report.created_by.username,
            "created_at": report.created_at
        })

    return Response({"project_id": project.id, "project_name": project.project_name, "reports": report_list})


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_report(request, project_id, report_id):

    try:
        project = Project.objects.get(id=project_id ,owner=request.user)
    except ObjectDoesNotExist:
        return Response({"error": "Project not found"}, status=404)

    try:
        report = Report.objects.get(id=report_id, project=project)
    except ObjectDoesNotExist:
        return Response({"error": "Report not found for this project"}, status=404)

    
    if report.file and report.file.name:
        file_key = report.file.name 

       
        if file_key.startswith("http://") or file_key.startswith("https://"):
            file_key = file_key.split(".com/")[-1]

        s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )

        try:
            s3_client.delete_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=file_key
            )
        except Exception as e:
            print("S3 delete error:", e)
            

    
    report.delete()

    return Response({"message": "Report deleted successfully"})
