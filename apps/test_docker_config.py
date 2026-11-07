"""Инварианты контейнерной конфигурации, заданные в ТЗ."""

import re
from pathlib import Path

from django.test import SimpleTestCase

BASE_DIR = Path(__file__).resolve().parent.parent


def read(name):
    return (BASE_DIR / name).read_text(encoding="utf-8")


class DockerfileTest(SimpleTestCase):
    def test_image_is_built_on_python_312(self):
        from_lines = [line for line in read("Dockerfile").splitlines() if line.startswith("FROM")]

        self.assertTrue(from_lines)
        for line in from_lines:
            self.assertIn("python:3.12", line)

    def test_image_serves_the_app_with_gunicorn(self):
        dockerfile = read("Dockerfile")
        cmd = next(line for line in dockerfile.splitlines() if line.startswith("CMD"))

        self.assertIn("gunicorn", cmd)
        self.assertNotIn("runserver", dockerfile)

    def test_static_files_are_collected_at_build_time(self):
        self.assertIn("collectstatic --noinput", read("Dockerfile"))

    def test_image_runs_with_production_settings_as_non_root(self):
        dockerfile = read("Dockerfile")

        self.assertIn("DJANGO_SETTINGS_MODULE=notifychain.settings.production", dockerfile)
        self.assertIn("USER django", dockerfile)


class ComposeFilesTest(SimpleTestCase):
    def test_there_is_one_main_file_and_one_dev_override(self):
        names = sorted(path.name for path in BASE_DIR.glob("docker-compose*.yml"))

        self.assertEqual(names, ["docker-compose.dev.yml", "docker-compose.yml"])

    def test_main_file_has_no_default_database_password(self):
        compose = read("docker-compose.yml")

        self.assertNotIn("securepassword123", compose)
        self.assertIn("${DB_PASSWORD:?", compose)

    def test_main_file_waits_for_healthy_database_and_redis(self):
        compose = read("docker-compose.yml")

        self.assertIn("pg_isready", compose)
        self.assertIn("redis-cli", compose)
        self.assertEqual(compose.count("condition: service_healthy"), 2)

    def test_main_file_runs_production_settings_and_dev_file_switches_to_dev(self):
        self.assertIn("notifychain.settings.production", read("docker-compose.yml"))
        self.assertIn("notifychain.settings.dev", read("docker-compose.dev.yml"))

    def test_env_example_covers_every_compose_variable_and_holds_no_real_secrets(self):
        example = read(".env.example")

        for name in ("SECRET_KEY", "ALLOWED_HOSTS", "DB_PASSWORD"):
            self.assertIn(f"{name}=", example)
        # настоящий ключ SendGrid выглядит как SG.<22 символа>.<43 символа>
        self.assertIsNone(re.search(r"SG\.[\w-]{20,}\.[\w-]{20,}", example))
        self.assertIsNone(re.search(r"\bAC[0-9a-f]{32}\b", example))

    def test_runserver_is_used_only_in_the_dev_compose_file(self):
        compose_files = sorted(BASE_DIR.glob("docker-compose*.yml"))

        self.assertTrue(compose_files)
        for path in compose_files:
            with self.subTest(file=path.name):
                uses_runserver = "runserver" in path.read_text(encoding="utf-8")

                self.assertEqual(uses_runserver, path.name == "docker-compose.dev.yml")

    def test_gunicorn_is_pinned_in_requirements(self):
        requirements = read("requirements.txt").lower()

        self.assertIn("gunicorn==", requirements)
