from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class NotificationTemplate(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название")
    subject = models.CharField(max_length=200, verbose_name="Тема")
    body = models.TextField(verbose_name="Содержимое")
    template_type = models.CharField(
        max_length=20,
        verbose_name="Тип",
        choices=[
            ("email", "Email"),
            ("sms", "SMS"),
            ("push", "Push уведомления"),
        ],
    )
    variables = models.JSONField(default=list, verbose_name="Переменные")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    class Meta:
        db_table = "notification_templates"
        verbose_name = "Шаблон уведомления"
        verbose_name_plural = "Шаблоны уведомлений"

    def __str__(self):
        return f"{self.name} ({self.template_type})"


class Notification(models.Model):
    STATUS_CHOICES = [
        ("pending", "Ожидание"),
        ("queued", "В очереди"),
        ("sending", "Отправляется"),
        ("sent", "Отправлено"),
        ("delivered", "Доставлено"),
        ("failed", "Ошибка"),
        ("cancelled", "Отменено"),
    ]

    PRIORITY_CHOICES = [
        ("low", "Низкий"),
        ("normal", "Обычный"),
        ("high", "Высокий"),
        ("urgent", "Срочный"),
    ]

    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications", verbose_name="Получатель"
    )
    template = models.ForeignKey(
        NotificationTemplate, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Шаблон"
    )

    channel = models.CharField(
        max_length=20,
        choices=[
            ("email", "Email"),
            ("sms", "SMS"),
            ("push", "Push Notification"),
        ],
        verbose_name="Канал",
    )

    subject = models.CharField(max_length=200, blank=True, verbose_name="Тема")
    message = models.TextField(verbose_name="Сообщение")
    recipient_address = models.CharField(max_length=255, verbose_name="Адрес получателя")

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="Статус"
    )
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default="normal", verbose_name="Приоритет"
    )

    context_data = models.JSONField(default=dict, verbose_name="Данные контекста")
    metadata = models.JSONField(default=dict, verbose_name="Метаданные")

    scheduled_at = models.DateTimeField(null=True, blank=True, verbose_name="Запланировано на")
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Отправлено")
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name="Доставлено")

    error_message = models.TextField(blank=True, verbose_name="Сообщение об ошибке")
    retry_count = models.PositiveIntegerField(default=0, verbose_name="Количество попыток")
    max_retries = models.PositiveIntegerField(default=3, verbose_name="Максимум попыток")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        db_table = "notifications"
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["recipient", "status"]),
            models.Index(fields=["scheduled_at"]),
        ]

    def __str__(self):
        return f"Notification to {self.recipient_address} via {self.channel}"

    def is_ready_to_send(self):
        if self.scheduled_at and self.scheduled_at > timezone.now():
            return False
        return self.status in ["pending", "queued"]

    def can_retry(self):
        return self.retry_count < self.max_retries and self.status == "failed"


class NotificationLog(models.Model):
    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="logs", verbose_name="Уведомление"
    )
    status = models.CharField(max_length=20, verbose_name="Статус")
    message = models.TextField(blank=True, verbose_name="Сообщение")
    provider_response = models.JSONField(default=dict, verbose_name="Ответ провайдера")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        db_table = "notification_logs"
        verbose_name = "Лог уведомления"
        verbose_name_plural = "Логи уведомлений"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Log for {self.notification.id}: {self.status}"
