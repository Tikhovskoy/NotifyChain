from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.notifications.exceptions import ValidationException
from apps.notifications.schema_serializers import ErrorSerializer

from .models import Provider, ProviderUsage
from .schema_serializers import (
    AvailableProvidersSerializer,
    ProviderStatsResultSerializer,
    ProviderTestResultSerializer,
)
from .serializers import (
    ProviderSerializer,
    ProviderUsageSerializer,
)
from .services import ProviderManager


class ProviderViewSet(viewsets.ModelViewSet):
    queryset = Provider.objects.all()
    serializer_class = ProviderSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["provider_type", "is_active", "is_default"]
    search_fields = ["name"]
    ordering_fields = ["name", "provider_type", "priority", "created_at"]
    ordering = ["provider_type", "priority"]

    @extend_schema(
        request=None,
        responses={200: ProviderTestResultSerializer, 409: ErrorSerializer},
        description="Проверяет конфигурацию и отправляет пробное сообщение через провайдера.",
    )
    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        provider = self.get_object()

        test_result = ProviderManager().test_provider(provider.id)

        return Response(
            {
                "provider_id": provider.id,
                "provider_name": provider.name,
                "test_result": test_result,
            }
        )

    @extend_schema(
        parameters=[OpenApiParameter("days", int, description="Период в днях, не больше 365")],
        responses=ProviderStatsResultSerializer,
    )
    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        provider = self.get_object()
        days = request.query_params.get("days", 7)

        try:
            days = min(int(days), 365)
        except (ValueError, TypeError):
            days = 7

        return Response(ProviderManager().get_provider_statistics(provider.id, days))

    @extend_schema(
        parameters=[OpenApiParameter("channel", str, required=True, enum=["email", "sms", "push"])],
        responses={200: AvailableProvidersSerializer, 400: ErrorSerializer},
    )
    @action(detail=False, methods=["get"])
    def available(self, request):
        channel = request.query_params.get("channel")

        if not channel:
            raise ValidationException("Параметр channel обязателен")

        available_providers = ProviderManager().get_available_providers(channel)
        serializer = ProviderSerializer(available_providers, many=True)

        return Response(
            {
                "channel": channel,
                "count": len(available_providers),
                "providers": serializer.data,
            }
        )


class ProviderUsageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ProviderUsage.objects.all()
    serializer_class = ProviderUsageSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["provider", "date", "hour"]
    ordering_fields = ["date", "hour", "requests_count", "success_rate"]
    ordering = ["-date", "-hour"]

    def get_queryset(self):
        return super().get_queryset().select_related("provider")
