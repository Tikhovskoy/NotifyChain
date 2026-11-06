import logging
from typing import Any

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from apps.users.models import NotificationPreference, UserProfile

from ..exceptions import (
    NotificationException,
    NotificationNotReadyException,
    UserPreferenceException,
    ValidationException,
)
from ..models import Notification, NotificationLog, NotificationTemplate

logger = logging.getLogger("notifychain.notifications")


class NotificationService:
    def create_notification(
        self,
        recipient: User,
        channel: str,
        message: str,
        subject: str = "",
        template: NotificationTemplate | None = None,
        context_data: dict[str, Any] | None = None,
        priority: str = "normal",
        scheduled_at: timezone.datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Notification:

        if context_data is None:
            context_data = {}
        if metadata is None:
            metadata = {}

        recipient_address = self._get_recipient_address(recipient, channel)
        if not recipient_address:
            raise ValidationException(
                f"Не найден {channel} адрес для пользователя {recipient.username}"
            )

        if not self._can_send_to_user(recipient, channel):
            raise UserPreferenceException(
                f"Пользователь {recipient.username} отключил {channel} уведомления"
            )

        notification = Notification.objects.create(
            recipient=recipient,
            template=template,
            channel=channel,
            subject=subject,
            message=message,
            recipient_address=recipient_address,
            priority=priority,
            context_data=context_data,
            metadata=metadata,
            scheduled_at=scheduled_at,
        )

        self._log_notification_event(notification, "created", "Notification created successfully")

        logger.info(
            f"Создано уведомление {notification.id} для {recipient.username} через {channel}"
        )
        return notification

    def send_notification(self, notification: Notification) -> bool:

        if not notification.is_ready_to_send():
            logger.warning(f"Уведомление {notification.id} не готово к отправке")
            return False

        try:
            with transaction.atomic():
                notification.status = "sending"
                notification.save()

                self._log_notification_event(
                    notification, "sending", "Started sending notification"
                )

                success = self._deliver_notification(notification)

                if success:
                    notification.status = "sent"
                    notification.sent_at = timezone.now()
                    self._log_notification_event(
                        notification, "sent", "Notification sent successfully"
                    )
                    logger.info(f"Успешно отправлено уведомление {notification.id}")
                else:
                    notification.status = "failed"
                    notification.retry_count += 1
                    self._log_notification_event(
                        notification, "failed", "Failed to send notification"
                    )
                    logger.error(f"Ошибка отправки уведомления {notification.id}")

                notification.save()
                return success

        except Exception as e:  # noqa: BLE001
            # Граница доставки: любой сбой не должен ронять вызывающего (API, задачу Celery),
            # он фиксируется в самом уведомлении и в его журнале.
            logger.error(f"Ошибка отправки уведомления {notification.id}: {str(e)}")
            notification.status = "failed"
            notification.error_message = str(e)
            notification.retry_count += 1
            notification.save()

            self._log_notification_event(notification, "error", f"Error: {str(e)}")
            return False

    def retry_failed_notification(self, notification: Notification) -> bool:

        if not notification.can_retry():
            logger.warning(f"Невозможно повторить отправку уведомления {notification.id}")
            return False

        logger.info(
            f"Повторная отправка уведомления {notification.id}, попытка {notification.retry_count + 1}"
        )
        return self.send_notification(notification)

    def send_bulk_notifications(
        self,
        recipients: list[User],
        channel: str,
        message: str,
        subject: str = "",
        template: NotificationTemplate | None = None,
        context_data: dict[str, Any] | None = None,
        priority: str = "normal",
    ) -> list[Notification]:

        notifications = []

        for recipient in recipients:
            try:
                notification = self.create_notification(
                    recipient=recipient,
                    channel=channel,
                    message=message,
                    subject=subject,
                    template=template,
                    context_data=context_data,
                    priority=priority,
                )
                notifications.append(notification)
            except NotificationException as e:
                logger.error(f"Ошибка создания уведомления для {recipient.username}: {str(e)}")
                continue

        logger.info(f"Создано {len(notifications)} массовых уведомлений для {channel}")
        return notifications

    def send_notification_async(self, notification: Notification) -> str:

        from tasks.notification_tasks import send_notification_task

        if not notification.is_ready_to_send():
            raise NotificationNotReadyException(
                f"Уведомление {notification.id} не готово к отправке"
            )

        notification.status = "queued"
        notification.save()

        self._log_notification_event(
            notification, "queued", "Notification queued for async processing"
        )

        task = send_notification_task.delay(notification.id)

        logger.info(
            f"Уведомление {notification.id} поставлено в очередь на асинхронную отправку, task_id: {task.id}"
        )
        return task.id

    def send_bulk_notifications_async(
        self,
        recipients: list[User],
        channel: str,
        message: str,
        subject: str = "",
        template: NotificationTemplate | None = None,
        context_data: dict[str, Any] | None = None,
        priority: str = "normal",
    ) -> str:

        from tasks.notification_tasks import send_bulk_notifications_task

        notifications = self.send_bulk_notifications(
            recipients=recipients,
            channel=channel,
            message=message,
            subject=subject,
            template=template,
            context_data=context_data,
            priority=priority,
        )

        notification_ids = []
        for notification in notifications:
            notification.status = "queued"
            notification.save()
            notification_ids.append(notification.id)

        task = send_bulk_notifications_task.delay(notification_ids)

        logger.info(
            f"{len(notification_ids)} уведомлений поставлено в очередь на массовую асинхронную отправку, task_id: {task.id}"
        )
        return task.id

    def schedule_notification(
        self,
        recipient: User,
        channel: str,
        message: str,
        scheduled_at: timezone.datetime,
        subject: str = "",
        template: NotificationTemplate | None = None,
        context_data: dict[str, Any] | None = None,
        priority: str = "normal",
        metadata: dict[str, Any] | None = None,
    ) -> Notification:

        if scheduled_at <= timezone.now():
            raise ValidationException("Время отправки должно быть в будущем")

        notification = self.create_notification(
            recipient=recipient,
            channel=channel,
            message=message,
            subject=subject,
            template=template,
            context_data=context_data,
            priority=priority,
            scheduled_at=scheduled_at,
            metadata=metadata,
        )

        logger.info(f"Запланировано уведомление {notification.id} на {scheduled_at}")
        return notification

    def get_user_notifications(
        self, user: User, limit: int = 20, status: str | None = None
    ) -> list[Notification]:

        queryset = Notification.objects.filter(recipient=user)

        if status:
            queryset = queryset.filter(status=status)

        return list(queryset[:limit])

    def _get_recipient_address(self, user: User, channel: str) -> str | None:

        if channel == "email":
            return user.email if user.email else None

        elif channel == "sms":
            try:
                profile = user.profile
                return profile.phone_number if profile.phone_number else None
            except UserProfile.DoesNotExist:
                return None

        elif channel == "push":
            try:
                profile = user.profile
                return profile.push_token if profile.push_token else None
            except UserProfile.DoesNotExist:
                return None

        return None

    def _can_send_to_user(self, user: User, channel: str) -> bool:

        try:
            preferences = user.notification_preferences
        except NotificationPreference.DoesNotExist:
            return True

        channel_enabled = {
            "email": preferences.email_enabled,
            "sms": preferences.sms_enabled,
            "push": preferences.push_enabled,
        }

        return channel_enabled.get(channel, True)

    def _deliver_notification(self, notification: Notification) -> bool:

        fallback_channels = ["email", "sms", "push"]
        channels_to_try = []

        if notification.channel in fallback_channels:
            start_index = fallback_channels.index(notification.channel)
            channels_to_try = fallback_channels[start_index:]
        else:
            channels_to_try = [notification.channel]

        for channel in channels_to_try:
            recipient_address = self._get_recipient_address(notification.recipient, channel)

            if not recipient_address:
                logger.warning(
                    f"Нет {channel} адреса для пользователя {notification.recipient.username}"
                )
                continue

            if not self._can_send_to_user(notification.recipient, channel):
                logger.warning(
                    f"Пользователь {notification.recipient.username} отключил {channel} уведомления"
                )
                continue

            logger.info(f"Пытаюсь отправить уведомление {notification.id} через канал {channel}")

            if self._try_send_via_channel(notification, channel, recipient_address):
                if channel != notification.channel:
                    logger.info(
                        f"Успешный fallback для уведомления {notification.id}: {notification.channel} → {channel}"
                    )
                    notification.channel = channel
                    notification.recipient_address = recipient_address
                return True

        logger.error(f"Все каналы недоступны для уведомления {notification.id}")
        return False

    def _try_send_via_channel(
        self, notification: Notification, channel: str, recipient_address: str
    ) -> bool:

        try:
            from apps.providers.services import ProviderManager

            provider_manager = ProviderManager()

            message = notification.message
            subject = notification.subject

            if notification.template and notification.context_data:
                from .template_service import TemplateService

                template_service = TemplateService()
                rendered = template_service.render_template(
                    notification.template, notification.context_data
                )
                subject = rendered["subject"]
                message = rendered["body"]

            response = provider_manager.send_notification(
                channel=channel,
                recipient=recipient_address,
                message=message,
                subject=subject,
                metadata=notification.metadata,
            )

            self._log_notification_event(
                notification, "provider_response", f"Provider response for {channel}", response
            )

            return response.get("success", False)

        except NotificationException as e:
            logger.error(f"Ошибка доставки уведомления {notification.id} через {channel}: {str(e)}")
            notification.error_message = str(e)
            return False

    def _log_notification_event(
        self,
        notification: Notification,
        status: str,
        message: str,
        provider_response: dict[str, Any] | None = None,
    ):

        if provider_response is None:
            provider_response = {}

        NotificationLog.objects.create(
            notification=notification,
            status=status,
            message=message,
            provider_response=provider_response,
        )
