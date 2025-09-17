from django.db import models
from django.core.exceptions import ValidationError


class Provider(models.Model):
    PROVIDER_TYPES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('push', 'Push Notification'),
    ]

    name = models.CharField(max_length=100, unique=True)
    provider_type = models.CharField(max_length=20, choices=PROVIDER_TYPES)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    priority = models.PositiveIntegerField(default=1, help_text="Приоритет использования (1 - высший)")

    config = models.JSONField(
        default=dict,
        help_text="Конфигурация провайдера (API ключи, настройки)"
    )

    rate_limit_per_minute = models.PositiveIntegerField(
        default=60,
        help_text="Лимит запросов в минуту"
    )
    rate_limit_per_hour = models.PositiveIntegerField(
        default=1000,
        help_text="Лимит запросов в час"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'providers'
        ordering = ['provider_type', 'priority']
        unique_together = ['provider_type', 'is_default']

    def __str__(self):
        return f"{self.name} ({self.provider_type})"

    def clean(self):
        if self.is_default:
            existing_default = Provider.objects.filter(
                provider_type=self.provider_type,
                is_default=True
            ).exclude(id=self.id)

            if existing_default.exists():
                raise ValidationError(
                    f"Default provider for {self.provider_type} already exists"
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ProviderUsage(models.Model):
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name='usage_stats')

    requests_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)

    date = models.DateField()
    hour = models.PositiveIntegerField(null=True, blank=True)

    average_response_time = models.FloatField(default=0.0, help_text="Среднее время ответа в секундах")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'provider_usage'
        unique_together = ['provider', 'date', 'hour']
        indexes = [
            models.Index(fields=['provider', 'date']),
            models.Index(fields=['date', 'hour']),
        ]

    def __str__(self):
        return f"Usage {self.provider.name} - {self.date}"

    @property
    def success_rate(self):
        if self.requests_count == 0:
            return 0
        return (self.success_count / self.requests_count) * 100


class ProviderCredential(models.Model):
    provider = models.OneToOneField(Provider, on_delete=models.CASCADE, related_name='credentials')

    api_key = models.CharField(max_length=255, blank=True)
    api_secret = models.CharField(max_length=255, blank=True)

    username = models.CharField(max_length=100, blank=True)
    password = models.CharField(max_length=255, blank=True)

    endpoint_url = models.URLField(blank=True)

    additional_params = models.JSONField(
        default=dict,
        help_text="Дополнительные параметры для провайдера"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'provider_credentials'

    def __str__(self):
        return f"Credentials for {self.provider.name}"
