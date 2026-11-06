"""Реальные классы провайдеров с замоканной сетью.

Важный контракт, на котором держится fallback: при сбое провайдер не бросает исключение,
а возвращает {"success": False, "error": ...}.
"""

import os
import smtplib
from unittest import mock

import requests
from django.test import SimpleTestCase
from twilio.base.exceptions import TwilioRestException

from apps.providers.services.email_providers import SendGridEmailProvider, SMTPEmailProvider
from apps.providers.services.sms_providers import TwilioSMSProvider
from apps.providers.services.telegram_providers import TelegramProvider

SMTP_ENV = {
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "robot",
    "SMTP_PASSWORD": "pw",
    "SMTP_USE_TLS": "True",
    "FROM_EMAIL": "robot@example.com",
}
SENDGRID_ENV = {"SENDGRID_API_KEY": "SG.key", "SENDGRID_FROM_EMAIL": "from@example.com"}
TWILIO_ENV = {
    "TWILIO_ACCOUNT_SID": "AC123",
    "TWILIO_AUTH_TOKEN": "tok",
    "TWILIO_FROM_NUMBER": "+15550001111",
}
TELEGRAM_ENV = {"TELEGRAM_BOT_TOKEN": "123:abc"}

EMPTY_ENV = dict.fromkeys(
    (
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SENDGRID_API_KEY",
        "SENDGRID_FROM_EMAIL",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_FROM_NUMBER",
        "TELEGRAM_BOT_TOKEN",
        "FROM_EMAIL",
    ),
    "",
)


def fake_response(status_code=200, json_data=None, text="", headers=None):
    response = mock.Mock()
    response.status_code = status_code
    response.json.return_value = json_data or {}
    response.text = text
    response.headers = headers or {}
    return response


class SMTPProviderTest(SimpleTestCase):
    def provider(self, env=SMTP_ENV):
        with mock.patch.dict(os.environ, env):
            return SMTPEmailProvider()

    def test_successful_send(self):
        provider = self.provider()

        with mock.patch("apps.providers.services.email_providers.smtplib.SMTP") as smtp:
            result = provider.send("to@example.com", "Привет\nмир", "Тема")

        self.assertTrue(result["success"])
        server = smtp.return_value
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("robot", "pw")
        server.sendmail.assert_called_once()
        server.quit.assert_called_once()

    def test_missing_credentials_is_reported_as_failure(self):
        provider = self.provider({**SMTP_ENV, "SMTP_USERNAME": "", "SMTP_PASSWORD": ""})

        result = provider.send("to@example.com", "текст")

        self.assertFalse(result["success"])
        self.assertIn("учетные данные", result["error"])

    def test_authentication_error_is_returned_not_raised(self):
        provider = self.provider()

        with mock.patch(
            "apps.providers.services.email_providers.smtplib.SMTP",
            side_effect=smtplib.SMTPAuthenticationError(535, b"bad credentials"),
        ):
            result = provider.send("to@example.com", "текст")

        self.assertFalse(result["success"])
        self.assertIn("аутентификации", result["error"])

    def test_refused_recipient_is_returned_not_raised(self):
        provider = self.provider()

        with mock.patch(
            "apps.providers.services.email_providers.smtplib.SMTP",
            side_effect=smtplib.SMTPRecipientsRefused({}),
        ):
            result = provider.send("to@example.com", "текст")

        self.assertFalse(result["success"])
        self.assertIn("отклонен", result["error"])

    def test_unexpected_error_is_returned_not_raised(self):
        provider = self.provider()

        with mock.patch(
            "apps.providers.services.email_providers.smtplib.SMTP",
            side_effect=ConnectionRefusedError("down"),
        ):
            result = provider.send("to@example.com", "текст")

        self.assertFalse(result["success"])
        self.assertIn("down", result["error"])

    def test_validate_config(self):
        self.assertTrue(self.provider().validate_config()["is_valid"])

        broken = self.provider({**SMTP_ENV, "SMTP_PASSWORD": "", "FROM_EMAIL": ""})
        report = broken.validate_config()
        self.assertFalse(report["is_valid"])
        self.assertTrue(report["errors"])

    def test_delivery_status_is_unknown(self):
        self.assertEqual(self.provider().get_delivery_status("1")["status"], "unknown")


class SendGridProviderTest(SimpleTestCase):
    def provider(self, env=SENDGRID_ENV):
        with mock.patch.dict(os.environ, env):
            return SendGridEmailProvider()

    def test_successful_send(self):
        provider = self.provider()
        response = fake_response(202, headers={"X-Message-Id": "abc"})

        with mock.patch("requests.post", return_value=response) as post:
            result = provider.send("to@example.com", "текст", "Тема")

        self.assertTrue(result["success"])
        self.assertEqual(result["message_id"], "abc")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer SG.key")

    def test_api_error_is_returned_not_raised(self):
        provider = self.provider()

        with mock.patch("requests.post", return_value=fake_response(401, text="denied")):
            result = provider.send("to@example.com", "текст")

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], 401)

    def test_timeout_and_network_errors_are_returned_not_raised(self):
        provider = self.provider()
        for error, fragment in [
            (requests.exceptions.Timeout(), "таймаут"),
            (requests.exceptions.ConnectionError("no route"), "no route"),
            (RuntimeError("странно"), "странно"),
        ]:
            with self.subTest(error=type(error).__name__):
                with mock.patch("requests.post", side_effect=error):
                    result = provider.send("to@example.com", "текст")

                self.assertFalse(result["success"])
                self.assertIn(fragment, result["error"])

    def test_missing_key_or_sender_is_failure(self):
        for env in (
            {**SENDGRID_ENV, "SENDGRID_API_KEY": ""},
            {**SENDGRID_ENV, "SENDGRID_FROM_EMAIL": ""},
        ):
            with self.subTest(env=env):
                result = self.provider(env).send("to@example.com", "текст")

                self.assertFalse(result["success"])

    def test_validate_config_and_status(self):
        self.assertTrue(self.provider().validate_config()["is_valid"])
        self.assertFalse(self.provider({"SENDGRID_API_KEY": ""}).validate_config()["is_valid"])
        self.assertIn("status", self.provider().get_delivery_status("1"))


class TwilioProviderTest(SimpleTestCase):
    def provider(self, env=TWILIO_ENV):
        with (
            mock.patch.dict(os.environ, env),
            mock.patch("apps.providers.services.sms_providers.Client") as client_class,
        ):
            provider = TwilioSMSProvider()
        self.client = client_class.return_value
        return provider

    def test_successful_send_normalizes_number_and_joins_subject(self):
        provider = self.provider()
        self.client.messages.create.return_value = mock.Mock(sid="SM1", status="queued")

        result = provider.send("15551234567", "текст", "Тема")

        self.assertTrue(result["success"])
        self.assertEqual(result["message_id"], "SM1")
        kwargs = self.client.messages.create.call_args.kwargs
        self.assertEqual(kwargs["to"], "+15551234567")
        self.assertEqual(kwargs["from_"], "+15550001111")
        self.assertEqual(kwargs["body"], "Тема\n\nтекст")

    def test_long_message_is_truncated(self):
        provider = self.provider()
        self.client.messages.create.return_value = mock.Mock(sid="SM1", status="queued")

        provider.send("+15551234567", "я" * 2000)

        body = self.client.messages.create.call_args.kwargs["body"]
        self.assertEqual(len(body), 1600)
        self.assertTrue(body.endswith("..."))

    def test_twilio_api_error_is_returned_not_raised(self):
        provider = self.provider()
        self.client.messages.create.side_effect = TwilioRestException(
            status=400, uri="/Messages", msg="bad number", code=21211
        )

        result = provider.send("+15551234567", "текст")

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], 21211)

    def test_unexpected_error_is_returned_not_raised(self):
        provider = self.provider()
        self.client.messages.create.side_effect = TimeoutError("slow")

        result = provider.send("+15551234567", "текст")

        self.assertFalse(result["success"])
        self.assertIn("slow", result["error"])

    def test_not_configured_provider_reports_failure(self):
        provider = self.provider({**TWILIO_ENV, "TWILIO_ACCOUNT_SID": "", "TWILIO_AUTH_TOKEN": ""})

        result = provider.send("+15551234567", "текст")

        self.assertFalse(result["success"])
        self.assertIn("конфигурации", result["error"])

    def test_missing_sender_number_is_failure(self):
        provider = self.provider({**TWILIO_ENV, "TWILIO_FROM_NUMBER": ""})

        self.assertFalse(provider.send("+15551234567", "текст")["success"])

    def test_validate_config(self):
        self.assertTrue(self.provider().validate_config()["is_valid"])
        self.assertFalse(self.provider({"TWILIO_FROM_NUMBER": "555"}).validate_config()["is_valid"])

    def test_message_status(self):
        provider = self.provider()
        self.client.messages.return_value.fetch.return_value = mock.Mock(
            status="delivered", error_code=None, error_message=None, price="-0.01", price_unit="USD"
        )

        status = provider.get_delivery_status("SM1")

        self.assertTrue(status["success"])
        self.assertEqual(status["status"], "delivered")

    def test_message_status_errors_are_returned_not_raised(self):
        provider = self.provider()
        self.client.messages.return_value.fetch.side_effect = TwilioRestException(
            status=404, uri="/Messages/SM1", msg="not found", code=20404
        )
        self.assertFalse(provider.get_delivery_status("SM1")["success"])

        self.client.messages.return_value.fetch.side_effect = RuntimeError("boom")
        self.assertFalse(provider.get_delivery_status("SM1")["success"])

        self.assertFalse(self.provider(EMPTY_ENV).get_delivery_status("SM1")["success"])


class TelegramProviderTest(SimpleTestCase):
    def provider(self, env=TELEGRAM_ENV):
        with mock.patch.dict(os.environ, env):
            return TelegramProvider()

    def test_successful_send(self):
        provider = self.provider()
        response = fake_response(200, {"ok": True, "result": {"message_id": 77}})

        with mock.patch("requests.post", return_value=response) as post:
            result = provider.send("@channel", "текст", "Тема")

        self.assertTrue(result["success"])
        self.assertEqual(result["message_id"], 77)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["chat_id"], "channel")
        self.assertEqual(payload["text"], "*Тема*\n\nтекст")

    def test_api_error_is_returned_not_raised(self):
        provider = self.provider()
        response = fake_response(400, {"ok": False, "description": "chat not found"})

        with mock.patch("requests.post", return_value=response):
            result = provider.send("12345", "текст")

        self.assertFalse(result["success"])
        self.assertIn("chat not found", result["error"])

    def test_timeout_and_network_errors_are_returned_not_raised(self):
        provider = self.provider()
        for error in (
            requests.exceptions.Timeout(),
            requests.exceptions.ConnectionError("no route"),
            ValueError("bad json"),
        ):
            with self.subTest(error=type(error).__name__):
                with mock.patch("requests.post", side_effect=error):
                    result = provider.send("12345", "текст")

                self.assertFalse(result["success"])

    def test_missing_token_is_failure(self):
        result = self.provider({"TELEGRAM_BOT_TOKEN": ""}).send("12345", "текст")

        self.assertFalse(result["success"])

    def test_validate_config_and_status(self):
        self.assertTrue(self.provider().validate_config()["is_valid"])
        self.assertFalse(self.provider({"TELEGRAM_BOT_TOKEN": ""}).validate_config()["is_valid"])
        self.assertEqual(self.provider().get_delivery_status("1")["status"], "delivered")

    def test_bot_info(self):
        provider = self.provider()
        ok = fake_response(
            200, {"ok": True, "result": {"id": 1, "username": "bot", "first_name": "Bot"}}
        )

        with mock.patch("requests.get", return_value=ok):
            self.assertTrue(provider.get_bot_info()["success"])

        denied = fake_response(401, {"ok": False, "description": "Unauthorized"})
        with mock.patch("requests.get", return_value=denied):
            self.assertFalse(provider.get_bot_info()["success"])

        with mock.patch("requests.get", side_effect=requests.exceptions.Timeout()):
            self.assertFalse(provider.get_bot_info()["success"])

        self.assertFalse(self.provider({"TELEGRAM_BOT_TOKEN": ""}).get_bot_info()["success"])
