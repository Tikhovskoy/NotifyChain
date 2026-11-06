from celery import Celery
from celery.schedules import crontab
from django.conf import settings

app = Celery("notifychain")

app.conf.beat_schedule = {
    "process-scheduled-notifications": {
        "task": "tasks.notification_tasks.process_scheduled_notifications",
        "schedule": 60.0,
    },
    "retry-failed-notifications": {
        "task": "tasks.notification_tasks.retry_failed_notifications",
        "schedule": 300.0,
    },
    "collect-system-metrics": {
        "task": "tasks.notification_tasks.collect_system_metrics",
        "schedule": crontab(minute=0),
    },
    "test-provider-connectivity": {
        "task": "tasks.notification_tasks.test_provider_connectivity",
        "schedule": 900.0,
    },
    "cleanup-old-notifications": {
        "task": "tasks.notification_tasks.cleanup_old_notifications",
        "schedule": crontab(hour=3, minute=0),
    },
}

app.conf.timezone = "UTC"
