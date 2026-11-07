import copy
from datetime import UTC, datetime, timedelta
from unittest import mock

from django.test import TestCase

from apps.providers.models import Provider, ProviderUsage
from apps.providers.services.usage_recorder import UsageRecorder
from apps.testing import frozen_time


class UsageRecorderTest(TestCase):
    def setUp(self):
        self.provider = Provider.objects.create(name="smtp", provider_type="email")
        self.recorder = UsageRecorder()

    def usage(self):
        return ProviderUsage.objects.get(provider=self.provider)

    def test_success_creates_a_row_with_counters(self):
        self.recorder.record(self.provider, success=True, duration=0.5)

        usage = self.usage()
        self.assertEqual(
            (usage.requests_count, usage.success_count, usage.failure_count), (1, 1, 0)
        )
        self.assertAlmostEqual(usage.average_response_time, 0.5)

    def test_failure_is_counted_separately(self):
        self.recorder.record(self.provider, success=False, duration=0.1)

        usage = self.usage()
        self.assertEqual(
            (usage.requests_count, usage.success_count, usage.failure_count), (1, 0, 1)
        )

    def test_average_response_time_is_a_running_average(self):
        for duration in (1.0, 3.0, 5.0):
            self.recorder.record(self.provider, success=True, duration=duration)

        self.assertAlmostEqual(self.usage().average_response_time, 3.0)

    def test_every_hour_gets_its_own_row(self):
        with frozen_time(datetime(2026, 3, 1, 10, 59, tzinfo=UTC)):
            self.recorder.record(self.provider, success=True, duration=1)
        with frozen_time(datetime(2026, 3, 1, 11, 1, tzinfo=UTC)):
            self.recorder.record(self.provider, success=True, duration=1)
        with frozen_time(datetime(2026, 3, 2, 10, 5, tzinfo=UTC)):
            self.recorder.record(self.provider, success=True, duration=1)

        slots = set(ProviderUsage.objects.values_list("date", "hour"))
        self.assertEqual(len(slots), 3)

    def test_concurrent_writers_do_not_overwrite_each_other(self):
        """Если запись прочитана до чужого обновления, счётчик всё равно не теряется."""

        self.recorder.record(self.provider, success=True, duration=1)
        stale = self.usage()

        with mock.patch.object(
            ProviderUsage.objects,
            "get_or_create",
            side_effect=lambda **kw: (copy.copy(stale), False),
        ):
            self.recorder.record(self.provider, success=True, duration=1)
            self.recorder.record(self.provider, success=False, duration=1)

        usage = self.usage()
        self.assertEqual(
            (usage.requests_count, usage.success_count, usage.failure_count), (3, 2, 1)
        )

    def test_updated_at_is_refreshed_within_the_same_hour(self):
        first, second = (
            datetime(2026, 3, 1, 10, 5, tzinfo=UTC),
            datetime(2026, 3, 1, 10, 40, tzinfo=UTC),
        )
        with frozen_time(first):
            self.recorder.record(self.provider, success=True, duration=1)
        with frozen_time(second):
            self.recorder.record(self.provider, success=True, duration=1)

        usage = self.usage()
        self.assertEqual(usage.created_at, first)
        self.assertEqual(usage.updated_at, second)


class UsageStatisticsTest(TestCase):
    def setUp(self):
        self.provider = Provider.objects.create(name="smtp", provider_type="email")
        self.recorder = UsageRecorder()

    def test_empty_statistics(self):
        stats = self.recorder.statistics(self.provider)

        self.assertEqual(stats["total_requests"], 0)
        self.assertEqual(stats["success_rate"], 0)
        self.assertEqual(stats["daily_stats"], [])
        self.assertEqual(stats["provider_name"], "smtp")

    def test_totals_and_success_rate(self):
        for success in (True, True, True, False):
            self.recorder.record(self.provider, success=success, duration=2.0)

        stats = self.recorder.statistics(self.provider)

        self.assertEqual(stats["total_requests"], 4)
        self.assertEqual(stats["successful_requests"], 3)
        self.assertEqual(stats["failed_requests"], 1)
        self.assertEqual(stats["success_rate"], 75.0)
        self.assertEqual(stats["average_response_time"], 2.0)
        self.assertEqual(len(stats["daily_stats"]), 1)

    def test_only_the_requested_period_is_included(self):
        with frozen_time(datetime.now(UTC) - timedelta(days=10)):
            self.recorder.record(self.provider, success=False, duration=1)
        self.recorder.record(self.provider, success=True, duration=1)

        week = self.recorder.statistics(self.provider, days=7)
        month = self.recorder.statistics(self.provider, days=30)

        self.assertEqual(week["total_requests"], 1)
        self.assertEqual(month["total_requests"], 2)
