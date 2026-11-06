"""Общие помощники для тестов API."""

from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase


class TokenAPITestCase(APITestCase):
    """Базовый класс: клиенты авторизуются по токену, как внешние системы."""

    def client_for(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client
