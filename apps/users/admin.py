from django.contrib import admin
from django.utils.html import format_html
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import UserProfile, NotificationPreference, UserDevice


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Профиль'
    fields = [
        'phone_number', 'timezone', 'language',
        'email_verified', 'phone_verified',
        'push_token', 'device_type'
    ]


class NotificationPreferenceInline(admin.StackedInline):
    model = NotificationPreference
    can_delete = False
    verbose_name_plural = 'Настройки уведомлений'
    fields = [
        'email_enabled', 'sms_enabled', 'push_enabled',
        'marketing_emails', 'security_alerts', 'system_notifications',
        'quiet_hours_start', 'quiet_hours_end', 'frequency_limit'
    ]


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline, NotificationPreferenceInline)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'device_name', 'device_type', 'is_active_colored',
        'last_seen', 'created_at'
    ]
    list_filter = ['device_type', 'is_active', 'last_seen', 'created_at']
    search_fields = ['user__username', 'device_name', 'device_id']
    readonly_fields = ['last_seen', 'created_at']
    raw_id_fields = ['user']

    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'device_id', 'device_name', 'device_type', 'is_active')
        }),
        ('Push уведомления', {
            'fields': ('push_token',)
        }),
        ('Техническая информация', {
            'fields': ('user_agent', 'ip_address'),
            'classes': ('collapse',)
        }),
        ('Временные метки', {
            'fields': ('last_seen', 'created_at'),
            'classes': ('collapse',)
        })
    )

    def is_active_colored(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">✓ Активно</span>')
        return format_html('<span style="color: red;">✗ Неактивно</span>')
    is_active_colored.short_description = 'Статус'
