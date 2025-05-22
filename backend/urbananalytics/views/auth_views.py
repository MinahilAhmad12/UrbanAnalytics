from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from urbananalytics.serializers import MyTokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from urbananalytics.serializers import MyTokenObtainPairSerializer

User = get_user_model()

@csrf_exempt
def signup(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')

        if not email:
            return JsonResponse({'error': 'Email is required.'}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({'error': 'Username already exists.'}, status=400)
        if User.objects.filter(email=email).exists():
            return JsonResponse({'error': 'Email already exists.'}, status=400)


        user = User.objects.create_user(username=username, email=email, password=password)
        
        
        

        import random
        otp = str(random.randint(100000, 999999))
        user.otp_code = otp
        user.save()

        try:
            send_mail(
                'Verify your Email',
                f'Use this OTP code: {otp}',
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False,
            )
        except Exception as e:
            user.delete()  
            return JsonResponse({'error': f'Failed to send email: {str(e)}'}, status=500)

        return JsonResponse({'message': 'User created successfully. Verification email sent!'})



@csrf_exempt
def verify_signup_otp(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        email = data.get('email')
        otp = data.get('otp')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found.'}, status=404)

        if user.otp_code == otp:
            user.is_verified = True   
            user.otp_code = ''         
            user.save()
            return JsonResponse({'message': 'Signup OTP verified successfully!'})
        else:
            return JsonResponse({'error': 'Invalid OTP.'}, status=400)

@csrf_exempt
def resend_signup_verification_email(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        email = data.get('email')

        try:
            user = User.objects.get(email=email)
            if user.is_verified:
                return JsonResponse({'message': 'User already verified.'})

            
            import random
            otp = str(random.randint(100000, 999999))
            user.otp_code = otp
            user.save()

            send_mail(
                'Resend Verification Email',
                f'Use this OTP code: {otp}',
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False,
            )

            return JsonResponse({'message': 'Verification email resent successfully.'})

        except User.DoesNotExist:
            return JsonResponse({'error': 'User with this email does not exist.'}, status=404)
@csrf_exempt
def forgot_password(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        email = data.get('email')

        try:
            user = User.objects.get(email=email)

            
            import random
            otp = str(random.randint(100000, 999999))
            user.otp_code = otp
            user.save()

            
            send_mail(
                'Reset Your Password - OTP',
                f'Your OTP code for resetting your password is: {otp}',
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False,
            )

            return JsonResponse({'message': 'Password reset OTP sent successfully.'})

        except User.DoesNotExist:
            return JsonResponse({'error': 'User with this email does not exist.'}, status=404)
@csrf_exempt
def resend_forgot_password_email(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        email = data.get('email')

        try:
            user = User.objects.get(email=email)

            import random
            otp = str(random.randint(100000, 999999))
            user.otp_code = otp
            user.save()

            send_mail(
                'Resend Reset Password Email',
                f'Use this OTP code to reset your password: {otp}',
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False,
            )

            return JsonResponse({'message': 'Password reset OTP resent successfully.'})

        except User.DoesNotExist:
            return JsonResponse({'error': 'User with this email does not exist.'}, status=404)

@csrf_exempt
def verify_forgot_password_otp(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        email = data.get('email')
        otp = data.get('otp')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found.'}, status=404)

        if user.otp_code == otp:
            user.otp_code = ''  
            user.save()
            return JsonResponse({'message': 'Forgot password OTP verified successfully!'})
        else:
            return JsonResponse({'error': 'Invalid OTP.'}, status=400)

@csrf_exempt
def reset_password(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        email = data.get('email')
        new_password = data.get('new_password')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found.'}, status=404)

        user.set_password(new_password)
        user.save()

        return JsonResponse({'message': 'Password reset successfully.'})
    else:
        return JsonResponse({'error': 'Only POST method allowed.'}, status=400)


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
