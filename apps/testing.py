"""Общие помощники для тестов."""

from contextlib import ExitStack
from datetime import UTC
from unittest import mock

from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase


def frozen_time(moment):
    """Замораживает «сейчас» для Django и для time.time (счётчики лимитов, TTL кэша).

    Использование: `with frozen_time(datetime(2026, 3, 1, 10, 30, tzinfo=UTC)): ...`
    """

    moment = moment.astimezone(UTC)
    stack = ExitStack()
    stack.enter_context(mock.patch("django.utils.timezone.now", return_value=moment))
    stack.enter_context(mock.patch("time.time", return_value=moment.timestamp()))
    return stack


class TokenAPITestCase(APITestCase):
    """Базовый класс: клиенты авторизуются по токену, как внешние системы.

    Подклассы, переопределяющие setUp, должны вызывать super().setUp(): здесь очищается
    кэш, в котором DRF хранит счётчики throttling (pk пользователей между тестами повторяются).
    """

    def setUp(self):
        super().setUp()
        cache.clear()

    def client_for(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client
