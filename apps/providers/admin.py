from django.contrib import admin
from django.utils.html import format_html
from django.db import models
from django.forms import Textarea

from .models import Provider, ProviderCredential, ProviderUsage


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'provider_type', 'is_active_colored', 'is_default_colored',
        'priority', 'rate_limit_info', 'created_at'
    ]
    list_filter = ['provider_type', 'is_active', 'is_default', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'provider_type', 'is_active', 'is_default', 'priority')
        }),
        ('Лимиты', {
            'fields': ('rate_limit_per_minute', 'rate_limit_per_hour')
        }),
        ('Конфигурация', {
            'fields': ('config',),
            'description': 'JSON конфигурация провайдера'
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    formfield_overrides = {
        models.JSONField: {'widget': Textarea(attrs={'rows': 10, 'cols': 80})},
    }

    def is_active_colored(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">✓ Активен</span>')
        return format_html('<span style="color: red;">✗ Неактивен</span>')
    is_active_colored.short_description = 'Статус'

    def is_default_colored(self, obj):
        if obj.is_default:
            return format_html('<span style="color: blue;">★ По умолчанию</span>')
        return '-'
    is_default_colored.short_description = 'По умолчанию'

    def rate_limit_info(self, obj):
        return f"{obj.rate_limit_per_minute}/мин, {obj.rate_limit_per_hour}/час"
    rate_limit_info.short_description = 'Лимиты'


@admin.register(ProviderCredential)
class ProviderCredentialAdmin(admin.ModelAdmin):
    list_display = ['provider', 'has_api_key', 'has_username', 'endpoint_url_short', 'updated_at']
    list_filter = ['updated_at']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['provider']

    fieldsets = (
        ('Провайдер', {
            'fields': ('provider',)
        }),
        ('API ключи', {
            'fields': ('api_key', 'api_secret'),
            'description': 'API ключи для провайдера'
        }),
        ('Авторизация', {
            'fields': ('username', 'password'),
            'description': 'Данные для базовой авторизации'
        }),
        ('Настройки', {
            'fields': ('endpoint_url', 'additional_params')
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    formfield_overrides = {
        models.JSONField: {'widget': Textarea(attrs={'rows': 6, 'cols': 80})},
    }

    def has_api_key(self, obj):
        return '✓' if obj.api_key else '✗'
    has_api_key.short_description = 'API ключ'

    def has_username(self, obj):
        return '✓' if obj.username else '✗'
    has_username.short_description = 'Логин'

    def endpoint_url_short(self, obj):
        if obj.endpoint_url:
            return obj.endpoint_url[:50] + '...' if len(obj.endpoint_url) > 50 else obj.endpoint_url
        return '-'
    endpoint_url_short.short_description = 'Endpoint'


@admin.register(ProviderUsage)
class ProviderUsageAdmin(admin.ModelAdmin):
    list_display = [
        'provider', 'date', 'hour', 'requests_count', 'success_count',
        'failure_count', 'success_rate_colored', 'average_response_time_formatted'
    ]
    list_filter = ['provider', 'date', 'hour']
    readonly_fields = ['created_at', 'updated_at', 'success_rate_display']
    raw_id_fields = ['provider']

    fieldsets = (
        ('Основная информация', {
            'fields': ('provider', 'date', 'hour')
        }),
        ('Статистика запросов', {
            'fields': ('requests_count', 'success_count', 'failure_count', 'success_rate_display')
        }),
        ('Производительность', {
            'fields': ('average_response_time',)
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def success_rate_colored(self, obj):
        rate = obj.success_rate
        if rate >= 95:
            color = 'green'
        elif rate >= 80:
            color = 'orange'
        else:
            color = 'red'
        return format_html('<span style="color: {};">{:.1f}%</span>', color, rate)
    success_rate_colored.short_description = 'Успешность'

    def success_rate_display(self, obj):
        return f"{obj.success_rate:.2f}%"
    success_rate_display.short_description = 'Процент успешности'

    def average_response_time_formatted(self, obj):
        if obj.average_response_time < 1:
            return f"{obj.average_response_time * 1000:.0f}мс"
        return f"{obj.average_response_time:.2f}с"
    average_response_time_formatted.short_description = 'Время ответа'
