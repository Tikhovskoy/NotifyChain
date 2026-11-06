from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.providers.services.rate_limiter import ProviderRateLimiter


def provider(pk=1, per_minute=2, per_hour=100):
    return SimpleNamespace(id=pk, rate_limit_per_minute=per_minute, rate_limit_per_hour=per_hour)


class ProviderRateLimiterTest(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.limiter = ProviderRateLimiter()

    def test_attempts_up_to_the_limit_are_allowed_and_the_next_is_not(self):
        smtp = provider(per_minute=3)

        results = [self.limiter.acquire(smtp) for _ in range(4)]

        self.assertEqual(results, [True, True, True, False])

    def test_providers_have_independent_counters(self):
        first, second = provider(pk=1, per_minute=1), provider(pk=2, per_minute=1)

        self.assertTrue(self.limiter.acquire(first))
        self.assertFalse(self.limiter.acquire(first))
        self.assertTrue(self.limiter.acquire(second))

    def test_hourly_limit_applies_even_when_the_minute_limit_is_not_reached(self):
        smtp = provider(per_minute=100, per_hour=2)

        results = [self.limiter.acquire(smtp) for _ in range(3)]

        self.assertEqual(results, [True, True, False])

    def test_rejected_minute_attempts_do_not_consume_the_hourly_budget(self):
        smtp = provider(per_minute=1, per_hour=2)

        self.limiter.acquire(smtp)  # учтена и в минуте, и в часе
        for _ in range(5):
            self.limiter.acquire(smtp)  # отклонены лимитом минуты

        with mock.patch("time.time", return_value=10**9 + 120):  # следующая минута того же часа
            self.assertTrue(self.limiter.acquire(smtp))

    def test_counter_that_expired_between_add_and_incr_starts_over(self):
        fake_cache = mock.Mock()
        fake_cache.add.side_effect = [False, True, True]
        fake_cache.incr.side_effect = ValueError("Key 'x' not found")
        limiter = ProviderRateLimiter(cache_backend=fake_cache)

        self.assertTrue(limiter.acquire(provider()))

    @override_settings(RATE_LIMIT_ENABLED=False)
    def test_disabled_limiter_allows_everything_and_counts_nothing(self):
        smtp = provider(per_minute=1)

        results = [self.limiter.acquire(smtp) for _ in range(5)]

        self.assertEqual(results, [True] * 5)
        self.assertIsNone(cache.get("ratelimit:1:minute:0"))
