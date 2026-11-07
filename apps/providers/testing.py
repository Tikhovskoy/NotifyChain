"""Помощники для тестов провайдеров: фейковые классы и общая подготовка."""

from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from apps.providers.models import Provider
from apps.providers.services import ProviderManager
from apps.providers.services.base_provider import BaseProvider


def fake_provider_class(send, provider_type="email", validate=None):
    """Строит класс провайдера, чей send_notification делегирует мок-функции `send`.

    `validate` — мок для validate_config; по умолчанию конфигурация считается валидной.
    """

    class FakeProvider(BaseProvider):
        def send_notification(self, recipient, message, subject="", metadata=None):
            return send(recipient, message, subject, metadata)

        def validate_config(self):
            return validate() if validate else {"is_valid": True, "errors": []}

        def get_delivery_status(self, message_id):
            return {"status": "unknown"}

    FakeProvider.provider_type = provider_type
    return FakeProvider


def ok(name):
    return mock.Mock(return_value={"success": True, "provider": name})


def raises(error):
    return mock.Mock(side_effect=error)


def rejects(error="rejected"):
    return mock.Mock(return_value={"success": False, "error": error})


class ProviderFallbackTestCase(TestCase):
    """Общая подготовка: менеджер с зарегистрированными фейковыми классами."""

    def setUp(self):
        cache.clear()  # в кэше лежат счётчики rate limit, pk провайдеров между тестами повторяются
        self.manager = ProviderManager()
        self.calls = []

    def add_provider(self, name, send, priority=1, channel="email", validate=None, **extra):
        """Создаёт запись Provider и регистрирует для неё фейковый класс."""

        def tracked(*args):
            self.calls.append(name)
            return send(*args)

        self.manager.register_provider_class(name, fake_provider_class(tracked, channel, validate))
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
