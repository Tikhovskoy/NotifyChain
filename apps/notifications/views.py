from django.contrib.auth.models import User
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.permissions import IsStaffOrReadOnly

from .exceptions import RetryNotAllowedException
from .models import Notification, NotificationTemplate
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

    # preview и validate_template только считают результат и ничего не сохраняют,
    # поэтому доступны любому аутентифицированному пользователю, хотя это POST.
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def preview(self, request, pk=None):
        template = self.get_object()
        serializer = TemplatePreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        context_data = serializer.validated_data.get("context_data", {})
        preview = TemplateService().get_template_preview(template, context_data)

        return Response(
            {
                "template_id": template.id,
                "template_name": template.name,
                "rendered_subject": preview["subject"],
                "rendered_body": preview["body"],
                "context_data": context_data,
            }
        )

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def validate_template(self, request, pk=None):
        template = self.get_object()
        template_service = TemplateService()

        validation_result = template_service.validate_template(template)

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

    def get_queryset(self):
        queryset = super().get_queryset()

        if not self.request.user.is_staff:
            queryset = queryset.filter(recipient=self.request.user)

        return queryset.select_related("recipient", "template").prefetch_related("logs")

    def _own_recipient_filter(self):
        """None для администратора (видит всё), иначе текущий пользователь."""
        return None if self.request.user.is_staff else self.request.user

    @action(detail=False, methods=["post"])
    def send(self, request):
        serializer = SendNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        notification = serializer.save()
        success = NotificationService().send_notification(notification)

        response_data = NotificationSerializer(notification).data
        response_data["sent_immediately"] = success

        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def send_async(self, request):
        serializer = SendNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        notification = serializer.save()
        task_id = NotificationService().send_notification_async(notification)

        response_data = NotificationSerializer(notification).data
        response_data["task_id"] = task_id
        response_data["queued_for_async_processing"] = True

        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def send_bulk(self, request):
        serializer = BulkNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        notifications = serializer.save()

        return Response(
            {
                "message": f"Created {len(notifications)} notifications",
                "notifications": [
                    {
                        "id": notif.id,
                        "recipient": notif.recipient.username,
                        "status": notif.status,
                    }
                    for notif in notifications
                ],
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"])
    def send_bulk_async(self, request):
        serializer = BulkNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        recipients = list(User.objects.filter(id__in=data["recipient_ids"]))
        template = None
        if data.get("template_id"):
            template = NotificationTemplate.objects.get(id=data["template_id"])

        task_id = NotificationService().send_bulk_notifications_async(
            recipients=recipients,
            channel=data["channel"],
            message=data["message"],
            subject=data.get("subject", ""),
            template=template,
            context_data=data.get("context_data", {}),
            priority=data.get("priority", "normal"),
        )

        return Response(
            {
                "message": f"Queued {len(recipients)} notifications for async processing",
                "recipient_count": len(recipients),
                "task_id": task_id,
                "queued_for_async_processing": True,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        notification = self.get_object()

        if not notification.can_retry():
            raise RetryNotAllowedException("Невозможно повторить отправку уведомления")

        success = NotificationService().retry_failed_notification(notification)

        return Response(
            {
                "notification_id": notification.id,
                "retry_successful": success,
                "current_status": notification.status,
                "retry_count": notification.retry_count,
            }
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
