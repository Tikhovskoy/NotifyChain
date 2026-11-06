"""Fallback между провайдерами одного канала, rate limit и статистика использования.

Провайдеры подменены фейковыми классами, поэтому сеть не нужна.
"""

from contextlib import ExitStack
from datetime import UTC, datetime
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from apps.notifications.exceptions import ProviderException
from apps.providers.models import Provider, ProviderUsage
from apps.providers.services import ProviderManager
from apps.providers.services.base_provider import BaseProvider


def fake_provider_class(send, provider_type="email"):
    """Строит класс провайдера, чей send_notification делегирует мок-функции `send`."""

    class FakeProvider(BaseProvider):
        def send_notification(self, recipient, message, subject="", metadata=None):
            return send(recipient, message, subject, metadata)

        def validate_config(self):
            return {"is_valid": True, "errors": []}

        def get_delivery_status(self, message_id):
            return {"status": "unknown"}

    FakeProvider.provider_type = provider_type
    return FakeProvider


def ok(name):
    return mock.Mock(return_value={"success": True, "provider": name})


def raises(error):
    return mock.Mock(side_effect=error)


class ProviderFallbackTestCase(TestCase):
    """Общая подготовка: менеджер с зарегистрированными фейковыми классами."""

    def setUp(self):
        cache.clear()  # в кэше лежат счётчики rate limit, pk провайдеров между тестами повторяются
        self.manager = ProviderManager()
        self.calls = []

    def add_provider(self, name, send, priority=1, channel="email", **extra):
        """Создаёт запись Provider и регистрирует для неё фейковый класс."""

        def tracked(*args):
            self.calls.append(name)
            return send(*args)

        self.manager.register_provider_class(name, fake_provider_class(tracked, channel))
        return Provider.objects.create(
            name=name,
            provider_type=channel,
            priority=priority,
            config={"class_name": name},
            **extra,
        )

    def send(self, channel="email", **kwargs):
        return self.manager.send_notification(
            channel=channel, recipient="to@example.com", message="текст", subject="Тема", **kwargs
        )


class InChannelFallbackTest(ProviderFallbackTestCase):
    def test_healthy_primary_is_used_and_backup_stays_idle(self):
        self.add_provider("smtp", ok("smtp"), priority=1)
        self.add_provider("sendgrid", ok("sendgrid"), priority=2)

        response = self.send()

        self.assertEqual(response["provider"], "smtp")
        self.assertEqual(self.calls, ["smtp"])

    def test_backup_is_used_when_primary_raises(self):
        self.add_provider("smtp", raises(ConnectionError("smtp down")), priority=1)
        self.add_provider("sendgrid", ok("sendgrid"), priority=2)

        response = self.send()

        self.assertEqual(response["provider"], "sendgrid")
        self.assertEqual(self.calls, ["smtp", "sendgrid"])

    def test_providers_are_tried_in_priority_order(self):
        self.add_provider("third", raises(RuntimeError("x")), priority=3)
        self.add_provider("first", raises(RuntimeError("x")), priority=1)
        self.add_provider("second", ok("second"), priority=2)

        self.send()

        self.assertEqual(self.calls, ["first", "second"])

    def test_inactive_provider_is_skipped(self):
        self.add_provider("smtp", ok("smtp"), priority=1, is_active=False)
        self.add_provider("sendgrid", ok("sendgrid"), priority=2)

        response = self.send()

        self.assertEqual(response["provider"], "sendgrid")
        self.assertEqual(self.calls, ["sendgrid"])

    def test_providers_of_other_channels_are_not_used(self):
        self.add_provider("smtp", raises(RuntimeError("down")), channel="email")
        self.add_provider("twilio", ok("twilio"), channel="sms")

        with self.assertRaises(ProviderException):
            self.send(channel="email")

        self.assertEqual(self.calls, ["smtp"])

    def test_all_providers_failing_raises_with_last_error(self):
        self.add_provider("smtp", raises(RuntimeError("smtp down")), priority=1)
        self.add_provider("sendgrid", raises(RuntimeError("sendgrid down")), priority=2)

        with self.assertRaises(ProviderException) as caught:
            self.send()

        self.assertIn("email", str(caught.exception))
        self.assertIn("sendgrid down", str(caught.exception))
        self.assertEqual(self.calls, ["smtp", "sendgrid"])

    def test_channel_without_providers_raises(self):
        with self.assertRaises(ProviderException):
            self.send(channel="push")

    def test_explicit_provider_name_disables_fallback(self):
        self.add_provider("smtp", raises(RuntimeError("smtp down")), priority=1)
        self.add_provider("sendgrid", ok("sendgrid"), priority=2)

        with self.assertRaises(ProviderException):
            self.send(provider_name="smtp")

        self.assertEqual(self.calls, ["smtp"])

    def test_unknown_explicit_provider_raises(self):
        with self.assertRaises(ProviderException):
            self.send(provider_name="nope")

    def test_unregistered_provider_class_counts_as_failure_and_falls_back(self):
        Provider.objects.create(
            name="ghost", provider_type="email", priority=1, config={"class_name": "ghost"}
        )
        self.add_provider("sendgrid", ok("sendgrid"), priority=2)

        response = self.send()

        self.assertEqual(response["provider"], "sendgrid")


def rejects(error="rejected"):
    return mock.Mock(return_value={"success": False, "error": error})


class FailureResponseFallbackTest(ProviderFallbackTestCase):
    """Реальные провайдеры не бросают исключение при сбое, а возвращают success=False."""

    def test_backup_is_used_when_primary_returns_failure_response(self):
        self.add_provider("smtp", rejects("SMTP ошибка аутентификации"), priority=1)
        self.add_provider("sendgrid", ok("sendgrid"), priority=2)

        response = self.send()

        self.assertEqual(response["provider"], "sendgrid")
        self.assertEqual(self.calls, ["smtp", "sendgrid"])

    def test_failure_response_is_recorded_as_failure_in_usage(self):
        smtp = self.add_provider("smtp", rejects(), priority=1)
        self.add_provider("sendgrid", ok("sendgrid"), priority=2)

        self.send()

        usage = ProviderUsage.objects.get(provider=smtp)
        self.assertEqual((usage.success_count, usage.failure_count), (0, 1))

    def test_all_failure_responses_raise_with_the_provider_error(self):
        self.add_provider("smtp", rejects("smtp отклонил"), priority=1)
        self.add_provider("sendgrid", rejects("sendgrid отклонил"), priority=2)

        with self.assertRaises(ProviderException) as caught:
            self.send()

        self.assertIn("sendgrid отклонил", str(caught.exception))

    def test_response_without_success_flag_is_a_failure(self):
        self.add_provider("smtp", mock.Mock(return_value={}), priority=1)
        self.add_provider("sendgrid", ok("sendgrid"), priority=2)

        response = self.send()

        self.assertEqual(response["provider"], "sendgrid")


class RateLimitFallbackTest(ProviderFallbackTestCase):
    def test_rate_limited_primary_is_skipped_in_favour_of_backup(self):
        self.add_provider("smtp", ok("smtp"), priority=1, rate_limit_per_minute=2)
        self.add_provider("sendgrid", ok("sendgrid"), priority=2)

        providers_used = [self.send()["provider"] for _ in range(3)]

        self.assertEqual(providers_used, ["smtp", "smtp", "sendgrid"])

    def test_all_providers_rate_limited_raises(self):
        self.add_provider("smtp", ok("smtp"), priority=1, rate_limit_per_minute=1)
        self.add_provider("sendgrid", ok("sendgrid"), priority=2, rate_limit_per_minute=1)
        self.send()
        self.send()

        with self.assertRaises(ProviderException):
            self.send()

    def test_hourly_limit_also_applies(self):
        self.add_provider("smtp", ok("smtp"), priority=1, rate_limit_per_hour=1)
        self.add_provider("sendgrid", ok("sendgrid"), priority=2)

        providers_used = [self.send()["provider"] for _ in range(2)]

        self.assertEqual(providers_used, ["smtp", "sendgrid"])

    def test_skipped_provider_is_not_called_and_not_counted(self):
        smtp = self.add_provider("smtp", ok("smtp"), priority=1, rate_limit_per_minute=1)
        self.add_provider("sendgrid", ok("sendgrid"), priority=2)
        self.send()

        self.send()

        self.assertEqual(self.calls, ["smtp", "sendgrid"])
        self.assertEqual(ProviderUsage.objects.get(provider=smtp).requests_count, 1)


def at(moment):
    """Замораживает «сейчас» для Django и для time.time (счётчики лимитов, TTL кэша)."""

    moment = moment.astimezone(UTC)
    stack = ExitStack()
    stack.enter_context(mock.patch("django.utils.timezone.now", return_value=moment))
    stack.enter_context(mock.patch("time.time", return_value=moment.timestamp()))
    return stack


class RateLimitWindowTest(ProviderFallbackTestCase):
    """Лимиты должны работать в любой момент часа, а не только в первую минуту."""

    def setUp(self):
        super().setUp()
        self.smtp = self.add_provider("smtp", ok("smtp"), priority=1, rate_limit_per_minute=2)
        self.add_provider("sendgrid", ok("sendgrid"), priority=2)

    def providers_used(self, count):
        return [self.send()["provider"] for _ in range(count)]

    def test_minute_limit_is_enforced_late_in_the_hour(self):
        with at(datetime(2026, 3, 1, 10, 5, tzinfo=UTC)):
            self.send()

        with at(datetime(2026, 3, 1, 10, 30, tzinfo=UTC)):
            used = self.providers_used(3)

        self.assertEqual(used, ["smtp", "smtp", "sendgrid"])

    def test_minute_counter_resets_in_the_next_minute(self):
        with at(datetime(2026, 3, 1, 10, 30, 10, tzinfo=UTC)):
            self.assertEqual(self.providers_used(3), ["smtp", "smtp", "sendgrid"])

        with at(datetime(2026, 3, 1, 10, 31, 5, tzinfo=UTC)):
            self.assertEqual(self.providers_used(1), ["smtp"])

    def test_hourly_limit_counts_requests_across_minutes(self):
        Provider.objects.filter(pk=self.smtp.pk).update(
            rate_limit_per_minute=100, rate_limit_per_hour=3
        )
        used = []
        for minute in (1, 2, 3, 4):
            with at(datetime(2026, 3, 1, 10, minute, tzinfo=UTC)):
                used.extend(self.providers_used(1))

        self.assertEqual(used, ["smtp", "smtp", "smtp", "sendgrid"])

    def test_hourly_counter_resets_in_the_next_hour(self):
        Provider.objects.filter(pk=self.smtp.pk).update(
            rate_limit_per_minute=100, rate_limit_per_hour=1
        )
        with at(datetime(2026, 3, 1, 10, 50, tzinfo=UTC)):
            self.assertEqual(self.providers_used(2), ["smtp", "sendgrid"])

        with at(datetime(2026, 3, 1, 11, 0, 30, tzinfo=UTC)):
            self.assertEqual(self.providers_used(1), ["smtp"])

    def test_limits_can_be_switched_off(self):
        with (
            self.settings(RATE_LIMIT_ENABLED=False),
            at(datetime(2026, 3, 1, 10, 30, tzinfo=UTC)),
        ):
            used = self.providers_used(4)

        self.assertEqual(used, ["smtp"] * 4)


class UsageStatisticsTest(ProviderFallbackTestCase):
    def usage(self, provider):
        return ProviderUsage.objects.get(provider=provider)

    def test_success_is_recorded(self):
        smtp = self.add_provider("smtp", ok("smtp"))

        self.send()

        usage = self.usage(smtp)
        self.assertEqual(
            (usage.requests_count, usage.success_count, usage.failure_count), (1, 1, 0)
        )
        self.assertGreaterEqual(usage.average_response_time, 0)

    def test_failure_is_recorded_for_failed_provider_and_success_for_backup(self):
        smtp = self.add_provider("smtp", raises(RuntimeError("down")), priority=1)
        sendgrid = self.add_provider("sendgrid", ok("sendgrid"), priority=2)

        self.send()

        smtp_usage, sendgrid_usage = self.usage(smtp), self.usage(sendgrid)
        self.assertEqual(
            (smtp_usage.requests_count, smtp_usage.success_count, smtp_usage.failure_count),
            (1, 0, 1),
        )
        self.assertEqual(
            (
                sendgrid_usage.requests_count,
                sendgrid_usage.success_count,
                sendgrid_usage.failure_count,
            ),
            (1, 1, 0),
        )

    def test_counters_accumulate_within_the_same_hour(self):
        smtp = self.add_provider("smtp", ok("smtp"))

        for _ in range(3):
            self.send()

        usage = self.usage(smtp)
        self.assertEqual((usage.requests_count, usage.success_count), (3, 3))
        self.assertEqual(ProviderUsage.objects.filter(provider=smtp).count(), 1)

    def test_statistics_summary(self):
        smtp = self.add_provider("smtp", raises(RuntimeError("down")), priority=1)
        self.add_provider("sendgrid", ok("sendgrid"), priority=2)
        self.send()
        self.send()

        stats = self.manager.get_provider_statistics(smtp.id)

        self.assertEqual(stats["total_requests"], 2)
        self.assertEqual(stats["failed_requests"], 2)
        self.assertEqual(stats["success_rate"], 0)
        self.assertEqual(len(stats["daily_stats"]), 1)


class ProviderManagerMiscTest(ProviderFallbackTestCase):
    def test_get_provider_prefers_default_then_priority(self):
        self.add_provider("smtp", ok("smtp"), priority=1)
        backup = self.add_provider("sendgrid", ok("sendgrid"), priority=2, is_default=True)

        instance = self.manager.get_provider("email")

        self.assertEqual(instance.name, backup.name)

    def test_get_provider_rejects_missing_and_inactive(self):
        with self.assertRaises(ProviderException):
            self.manager.get_provider("email")

        self.add_provider("smtp", ok("smtp"), is_active=False)
        with self.assertRaises(ProviderException):
            self.manager.get_provider("email", provider_name="smtp")

    def test_get_available_providers_only_active_sorted(self):
        self.add_provider("b", ok("b"), priority=2)
        self.add_provider("a", ok("a"), priority=1)
        self.add_provider("off", ok("off"), priority=0, is_active=False)

        names = [p.name for p in self.manager.get_available_providers("email")]

        self.assertEqual(names, ["a", "b"])
