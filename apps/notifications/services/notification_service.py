import logging
from typing import Dict, Any, Optional, List
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import transaction

from ..models import Notification, NotificationTemplate, NotificationLog
from apps.users.models import NotificationPreference, UserProfile
from apps.providers.models import Provider

logger = logging.getLogger('notifychain.notifications')


class NotificationService:

    def create_notification(
        self,
        recipient: User,
        channel: str,
        message: str,
        subject: str = "",
        template: Optional[NotificationTemplate] = None,
        context_data: Optional[Dict[str, Any]] = None,
        priority: str = 'normal',
        scheduled_at: Optional[timezone.datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Notification:

        if context_data is None:
            context_data = {}
        if metadata is None:
            metadata = {}

        recipient_address = self._get_recipient_address(recipient, channel)
        if not recipient_address:
            raise ValueError(f"No {channel} address found for user {recipient.username}")

        if not self._can_send_to_user(recipient, channel):
            raise ValueError(f"User {recipient.username} has disabled {channel} notifications")

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
            scheduled_at=scheduled_at
        )

        self._log_notification_event(notification, 'created', 'Notification created successfully')

        logger.info(f"Created notification {notification.id} for {recipient.username} via {channel}")
        return notification

    def send_notification(self, notification: Notification) -> bool:

        if not notification.is_ready_to_send():
            logger.warning(f"Notification {notification.id} is not ready to send")
            return False

        try:
            with transaction.atomic():
                notification.status = 'sending'
                notification.save()

                self._log_notification_event(notification, 'sending', 'Started sending notification')

                success = self._deliver_notification(notification)

                if success:
                    notification.status = 'sent'
                    notification.sent_at = timezone.now()
                    self._log_notification_event(notification, 'sent', 'Notification sent successfully')
                    logger.info(f"Successfully sent notification {notification.id}")
                else:
                    notification.status = 'failed'
                    notification.retry_count += 1
                    self._log_notification_event(notification, 'failed', 'Failed to send notification')
                    logger.error(f"Failed to send notification {notification.id}")

                notification.save()
                return success

        except Exception as e:
            logger.error(f"Error sending notification {notification.id}: {str(e)}")
            notification.status = 'failed'
            notification.error_message = str(e)
            notification.retry_count += 1
            notification.save()

            self._log_notification_event(notification, 'error', f"Error: {str(e)}")
            return False

    def retry_failed_notification(self, notification: Notification) -> bool:

        if not notification.can_retry():
            logger.warning(f"Notification {notification.id} cannot be retried")
            return False

        logger.info(f"Retrying notification {notification.id}, attempt {notification.retry_count + 1}")
        return self.send_notification(notification)

    def send_bulk_notifications(
        self,
        recipients: List[User],
        channel: str,
        message: str,
        subject: str = "",
        template: Optional[NotificationTemplate] = None,
        context_data: Optional[Dict[str, Any]] = None,
        priority: str = 'normal'
    ) -> List[Notification]:

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
                    priority=priority
                )
                notifications.append(notification)
            except Exception as e:
                logger.error(f"Failed to create notification for {recipient.username}: {str(e)}")
                continue

        logger.info(f"Created {len(notifications)} bulk notifications for {channel}")
        return notifications

    def get_user_notifications(
        self,
        user: User,
        limit: int = 20,
        status: Optional[str] = None
    ) -> List[Notification]:

        queryset = Notification.objects.filter(recipient=user)

        if status:
            queryset = queryset.filter(status=status)

        return list(queryset[:limit])

    def _get_recipient_address(self, user: User, channel: str) -> Optional[str]:

        if channel == 'email':
            return user.email if user.email else None

        elif channel == 'sms':
            try:
                profile = user.profile
                return profile.phone_number if profile.phone_number else None
            except UserProfile.DoesNotExist:
                return None

        elif channel == 'push':
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
            'email': preferences.email_enabled,
            'sms': preferences.sms_enabled,
            'push': preferences.push_enabled,
        }

        return channel_enabled.get(channel, True)

    def _deliver_notification(self, notification: Notification) -> bool:

        logger.info(f"Delivering notification {notification.id} via {notification.channel}")

        return True

    def _log_notification_event(
        self,
        notification: Notification,
        status: str,
        message: str,
        provider_response: Optional[Dict[str, Any]] = None
    ):

        if provider_response is None:
            provider_response = {}

        NotificationLog.objects.create(
            notification=notification,
            status=status,
            message=message,
            provider_response=provider_response
        )