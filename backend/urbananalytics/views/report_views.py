from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from urbananalytics.models import Project,Report
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
from django.core.files.base import ContentFile


@csrf_exempt
def generate_report(request, project_id):
    if request.method == "POST":
        
        try:
            # Get the project and related data
            project = Project.objects.get(id=project_id, user=request.user)
            city_analyses = project.city_analyses.all()

            # Create PDF in memory
            buffer = BytesIO()
            p = canvas.Canvas(buffer, pagesize=letter)

            # Set up the title
            p.setFont("Helvetica", 14)
            p.drawString(100, 750, f"Report for Project: {project.name}")
            p.drawString(100, 710, f"Created At: {project.created_at}")
            
            # Add analysis data for each city
            y_position = 690
            for city in city_analyses:
                p.drawString(100, y_position, f"City: {city.city_name}")
                p.drawString(100, y_position - 20, f"Selected UCs: {', '.join(city.selected_ucs)}")
                p.drawString(100, y_position - 40, f"NDVI: {city.ndvi['value'] if city.ndvi else 'N/A'}")
                p.drawString(100, y_position - 60, f"Thermal: {city.thermal['value'] if city.thermal else 'N/A'}")
                p.drawString(100, y_position - 80, f"AQI: {city.aqi['value'] if city.aqi else 'N/A'}")
                y_position -= 100  # Adjust the space for next city

            # Save PDF to buffer
            p.showPage()
            p.save()
            
            # Save the PDF to the database
            buffer.seek(0)
            report_file = buffer.read()
            wrapped_file = ContentFile(report_file, name=f"{project.name}_report.pdf")

            report = Report.objects.create(
                user=request.user,
                project=project,
                name=f"{project.name} Report",
                report_file=wrapped_file
            )
            
            return JsonResponse({"message": "Report generated", "report_id": report.id}, status=201)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
def get_saved_reports(request):
    if request.method == "GET":
        
        try:
            # Get all reports for the logged-in user
            reports = Report.objects.filter(user=request.user)

            response_data = [
                {
                    "report_id": report.id,
                    "name": report.name,
                    "generated_at": report.generated_at,
                    "report_file": report.report_file.url
                }
                for report in reports
            ]

            return JsonResponse(response_data, safe=False)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

