from django.urls import path
from .views import signup,verify_signup_otp,resend_signup_verification_email, forgot_password,verify_forgot_password_otp, reset_password, resend_forgot_password_email,signin_view,get_saved_reports,delete_project,view_project,create_project,generate_report,list_user_projects
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('signup/', signup),
    path('verify-signup-otp/', verify_signup_otp),
    path('resend-signup-verification-email/', resend_signup_verification_email),
    path('forgot-password/', forgot_password),
    path('resend-forgot-password-email/', resend_forgot_password_email),
    path('verify-forgot-password-otp/', verify_forgot_password_otp),
    path('reset-password/', reset_password),
    path('signin/', signin_view),
    path('create-project/',create_project),
    path('view-project/<int:project_id>/',view_project),
    path('delete-project/<int:project_id>/',delete_project),
    path('generate-report/<int:project_id>/',generate_report),
    path('get-saved-reports/',get_saved_reports),
    path('list-user-projects/',list_user_projects)
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

