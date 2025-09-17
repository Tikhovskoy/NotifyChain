from django.db import models
from django.contrib.auth.models import User


class SystemMetrics(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)

    notifications_sent = models.PositiveIntegerField(default=0)
    notifications_failed = models.PositiveIntegerField(default=0)
    notifications_queued = models.PositiveIntegerField(default=0)

    email_sent = models.PositiveIntegerField(default=0)
    sms_sent = models.PositiveIntegerField(default=0)
    push_sent = models.PositiveIntegerField(default=0)

    active_users = models.PositiveIntegerField(default=0)
    queue_size = models.PositiveIntegerField(default=0)

    average_delivery_time = models.FloatField(default=0.0, help_text="Среднее время доставки в секундах")

    class Meta:
        db_table = 'system_metrics'
        ordering = ['-timestamp']

    def __str__(self):
        return f"Metrics {self.timestamp.strftime('%Y-%m-%d %H:%M')}"

    @property
    def total_notifications(self):
        return self.notifications_sent + self.notifications_failed

    @property
    def success_rate(self):
        if self.total_notifications == 0:
            return 0
        return (self.notifications_sent / self.total_notifications) * 100


class AlertRule(models.Model):
    METRIC_CHOICES = [
        ('success_rate', 'Success Rate'),
        ('queue_size', 'Queue Size'),
        ('delivery_time', 'Delivery Time'),
        ('error_rate', 'Error Rate'),
    ]

    CONDITION_CHOICES = [
        ('gt', 'Greater Than'),
        ('lt', 'Less Than'),
        ('eq', 'Equal To'),
    ]

    name = models.CharField(max_length=100)
    metric = models.CharField(max_length=20, choices=METRIC_CHOICES)
    condition = models.CharField(max_length=5, choices=CONDITION_CHOICES)
    threshold = models.FloatField()

    is_active = models.BooleanField(default=True)
    notification_emails = models.JSONField(default=list, help_text="Список email для уведомлений")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'alert_rules'

    def __str__(self):
        return f"Alert: {self.name}"

    def check_condition(self, value):
        if self.condition == 'gt':
            return value > self.threshold
        elif self.condition == 'lt':
            return value < self.threshold
        elif self.condition == 'eq':
            return value == self.threshold
        return False


class Alert(models.Model):
    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('critical', 'Critical'),
    ]

    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name='alerts')
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)

    message = models.TextField()
    current_value = models.FloatField()
    threshold_value = models.FloatField()

    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'alerts'
        ordering = ['-created_at']

    def __str__(self):
        return f"Alert: {self.rule.name} - {self.severity}"


class PerformanceLog(models.Model):
    operation = models.CharField(max_length=100)
    duration = models.FloatField(help_text="Время выполнения в секундах")

    provider_name = models.CharField(max_length=100, blank=True)
    channel = models.CharField(max_length=20, blank=True)

    success = models.BooleanField()
    error_message = models.TextField(blank=True)

    metadata = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'performance_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['operation', 'timestamp']),
            models.Index(fields=['provider_name', 'success']),
        ]

    def __str__(self):
        return f"{self.operation} - {self.duration:.3f}s"


class DeliveryReport(models.Model):
    date = models.DateField()

    total_sent = models.PositiveIntegerField(default=0)
    email_sent = models.PositiveIntegerField(default=0)
    sms_sent = models.PositiveIntegerField(default=0)
    push_sent = models.PositiveIntegerField(default=0)

    total_failed = models.PositiveIntegerField(default=0)
    email_failed = models.PositiveIntegerField(default=0)
    sms_failed = models.PositiveIntegerField(default=0)
    push_failed = models.PositiveIntegerField(default=0)

    average_delivery_time = models.FloatField(default=0.0)
    peak_hour = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'delivery_reports'
        unique_together = ['date']
        ordering = ['-date']

    def __str__(self):
        return f"Report {self.date}"

    @property
    def total_notifications(self):
        return self.total_sent + self.total_failed

    @property
    def success_rate(self):
        if self.total_notifications == 0:
            return 0
        return (self.total_sent / self.total_notifications) * 100
