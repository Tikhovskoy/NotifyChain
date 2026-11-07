import importlib
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import decouple
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

BASE_DIR = Path(__file__).resolve().parent.parent

# Фиктивный ключ: длиннее 50 символов и без префикса django-insecure-, иначе check --deploy ругается
FAKE_SECRET_KEY = "ci-only-fake-key-" + "abcdefghijklmnopqrstuvwxyz0123456789" * 2

PRODUCTION_ENV = {
    "SECRET_KEY": FAKE_SECRET_KEY,
    "ALLOWED_HOSTS": "api.example.com,notify.example.com",
    "DATABASE_URL": "postgresql://notify:pass@db:5432/notifychain",
    "REDIS_URL": "redis://redis:6379/0",
    # Явно: значения из локального .env разработчика не должны влиять на проверки
    "SECURE_SSL_REDIRECT": "True",
    "TRUST_X_FORWARDED_PROTO": "False",
    "CORS_ALLOWED_ORIGINS": "",
}
PRODUCTION = "notifychain.settings.production"
DEV = "notifychain.settings.dev"


def load_settings(module_name, env):
    """Импортирует модуль настроек заново с заданным окружением и без чтения .env."""
    isolated_config = decouple.Config(decouple.RepositoryEmpty())
    with (
        mock.patch.dict(os.environ, env, clear=True),
        mock.patch.object(decouple.config, "config", isolated_config),
    ):
        sys.modules.pop(module_name, None)
        try:
            return importlib.import_module(module_name)
        finally:
            sys.modules.pop(module_name, None)


class ProductionSettingsTest(SimpleTestCase):
    def test_production_settings_can_be_imported(self):
        module = load_settings(PRODUCTION, PRODUCTION_ENV)

        self.assertFalse(module.DEBUG)
        self.assertEqual(module.SECRET_KEY, FAKE_SECRET_KEY)
        self.assertEqual(module.ALLOWED_HOSTS, ["api.example.com", "notify.example.com"])
        self.assertEqual(module.DATABASES["default"]["ENGINE"], "django.db.backends.postgresql")

    def test_debug_cannot_be_enabled_through_environment(self):
        module = load_settings(PRODUCTION, {**PRODUCTION_ENV, "DEBUG": "True"})

        self.assertFalse(module.DEBUG)

    def test_secret_key_is_required(self):
        env = {k: v for k, v in PRODUCTION_ENV.items() if k != "SECRET_KEY"}

        with self.assertRaises(decouple.UndefinedValueError):
            load_settings(PRODUCTION, env)

    def test_allowed_hosts_are_required(self):
        env = {k: v for k, v in PRODUCTION_ENV.items() if k != "ALLOWED_HOSTS"}

        with self.assertRaises(decouple.UndefinedValueError):
            load_settings(PRODUCTION, env)

    def test_empty_allowed_hosts_are_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            load_settings(PRODUCTION, {**PRODUCTION_ENV, "ALLOWED_HOSTS": ""})

    def test_static_files_are_served_by_whitenoise_right_after_security_middleware(self):
        module = load_settings(PRODUCTION, PRODUCTION_ENV)

        middleware = module.MIDDLEWARE
        security = middleware.index("django.middleware.security.SecurityMiddleware")
        self.assertEqual(middleware[security + 1], "whitenoise.middleware.WhiteNoiseMiddleware")
        self.assertTrue(str(module.STATIC_ROOT).endswith("staticfiles"))

    def test_cache_does_not_share_database_with_celery_broker(self):
        module = load_settings(PRODUCTION, PRODUCTION_ENV)

        self.assertTrue(module.CELERY_BROKER_URL.endswith("/0"))
        self.assertTrue(module.CACHES["default"]["LOCATION"].endswith("/1"))


class DevSettingsTest(SimpleTestCase):
    def test_dev_settings_work_without_any_environment(self):
        module = load_settings(DEV, {})

        self.assertTrue(module.DEBUG)
        self.assertIn("localhost", module.ALLOWED_HOSTS)
        self.assertTrue(module.SECRET_KEY)

    def test_dev_settings_take_secret_key_from_environment(self):
        module = load_settings(DEV, {"SECRET_KEY": "x"})

        self.assertEqual(module.SECRET_KEY, "x")


class SettingsEntryPointsTest(SimpleTestCase):
    """Проверки в отдельных процессах: тут важно именно поведение «с нуля»."""

    @staticmethod
    def run_python(code, env_extra):
        env = {k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"}
        env.update(env_extra)
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_deploy_check_passes_with_production_settings(self):
        env = {**os.environ, **PRODUCTION_ENV, "DJANGO_SETTINGS_MODULE": PRODUCTION}

        result = subprocess.run(
            [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
            cwd=BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_web_servers_default_to_production_settings(self):
        for module in ("notifychain.wsgi", "notifychain.asgi"):
            with self.subTest(module=module):
                code = f"import {module}, os; print(os.environ['DJANGO_SETTINGS_MODULE'])"
                result = self.run_python(code, PRODUCTION_ENV)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), PRODUCTION)

    def test_celery_defaults_to_production_settings(self):
        code = "import notifychain.celery, os; print(os.environ['DJANGO_SETTINGS_MODULE'])"

        result = self.run_python(code, PRODUCTION_ENV)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), PRODUCTION)

    def test_explicit_settings_module_wins_over_defaults(self):
        code = "import notifychain.wsgi, os; print(os.environ['DJANGO_SETTINGS_MODULE'])"

        result = self.run_python(code, {"DJANGO_SETTINGS_MODULE": DEV})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), DEV)
