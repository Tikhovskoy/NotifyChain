from django.contrib import admin
from django.utils.html import format_html

from .models import SystemMetrics, AlertRule, Alert, PerformanceLog, DeliveryReport


@admin.register(SystemMetrics)
class SystemMetricsAdmin(admin.ModelAdmin):
    list_display = [
        'timestamp', 'total_notifications', 'success_rate_colored',
        'notifications_queued', 'average_delivery_time_formatted'
    ]
    list_filter = ['timestamp']
    readonly_fields = ['timestamp', 'success_rate_display', 'total_notifications_display']

    fieldsets = (
        ('Временная метка', {
            'fields': ('timestamp',)
        }),
        ('Уведомления', {
            'fields': (
                'notifications_sent', 'notifications_failed', 'notifications_queued',
                'total_notifications_display', 'success_rate_display'
            )
        }),
        ('По каналам', {
            'fields': ('email_sent', 'sms_sent', 'push_sent')
        }),
        ('Система', {
            'fields': ('active_users', 'queue_size', 'average_delivery_time')
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

    def total_notifications_display(self, obj):
        return obj.total_notifications
    total_notifications_display.short_description = 'Всего уведомлений'

    def average_delivery_time_formatted(self, obj):
        if obj.average_delivery_time < 1:
            return f"{obj.average_delivery_time * 1000:.0f}мс"
        return f"{obj.average_delivery_time:.2f}с"
    average_delivery_time_formatted.short_description = 'Время доставки'


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'metric', 'condition_display', 'threshold',
        'is_active_colored', 'created_at'
    ]
    list_filter = ['metric', 'condition', 'is_active', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'is_active')
        }),
        ('Условие', {
            'fields': ('metric', 'condition', 'threshold')
        }),
        ('Уведомления', {
            'fields': ('notification_emails',)
        }),
        ('Временные метки', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def condition_display(self, obj):
        symbols = {'gt': '>', 'lt': '<', 'eq': '='}
        return f"{obj.get_metric_display()} {symbols.get(obj.condition, obj.condition)} {obj.threshold}"
    condition_display.short_description = 'Условие'

    def is_active_colored(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">✓ Активно</span>')
        return format_html('<span style="color: red;">✗ Неактивно</span>')
    is_active_colored.short_description = 'Статус'


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = [
        'rule', 'severity_colored', 'current_value', 'threshold_value',
        'is_resolved_colored', 'created_at'
    ]
    list_filter = ['severity', 'is_resolved', 'created_at']
    search_fields = ['rule__name', 'message']
    readonly_fields = ['created_at']

    fieldsets = (
        ('Правило', {
            'fields': ('rule', 'severity')
        }),
        ('Детали', {
            'fields': ('message', 'current_value', 'threshold_value')
        }),
        ('Разрешение', {
            'fields': ('is_resolved', 'resolved_at', 'resolved_by')
        }),
        ('Время', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )

    def severity_colored(self, obj):
        colors = {
            'info': '#17a2b8',
            'warning': '#ffc107',
            'error': '#dc3545',
            'critical': '#6f42c1'
        }
        color = colors.get(obj.severity, '#6c757d')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_severity_display()
        )
    severity_colored.short_description = 'Важность'

    def is_resolved_colored(self, obj):
        if obj.is_resolved:
            return format_html('<span style="color: green;">✓ Решено</span>')
        return format_html('<span style="color: red;">✗ Активно</span>')
    is_resolved_colored.short_description = 'Статус'


@admin.register(PerformanceLog)
class PerformanceLogAdmin(admin.ModelAdmin):
    list_display = [
        'operation', 'provider_name', 'duration_formatted',
        'success_colored', 'timestamp'
    ]
    list_filter = ['operation', 'provider_name', 'success', 'timestamp']
    search_fields = ['operation', 'provider_name', 'error_message']
    readonly_fields = ['timestamp']

    fieldsets = (
        ('Операция', {
            'fields': ('operation', 'provider_name', 'channel')
        }),
        ('Результат', {
            'fields': ('success', 'duration', 'error_message')
        }),
        ('Метаданные', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Время', {
            'fields': ('timestamp',),
            'classes': ('collapse',)
        })
    )

    def duration_formatted(self, obj):
        if obj.duration < 1:
            return f"{obj.duration * 1000:.0f}мс"
        return f"{obj.duration:.3f}с"
    duration_formatted.short_description = 'Длительность'

    def success_colored(self, obj):
        if obj.success:
            return format_html('<span style="color: green;">✓ Успех</span>')
        return format_html('<span style="color: red;">✗ Ошибка</span>')
    success_colored.short_description = 'Результат'


@admin.register(DeliveryReport)
class DeliveryReportAdmin(admin.ModelAdmin):
    list_display = [
        'date', 'total_sent', 'total_failed', 'success_rate_colored',
        'average_delivery_time_formatted', 'peak_hour'
    ]
    list_filter = ['date']
    readonly_fields = ['created_at', 'updated_at', 'success_rate_display', 'total_notifications_display']

    fieldsets = (
        ('Дата', {
            'fields': ('date',)
        }),
        ('Общая статистика', {
            'fields': (
                'total_sent', 'total_failed', 'total_notifications_display',
                'success_rate_display', 'average_delivery_time'
            )
        }),
        ('По каналам - отправлено', {
            'fields': ('email_sent', 'sms_sent', 'push_sent')
        }),
        ('По каналам - ошибки', {
            'fields': ('email_failed', 'sms_failed', 'push_failed')
        }),
        ('Дополнительно', {
            'fields': ('peak_hour',)
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

    def total_notifications_display(self, obj):
        return obj.total_notifications
    total_notifications_display.short_description = 'Всего уведомлений'

    def average_delivery_time_formatted(self, obj):
        if obj.average_delivery_time < 1:
            return f"{obj.average_delivery_time * 1000:.0f}мс"
        return f"{obj.average_delivery_time:.2f}с"
    average_delivery_time_formatted.short_description = 'Время доставки'
