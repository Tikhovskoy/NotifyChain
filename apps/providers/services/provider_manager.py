import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.notifications.exceptions import DeliveryException, ProviderException

from ..models import Provider, ProviderUsage
from .base_provider import BaseProvider
from .rate_limiter import ProviderRateLimiter
from .registry import ProviderRegistry

logger = logging.getLogger("notifychain.providers")


class ProviderManager:
    """Отправка с fallback между провайдерами канала.

    Сам менеджер только оркестрирует. Выбор провайдеров делает ProviderRegistry, лимиты считает
    ProviderRateLimiter.
    """

    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        rate_limiter: ProviderRateLimiter | None = None,
    ):
        self.registry = registry or ProviderRegistry()
        self.rate_limiter = rate_limiter or ProviderRateLimiter()

    def get_provider(self, channel: str, provider_name: str | None = None) -> BaseProvider:
        return self.registry.get_instance(self.registry.resolve(channel, provider_name))

    def send_notification(
        self,
        channel: str,
        recipient: str,
        message: str,
        subject: str = "",
        metadata: dict[str, Any] | None = None,
        provider_name: str | None = None,
    ) -> dict[str, Any]:

        last_exception = None

        for provider_model in self.registry.candidates(channel, provider_name):
            if not provider_model.is_active:
                logger.info(f"Пропускаю неактивный провайдер {provider_model.name}")
                continue

            start_time = timezone.now()

            try:
                if not self.rate_limiter.acquire(provider_model):
                    logger.warning(
                        f"Превышен лимит для провайдера {provider_model.name}, пробую следующий"
                    )
                    continue

                provider_instance = self.registry.get_instance(provider_model)
                logger.info(f"Пытаюсь отправить через провайдер {provider_model.name}")

                response = provider_instance.send(recipient, message, subject, metadata)

                # Реальные провайдеры не бросают исключение при сбое, а возвращают
                # {"success": False, "error": ...}: для fallback это такая же неудача.
                if not response.get("success"):
                    raise DeliveryException(
                        response.get("error") or f"Провайдер {provider_model.name} вернул отказ"
                    )

                duration = (timezone.now() - start_time).total_seconds()
                self._record_usage(provider_model, success=True, duration=duration)

                logger.info(f"Успешно отправлено через провайдер {provider_model.name}")
                return response

            except Exception as e:
                duration = (timezone.now() - start_time).total_seconds()
                self._record_usage(provider_model, success=False, duration=duration)

                logger.warning(f"Ошибка отправки через {provider_model.name}: {str(e)}")
                last_exception = e

                if provider_name:
                    break

                continue

        error_msg = f"Все провайдеры канала {channel} недоступны"
        if last_exception:
            error_msg += f": {str(last_exception)}"

        logger.error(error_msg)
        raise ProviderException(error_msg)

    def get_available_providers(self, channel: str) -> list[Provider]:
        return self.registry.get_available(channel)

    def get_provider_statistics(self, provider_id: int, days: int = 7) -> dict[str, Any]:

        provider = Provider.objects.get(id=provider_id)
        start_date = timezone.now().date() - timedelta(days=days)

        usage_stats = ProviderUsage.objects.filter(provider=provider, date__gte=start_date)

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
                for stat in usage_stats.order_by("date")
            ],
        }

    def test_provider(self, provider_id: int) -> dict[str, Any]:

        provider = Provider.objects.get(id=provider_id)
        provider_instance = self.registry.get_instance(provider)

        test_result = {
            "provider_name": provider.name,
            "provider_type": provider.provider_type,
            "config_valid": False,
            "connection_test": False,
            "errors": [],
        }

        try:
            test_result["config_valid"] = provider_instance.validate_config()
        except Exception as e:
            test_result["errors"].append(f"Config validation failed: {str(e)}")

        if test_result["config_valid"]:
            try:
                test_recipient = self._get_test_recipient(provider.provider_type)
                response = provider_instance.send(
                    test_recipient, "Test message from NotifyChain", "Test notification"
                )
                test_result["connection_test"] = response.get("success", False)
            except Exception as e:
                test_result["errors"].append(f"Connection test failed: {str(e)}")

        return test_result

    def register_provider_class(self, name: str, provider_class: type[BaseProvider]):
        self.registry.register(name, provider_class)

    def _record_usage(self, provider: Provider, success: bool, duration: float):

        today = timezone.now().date()
        current_hour = timezone.now().hour

        usage, created = ProviderUsage.objects.get_or_create(
            provider=provider,
            date=today,
            hour=current_hour,
            defaults={
                "requests_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "average_response_time": 0.0,
            },
        )

        usage.requests_count += 1
        if success:
            usage.success_count += 1
        else:
            usage.failure_count += 1

        if usage.requests_count > 1:
            usage.average_response_time = (
                usage.average_response_time * (usage.requests_count - 1) + duration
            ) / usage.requests_count
        else:
            usage.average_response_time = duration

        usage.save()

    def _get_test_recipient(self, provider_type: str) -> str:

        test_recipients = {
            "email": "test@example.com",
            "sms": "+1234567890",
            "push": "test_device_token",
        }
        return test_recipients.get(provider_type, "test_recipient")
