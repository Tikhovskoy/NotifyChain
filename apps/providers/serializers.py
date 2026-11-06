from rest_framework import serializers

from .models import Provider, ProviderUsage


class ProviderSerializer(serializers.ModelSerializer):
    rate_limit_info = serializers.SerializerMethodField()
    usage_stats = serializers.SerializerMethodField()

    class Meta:
        model = Provider
        fields = [
            "id",
            "name",
            "provider_type",
            "is_active",
            "is_default",
            "priority",
            "config",
            "rate_limit_per_minute",
            "rate_limit_per_hour",
            "rate_limit_info",
            "usage_stats",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_rate_limit_info(self, obj):
        return f"{obj.rate_limit_per_minute}/мин, {obj.rate_limit_per_hour}/час"

    def get_usage_stats(self, obj):
        try:
            latest_usage = obj.usage_stats.order_by("-date").first()
            if latest_usage:
                return {
                    "success_rate": latest_usage.success_rate,
                    "last_update": latest_usage.date,
                    "total_requests": latest_usage.requests_count,
                }
        except:
            pass
        return None

    def validate(self, data):
        if data.get("is_default") and self.instance:
            existing_default = Provider.objects.filter(
                provider_type=data.get("provider_type", self.instance.provider_type),
                is_default=True,
            ).exclude(id=self.instance.id)

            if existing_default.exists():
                raise serializers.ValidationError("Default provider for this type already exists")

        return data


class ProviderUsageSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source="provider.name", read_only=True)
    success_rate_display = serializers.SerializerMethodField()

    class Meta:
        model = ProviderUsage
        fields = [
            "id",
            "provider",
            "provider_name",
            "date",
            "hour",
            "requests_count",
            "success_count",
            "failure_count",
            "success_rate",
            "success_rate_display",
            "average_response_time",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "success_rate"]

    def get_success_rate_display(self, obj):
        return f"{obj.success_rate:.2f}%"


class TestProviderSerializer(serializers.Serializer):
    provider_id = serializers.IntegerField()

    def validate_provider_id(self, value):
        try:
            Provider.objects.get(id=value)
            return value
        except Provider.DoesNotExist:
            raise serializers.ValidationError("Провайдер не найден")


class ProviderStatsSerializer(serializers.Serializer):
    provider_id = serializers.IntegerField()
    days = serializers.IntegerField(default=7, min_value=1, max_value=365)

    def validate_provider_id(self, value):
        try:
            Provider.objects.get(id=value)
            return value
        except Provider.DoesNotExist:
            raise serializers.ValidationError("Провайдер не найден")
