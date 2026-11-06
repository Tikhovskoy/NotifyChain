from django.contrib.auth.models import User
from rest_framework import serializers

from .exceptions import NotificationException
from .models import Notification, NotificationLog, NotificationTemplate
from .services import NotificationService, TemplateService
from .utils import NotificationValidator


class NotificationTemplateSerializer(serializers.ModelSerializer):
    template_service_class = TemplateService

    variables_count = serializers.SerializerMethodField()

    class Meta:
        model = NotificationTemplate
        fields = [
            "id",
            "name",
            "subject",
            "body",
            "template_type",
            "variables",
            "variables_count",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_variables_count(self, obj):
        return len(obj.variables) if obj.variables else 0

    def validate(self, data):
        template_service = self.context.get("template_service") or self.template_service_class()

        template = NotificationTemplate(**data)
        validation_result = template_service.validate_template(template)

        if not validation_result["is_valid"]:
            raise serializers.ValidationError({"template_errors": validation_result["errors"]})

        return data


class NotificationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationLog
        fields = ["id", "status", "message", "provider_response", "created_at"]
        read_only_fields = ["created_at"]


class NotificationSerializer(serializers.ModelSerializer):
    recipient_username = serializers.CharField(source="recipient.username", read_only=True)
    template_name = serializers.CharField(source="template.name", read_only=True)
    logs = NotificationLogSerializer(many=True, read_only=True)
    can_retry = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "recipient",
            "recipient_username",
            "recipient_address",
            "template",
            "template_name",
            "channel",
            "subject",
            "message",
            "status",
            "priority",
            "context_data",
            "metadata",
            "scheduled_at",
            "sent_at",
            "delivered_at",
            "error_message",
            "retry_count",
            "max_retries",
            "can_retry",
            "created_at",
            "updated_at",
            "logs",
        ]
        read_only_fields = [
            "sent_at",
            "delivered_at",
            "error_message",
            "retry_count",
            "created_at",
            "updated_at",
            "logs",
        ]

    def get_can_retry(self, obj):
        return obj.can_retry()


class NotificationRequestSerializer(serializers.Serializer):
    """Общие поля запросов на отправку: канал, текст, шаблон и приоритет.

    Сервис берётся из контекста (его кладёт представление) или создаётся из `service_class`,
    поэтому в тестах его можно подменить.
    """

    service_class = NotificationService

    channel = serializers.ChoiceField(choices=["email", "sms", "push"])
    message = serializers.CharField(max_length=10000)
    subject = serializers.CharField(max_length=200, required=False, allow_blank=True)
    template_id = serializers.IntegerField(required=False, allow_null=True)
    context_data = serializers.JSONField(default=dict)
    priority = serializers.ChoiceField(
        choices=["low", "normal", "high", "urgent"], default="normal"
    )

    def get_service(self):
        return self.context.get("service") or self.service_class()

    def get_template(self):
        template_id = self.validated_data.get("template_id")
        return NotificationTemplate.objects.get(id=template_id) if template_id else None

    def validate_template_id(self, value):
        if value:
            try:
                template = NotificationTemplate.objects.get(id=value)
            except NotificationTemplate.DoesNotExist:
                raise serializers.ValidationError("Шаблон не найден") from None
            if not template.is_active:
                raise serializers.ValidationError("Шаблон неактивен")
        return value

    def delivery_options(self):
        """Параметры сервиса, общие для одиночной и массовой отправки."""

        data = self.validated_data
        return {
            "channel": data["channel"],
            "message": data["message"],
            "subject": data.get("subject", ""),
            "template": self.get_template(),
            "context_data": data.get("context_data", {}),
            "priority": data.get("priority", "normal"),
        }


class SendNotificationSerializer(NotificationRequestSerializer):
    recipient_id = serializers.IntegerField()
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)
    metadata = serializers.JSONField(default=dict)

    def validate_recipient_id(self, value):
        try:
            user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь не найден") from None
        if not user.is_active:
            raise serializers.ValidationError("Пользователь неактивен")
        return value

    def validate(self, data):
        try:
            user = User.objects.get(id=data["recipient_id"])
            NotificationValidator.validate_recipient(user, data["channel"])
            NotificationValidator.validate_channel(data["channel"])
            NotificationValidator.validate_priority(data["priority"])
            NotificationValidator.validate_message_content(data["message"], data.get("subject", ""))
        except NotificationException as e:
            raise serializers.ValidationError(str(e)) from e

        return data

    def create(self, validated_data):
        return self.get_service().create_notification(
            recipient=User.objects.get(id=validated_data["recipient_id"]),
            scheduled_at=validated_data.get("scheduled_at"),
            metadata=validated_data.get("metadata", {}),
            **self.delivery_options(),
        )


class BulkNotificationSerializer(NotificationRequestSerializer):
    recipient_ids = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=1000
    )

    def validate_recipient_ids(self, value):
        unique_ids = list(set(value))
        existing_users = User.objects.filter(id__in=unique_ids, is_active=True)

        if len(existing_users) != len(unique_ids):
            existing_ids = {user.id for user in existing_users}
            invalid_ids = set(unique_ids) - existing_ids
            raise serializers.ValidationError(f"Invalid or inactive user IDs: {list(invalid_ids)}")

        return unique_ids

    def get_recipients(self):
        if not hasattr(self, "_recipients"):
            self._recipients = list(
                User.objects.filter(id__in=self.validated_data["recipient_ids"])
            )
        return self._recipients

    def create(self, validated_data):
        """Создаёт уведомления для получателей и возвращает их (без отправки)."""

        return self.get_service().send_bulk_notifications(
            recipients=self.get_recipients(), **self.delivery_options()
        )

    def enqueue(self):
        """Создаёт уведомления и ставит их в очередь Celery. Возвращает id задачи."""

        return self.get_service().send_bulk_notifications_async(
            recipients=self.get_recipients(), **self.delivery_options()
        )


class TemplatePreviewSerializer(serializers.Serializer):
    template_id = serializers.IntegerField()
    context_data = serializers.JSONField(default=dict)

    def validate_template_id(self, value):
        try:
            NotificationTemplate.objects.get(id=value)
            return value
        except NotificationTemplate.DoesNotExist:
            raise serializers.ValidationError("Шаблон не найден") from None


class NotificationStatsSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False)
    days = serializers.IntegerField(default=7, min_value=1, max_value=365)

    def validate_user_id(self, value):
        if value:
            try:
                User.objects.get(id=value)
                return value
            except User.DoesNotExist:
                raise serializers.ValidationError("Пользователь не найден") from None
        return value
