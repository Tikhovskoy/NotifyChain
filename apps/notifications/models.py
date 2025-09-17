from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class NotificationTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    template_type = models.CharField(
        max_length=20,
        choices=[
            ('email', 'Email'),
            ('sms', 'SMS'),
            ('push', 'Push Notification'),
        ]
    )
    variables = models.JSONField(default=list, help_text="Список переменных для подстановки")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'notification_templates'

    def __str__(self):
        return f"{self.name} ({self.template_type})"


class Notification(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('queued', 'Queued'),
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    template = models.ForeignKey(NotificationTemplate, on_delete=models.CASCADE, null=True, blank=True)

    channel = models.CharField(
        max_length=20,
        choices=[
            ('email', 'Email'),
            ('sms', 'SMS'),
            ('push', 'Push Notification'),
        ]
    )

    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    recipient_address = models.CharField(max_length=255)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')

    context_data = models.JSONField(default=dict, help_text="Данные для подстановки в шаблон")
    metadata = models.JSONField(default=dict, help_text="Дополнительные метаданные")

    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['recipient', 'status']),
            models.Index(fields=['scheduled_at']),
        ]

    def __str__(self):
        return f"Notification to {self.recipient_address} via {self.channel}"

    def is_ready_to_send(self):
        if self.scheduled_at and self.scheduled_at > timezone.now():
            return False
        return self.status in ['pending', 'queued']

    def can_retry(self):
        return self.retry_count < self.max_retries and self.status == 'failed'


class NotificationLog(models.Model):
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='logs')
    status = models.CharField(max_length=20)
    message = models.TextField(blank=True)
    provider_response = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notification_logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"Log for {self.notification.id}: {self.status}"
