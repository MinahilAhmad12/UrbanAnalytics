from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from urbananalytics.models import Project,ProjectArea, MapState,AreaAnalysis,UnionCouncil
from rest_framework.response import Response
from rest_framework import status
from urbananalytics.serializers import ProjectSerializer,ProjectWithAreasSerializer,ProjectAreaSerializer, MapStateSerializer
import json



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
    name = data.get('name', 'Unnamed Area')
    date_range_start = data.get('date_range_start')
    date_range_end = data.get('date_range_end')

    if area_type not in ['uc', 'custom', 'kml']:
        return Response({'detail': 'Invalid area_type.'}, status=400)

    created_area_ids = []

    if area_type == 'uc':
        selected_city = data.get('selected_city')
        uc_ids_list = data.get('uc_ids', [])
        uc_analyses = data.get('analyses', {})
        map_states = data.get('map_state', {})

        if not selected_city or not uc_ids_list:
            return Response({'detail': 'selected_city and uc_ids are required for area_type "uc".'}, status=400)

        for uc_id in uc_ids_list:
            try:
                uc = UnionCouncil.objects.get(id=uc_id)
            except UnionCouncil.DoesNotExist:
                continue

            area = ProjectArea.objects.create(
                project=project,
                area_type='uc',
                name=f"{name} - {uc.uc_name}",
                date_range_start=date_range_start,
                date_range_end=date_range_end,
                selected_city=selected_city
            )
            area.uc_ids.set([uc])

            uc_analysis = uc_analyses.get(str(uc_id), [])
            for analysis in uc_analysis:
                AreaAnalysis.objects.create(
                    project_area=area,
                    analysis_type=analysis['analysis_type'],
                    tile_url=analysis['tile_url'],
                    stats=analysis['stats']
                )

            map_data = map_states.get(str(uc_id))
            if map_data:
                MapState.objects.create(
                    project_area=area,
                    center_coords=map_data.get('center_coords'),
                    zoom_level=map_data.get('zoom_level'),
                    active_layer=map_data.get('active_layer'),
                    toggle_state=map_data.get('toggle_state', {}),
                    basemap_style=map_data.get('basemap_style', 'streets')
                )

            created_area_ids.append(area.id)

    elif area_type in ['custom', 'kml']:
        custom_geometry = data.get('custom_geometry') if area_type == 'custom' else None
        kml_file = request.FILES.get('kml_file') if area_type == 'kml' else None

        if area_type == 'custom' and not custom_geometry:
            return Response({'detail': 'custom_geometry is required for area_type "custom".'}, status=400)
        if area_type == 'kml' and not kml_file:
            return Response({'detail': 'kml_file is required for area_type "kml".'}, status=400)

        area = ProjectArea.objects.create(
            project=project,
            area_type=area_type,
            name=name,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            custom_geometry=custom_geometry,
            kml_file=kml_file
        )
        analyses = data.get('analyses')
        if isinstance(analyses, str):
            try:
                analyses = json.loads(analyses)
            except json.JSONDecodeError:
                return Response({"error": "Invalid JSON format inside analyses list"}, status=400)

        map_data = data.get('map_state')

        if isinstance(map_data, str):
            try:
                map_data = json.loads(map_data)
            except json.JSONDecodeError:
                return Response({"error": "Invalid JSON format for 'map_state'"}, status=400)
        for analysis in analyses:
            AreaAnalysis.objects.create(
                    project_area=area,
                    analysis_type=analysis['analysis_type'],
                    tile_url=analysis['tile_url'],
                    stats=analysis['stats']
                )

        if map_data:
            MapState.objects.create(
                project_area=area,
                center_coords=map_data.get('center_coords'),
                zoom_level=map_data.get('zoom_level'),
                active_layer=map_data.get('active_layer'),
                toggle_state=map_data.get('toggle_state', {}),
                basemap_style=map_data.get('basemap_style', 'streets')
            )

        created_area_ids.append(area.id)


    return Response({
        'detail': 'Area(s) and analyses saved successfully.',
        'created_area_ids': created_area_ids
    })
