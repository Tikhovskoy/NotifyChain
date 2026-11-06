"""Межканальный fallback: email → sms → push (порядок из README).

Менеджер провайдеров подменён: тесты проверяют логику сервиса, а не сетевые вызовы.
"""

from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase

from apps.notifications.exceptions import ProviderException
from apps.notifications.models import Notification, NotificationLog
from apps.notifications.services import NotificationService
from apps.providers.services import ProviderManager
from apps.users.models import NotificationPreference, UserProfile

PHONE = "+15551234567"
CHAT_ID = "424242"


class CrossChannelFallbackTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", email="alice@example.com")
        UserProfile.objects.create(user=self.user, phone_number=PHONE, push_token=CHAT_ID)
        self.service = NotificationService()
        self.attempts = []

    def notification(self, channel="email"):
        return Notification.objects.create(
            recipient=self.user,
            channel=channel,
            subject="Заказ",
            message="Ваш заказ готов",
            recipient_address="alice@example.com",
        )

    def deliver(self, notification, failing_channels=()):
        """Отправляет уведомление; провайдеры каналов из failing_channels недоступны."""

        def fake_send(manager, channel, recipient, message, subject="", **kwargs):
            self.attempts.append((channel, recipient))
            if channel in failing_channels:
                raise ProviderException(f"Все провайдеры канала {channel} недоступны")
            return {"success": True, "provider": f"{channel}_provider"}

        with mock.patch.object(
            ProviderManager, "send_notification", autospec=True, side_effect=fake_send
        ):
            result = self.service.send_notification(notification)

        notification.refresh_from_db()
        return result

    def test_delivered_through_requested_channel_without_fallback(self):
        notification = self.notification("email")

        result = self.deliver(notification)

        self.assertTrue(result)
        self.assertEqual(self.attempts, [("email", "alice@example.com")])
        self.assertEqual(notification.channel, "email")
        self.assertEqual(notification.status, "sent")
        self.assertIsNotNone(notification.sent_at)

    def test_unavailable_email_falls_back_to_sms(self):
        notification = self.notification("email")

        result = self.deliver(notification, failing_channels={"email"})

        self.assertTrue(result)
        self.assertEqual(self.attempts, [("email", "alice@example.com"), ("sms", PHONE)])
        self.assertEqual(notification.channel, "sms")
        self.assertEqual(notification.recipient_address, PHONE)
        self.assertEqual(notification.status, "sent")

    def test_channels_are_tried_in_the_order_email_sms_push(self):
        notification = self.notification("email")

        result = self.deliver(notification, failing_channels={"email", "sms"})

        self.assertTrue(result)
        self.assertEqual([channel for channel, _ in self.attempts], ["email", "sms", "push"])
        self.assertEqual(notification.channel, "push")
        self.assertEqual(notification.recipient_address, CHAT_ID)

    def test_fallback_never_goes_back_to_an_earlier_channel(self):
        notification = self.notification("sms")

        self.deliver(notification, failing_channels={"sms"})

        self.assertEqual([channel for channel, _ in self.attempts], ["sms", "push"])

    def test_push_is_the_last_resort(self):
        notification = self.notification("push")

        result = self.deliver(notification, failing_channels={"push"})

        self.assertFalse(result)
        self.assertEqual([channel for channel, _ in self.attempts], ["push"])

    def test_channel_without_address_is_skipped(self):
        profile = self.user.profile
        profile.phone_number = ""
        profile.save()
        notification = self.notification("email")

        result = self.deliver(notification, failing_channels={"email"})

        self.assertTrue(result)
        self.assertEqual([channel for channel, _ in self.attempts], ["email", "push"])

    def test_channel_disabled_in_preferences_is_skipped(self):
        NotificationPreference.objects.create(
            user=self.user, email_enabled=True, sms_enabled=False, push_enabled=True
        )
        notification = self.notification("email")

        result = self.deliver(notification, failing_channels={"email"})

        self.assertTrue(result)
        self.assertEqual([channel for channel, _ in self.attempts], ["email", "push"])

    def test_all_channels_unavailable_marks_notification_failed(self):
        notification = self.notification("email")

        result = self.deliver(notification, failing_channels={"email", "sms", "push"})

        self.assertFalse(result)
        self.assertEqual([channel for channel, _ in self.attempts], ["email", "sms", "push"])
        self.assertEqual(notification.status, "failed")
        self.assertEqual(notification.retry_count, 1)
        self.assertIn("push", notification.error_message)
        self.assertTrue(notification.can_retry())

    def test_fallback_is_written_to_the_notification_log(self):
        notification = self.notification("email")

        self.deliver(notification, failing_channels={"email"})

        statuses = set(
            NotificationLog.objects.filter(notification=notification).values_list(
                "status", flat=True
            )
        )
        self.assertTrue({"sending", "provider_response", "sent"} <= statuses)

    def test_notification_that_is_not_ready_is_not_sent(self):
        notification = self.notification("email")
        Notification.objects.filter(pk=notification.pk).update(status="sent")
        notification.refresh_from_db()

        result = self.deliver(notification)

        self.assertFalse(result)
        self.assertEqual(self.attempts, [])
