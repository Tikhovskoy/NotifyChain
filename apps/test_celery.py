import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BASE_DIR = Path(__file__).resolve().parent.parent

LIST_TASKS = (
    "from notifychain.celery import app; "
    "app.loader.import_default_modules(); "
    "print('\\n'.join(sorted(app.tasks)))"
)


class WorkerTaskRegistrationTest(SimpleTestCase):
    """Воркер должен знать задачи из пакета tasks/, иначе очередь копит нераспознанные задачи."""

    def registered_tasks(self):
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "notifychain.settings.dev"}
        result = subprocess.run(
            [sys.executable, "-c", LIST_TASKS],
            cwd=BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return set(result.stdout.split())

    def test_notification_tasks_are_registered_in_a_fresh_worker(self):
        tasks = self.registered_tasks()

        for name in (
            "tasks.notification_tasks.send_notification_task",
            "tasks.notification_tasks.send_bulk_notifications_task",
        ):
            self.assertIn(name, tasks)

    def test_maintenance_tasks_are_registered_in_a_fresh_worker(self):
        tasks = self.registered_tasks()

        for name in (
            "tasks.notification_tasks.process_scheduled_notifications",
            "tasks.notification_tasks.retry_failed_notifications",
            "tasks.notification_tasks.cleanup_old_notifications",
        ):
            self.assertIn(name, tasks)
