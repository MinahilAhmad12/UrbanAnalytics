

from rest_framework import serializers
from .models import Project,AreaAnalysis,Report,MapState
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)

        if not self.user.is_verified:
            raise serializers.ValidationError("Please verify your email before signing in.")

        data['username'] = self.user.username
        data['email'] = self.user.email
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        return token


class ProjectSerializer(serializers.ModelSerializer):
    kml_file = serializers.FileField(required=False, allow_null=True)

    class Meta:
        model  = Project
        fields = ['id', 'project_name', 'location_name', 'kml_file', 'created_at']
        read_only_fields = ['id', 'created_at']




