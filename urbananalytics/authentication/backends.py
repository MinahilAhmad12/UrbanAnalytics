from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

class CustomAuthenticationBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = get_user_model().objects.get(username=username)
            if user.check_password(password) and user.is_verified:
                return user
        except get_user_model().DoesNotExist:
            return None
        return None