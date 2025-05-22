import io
from django.http import FileResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.response import Response
from urbananalytics.models import ProjectArea, Report,Project,AreaAnalysis
from urbananalytics.serializers import ReportCreateSerializer,ReportListSerializer
from reportlab.pdfgen import canvas
from django.utils.timezone import localtime
from django.utils.timezone import now, localtime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_CENTER



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_report(request, project_id, area_id):
    
    try:
        pa = ProjectArea.objects.select_related('project__owner') \
            .get(id=area_id, project__id=project_id, project__owner=request.user)
    except ProjectArea.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    report_type = request.data.get('report_type', 'environmental_summary')
    params = request.data.get('parameters', {})

    analysis_data = AreaAnalysis.objects.filter(project_area=pa)

    
    ndvi_stats = {}
    thermal_stats = {}
    aqi_stats = {}

    for analysis in analysis_data:
        stats = analysis.stats  
        if analysis.analysis_type == 'ndvi':
            ndvi_stats = {
                "mean": stats.get('mean'),
                "max": stats.get('max'),
                "min": stats.get('min'),
                "std_dev": stats.get('std_dev')
            }
        elif analysis.analysis_type == 'thermal':
            thermal_stats = {
                "mean": stats.get('mean'),
                "max": stats.get('max'),
                "min": stats.get('min'),
                "std_dev": stats.get('std_dev')
            }
        elif analysis.analysis_type == 'aqi':
            aqi_stats = {
                "mean": stats.get('mean'),
                "max": stats.get('max'),
                "min": stats.get('min'),
                "std_dev": stats.get('std_dev')
            }

    
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

    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()
    elements = []

    created_time = now()
    elements.append(Paragraph(f"<b>Report:</b> {report_type}", styles['Title']))
    area_name = ""
    area_type_display = pa.area_type.upper() if pa.area_type else "Unknown"

    if pa.area_type == 'uc':
        area_name = pa.selected_city  
    elif pa.area_type == 'custom':
        area_name = "Custom Area"
    elif pa.area_type == 'kml':
        area_name = "Uploaded KML Area"
        
    centered_style = ParagraphStyle(
        name='CenteredHeading',
        parent=styles['Heading3'],
        alignment=TA_CENTER,
        spaceAfter=12
    )
    
    area_info = f"<b>Area:</b> {area_name}<br/><b>Type:</b> {area_type_display}"
    elements.append(Paragraph(area_info, centered_style))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(f"<b>Generated At:</b> {localtime(created_time).strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    elements.append(Paragraph(f"<b>Area ID:</b> {pa.id}", styles['Normal']))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("<b>NDVI Stats</b>", styles['Heading2']))
    for key, val in ndvi_stats.items():
        elements.append(Paragraph(f"<font color='gray'>{key.capitalize()}:</font> <b>{val}</b>", styles['Normal']))
    elements.append(Spacer(1, 6))

    elements.append(Paragraph("<b>Thermal Stats</b>", styles['Heading2']))
    for key, val in thermal_stats.items():
        elements.append(Paragraph(f"<font color='gray'>{key.capitalize()}:</font> <b>{val}</b>", styles['Normal']))
    elements.append(Spacer(1, 6))

    elements.append(Paragraph("<b>AQI Stats</b>", styles['Heading2']))
    for key, val in aqi_stats.items():
        elements.append(Paragraph(f"<font color='gray'>{key.capitalize()}:</font> <b>{val}</b>", styles['Normal']))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("<b>Tree Plantation Recommendation:</b>", styles['Heading2']))
    elements.append(Paragraph(f"<b>{plantation_recommendation}</b>", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)

    
    filename = f"{report_type}_area{pa.id}_{pa.project.id}.pdf"
    report = Report.objects.create(
        project_area=pa,
        report_type=report_type,
        parameters=params,
        created_at=created_time
    )
    report.file.save(filename, buffer, save=True)

    
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

