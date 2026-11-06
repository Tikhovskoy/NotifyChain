import logging
from typing import Dict, Any, List, Optional
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from .models import Notification
from .exceptions import ValidationException, UserPreferenceException

logger = logging.getLogger("notifychain.notifications")


class NotificationValidator:
    @staticmethod
    def validate_recipient(recipient: User, channel: str) -> bool:

        if not isinstance(recipient, User):
            raise ValidationException("Получатель должен быть экземпляром User")

        if not recipient.is_active:
            raise ValidationException("Невозможно отправлять уведомления неактивным пользователям")

        if channel == "email" and not recipient.email:
            raise ValidationException("У пользователя нет email адреса")

        return True

    @staticmethod
    def validate_channel(channel: str) -> bool:

        valid_channels = ["email", "sms", "push"]
        if channel not in valid_channels:
            raise ValidationException(
                f"Неверный канал: {channel}. Должен быть одним из {valid_channels}"
            )

        return True

    @staticmethod
    def validate_priority(priority: str) -> bool:

        valid_priorities = ["low", "normal", "high", "urgent"]
        if priority not in valid_priorities:
            raise ValidationException(
                f"Неверный приоритет: {priority}. Должен быть одним из {valid_priorities}"
            )

        return True

    @staticmethod
    def validate_message_content(message: str, subject: str = "") -> bool:

        if not message or not message.strip():
            raise ValidationException("Содержимое сообщения не может быть пустым")

        if len(message) > 10000:
            raise ValidationException("Сообщение слишком длинное (максимум 10000 символов)")

        if subject and len(subject) > 200:
            raise ValidationException("Тема слишком длинная (максимум 200 символов)")

        return True


class NotificationHelper:
    @staticmethod
    def get_user_notification_stats(user: User) -> Dict[str, Any]:

        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        notifications = Notification.objects.filter(recipient=user)

        stats = {
            "total": notifications.count(),
            "today": notifications.filter(created_at__date=today).count(),
            "this_week": notifications.filter(created_at__date__gte=week_ago).count(),
            "this_month": notifications.filter(created_at__date__gte=month_ago).count(),
            "by_status": {},
            "by_channel": {},
            "recent": list(
                notifications.order_by("-created_at")[:5].values(
                    "id", "channel", "subject", "status", "created_at"
                )
            ),
        }

        for status_choice in Notification.STATUS_CHOICES:
            status = status_choice[0]
            stats["by_status"][status] = notifications.filter(status=status).count()

        for channel_choice in ["email", "sms", "push"]:
            stats["by_channel"][channel_choice] = notifications.filter(
                channel=channel_choice
            ).count()

        return stats

    @staticmethod
    def check_rate_limit(user: User, channel: str, time_window_minutes: int = 60) -> bool:

        time_threshold = timezone.now() - timedelta(minutes=time_window_minutes)

        try:
            preferences = user.notification_preferences
            limit = preferences.frequency_limit
        except:
            limit = 50

        recent_count = Notification.objects.filter(
            recipient=user, channel=channel, created_at__gte=time_threshold
        ).count()

        return recent_count < limit

    @staticmethod
    def is_quiet_time(user: User) -> bool:

        try:
            preferences = user.notification_preferences
            if not preferences.quiet_hours_start or not preferences.quiet_hours_end:
                return False

            current_time = timezone.now().time()
            return preferences.is_quiet_time(current_time)

        except:
            return False

    @staticmethod
    def get_pending_notifications(limit: int = 100) -> List[Notification]:

        return list(
            Notification.objects.filter(status="pending").order_by("priority", "created_at")[:limit]
        )

    @staticmethod
    def get_failed_notifications_for_retry(limit: int = 50) -> List[Notification]:

        return list(
            Notification.objects.filter(status="failed")
            .exclude(retry_count__gte=3)
            .order_by("created_at")[:limit]
        )

    @staticmethod
    def cleanup_old_notifications(days: int = 90) -> int:

        cutoff_date = timezone.now() - timedelta(days=days)

        deleted_count = Notification.objects.filter(
            created_at__lt=cutoff_date, status__in=["sent", "delivered", "failed"]
        ).delete()[0]

        logger.info(f"Очищено {deleted_count} старых уведомлений")
        return deleted_count

    @staticmethod
    def format_notification_for_display(notification: Notification) -> Dict[str, Any]:

        return {
            "id": notification.id,
            "recipient": notification.recipient.username,
            "channel": notification.get_channel_display(),
            "subject": notification.subject,
            "status": notification.get_status_display(),
            "priority": notification.get_priority_display(),
            "created_at": notification.created_at,
            "sent_at": notification.sent_at,
            "error_message": notification.error_message,
            "retry_count": notification.retry_count,
            "can_retry": notification.can_retry(),
        }
