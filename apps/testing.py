"""Общие помощники для тестов API."""

from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase


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
