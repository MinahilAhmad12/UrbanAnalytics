from django.urls import path
from urbananalytics.views import (
    signup,
    verify_signup_otp,
    resend_signup_verification_email,
    forgot_password,
    verify_forgot_password_otp,
    reset_password,
    resend_forgot_password_email,
    create_project,
    get_user_projects,
    view_project_area,
    get_project_details,
    delete_project_area,
    get_ucs,
    save_area_with_analyses,
    perform_gee_average_analysis,
    pixelwise_analysis,
    get_pixel_value,
    per_year_analysis,
    get_yearly_pixel_value,
    before_after_comparison_stats,
    before_after_comparison_pixelwise,
    create_average_report,
    get_report_download_url,
    generate_yearly_report,
    generate_before_after_report,
    chatbot_api,
)
from django.conf.urls.static import static
from urbananalytics.views import MyTokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView
from django.conf import settings
from django.urls import path

urlpatterns = [
    path("signup/", signup),
    path("verify-signup-otp/", verify_signup_otp),
    path("resend-signup-verification-email/", resend_signup_verification_email),
    path("forgot-password/", forgot_password),
    path("resend-forgot-password-email/", resend_forgot_password_email),
    path("verify-forgot-password-otp/", verify_forgot_password_otp),
    path("reset-password/", reset_password),
    path("signin/", MyTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/projects/", create_project, name="create_project"),
    path("my-projects/", get_user_projects, name="get_user_projects"),
    path(
        "projects/<int:project_id>/areas/<int:area_id>/view/",
        view_project_area,
        name="view_project_area",
    ),
    path(
        "projects/<int:project_id>/with-areas/",
        get_project_details,
        name="get_project_details",
    ),
    path(
        "project-area/<int:area_id>/delete/",
        delete_project_area,
        name="delete_project_area",
    ),
    path("areas/save/", save_area_with_analyses, name="save_area_with_analyses"),
    path("get_ucs/", get_ucs, name="get_ucs_by_city"),
    path("analyze/", perform_gee_average_analysis, name="perform_gee_analysis"),
    path(
        "pixelwiseanalysis/", pixelwise_analysis, name="perform_gee_pixelwiseanalysis"
    ),
    path("getpixelvalue/", get_pixel_value, name="get_pixel_value"),
    path("per_year_analysis/", per_year_analysis, name="per_year_analysis"),
    path(
        "get_yearly_pixel_value/", get_yearly_pixel_value, name="get_yearly_pixel_value"
    ),
    path(
        "before_after_comparison_stats/",
        before_after_comparison_stats,
        name="before_after_comparison_stats",
    ),
    path(
        "before_after_comparison_pixelwise/",
        before_after_comparison_pixelwise,
        name="before_after_comparison_pixelwise",
    ),
    path("reports/generate/", create_average_report, name="generate_average_report"),
    path(
        "reports/download/<int:report_id>/",
        get_report_download_url,
        name="download_report",
    ),
    path("reports/yearly/", generate_yearly_report, name="generate_yearly_report"),
    path(
        "reports/before-after/",
        generate_before_after_report,
        name="generate_before_after_report",
    ),
    path("chatbot/", chatbot_api, name="chatbot_api"),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
