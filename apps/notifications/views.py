from django.contrib.auth.models import User
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

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
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["template_type", "is_active"]
    search_fields = ["name", "subject", "body"]
    ordering_fields = ["name", "created_at", "updated_at"]
    ordering = ["-created_at"]

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        template = self.get_object()
        serializer = TemplatePreviewSerializer(data=request.data)

        if serializer.is_valid():
            template_service = TemplateService()

            try:
                context_data = serializer.validated_data.get("context_data", {})
                preview = template_service.get_template_preview(template, context_data)

                return Response(
                    {
                        "template_id": template.id,
                        "template_name": template.name,
                        "rendered_subject": preview["subject"],
                        "rendered_body": preview["body"],
                        "context_data": context_data,
                    }
                )

            except Exception as e:
                return Response(
                    {"error": f"Ошибка генерации превью: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
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
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "channel", "priority"]
    search_fields = ["subject", "recipient__username", "recipient_address"]
    ordering_fields = ["created_at", "sent_at", "priority"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()

        if self.request.user.is_authenticated and not self.request.user.is_staff:
            queryset = queryset.filter(recipient=self.request.user)
        elif not self.request.user.is_authenticated:
            queryset = queryset.none()

        return queryset.select_related("recipient", "template").prefetch_related("logs")

    @action(detail=False, methods=["post"])
    def send(self, request):
        serializer = SendNotificationSerializer(data=request.data)

        if serializer.is_valid():
            try:
                notification = serializer.save()

                notification_service = NotificationService()
                success = notification_service.send_notification(notification)

                response_data = NotificationSerializer(notification).data
                response_data["sent_immediately"] = success

                return Response(response_data, status=status.HTTP_201_CREATED)

            except Exception as e:
                return Response(
                    {"error": f"Ошибка отправки уведомления: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def send_async(self, request):
        serializer = SendNotificationSerializer(data=request.data)

        if serializer.is_valid():
            try:
                notification = serializer.save()

                notification_service = NotificationService()
                task_id = notification_service.send_notification_async(notification)

                response_data = NotificationSerializer(notification).data
                response_data["task_id"] = task_id
                response_data["queued_for_async_processing"] = True

                return Response(response_data, status=status.HTTP_201_CREATED)

            except Exception as e:
                return Response(
                    {"error": f"Ошибка постановки уведомления в очередь: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def send_bulk(self, request):
        serializer = BulkNotificationSerializer(data=request.data)

        if serializer.is_valid():
            try:
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

            except Exception as e:
                return Response(
                    {"error": f"Ошибка создания массовых уведомлений: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def send_bulk_async(self, request):
        serializer = BulkNotificationSerializer(data=request.data)

        if serializer.is_valid():
            try:
                from django.contrib.auth.models import User

                recipients = User.objects.filter(id__in=serializer.validated_data["recipient_ids"])
                template = None

                if serializer.validated_data.get("template_id"):
                    from .models import NotificationTemplate

                    template = NotificationTemplate.objects.get(
                        id=serializer.validated_data["template_id"]
                    )

                notification_service = NotificationService()
                task_id = notification_service.send_bulk_notifications_async(
                    recipients=list(recipients),
                    channel=serializer.validated_data["channel"],
                    message=serializer.validated_data["message"],
                    subject=serializer.validated_data.get("subject", ""),
                    template=template,
                    context_data=serializer.validated_data.get("context_data", {}),
                    priority=serializer.validated_data.get("priority", "normal"),
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

            except Exception as e:
                return Response(
                    {"error": f"Ошибка массовой постановки в очередь: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        notification = self.get_object()

        if not notification.can_retry():
            return Response(
                {"error": "Невозможно повторить отправку уведомления"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        notification_service = NotificationService()

        try:
            success = notification_service.retry_failed_notification(notification)

            return Response(
                {
                    "notification_id": notification.id,
                    "retry_successful": success,
                    "current_status": notification.status,
                    "retry_count": notification.retry_count,
                }
            )

        except Exception as e:
            return Response(
                {"error": f"Ошибка повторной отправки: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=False, methods=["get"])
    def stats(self, request):
        serializer = NotificationStatsSerializer(data=request.query_params)

        if serializer.is_valid():
            user_id = serializer.validated_data.get("user_id")
            days = serializer.validated_data.get("days", 7)

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

        pending_notifications = NotificationHelper.get_pending_notifications(limit)

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

        failed_notifications = NotificationHelper.get_failed_notifications_for_retry(limit)

        return Response(
            {
                "count": len(failed_notifications),
                "notifications": NotificationSerializer(failed_notifications, many=True).data,
            }
        )
