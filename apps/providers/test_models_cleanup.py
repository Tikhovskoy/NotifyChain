from django.apps import apps
from django.db import connection
from django.test import TestCase


class UnusedCredentialModelTest(TestCase):
    """Ключи провайдеров берутся из переменных окружения, отдельная модель не нужна."""

    def test_provider_credential_model_is_gone(self):
        with self.assertRaises(LookupError):
            apps.get_model("providers", "ProviderCredential")

    def test_provider_credentials_table_is_dropped_by_migrations(self):
        self.assertNotIn("provider_credentials", connection.introspection.table_names())
