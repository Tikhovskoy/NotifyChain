from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from apps.notifications.exceptions import ValidationException

from .models import Provider, ProviderUsage
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

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        provider = self.get_object()
        days = request.query_params.get("days", 7)

        try:
            days = min(int(days), 365)
        except (ValueError, TypeError):
            days = 7

        return Response(ProviderManager().get_provider_statistics(provider.id, days))

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
