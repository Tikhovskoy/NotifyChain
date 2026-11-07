"""Сериализаторы только для документации OpenAPI: описывают ответы действий.

Сами ответы собираются во views вручную, поэтому эти классы в рантайме не используются.
"""

from rest_framework import serializers

from .serializers import NotificationSerializer


class ErrorSerializer(serializers.Serializer):
    error = serializers.CharField()
    code = serializers.CharField()


class SendResultSerializer(NotificationSerializer):
    sent_immediately = serializers.BooleanField()

    class Meta(NotificationSerializer.Meta):
        fields = [*NotificationSerializer.Meta.fields, "sent_immediately"]


class QueuedResultSerializer(NotificationSerializer):
    task_id = serializers.CharField()
    queued_for_async_processing = serializers.BooleanField()

    class Meta(NotificationSerializer.Meta):
        fields = [*NotificationSerializer.Meta.fields, "task_id", "queued_for_async_processing"]


class BulkItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    recipient = serializers.CharField(help_text="Имя пользователя")
    status = serializers.CharField()


class BulkCreatedSerializer(serializers.Serializer):
    message = serializers.CharField()
    notifications = BulkItemSerializer(many=True)


class BulkQueuedSerializer(serializers.Serializer):
    message = serializers.CharField()
    recipient_count = serializers.IntegerField()
    task_id = serializers.CharField()
    queued_for_async_processing = serializers.BooleanField()


class RetryResultSerializer(serializers.Serializer):
    notification_id = serializers.IntegerField()
    retry_successful = serializers.BooleanField()
    current_status = serializers.CharField()
    retry_count = serializers.IntegerField()


class NotificationListResultSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    notifications = NotificationSerializer(many=True)


class TemplatePreviewResultSerializer(serializers.Serializer):
    template_id = serializers.IntegerField()
    template_name = serializers.CharField()
    rendered_subject = serializers.CharField()
    rendered_body = serializers.CharField()
    context_data = serializers.JSONField()


class TemplateValidationResultSerializer(serializers.Serializer):
    template_id = serializers.IntegerField()
    template_name = serializers.CharField()
    is_valid = serializers.BooleanField()
    errors = serializers.ListField(child=serializers.CharField())
    warnings = serializers.ListField(child=serializers.CharField())
    required_variables = serializers.ListField(child=serializers.CharField())
