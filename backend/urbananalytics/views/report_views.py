from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.conf import settings
import boto3

from urbananalytics.utils.reporting import generate_average_report
from urbananalytics.models import Report



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_average_report(request):
    data = request.data
    required = ["project_id", "analysis_type", "report_type", "area_type", "start_date", "end_date"]
    if not all(data.get(k) for k in required):
        return Response({"error": "Missing required parameters"}, status=400)
    try:
        res = generate_average_report(
            project_id=data["project_id"],
            analysis_type=data["analysis_type"],
            report_type=data["report_type"],
            area_type=data["area_type"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            created_by=request.user
        )
        return Response({
            "message": f"{data['report_type'].capitalize()} {data['analysis_type'].capitalize()} report generated successfully",
            "report_id": res["report"].id,
            "download_url": res["s3_url"]
        })
    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_report_download_url(request, report_id):
    report = get_object_or_404(Report, id=report_id, created_by=request.user)
    if not report.file:
        return Response({"error": "No file associated with this report"}, status=404)

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )

    url = s3_client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": report.file.name},
        ExpiresIn=3600
    )

    return Response({"download_url": url})
