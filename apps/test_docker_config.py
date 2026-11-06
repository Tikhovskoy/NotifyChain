"""Инварианты контейнерной конфигурации, заданные в ТЗ."""

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
