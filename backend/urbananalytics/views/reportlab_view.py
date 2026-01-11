from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.conf import settings
from urbananalytics.models import YearlyAnalysis, BeforeAfterAnalysis, Report
from urbananalytics.utils.reportlab import (
    create_annual_report_pdf,
    create_before_after_report_pdf,
    upload_report_to_s3
)
from urbananalytics.utils.upload_report_to_supabase import upload_report_to_supabase
import threading 
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_yearly_report(request):
    try:
        project_id = request.data.get("project_id")
        analysis_type = request.data.get("analysis_type")
        year = request.data.get("year")
        area_type = request.data.get("area_type")

        if not all([project_id, analysis_type, year, area_type]):
            return Response({"error": "Missing required parameters"}, status=400)

        instances = YearlyAnalysis.objects.filter(
            project_id=project_id,
            analysis_type=analysis_type,
            year=year,
            area_type=area_type,
            is_pixelwise=False
        ).order_by("uc_name")

        if not instances.exists():
            return Response({"error": "No analysis data found for report"}, status=404)

        pdf_path = create_annual_report_pdf(instances, created_by=request.user)

        pdf_url = upload_report_to_s3(
            local_path=pdf_path,
            project_id=project_id,
            year=year,
            api_name="generate_yearly_report"
        )

        report = Report.objects.create(
            project_id=project_id,
            analysis_type=analysis_type.lower(),
            report_type="1yr_average",
            area_type=area_type,
            year=year,
            file=pdf_url,
            created_by=request.user,
            message=f"{analysis_type.upper()} Annual Report ({year})"
        )

        threading.Thread(target=upload_report_to_supabase, args=(report.id,)).start()

        return Response({
            "message": "Yearly PDF report generated, uploaded to S3, and indexed in Supabase.",
            "pdf_url": pdf_url
        }, status=200)

    except Exception as e:
        return Response({"error": str(e)}, status=500)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_before_after_report(request):
    try:
        project_id = request.data.get("project_id")
        analysis_type = request.data.get("analysis_type")
        before_year = request.data.get("before_year")
        after_year = request.data.get("after_year")

        if not all([project_id, analysis_type, before_year, after_year]):
            return Response({"error": "Missing required parameters"}, status=400)

        entries = BeforeAfterAnalysis.objects.filter(
            project_id=project_id,
            analysis_type=analysis_type,
            before_year=before_year,
            after_year=after_year
        ).order_by("uc_name")

        if not entries.exists():
            return Response({"error": "No data found for report"}, status=404)
        pdf_path = create_before_after_report_pdf(entries, created_by=request.user)

        pdf_url = upload_report_to_s3(
            local_path=pdf_path,
            project_id=project_id,
            year=after_year,
            api_name="before_after_comparison"
        )

        report = Report.objects.create(
            project_id=project_id,
            analysis_type=analysis_type.lower(),
            report_type="2yr_comparison",
            area_type="uc",
            before_year=before_year,
            after_year=after_year,
            file=pdf_url,
            created_by=request.user,
            message=f"{analysis_type.upper()} Comparison Report ({before_year}→{after_year})"
        )

        return Response({
            "message": "Before–After Comparison report generated, uploaded to S3",
            "pdf_url": pdf_url
        }, status=200)

    except Exception as e:
        return Response({"error": str(e)}, status=500)