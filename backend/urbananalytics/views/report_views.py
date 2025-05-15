import io
from django.http import FileResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.response import Response
from urbananalytics.models import ProjectArea, Report,Project,AreaAnalysis
from urbananalytics.serializers import ReportCreateSerializer,ReportListSerializer
from reportlab.pdfgen import canvas

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_report(request, project_id, area_id):
    """
    POST /api/projects/{project_id}/areas/{area_id}/reports/
    {
      "report_type": "environmental_summary",
      // any extra params
    }
    """
    # 1) Lookup the area and ensure user owns the project
    try:
        pa = ProjectArea.objects.select_related('project__owner') \
            .get(id=area_id, project__id=project_id, project__owner=request.user)
    except ProjectArea.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    report_type = request.data.get('report_type', 'environmental_summary')
    params = request.data.get('parameters', {})

    # 2) Fetch analysis data for NDVI, Thermal, AQI
    analysis_data = AreaAnalysis.objects.filter(project_area=pa)

    # Prepare dictionaries to store stats
    ndvi_stats = {}
    thermal_stats = {}
    aqi_stats = {}

    # Extract data for each analysis type (ndvi, thermal, aqi)
    for analysis in analysis_data:
        stats = analysis.stats
        if analysis.analysis_type == 'ndvi':
            ndvi_stats = {
                "mean": stats.get('mean_ndvi'),
                "max": stats.get('max_ndvi'),
                "min": stats.get('min_ndvi'),
                "std_dev": stats.get('stddev_ndvi')
            }
        elif analysis.analysis_type == 'thermal':
            thermal_stats = {
                "mean": stats.get('mean_temp'),
                "max": stats.get('max_temp'),
                "min": stats.get('min_temp'),
                "std_dev": stats.get('stddev_temp')
            }
        elif analysis.analysis_type == 'aqi':
            aqi_stats = {
                "mean": stats.get('mean_aqi'),
                "max": stats.get('max_aqi'),
                "min": stats.get('min_aqi'),
                "category": stats.get('aqi_category')
            }

    # 3) Check suitability for tree plantation with partial data logic
    if ndvi_stats.get("mean") is not None and thermal_stats.get("mean") is not None and aqi_stats.get("mean") is not None:
        if ndvi_stats["mean"] < 0.3 and thermal_stats["mean"] > 35.0 and aqi_stats["mean"] > 100:
            plantation_recommendation = "Yes — Suitable for Tree Plantation"
        else:
            plantation_recommendation = "No — Not a Priority Zone"
    elif ndvi_stats.get("mean") is not None and thermal_stats.get("mean") is not None:
        if ndvi_stats["mean"] < 0.3 and thermal_stats["mean"] > 35.0:
            plantation_recommendation = "Likely Suitable (Based on NDVI + Thermal)"
        else:
            plantation_recommendation = "Unlikely (Based on NDVI + Thermal)"
    elif ndvi_stats.get("mean") is not None:
        if ndvi_stats["mean"] < 0.3:
            plantation_recommendation = "Potentially Suitable (Based on NDVI only)"
        else:
            plantation_recommendation = "Not Suitable (Based on NDVI only)"
    else:
        plantation_recommendation = "Insufficient data"

    # 4) Build the PDF in memory
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)

    # Add Report Title
    pdf.drawString(100, 800, f"Report: {report_type}")
    pdf.drawString(100, 780, f"Area ID: {pa.id}")
    
    
    # Add Analysis Data (Stats)
    pdf.drawString(100, 740, f"NDVI Stats: {ndvi_stats}")
    pdf.drawString(100, 720, f"Thermal Stats: {thermal_stats}")
    pdf.drawString(100, 700, f"AQI Stats: {aqi_stats}")
    
    
    pdf.drawString(100, 680, f"Tree Plantation Recommendation: {plantation_recommendation}")

    # Add more report content as needed...
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    # 5) Save the file to your Report model
    filename = f"{report_type}_area{pa.id}_{pa.project.id}.pdf"
    report = Report.objects.create(
        project_area=pa,
        report_type=report_type,
        parameters=params
    )
    report.file.save(filename, buffer, save=True)

    # 6) Return the report record
    return Response(ReportCreateSerializer(report, context={'request': request}).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_project_reports(request, project_id):
    try:
        project = Project.objects.get(id=project_id, owner=request.user)
    except Project.DoesNotExist:
        return Response({'detail': 'Project not found.'}, status=status.HTTP_404_NOT_FOUND)

    reports = Report.objects.filter(project_area__project=project)
    serializer = ReportListSerializer(reports, many=True, context={'request': request})
    return Response(serializer.data)

