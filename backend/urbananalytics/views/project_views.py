from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from urbananalytics.models import Project,ProjectArea, MapState,AreaAnalysis,UnionCouncil
from rest_framework.response import Response
from rest_framework import status
from urbananalytics.serializers import ProjectSerializer,ProjectWithAreasSerializer,ProjectAreaSerializer, MapStateSerializer



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_project(request):
    serializer = ProjectSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    project = serializer.save(owner=request.user)
    return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_projects(request):
    projects = Project.objects.filter(owner=request.user).prefetch_related('areas__analyses')
    serializer = ProjectWithAreasSerializer(projects, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def view_project_area(request, project_id, area_id):
    
    try:
        area = ProjectArea.objects.select_related('project__owner') \
                .get(id=area_id, project__id=project_id, project__owner=request.user)
    except ProjectArea.DoesNotExist:
        return Response({"error": "Area not found"}, status=status.HTTP_404_NOT_FOUND)

    map_state = MapState.objects.filter(project_area=area).first()

    return Response({
        "area": ProjectAreaSerializer(area).data,
        "map_state": MapStateSerializer(map_state).data if map_state else None
    })
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_project_details(request, project_id):
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({'detail': 'Project not found'}, status=404)

    serializer = ProjectWithAreasSerializer(project)
    return Response(serializer.data)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_project_area(request, area_id):
    try:
        area = ProjectArea.objects.get(id=area_id)
    except ProjectArea.DoesNotExist:
        return Response({"detail": "Project area not found."}, status=status.HTTP_404_NOT_FOUND)
    
    
    if area.project.owner != request.user:
        return Response({"detail": "Not authorized to delete this project area."}, status=status.HTTP_403_FORBIDDEN)
    
    area.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_area_with_analyses(request):
    data = request.data
    user = request.user

    try:
        project = Project.objects.get(id=data['project_id'], owner=user)
    except Project.DoesNotExist:
        return Response({'detail': 'Project not found'}, status=404)

    area_type = data.get('area_type')
    name = data.get('name')
    date_range_start = data.get('date_range_start')
    date_range_end = data.get('date_range_end')

    if area_type not in ['uc', 'custom', 'kml']:
        return Response({'detail': 'Invalid area_type'}, status=400)

    selected_city = None
    custom_geometry = None
    kml_file = None

    if area_type == 'uc':
        selected_city = data.get('selected_city')
        uc_ids_list = data.get('uc_ids', [])
        if not selected_city:
            return Response({'detail': 'selected_city is required for area_type "uc".'}, status=400)
    elif area_type == 'custom':
        custom_geometry = data.get('custom_geometry')
        if not custom_geometry:
            return Response({'detail': 'custom_geometry is required for area_type "custom".'}, status=400)
    elif area_type == 'kml':
        kml_file = request.FILES.get('kml_file')
        if not kml_file:
            return Response({'detail': 'kml_file is required for area_type "kml".'}, status=400)

    area = ProjectArea.objects.create(
        project=project,
        area_type=area_type,
        name=name,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        selected_city=selected_city,
        custom_geometry=custom_geometry,
        kml_file=kml_file,
    )

    if area_type == 'uc':
        if uc_ids_list:
            union_councils = UnionCouncil.objects.filter(id__in=uc_ids_list)
            area.uc_ids.set(union_councils)

    
    analyses = data.get('analyses', [])
    for analysis in analyses:
        try:
            AreaAnalysis.objects.create(
                project_area=area,
                analysis_type=analysis['analysis_type'],
                tile_url=analysis['tile_url'],
                stats=analysis['stats']
            )
        except Exception as e:
            area.delete()  
            return Response({'detail': f'Error creating analysis: {str(e)}'}, status=400)

    map_data = data.get('map_state')
    if map_data:
        try:
            MapState.objects.create(
                project_area=area,
                center_coords=map_data.get('center_coords', None),
                zoom_level=map_data.get('zoom_level', None),
                active_layer=map_data.get('active_layer', None),
                toggle_state=map_data.get('toggle_state', {}),
                basemap_style=map_data.get('basemap_style', 'streets')
            )
        except Exception as e:
            area.delete()  
            return Response({'detail': f'Error creating map state: {str(e)}'}, status=400)

    return Response({'detail': 'Area and analyses saved successfully', 'area_id': area.id})
