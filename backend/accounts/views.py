from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings


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
        
        token = default_token_generator.make_token(user)
        verification_link = f"http://localhost:8000/api/verify-email/?uid={user.id}&token={token}"

        import random
        otp = str(random.randint(100000, 999999))
        user.otp_code = otp
        user.save()

        try:
            send_mail(
                'Verify your Email',
                f'Click the link to verify your email: {verification_link}\n\nOr use this OTP code: {otp}',
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False,
            )
        except Exception as e:
            user.delete()  # If sending email fails, delete the user
            return JsonResponse({'error': f'Failed to send email: {str(e)}'}, status=500)

        return JsonResponse({'message': 'User created successfully. Verification email sent!'})


from django.shortcuts import get_object_or_404

@csrf_exempt
def verify_email(request):
    uid = request.GET.get('uid')
    token = request.GET.get('token')

    user = get_object_or_404(User, id=uid)

    if default_token_generator.check_token(user, token):
        user.is_verified = True
        user.save()
        return JsonResponse({'message': 'Email verified successfully!'})
    else:
        return JsonResponse({'error': 'Invalid or expired token.'}, status=400)
@csrf_exempt
def verify_otp(request):
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
            return JsonResponse({'message': 'OTP verified successfully!'})
        else:
            return JsonResponse({'error': 'Invalid OTP.'}, status=400)
@csrf_exempt
def resend_verification_email(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        email = data.get('email')

        try:
            user = User.objects.get(email=email)
            if user.is_verified:
                return JsonResponse({'message': 'User already verified.'})

            token = default_token_generator.make_token(user)
            verification_link = f"http://localhost:8000/api/verify-email/?uid={user.id}&token={token}"

            import random
            otp = str(random.randint(100000, 999999))
            user.otp_code = otp
            user.save()

            send_mail(
                'Resend Verification Email',
                f'Click the link to verify your email: {verification_link}\n\nOr use this OTP code: {otp}',
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
            token = default_token_generator.make_token(user)
            reset_link = f"http://localhost:3000/reset-password?uid={user.id}&token={token}"

            send_mail(
                'Reset Your Password',
                f'Click the link to reset your password: {reset_link}',
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False,
            )

            return JsonResponse({'message': 'Password reset email sent successfully.'})

        except User.DoesNotExist:
            return JsonResponse({'error': 'User with this email does not exist.'}, status=404)
@csrf_exempt
def reset_password(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        uid = data.get('uid')
        token = data.get('token')
        new_password = data.get('new_password')

        try:
            user = User.objects.get(id=uid)
        except User.DoesNotExist:
            return JsonResponse({'error': 'Invalid user.'}, status=400)

        if not default_token_generator.check_token(user, token):
            return JsonResponse({'error': 'Invalid or expired token.'}, status=400)

        user.set_password(new_password)
        user.save()

        return JsonResponse({'message': 'Password reset successfully.'})
    else:
        return JsonResponse({'error': 'Only POST method allowed.'}, status=400)
