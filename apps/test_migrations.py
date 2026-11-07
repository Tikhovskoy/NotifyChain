from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class MigrationsInSyncTest(TestCase):
    def test_models_have_no_unapplied_changes(self):
        """Изменение моделей без миграции ломает деплой: CI запускает ту же проверку."""

        out = StringIO()

        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
        except SystemExit:
            self.fail(f"Модели расходятся с миграциями:\n{out.getvalue()}")
