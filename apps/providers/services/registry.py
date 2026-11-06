import logging

from apps.notifications.exceptions import ProviderException, ProviderNotFoundException

from ..models import Provider
from .base_provider import BaseProvider, MockEmailProvider, MockPushProvider, MockSMSProvider
from .email_providers import SendGridEmailProvider, SMTPEmailProvider
from .sms_providers import TwilioSMSProvider
from .telegram_providers import TelegramProvider

logger = logging.getLogger("notifychain.providers")

DEFAULT_PROVIDER_CLASSES: dict[str, type[BaseProvider]] = {
    "mock_email": MockEmailProvider,
    "mock_sms": MockSMSProvider,
    "mock_push": MockPushProvider,
    "smtp": SMTPEmailProvider,
    "sendgrid": SendGridEmailProvider,
    "twilio": TwilioSMSProvider,
    "telegram": TelegramProvider,
}


class ProviderRegistry:
    """Реестр классов провайдеров и выбор провайдера для канала.

    Класс провайдера выбирается по ключу `class_name` в `Provider.config`. Для записи без
    `class_name` берётся mock-класс канала.
    """

    def __init__(self, classes: dict[str, type[BaseProvider]] | None = None):
        self._classes = dict(DEFAULT_PROVIDER_CLASSES if classes is None else classes)
        self._instances: dict[str, BaseProvider] = {}

    def register(self, name: str, provider_class: type[BaseProvider]) -> None:
        self._classes[name] = provider_class
        logger.info(f"Зарегистрирован класс провайдера {name}")

    def get_instance(self, provider: Provider) -> BaseProvider:
        cache_key = f"{provider.name}_{provider.id}"

        if cache_key not in self._instances:
            class_name = provider.config.get("class_name", f"mock_{provider.provider_type}")
            provider_class = self._classes.get(class_name)

            if not provider_class:
                raise ProviderException(f"Класс провайдера {class_name} не найден")

            self._instances[cache_key] = provider_class()

        instance = self._instances[cache_key]
        instance.name = provider.name
        return instance

    def get_available(self, channel: str) -> list[Provider]:
        """Активные провайдеры канала в порядке приоритета."""

        return list(
            Provider.objects.filter(provider_type=channel, is_active=True).order_by("priority")
        )

    def find_by_name(self, name: str) -> Provider | None:
        try:
            return Provider.objects.get(name=name, is_active=True)
        except Provider.DoesNotExist:
            return None

    def find_default(self, channel: str) -> Provider | None:
        try:
            return Provider.objects.get(provider_type=channel, is_default=True, is_active=True)
        except Provider.DoesNotExist:
            return (
                Provider.objects.filter(provider_type=channel, is_active=True)
                .order_by("priority")
                .first()
            )

    def resolve(self, channel: str, provider_name: str | None = None) -> Provider:
        """Провайдер для одиночной отправки: по имени или по умолчанию для канала."""

        provider = self.find_by_name(provider_name) if provider_name else self.find_default(channel)

        if not provider:
            raise ProviderNotFoundException(f"Провайдер не найден для канала {channel}")

        if not provider.is_active:
            raise ProviderException(f"Провайдер {provider.name} неактивен")

        return provider

    def candidates(self, channel: str, provider_name: str | None = None) -> list[Provider]:
        """Провайдеры в том порядке, в котором их нужно пробовать при отправке (fallback).

        С явным именем fallback отключён: пробуется только этот провайдер.
        """

        if provider_name:
            provider = self.find_by_name(provider_name)
            if not provider:
                raise ProviderNotFoundException(f"Провайдер {provider_name} не найден")
            return [provider]

        providers = self.get_available(channel)
        if not providers:
            raise ProviderException(f"Нет доступных провайдеров для канала {channel}")
        return providers
