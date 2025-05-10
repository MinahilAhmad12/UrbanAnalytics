from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from urbananalytics.utils import geocode_location, get_kml_center
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from urbananalytics.models import Project
from rest_framework.response import Response
@csrf_exempt
def create_project(request):
    if request.method == "POST":
        
        try:
            data = request.POST.dict()
            map_data = {}

            # Case 1: Location is entered as text (e.g., "Lahore")
            if "location" in data:
                map_data = geocode_location(data["location"])
                print("Location map_data:", map_data)

            # Case 2: KML file is uploaded
            elif "kml_file" in request.FILES:
                file = request.FILES["kml_file"]
                map_data = get_kml_center(file)
                print("Location map_data:", map_data)

            # Create the project with map_data
            project = Project.objects.create(
                user=request.user,
                name=data["name"],
                location=data.get("location", ""),
                kml_file=request.FILES.get("kml_file"),
                map_data=map_data
            )

            return JsonResponse({"message": "Project created", "project_id": project.id}, status=201)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

@csrf_exempt
@permission_classes([IsAuthenticated])
def view_project(request, project_id):
    if request.method == "GET":
        try:
            project = Project.objects.get(id=project_id, user=request.user)
            city_analyses = project.city_analyses.all()

            response_data = {
                "id": project.id,
                "name": project.name,
                "map_data": project.map_data,
                "created_at": project.created_at.isoformat(),
                "city_analyses": [
                    {
                        "city_name": city.city_name,
                        "selected_ucs": city.selected_ucs,
                        "ndvi": city.ndvi,
                        "thermal": city.thermal,
                        "aqi": city.aqi
                    } for city in city_analyses
                ]
            }

            return JsonResponse(response_data, safe=False)

        except Project.DoesNotExist:
            return JsonResponse({"error": "Project not found"}, status=404)
@csrf_exempt
def delete_project(request, project_id):
    if request.method == "DELETE":
        
        try:
            project = Project.objects.get(id=project_id, user=request.user)
            project.delete()
            return JsonResponse({"message": "Project deleted"}, status=200)
        except Project.DoesNotExist:
            return JsonResponse({"error": "Project not found"}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_user_projects(request):
    user = request.user
    name = request.query_params.get('name')
    created_date = request.query_params.get('created_at')  # format: YYYY-MM-DD

    projects = Project.objects.filter(user=user)

    if name:
        projects = projects.filter(name__icontains=name)
    
    if created_date:
        projects = projects.filter(created_at__date=created_date)

    projects = projects.order_by('-created_at')

    project_list = []
    for project in projects:
        project_list.append({
            'id': project.id,
            'name': project.name,
            'location': project.location,
            'kml_file': project.kml_file.url if project.kml_file else None,
            'map_data': project.map_data,
            'created_at': project.created_at,
        })

    return Response(project_list)
