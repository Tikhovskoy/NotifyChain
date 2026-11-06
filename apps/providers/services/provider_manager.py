import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.notifications.exceptions import (
    DeliveryException,
    ProviderException,
    ProviderNotFoundException,
)

from ..models import Provider, ProviderUsage
from .base_provider import BaseProvider, MockEmailProvider, MockPushProvider, MockSMSProvider
from .email_providers import SendGridEmailProvider, SMTPEmailProvider
from .sms_providers import TwilioSMSProvider
from .telegram_providers import TelegramProvider

logger = logging.getLogger("notifychain.providers")


class ProviderManager:
    def __init__(self):
        self._provider_classes = {
            "mock_email": MockEmailProvider,
            "mock_sms": MockSMSProvider,
            "mock_push": MockPushProvider,
            "smtp": SMTPEmailProvider,
            "sendgrid": SendGridEmailProvider,
            "twilio": TwilioSMSProvider,
            "telegram": TelegramProvider,
        }
        self._provider_instances = {}

    def get_provider(self, channel: str, provider_name: str | None = None) -> BaseProvider:

        if provider_name:
            provider = self._get_provider_by_name(provider_name)
        else:
            provider = self._get_default_provider(channel)

        if not provider:
            raise ProviderNotFoundException(f"Провайдер не найден для канала {channel}")

        if not provider.is_active:
            raise ProviderException(f"Провайдер {provider.name} неактивен")

        return self._get_provider_instance(provider)

    def send_notification(
        self,
        channel: str,
        recipient: str,
        message: str,
        subject: str = "",
        metadata: dict[str, Any] | None = None,
        provider_name: str | None = None,
    ) -> dict[str, Any]:

        if provider_name:
            providers_to_try = [self._get_provider_by_name(provider_name)]
            if not providers_to_try[0]:
                raise ProviderNotFoundException(f"Провайдер {provider_name} не найден")
        else:
            providers_to_try = self.get_available_providers(channel)
            if not providers_to_try:
                raise ProviderException(f"Нет доступных провайдеров для канала {channel}")

        last_exception = None

        for provider_model in providers_to_try:
            if not provider_model.is_active:
                logger.info(f"Пропускаю неактивный провайдер {provider_model.name}")
                continue

            start_time = timezone.now()

            try:
                if not self._check_rate_limit(provider_model):
                    logger.warning(
                        f"Превышен лимит для провайдера {provider_model.name}, пробую следующий"
                    )
                    continue

                provider_instance = self._get_provider_instance(provider_model)
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

        return list(
            Provider.objects.filter(provider_type=channel, is_active=True).order_by("priority")
        )

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
        provider_instance = self._get_provider_instance(provider)

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

        self._provider_classes[name] = provider_class
        logger.info(f"Зарегистрирован класс провайдера {name}")

    def _get_provider_by_name(self, name: str) -> Provider | None:
        try:
            return Provider.objects.get(name=name, is_active=True)
        except Provider.DoesNotExist:
            return None

    def _get_default_provider(self, channel: str) -> Provider | None:
        try:
            return Provider.objects.get(provider_type=channel, is_default=True, is_active=True)
        except Provider.DoesNotExist:
            providers = Provider.objects.filter(provider_type=channel, is_active=True).order_by(
                "priority"
            )
            return providers.first() if providers.exists() else None

    def _get_provider_instance(self, provider: Provider) -> BaseProvider:

        cache_key = f"{provider.name}_{provider.id}"

        if cache_key not in self._provider_instances:
            provider_class_name = provider.config.get(
                "class_name", f"mock_{provider.provider_type}"
            )
            provider_class = self._provider_classes.get(provider_class_name)

            if not provider_class:
                raise ProviderException(f"Класс провайдера {provider_class_name} не найден")

            self._provider_instances[cache_key] = provider_class()

        instance = self._provider_instances[cache_key]
        instance.name = provider.name
        return instance

    def _get_provider_model(self, provider_name: str) -> Provider:
        return Provider.objects.get(name=provider_name)

    def _check_rate_limit(self, provider: Provider) -> bool:

        now = timezone.now()

        minute_ago = now - timedelta(minutes=1)
        recent_usage = ProviderUsage.objects.filter(provider=provider, created_at__gte=minute_ago)

        requests_last_minute = sum(usage.requests_count for usage in recent_usage)
        if requests_last_minute >= provider.rate_limit_per_minute:
            return False

        hour_ago = now - timedelta(hours=1)
        hourly_usage = ProviderUsage.objects.filter(provider=provider, created_at__gte=hour_ago)

        requests_last_hour = sum(usage.requests_count for usage in hourly_usage)
        if requests_last_hour >= provider.rate_limit_per_hour:
            return False

        return True

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
