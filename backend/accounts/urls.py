from django.urls import path
from .views import signup, verify_email, verify_otp,resend_verification_email, forgot_password, reset_password

urlpatterns = [
    path('signup/', signup),
    path('verify-email/', verify_email),
    path('verify-otp/', verify_otp),
    path('resend-verification-email/', resend_verification_email),
    path('forgot-password/', forgot_password),
    path('reset-password/', reset_password),
]

