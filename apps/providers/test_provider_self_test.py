"""Проверка провайдера из админки: ProviderManager.test_provider."""

from unittest import mock

from apps.providers.testing import ProviderFallbackTestCase, ok, raises, rejects


class ProviderSelfTestTest(ProviderFallbackTestCase):
    def test_valid_config_sends_a_test_message_and_reports_success(self):
        provider = self.add_provider("smtp", ok("smtp"))

        result = self.manager.test_provider(provider.id)

        self.assertTrue(result["config_valid"])
        self.assertTrue(result["connection_test"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(self.calls, ["smtp"])

    def test_invalid_config_is_reported_and_no_message_is_sent(self):
        validate = mock.Mock(
            return_value={"is_valid": False, "errors": ["SMTP_PASSWORD не указан"]}
        )
        provider = self.add_provider("smtp", ok("smtp"), validate=validate)

        result = self.manager.test_provider(provider.id)

        self.assertFalse(result["config_valid"])
        self.assertFalse(result["connection_test"])
        self.assertIn("SMTP_PASSWORD не указан", result["errors"])
        self.assertEqual(self.calls, [], "провайдер с неверной конфигурацией не должен отправлять")

    def test_failed_test_message_is_reported(self):
        provider = self.add_provider("smtp", rejects("auth failed"))

        result = self.manager.test_provider(provider.id)

        self.assertTrue(result["config_valid"])
        self.assertFalse(result["connection_test"])

    def test_exception_while_sending_is_collected_in_errors(self):
        provider = self.add_provider("smtp", raises(ConnectionError("boom")))

        result = self.manager.test_provider(provider.id)

        self.assertFalse(result["connection_test"])
        self.assertTrue(any("boom" in error for error in result["errors"]))

    def test_exception_in_config_validation_is_collected_in_errors(self):
        validate = mock.Mock(side_effect=RuntimeError("broken validator"))
        provider = self.add_provider("smtp", ok("smtp"), validate=validate)

        result = self.manager.test_provider(provider.id)

        self.assertFalse(result["config_valid"])
        self.assertTrue(any("broken validator" in error for error in result["errors"]))
        self.assertEqual(self.calls, [])

    def test_test_recipient_depends_on_the_channel(self):
        email = self.add_provider("mail", ok("mail"), channel="email")
        sms = self.add_provider("sms", ok("sms"), channel="sms")
        push = self.add_provider("push", ok("push"), channel="push")
        seen = {}
        for provider in (email, sms, push):
            seen[provider.provider_type] = self.manager._get_test_recipient(provider.provider_type)

        self.assertEqual(seen["email"], "test@example.com")
        self.assertTrue(seen["sms"].startswith("+"))
        self.assertTrue(seen["push"])
