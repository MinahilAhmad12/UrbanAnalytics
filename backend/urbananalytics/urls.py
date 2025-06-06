from django.urls import path
from urbananalytics.views import signup,verify_signup_otp,resend_signup_verification_email, forgot_password,verify_forgot_password_otp, reset_password, resend_forgot_password_email,create_project,get_user_projects,generate_report,view_project_area,get_project_details,get_project_reports,delete_project_area,get_ucs_by_city,save_area_with_analyses,perform_gee_analysis
from django.conf import settings
from django.conf.urls.static import static
from urbananalytics.views import MyTokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('signup/', signup),
    path('verify-signup-otp/', verify_signup_otp),
    path('resend-signup-verification-email/', resend_signup_verification_email),
    path('forgot-password/', forgot_password),
    path('resend-forgot-password-email/', resend_forgot_password_email),
    path('verify-forgot-password-otp/', verify_forgot_password_otp),
    path('reset-password/', reset_password),
    path('signin/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/projects/', create_project, name='create_project'),
    path('my-projects/', get_user_projects, name='get_user_projects'),
    path('projects/<int:project_id>/areas/<int:area_id>/view/', view_project_area, name='view_project_area'),
    path('projects/<int:project_id>/with-areas/', get_project_details, name='get_project_details'),
    path('project-area/<int:area_id>/delete/', delete_project_area, name='delete_project_area'),
    path('areas/save/',save_area_with_analyses,name = "save_area_with_analyses"),
    path(
      'projects/<int:project_id>/areas/<int:area_id>/reports/',
      generate_report,
      name='generate_report'
    ),
    path('projects/<int:project_id>/reports/', get_project_reports, name='get_project_reports'),
    path('ucs/<str:city_name>/',get_ucs_by_city, name='get_ucs_by_city'),
    path('analyze/', perform_gee_analysis, name='perform_gee_analysis'),
    
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
