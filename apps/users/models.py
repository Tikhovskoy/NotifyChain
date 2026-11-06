from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator


class UserProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile", verbose_name="Пользователь"
    )

    phone_regex = RegexValidator(regex=r"^\+?1?\d{9,15}$")
    phone_number = models.CharField(
        validators=[phone_regex], max_length=17, blank=True, verbose_name="Номер телефона"
    )

    timezone = models.CharField(max_length=50, default="UTC", verbose_name="Часовой пояс")
    language = models.CharField(max_length=10, default="en", verbose_name="Язык")

    email_verified = models.BooleanField(default=False, verbose_name="Email подтвержден")
    phone_verified = models.BooleanField(default=False, verbose_name="Телефон подтвержден")

    push_token = models.CharField(max_length=255, blank=True, verbose_name="Push токен")
    device_type = models.CharField(
        max_length=20,
        choices=[
            ("ios", "iOS"),
            ("android", "Android"),
            ("web", "Web"),
        ],
        blank=True,
        verbose_name="Тип устройства",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        db_table = "user_profiles"
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

    def __str__(self):
        return f"Profile of {self.user.username}"

    @property
    def display_name(self):
        if self.user.first_name and self.user.last_name:
            return f"{self.user.first_name} {self.user.last_name}"
        return self.user.username


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
        verbose_name="Пользователь",
    )

    email_enabled = models.BooleanField(default=True, verbose_name="Email включен")
    sms_enabled = models.BooleanField(default=False, verbose_name="SMS включен")
    push_enabled = models.BooleanField(default=True, verbose_name="Push включен")

    marketing_emails = models.BooleanField(default=False, verbose_name="Маркетинговые письма")
    security_alerts = models.BooleanField(default=True, verbose_name="Оповещения безопасности")
    system_notifications = models.BooleanField(default=True, verbose_name="Системные уведомления")

    quiet_hours_start = models.TimeField(null=True, blank=True, verbose_name="Начало тихих часов")
    quiet_hours_end = models.TimeField(null=True, blank=True, verbose_name="Конец тихих часов")

    frequency_limit = models.PositiveIntegerField(default=50, verbose_name="Лимит частоты")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        db_table = "notification_preferences"
        verbose_name = "Настройки уведомлений"
        verbose_name_plural = "Настройки уведомлений"

    def __str__(self):
        return f"Preferences of {self.user.username}"

    def is_quiet_time(self, current_time):
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False

        if self.quiet_hours_start <= self.quiet_hours_end:
            return self.quiet_hours_start <= current_time <= self.quiet_hours_end
        else:
            return current_time >= self.quiet_hours_start or current_time <= self.quiet_hours_end


class UserDevice(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="devices", verbose_name="Пользователь"
    )

    device_id = models.CharField(max_length=255, unique=True, verbose_name="ID устройства")
    device_name = models.CharField(max_length=100, blank=True, verbose_name="Название устройства")
    device_type = models.CharField(
        max_length=20,
        choices=[
            ("ios", "iOS"),
            ("android", "Android"),
            ("web", "Web"),
        ],
        verbose_name="Тип устройства",
    )

    push_token = models.CharField(max_length=255, blank=True, verbose_name="Push токен")
    is_active = models.BooleanField(default=True, verbose_name="Активно")

    user_agent = models.TextField(blank=True, verbose_name="User Agent")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP адрес")

    last_seen = models.DateTimeField(auto_now=True, verbose_name="Последний визит")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        db_table = "user_devices"
        verbose_name = "Устройство пользователя"
        verbose_name_plural = "Устройства пользователей"
        unique_together = ["user", "device_id"]

    def __str__(self):
        return f"{self.device_name or self.device_id} - {self.user.username}"
