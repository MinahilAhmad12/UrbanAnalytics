

from rest_framework import serializers
from .models import Project,ProjectArea, AreaAnalysis,Report,MapState
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
    class Meta:
        model  = Project
        fields = ['id', 'name', 'created_at']
        read_only_fields = ['id', 'created_at']

class AreaAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = AreaAnalysis
        fields = ['analysis_type', 'results']

class ProjectAreaSerializer(serializers.ModelSerializer):
    analyses = AreaAnalysisSerializer(many=True, read_only=True)

    class Meta:
        model = ProjectArea
        fields = ['id', 'area_type', 'name', 'date_range_start', 'date_range_end',
                  'selected_city', 'custom_geometry', 'analyses']


class ProjectWithAreasSerializer(serializers.ModelSerializer):
    areas = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ['id', 'name', 'created_at', 'areas']

    def get_areas(self, obj):
        areas = obj.areas.all()
        return ProjectAreaSerializer(areas, many=True).data


class MapStateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MapState
        fields = ['center_lat', 'center_lng', 'zoom', 'active_layer', 'toggle_states']



class ReportListSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()
    area_name = serializers.SerializerMethodField()
    date_range = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            'id',
            'report_type',
            'created_at',
            'parameters',
            'download_url',
            'area_name',
            'date_range',
        ]

    def get_download_url(self, obj):
        request = self.context.get('request')
        if request is None:
            return obj.file.url  
        return request.build_absolute_uri(obj.file.url)


    def get_area_name(self, obj):
        return obj.project_area.name

    def get_date_range(self, obj):
        pa = obj.project_area
        if pa.date_range_start and pa.date_range_end:
            return f"{pa.date_range_start} to {pa.date_range_end}"
        return None


class ReportCreateSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = ['id', 'report_type', 'created_at', 'parameters', 'file', 'download_url']

    def get_download_url(self, obj):
        request = self.context.get('request')
        if request is None:
            return obj.file.url  
        return request.build_absolute_uri(obj.file.url)