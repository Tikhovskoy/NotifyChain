from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import NotificationPreference, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Профиль"
    fields = [
        "phone_number",
        "timezone",
        "language",
        "email_verified",
        "phone_verified",
        "push_token",
        "device_type",
    ]


class NotificationPreferenceInline(admin.StackedInline):
    model = NotificationPreference
    can_delete = False
    verbose_name_plural = "Настройки уведомлений"
    fields = [
        "email_enabled",
        "sms_enabled",
        "push_enabled",
        "marketing_emails",
        "security_alerts",
        "system_notifications",
        "quiet_hours_start",
        "quiet_hours_end",
        "frequency_limit",
    ]


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline, NotificationPreferenceInline)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
