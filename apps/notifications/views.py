from django.contrib.auth.models import User
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.permissions import IsStaffOrReadOnly

from .exceptions import RetryNotAllowedException
from .models import Notification, NotificationTemplate
from .schema_serializers import (
    BulkCreatedSerializer,
    BulkQueuedSerializer,
    ErrorSerializer,
    NotificationListResultSerializer,
    QueuedResultSerializer,
    RetryResultSerializer,
    SendResultSerializer,
    TemplatePreviewResultSerializer,
    TemplateValidationResultSerializer,
)
from .serializers import (
    BulkNotificationSerializer,
    NotificationSerializer,
    NotificationStatsSerializer,
    NotificationTemplateSerializer,
    SendNotificationSerializer,
    TemplatePreviewSerializer,
)
from .services import NotificationService, TemplateService
from .utils import NotificationHelper


class NotificationTemplateViewSet(viewsets.ModelViewSet):
    queryset = NotificationTemplate.objects.all()
    serializer_class = NotificationTemplateSerializer
    permission_classes = [IsStaffOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["template_type", "is_active"]
    search_fields = ["name", "subject", "body"]
    ordering_fields = ["name", "created_at", "updated_at"]
    ordering = ["-created_at"]
    template_service_class = TemplateService  # подменяется в тестах

    def get_template_service(self):
        return self.template_service_class()

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "template_service": self.get_template_service()}

    # preview и validate_template только считают результат и ничего не сохраняют,
    # поэтому доступны любому аутентифицированному пользователю, хотя это POST.
    @extend_schema(request=TemplatePreviewSerializer, responses=TemplatePreviewResultSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def preview(self, request, pk=None):
        template = self.get_object()
        serializer = TemplatePreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        context_data = serializer.validated_data.get("context_data", {})
        preview = self.get_template_service().get_template_preview(template, context_data)

        return Response(
            {
                "template_id": template.id,
                "template_name": template.name,
                "rendered_subject": preview["subject"],
                "rendered_body": preview["body"],
                "context_data": context_data,
            }
        )

    @extend_schema(request=None, responses=TemplateValidationResultSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def validate_template(self, request, pk=None):
        template = self.get_object()
        validation_result = self.get_template_service().validate_template(template)

        return Response(
            {
                "template_id": template.id,
                "template_name": template.name,
                "is_valid": validation_result["is_valid"],
                "errors": validation_result["errors"],
                "warnings": validation_result["warnings"],
                "required_variables": validation_result["required_variables"],
            }
        )


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "channel", "priority"]
    search_fields = ["subject", "recipient__username", "recipient_address"]
    ordering_fields = ["created_at", "sent_at", "priority"]
    ordering = ["-created_at"]
    service_class = NotificationService  # подменяется в тестах

    def get_service(self):
        return self.service_class()

    def get_queryset(self):
        queryset = super().get_queryset()

        if not self.request.user.is_staff:
            queryset = queryset.filter(recipient=self.request.user)

        return queryset.select_related("recipient", "template").prefetch_related("logs")

    def _own_recipient_filter(self):
        """None для администратора (видит всё), иначе текущий пользователь."""
        return None if self.request.user.is_staff else self.request.user

    @extend_schema(
        request=SendNotificationSerializer,
        responses={201: SendResultSerializer, 409: ErrorSerializer},
        description="Создаёт уведомление и сразу отправляет его с fallback между провайдерами и каналами.",
    )
    @action(detail=False, methods=["post"])
    def send(self, request):
        return self._send_single(request, deferred=False)

    @extend_schema(
        request=SendNotificationSerializer,
        responses={201: QueuedResultSerializer, 409: ErrorSerializer},
        description="Создаёт уведомление и ставит отправку в очередь Celery.",
    )
    @action(detail=False, methods=["post"])
    def send_async(self, request):
        return self._send_single(request, deferred=True)

    @extend_schema(
        request=BulkNotificationSerializer,
        responses={201: BulkCreatedSerializer},
        description="Создаёт уведомления для списка получателей, но не отправляет их.",
    )
    @action(detail=False, methods=["post"])
    def send_bulk(self, request):
        return self._send_bulk(request, deferred=False)

    @extend_schema(
        request=BulkNotificationSerializer,
        responses={201: BulkQueuedSerializer},
        description="Создаёт уведомления для списка получателей и ставит их в очередь Celery.",
    )
    @action(detail=False, methods=["post"])
    def send_bulk_async(self, request):
        return self._send_bulk(request, deferred=True)

    def _request_serializer(self, serializer_class, request, service):
        serializer = serializer_class(data=request.data, context={"service": service})
        serializer.is_valid(raise_exception=True)
        return serializer

    def _send_single(self, request, *, deferred):
        """Одно уведомление: отправить сразу или поставить в очередь Celery."""

        service = self.get_service()
        serializer = self._request_serializer(SendNotificationSerializer, request, service)
        notification = serializer.save()

        if deferred:
            extra = {
                "task_id": service.send_notification_async(notification),
                "queued_for_async_processing": True,
            }
        else:
            extra = {"sent_immediately": service.send_notification(notification)}

        return Response(
            {**NotificationSerializer(notification).data, **extra}, status=status.HTTP_201_CREATED
        )

    def _send_bulk(self, request, *, deferred):
        """Массовая рассылка: только создать уведомления или создать и поставить в очередь."""

        service = self.get_service()
        serializer = self._request_serializer(BulkNotificationSerializer, request, service)

        if deferred:
            recipients_count = len(serializer.get_recipients())
            body = {
                "message": f"Queued {recipients_count} notifications for async processing",
                "recipient_count": recipients_count,
                "task_id": serializer.enqueue(),
                "queued_for_async_processing": True,
            }
        else:
            notifications = serializer.save()
            body = {
                "message": f"Created {len(notifications)} notifications",
                "notifications": [
                    {"id": n.id, "recipient": n.recipient.username, "status": n.status}
                    for n in notifications
                ],
            }

        return Response(body, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={200: RetryResultSerializer, 409: ErrorSerializer})
    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        notification = self.get_object()

        if not notification.can_retry():
            raise RetryNotAllowedException("Невозможно повторить отправку уведомления")

        success = self.get_service().retry_failed_notification(notification)

        return Response(
            {
                "notification_id": notification.id,
                "retry_successful": success,
                "current_status": notification.status,
                "retry_count": notification.retry_count,
            }
        )

    @extend_schema(
        parameters=[NotificationStatsSerializer],
        responses=OpenApiTypes.OBJECT,
        description=(
            "Обычный пользователь получает статистику по своим уведомлениям. "
            "Администратор без user_id получает общую статистику за days дней."
        ),
    )
    @action(detail=False, methods=["get"])
    def stats(self, request):
        serializer = NotificationStatsSerializer(data=request.query_params)

        if serializer.is_valid():
            user_id = serializer.validated_data.get("user_id")
            days = serializer.validated_data.get("days", 7)

            if not request.user.is_staff:
                if user_id not in (None, request.user.id):
                    raise PermissionDenied(
                        "Статистика других пользователей доступна только администраторам"
                    )
                user_id = request.user.id

            if user_id:
                user = User.objects.get(id=user_id)
                stats = NotificationHelper.get_user_notification_stats(user)
            else:
                from datetime import timedelta

                from django.db.models import Count
                from django.utils import timezone

                end_date = timezone.now().date()
                start_date = end_date - timedelta(days=days)

                notifications = Notification.objects.filter(created_at__date__gte=start_date)

                stats = {
                    "period_days": days,
                    "total_notifications": notifications.count(),
                    "by_status": dict(
                        notifications.values("status")
                        .annotate(count=Count("id"))
                        .values_list("status", "count")
                    ),
                    "by_channel": dict(
                        notifications.values("channel")
                        .annotate(count=Count("id"))
                        .values_list("channel", "count")
                    ),
                    "by_priority": dict(
                        notifications.values("priority")
                        .annotate(count=Count("id"))
                        .values_list("priority", "count")
                    ),
                }

            return Response(stats)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        parameters=[OpenApiParameter("limit", int, description="Не больше 1000, по умолчанию 100")],
        responses=NotificationListResultSerializer,
    )
    @action(detail=False, methods=["get"])
    def pending(self, request):
        limit = request.query_params.get("limit", 100)

        try:
            limit = min(int(limit), 1000)
        except (ValueError, TypeError):
            limit = 100

        pending_notifications = NotificationHelper.get_pending_notifications(
            limit, recipient=self._own_recipient_filter()
        )

        return Response(
            {
                "count": len(pending_notifications),
                "notifications": NotificationSerializer(pending_notifications, many=True).data,
            }
        )

    @extend_schema(
        parameters=[OpenApiParameter("limit", int, description="Не больше 500, по умолчанию 50")],
        responses=NotificationListResultSerializer,
    )
    @action(detail=False, methods=["get"])
    def failed(self, request):
        limit = request.query_params.get("limit", 50)

        try:
            limit = min(int(limit), 500)
        except (ValueError, TypeError):
            limit = 50

        failed_notifications = NotificationHelper.get_failed_notifications_for_retry(
            limit, recipient=self._own_recipient_filter()
        )

        return Response(
            {
                "count": len(failed_notifications),
                "notifications": NotificationSerializer(failed_notifications, many=True).data,
            }
        )
