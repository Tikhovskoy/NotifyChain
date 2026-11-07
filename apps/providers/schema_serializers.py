"""Сериализаторы только для документации OpenAPI: описывают ответы действий провайдеров."""

from rest_framework import serializers

from .serializers import ProviderSerializer


class ProviderTestReportSerializer(serializers.Serializer):
    provider_name = serializers.CharField()
    provider_type = serializers.CharField()
    config_valid = serializers.BooleanField()
    connection_test = serializers.BooleanField()
    errors = serializers.ListField(child=serializers.CharField())


class ProviderTestResultSerializer(serializers.Serializer):
    provider_id = serializers.IntegerField()
    provider_name = serializers.CharField()
    test_result = ProviderTestReportSerializer()


class DailyStatSerializer(serializers.Serializer):
    date = serializers.DateField()
    requests = serializers.IntegerField()
    success = serializers.IntegerField()
    failures = serializers.IntegerField()
    avg_time = serializers.FloatField()


class ProviderStatsResultSerializer(serializers.Serializer):
    provider_name = serializers.CharField()
    period_days = serializers.IntegerField()
    total_requests = serializers.IntegerField()
    successful_requests = serializers.IntegerField()
    failed_requests = serializers.IntegerField()
    success_rate = serializers.FloatField(help_text="Проценты")
    average_response_time = serializers.FloatField(help_text="Секунды")
    daily_stats = DailyStatSerializer(many=True)


class AvailableProvidersSerializer(serializers.Serializer):
    channel = serializers.CharField()
    count = serializers.IntegerField()
    providers = ProviderSerializer(many=True)
