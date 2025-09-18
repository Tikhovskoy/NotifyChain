from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import Provider, ProviderUsage
from .serializers import (
    ProviderSerializer, ProviderUsageSerializer,
    TestProviderSerializer, ProviderStatsSerializer
)
from .services import ProviderManager


class ProviderViewSet(viewsets.ModelViewSet):
    queryset = Provider.objects.all()
    serializer_class = ProviderSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['provider_type', 'is_active', 'is_default']
    search_fields = ['name']
    ordering_fields = ['name', 'provider_type', 'priority', 'created_at']
    ordering = ['provider_type', 'priority']

    def get_permissions(self):
        return [AllowAny()]

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        provider = self.get_object()

        if not request.user.is_staff:
            return Response(
                {'error': 'Только администраторы могут тестировать провайдеры'},
                status=status.HTTP_403_FORBIDDEN
            )

        provider_manager = ProviderManager()

        try:
            test_result = provider_manager.test_provider(provider.id)

            return Response({
                'provider_id': provider.id,
                'provider_name': provider.name,
                'test_result': test_result
            })

        except Exception as e:
            return Response(
                {'error': f'Ошибка теста: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        provider = self.get_object()
        days = request.query_params.get('days', 7)

        try:
            days = min(int(days), 365)
        except (ValueError, TypeError):
            days = 7

        provider_manager = ProviderManager()

        try:
            stats = provider_manager.get_provider_statistics(provider.id, days)

            return Response(stats)

        except Exception as e:
            return Response(
                {'error': f'Ошибка получения статистики: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def available(self, request):
        channel = request.query_params.get('channel')

        if not channel:
            return Response(
                {'error': 'Параметр channel обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )

        provider_manager = ProviderManager()

        try:
            available_providers = provider_manager.get_available_providers(channel)
            serializer = ProviderSerializer(available_providers, many=True)

            return Response({
                'channel': channel,
                'count': len(available_providers),
                'providers': serializer.data
            })

        except Exception as e:
            return Response(
                {'error': f'Ошибка получения доступных провайдеров: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )


class ProviderUsageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ProviderUsage.objects.all()
    serializer_class = ProviderUsageSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['provider', 'date', 'hour']
    ordering_fields = ['date', 'hour', 'requests_count', 'success_rate']
    ordering = ['-date', '-hour']

    def get_queryset(self):
        return super().get_queryset().select_related('provider')
