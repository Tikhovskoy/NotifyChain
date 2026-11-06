"""Сквозной сценарий из README: SMTP → SendGrid → SMS (Twilio) → Telegram.

Работают реальные сервисы, менеджер провайдеров и классы провайдеров. Подменена только сеть:
smtplib, requests и клиент Twilio.
"""

import os
import smtplib
from contextlib import ExitStack
from io import StringIO
from unittest import mock

import requests
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from twilio.base.exceptions import TwilioRestException

from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from apps.providers.models import ProviderUsage
from apps.users.models import UserProfile

ENV = {
    "SMTP_HOST": "smtp.example.com",
    "SMTP_USERNAME": "robot",
    "SMTP_PASSWORD": "pw",
    "FROM_EMAIL": "robot@example.com",
    "SENDGRID_API_KEY": "SG.key",
    "SENDGRID_FROM_EMAIL": "robot@example.com",
    "TWILIO_ACCOUNT_SID": "AC123",
    "TWILIO_AUTH_TOKEN": "tok",
    "TWILIO_FROM_NUMBER": "+15550001111",
    "TELEGRAM_BOT_TOKEN": "123:abc",
}


def http_response(status_code, json_data=None):
    response = mock.Mock(status_code=status_code, headers={}, text="")
    response.json.return_value = json_data or {}
    return response


class FakeInternet:
    """Подменяет внешние сервисы; `down` — какие из них сейчас недоступны."""

    def __init__(self, down=()):
        self.down = set(down)
        self.http_calls = []
        self.sms_calls = []
        self.smtp_calls = 0

    def smtp(self, *args, **kwargs):
        self.smtp_calls += 1
        if "smtp" in self.down:
            raise smtplib.SMTPConnectError(421, "service not available")
        return mock.MagicMock()

    def post(self, url, **kwargs):
        self.http_calls.append(url)
        if "sendgrid" in url:
            if "sendgrid" in self.down:
                raise requests.exceptions.ConnectionError("sendgrid unreachable")
            return http_response(202)
        if "telegram" in url:
            if "telegram" in self.down:
                return http_response(502, {"ok": False, "description": "Bad Gateway"})
            return http_response(200, {"ok": True, "result": {"message_id": 1}})
        raise AssertionError(f"неожиданный запрос {url}")

    def twilio_create(self, **kwargs):
        self.sms_calls.append(kwargs)
        if "twilio" in self.down:
            raise TwilioRestException(status=503, uri="/Messages", msg="unavailable", code=20503)
        return mock.Mock(sid="SM1", status="queued")

    def __enter__(self):
        self._stack = ExitStack()
        self._stack.enter_context(mock.patch.dict(os.environ, ENV))
        self._stack.enter_context(
            mock.patch("apps.providers.services.email_providers.smtplib.SMTP", self.smtp)
        )
        self._stack.enter_context(mock.patch("requests.post", self.post))
        client_class = self._stack.enter_context(
            mock.patch("apps.providers.services.sms_providers.Client")
        )
        client_class.return_value.messages.create.side_effect = self.twilio_create
        return self

    def __exit__(self, *exc_info):
        return self._stack.__exit__(*exc_info)


class DeliveryChainTest(TestCase):
    def setUp(self):
        cache.clear()  # счётчики rate limit лежат в кэше

    @classmethod
    def setUpTestData(cls):
        call_command("setup_providers", stdout=StringIO())
        cls.user = User.objects.create_user("alice", email="alice@example.com")
        UserProfile.objects.create(user=cls.user, phone_number="+15551234567", push_token="4242")

    def deliver(self, down=()):
        notification = Notification.objects.create(
            recipient=self.user,
            channel="email",
            subject="Заказ",
            message="Ваш заказ готов",
            recipient_address="alice@example.com",
        )
        with FakeInternet(down) as internet:
            result = NotificationService().send_notification(notification)
        notification.refresh_from_db()
        return result, notification, internet

    def usage(self):
        """Счётчики по именам провайдеров: {имя: (успехи, сбои)}."""
        return {
            row.provider.name: (row.success_count, row.failure_count)
            for row in ProviderUsage.objects.select_related("provider")
        }

    def test_everything_works_primary_smtp_delivers(self):
        result, notification, internet = self.deliver()

        self.assertTrue(result)
        self.assertEqual(notification.channel, "email")
        self.assertEqual(internet.http_calls, [])
        self.assertEqual(self.usage(), {"smtp_email": (1, 0)})

    def test_smtp_down_sendgrid_takes_over_inside_the_email_channel(self):
        result, notification, internet = self.deliver(down={"smtp"})

        self.assertTrue(result)
        self.assertEqual(notification.channel, "email")
        self.assertEqual(notification.status, "sent")
        self.assertEqual(internet.sms_calls, [])
        self.assertEqual(self.usage(), {"smtp_email": (0, 1), "sendgrid_email": (1, 0)})

    def test_both_email_providers_down_falls_back_to_sms(self):
        result, notification, internet = self.deliver(down={"smtp", "sendgrid"})

        self.assertTrue(result)
        self.assertEqual(notification.channel, "sms")
        self.assertEqual(notification.recipient_address, "+15551234567")
        self.assertEqual(len(internet.sms_calls), 1)
        self.assertEqual(
            self.usage(),
            {"smtp_email": (0, 1), "sendgrid_email": (0, 1), "twilio_sms": (1, 0)},
        )

    def test_email_and_sms_down_falls_back_to_telegram(self):
        result, notification, internet = self.deliver(down={"smtp", "sendgrid", "twilio"})

        self.assertTrue(result)
        self.assertEqual(notification.channel, "push")
        self.assertEqual(notification.recipient_address, "4242")
        self.assertEqual(
            self.usage(),
            {
                "smtp_email": (0, 1),
                "sendgrid_email": (0, 1),
                "twilio_sms": (0, 1),
                "telegram_bot": (1, 0),
            },
        )

    def test_everything_down_marks_the_notification_failed(self):
        result, notification, _ = self.deliver(down={"smtp", "sendgrid", "twilio", "telegram"})

        self.assertFalse(result)
        self.assertEqual(notification.status, "failed")
        self.assertEqual(notification.retry_count, 1)
        self.assertEqual(
            self.usage(),
            {
                "smtp_email": (0, 1),
                "sendgrid_email": (0, 1),
                "twilio_sms": (0, 1),
                "telegram_bot": (0, 1),
            },
        )
