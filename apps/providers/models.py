from django.db import models


class Provider(models.Model):
    PROVIDER_TYPES = [
        ("email", "Email"),
        ("sms", "SMS"),
        ("push", "Push Notification"),
    ]

    name = models.CharField(max_length=100, unique=True, verbose_name="Название")
    provider_type = models.CharField(
        max_length=20, choices=PROVIDER_TYPES, verbose_name="Тип провайдера"
    )
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    is_default = models.BooleanField(default=False, verbose_name="По умолчанию")

    priority = models.PositiveIntegerField(default=1, verbose_name="Приоритет")

    config = models.JSONField(default=dict, verbose_name="Конфигурация")

    rate_limit_per_minute = models.PositiveIntegerField(default=60, verbose_name="Лимит в минуту")
    rate_limit_per_hour = models.PositiveIntegerField(default=1000, verbose_name="Лимит в час")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        db_table = "providers"
        verbose_name = "Провайдер"
        verbose_name_plural = "Провайдеры"
        ordering = ["provider_type", "priority"]

    def __str__(self):
        return f"{self.name} ({self.provider_type})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class ProviderUsage(models.Model):
    provider = models.ForeignKey(
        Provider, on_delete=models.CASCADE, related_name="usage_stats", verbose_name="Провайдер"
    )

    requests_count = models.PositiveIntegerField(default=0, verbose_name="Количество запросов")
    success_count = models.PositiveIntegerField(default=0, verbose_name="Успешных запросов")
    failure_count = models.PositiveIntegerField(default=0, verbose_name="Неудачных запросов")

    date = models.DateField(verbose_name="Дата")
    hour = models.PositiveIntegerField(null=True, blank=True, verbose_name="Час")

    average_response_time = models.FloatField(default=0.0, verbose_name="Среднее время ответа")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        db_table = "provider_usage"
        verbose_name = "Использование провайдера"
        verbose_name_plural = "Использование провайдеров"
        unique_together = ["provider", "date", "hour"]
        indexes = [
            models.Index(fields=["provider", "date"]),
            models.Index(fields=["date", "hour"]),
        ]

    def __str__(self):
        return f"Usage {self.provider.name} - {self.date}"

    @property
    def success_rate(self) -> float:
        if self.requests_count == 0:
            return 0
        return (self.success_count / self.requests_count) * 100
