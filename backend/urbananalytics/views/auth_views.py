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
from rest_framework_simplejwt.tokens import RefreshToken

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
            user.delete()  # If sending email fails, delete the user
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
        confirm_password = data.get('confirm_password')

        if new_password != confirm_password:
            return JsonResponse({'error': 'Passwords do not match.'}, status=400)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found.'}, status=404)

        user.set_password(new_password)
        user.save()

        return JsonResponse({'message': 'Password reset successfully.'})
    else:
        return JsonResponse({'error': 'Only POST method allowed.'}, status=400)

@csrf_exempt
def signin_view(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')

            if not username or not password:
                return JsonResponse({'error': 'Username and password are required.'}, status=400)

            
            print(f"Received username: {username}")
            print(f"Received password: {password}")

            
            user = authenticate(request, username=username, password=password)

            
            print(f"Authenticated user: {user}")

            if user is not None:
                if not user.is_verified:
                    return JsonResponse({'error': 'Please verify your email before signing in.'}, status=400)

                login(request, user)

                
                refresh = RefreshToken.for_user(user)
                access_token = str(refresh.access_token)
                refresh_token = str(refresh)

                return JsonResponse({
                    'message': 'Login successful',
                    'access_token': access_token,
                    'refresh_token': refresh_token
                }, status=200)

            else:
                return JsonResponse({'error': 'Invalid credentials'}, status=400)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
    else:
        return JsonResponse({'error': 'Only POST requests are allowed'}, status=405)