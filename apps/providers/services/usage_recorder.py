from datetime import timedelta
from typing import Any

from django.db.models import ExpressionWrapper, F, FloatField, Value
from django.utils import timezone

from ..models import Provider, ProviderUsage


class UsageRecorder:
    """Запись и сводка статистики использования провайдеров.

    Статистика ведётся по строке на каждый час: (провайдер, дата, час).
    """

    def record(self, provider: Provider, success: bool, duration: float) -> None:
        """Учитывает одну попытку отправки.

        Счётчики обновляются одним UPDATE через F-выражения, поэтому параллельные записи
        (воркеры Celery, процессы gunicorn) не затирают друг друга.
        """

        now = timezone.now()
        usage, _ = ProviderUsage.objects.get_or_create(
            provider=provider, date=now.date(), hour=now.hour
        )

        requests_before = F("requests_count")
        running_average = ExpressionWrapper(
            (F("average_response_time") * requests_before + Value(float(duration)))
            / (requests_before + 1),
            output_field=FloatField(),
        )

        ProviderUsage.objects.filter(pk=usage.pk).update(
            requests_count=requests_before + 1,
            success_count=F("success_count") + int(success),
            failure_count=F("failure_count") + int(not success),
            average_response_time=running_average,
            updated_at=now,
        )

    def statistics(self, provider: Provider, days: int = 7) -> dict[str, Any]:
        """Сводка по провайдеру за последние `days` дней."""

        start_date = timezone.now().date() - timedelta(days=days)
        usage_stats = list(
            ProviderUsage.objects.filter(provider=provider, date__gte=start_date).order_by(
                "date", "hour"
            )
        )

        total_requests = sum(stat.requests_count for stat in usage_stats)
        total_success = sum(stat.success_count for stat in usage_stats)
        total_failures = sum(stat.failure_count for stat in usage_stats)

        avg_response_time = 0
        if usage_stats:
            avg_response_time = sum(stat.average_response_time for stat in usage_stats) / len(
                usage_stats
            )

        success_rate = 0
        if total_requests > 0:
            success_rate = (total_success / total_requests) * 100

        return {
            "provider_name": provider.name,
            "period_days": days,
            "total_requests": total_requests,
            "successful_requests": total_success,
            "failed_requests": total_failures,
            "success_rate": round(success_rate, 2),
            "average_response_time": round(avg_response_time, 3),
            "daily_stats": [
                {
                    "date": stat.date,
                    "requests": stat.requests_count,
                    "success": stat.success_count,
                    "failures": stat.failure_count,
                    "avg_time": stat.average_response_time,
                }
                for stat in usage_stats
            ],
        }
