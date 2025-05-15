from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from urbananalytics.models import Project,ProjectArea, MapState
from rest_framework.response import Response
from rest_framework import status
from urbananalytics.serializers import ProjectSerializer,ProjectWithAreasSerializer,ProjectAreaSerializer, MapStateSerializer



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_project(request):
    """
    POST /api/projects/
    {
      "name": "My New Project"
    }
    → creates a Project(owner=request.user) and returns its details.
    """
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
    """
    GET /api/projects/{project_id}/areas/{area_id}/view/
    """
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
    return Response({"detail": "Project area deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

