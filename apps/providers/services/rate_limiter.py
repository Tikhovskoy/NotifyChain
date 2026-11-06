import time

from django.conf import settings
from django.core.cache import cache

MINUTE = 60
HOUR = 3600


class ProviderRateLimiter:
    """Лимиты провайдеров в запросах за минуту и за час.

    Счётчики лежат в кэше Django. В продакшене это Redis (см. settings/production.py), поэтому
    лимиты общие для всех процессов gunicorn и воркеров Celery, а операции атомарны. В dev-режиме
    используется кэш в памяти процесса.

    Окна фиксированные: счётчик привязан к календарной минуте или часу и сам истекает.
    """

    def __init__(self, cache_backend=None):
        self._cache = cache_backend or cache

    def acquire(self, provider) -> bool:
        """Учитывает попытку отправки и сообщает, не превышен ли лимит провайдера."""

        if not getattr(settings, "RATE_LIMIT_ENABLED", True):
            return True

        now = int(time.time())

        in_minute = self._count(provider.id, "minute", now // MINUTE, ttl=2 * MINUTE)
        if in_minute > provider.rate_limit_per_minute:
            return False

        in_hour = self._count(provider.id, "hour", now // HOUR, ttl=2 * HOUR)
        return in_hour <= provider.rate_limit_per_hour

    def _count(self, provider_id: int, window: str, bucket: int, ttl: int) -> int:
        key = f"ratelimit:{provider_id}:{window}:{bucket}"

        if self._cache.add(key, 1, timeout=ttl):
            return 1
        try:
            return self._cache.incr(key)
        except ValueError:
            # ключ истёк между add и incr
            self._cache.add(key, 1, timeout=ttl)
            return 1
