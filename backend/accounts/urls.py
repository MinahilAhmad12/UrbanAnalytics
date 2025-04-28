from django.urls import path
from .views import signup,verify_signup_otp,resend_signup_verification_email, forgot_password,verify_forgot_password_otp, reset_password, resend_forgot_password_email,signin_view

urlpatterns = [
    path('signup/', signup),
    path('verify-signup-otp/', verify_signup_otp),
    path('resend-signup-verification-email/', resend_signup_verification_email),
    path('forgot-password/', forgot_password),
    path('resend-forgot-password-email/', resend_forgot_password_email),
    path('verify-forgot-password-otp/', verify_forgot_password_otp),
    path('reset-password/', reset_password),
    path('signin/', signin_view),
]

