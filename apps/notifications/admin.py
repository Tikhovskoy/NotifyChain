from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Notification, NotificationLog, NotificationTemplate
from .services import TemplateService


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "template_type", "is_active", "created_at", "variables_count"]
    list_filter = ["template_type", "is_active", "created_at"]
    search_fields = ["name", "subject", "body"]
    readonly_fields = ["created_at", "updated_at", "template_preview"]

    fieldsets = (
        ("Основная информация", {"fields": ("name", "template_type", "is_active")}),
        ("Содержание", {"fields": ("subject", "body", "variables")}),
        ("Даты", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
        ("Предварительный просмотр", {"fields": ("template_preview",), "classes": ("collapse",)}),
    )

    def variables_count(self, obj):
        return len(obj.variables) if obj.variables else 0

    variables_count.short_description = "Переменных"

    def template_preview(self, obj):
        if obj.pk:
            try:
                template_service = TemplateService()
                preview = template_service.get_template_preview(obj)
                return format_html(
                    '<div style="background: #f8f9fa; padding: 10px; border: 1px solid #dee2e6;">'
                    "<strong>Тема:</strong> {}<br><br>"
                    "<strong>Сообщение:</strong><br>{}"
                    "</div>",
                    preview["subject"],
                    preview["body"].replace("\n", "<br>"),
                )
            except Exception as e:
                return format_html('<span style="color: red;">Ошибка: {}</span>', str(e))
        return "Сохраните шаблон для просмотра"

    template_preview.short_description = "Предварительный просмотр"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "recipient_link",
        "channel",
        "status_colored",
        "priority",
        "created_at",
        "sent_at",
        "retry_count",
    ]
    list_filter = ["status", "channel", "priority", "created_at", "sent_at"]
    search_fields = ["recipient__username", "recipient__email", "subject", "recipient_address"]
    readonly_fields = [
        "created_at",
        "updated_at",
        "sent_at",
        "delivered_at",
        "logs_summary",
        "notification_actions",
    ]
    raw_id_fields = ["recipient", "template"]

    fieldsets = (
        ("Получатель", {"fields": ("recipient", "recipient_address", "channel")}),
        ("Содержание", {"fields": ("template", "subject", "message", "context_data")}),
        ("Настройки", {"fields": ("status", "priority", "scheduled_at")}),
        (
            "Повторы и ошибки",
            {"fields": ("retry_count", "max_retries", "error_message"), "classes": ("collapse",)},
        ),
        ("Метаданные", {"fields": ("metadata",), "classes": ("collapse",)}),
        (
            "Временные метки",
            {
                "fields": ("created_at", "updated_at", "sent_at", "delivered_at"),
                "classes": ("collapse",),
            },
        ),
        (
            "Логи и действия",
            {"fields": ("logs_summary", "notification_actions"), "classes": ("collapse",)},
        ),
    )

    def recipient_link(self, obj):
        url = reverse("admin:auth_user_change", args=[obj.recipient.id])
        return format_html('<a href="{}">{}</a>', url, obj.recipient.username)

    recipient_link.short_description = "Получатель"

    def status_colored(self, obj):
        colors = {
            "pending": "#6c757d",
            "queued": "#0d6efd",
            "sending": "#fd7e14",
            "sent": "#198754",
            "delivered": "#20c997",
            "failed": "#dc3545",
            "cancelled": "#6f42c1",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>', color, obj.get_status_display()
        )

    status_colored.short_description = "Статус"

    def logs_summary(self, obj):
        if obj.pk:
            logs = obj.logs.all()[:5]
            if logs:
                html = "<ul>"
                for log in logs:
                    html += f"<li><strong>{log.status}</strong>: {log.message} <em>({log.created_at})</em></li>"
                html += "</ul>"
                return format_html(html)
            return "Логов нет"
        return "Сохраните уведомление для просмотра логов"

    logs_summary.short_description = "Последние логи"

    def notification_actions(self, obj):
        if obj.pk:
            actions = []
            if obj.can_retry():
                actions.append(
                    "<button onclick=\"alert('Функция повтора будет добавлена')\">Повторить</button>"
                )
            if obj.status == "pending":
                actions.append(
                    "<button onclick=\"alert('Функция отмены будет добавлена')\">Отменить</button>"
                )
            return format_html(" ".join(actions)) if actions else "Нет доступных действий"
        return "Сохраните уведомление для просмотра действий"

    notification_actions.short_description = "Действия"


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ["notification_id", "status", "message_short", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["notification__id", "status", "message"]
    readonly_fields = ["created_at", "provider_response_formatted"]

    fieldsets = (
        ("Основная информация", {"fields": ("notification", "status", "message")}),
        (
            "Ответ провайдера",
            {"fields": ("provider_response_formatted",), "classes": ("collapse",)},
        ),
        ("Время", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    def message_short(self, obj):
        return obj.message[:100] + "..." if len(obj.message) > 100 else obj.message

    message_short.short_description = "Сообщение"

    def provider_response_formatted(self, obj):
        if obj.provider_response:
            import json

            formatted = json.dumps(obj.provider_response, indent=2, ensure_ascii=False)
            return format_html("<pre>{}</pre>", formatted)
        return "Ответа нет"

    provider_response_formatted.short_description = "Ответ провайдера"
