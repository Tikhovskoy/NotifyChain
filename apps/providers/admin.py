from django.contrib import admin
from django.utils.html import format_html
from django.db import models
from django.forms import Textarea

from .models import Provider

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