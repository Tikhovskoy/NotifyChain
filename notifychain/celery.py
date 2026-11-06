import os

from celery import Celery

# Этот модуль импортируется из notifychain/__init__.py раньше wsgi.py и asgi.py, поэтому
# значение по умолчанию здесь должно быть таким же безопасным, как у них. Для локальной
# разработки задайте DJANGO_SETTINGS_MODULE=notifychain.settings.dev.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "notifychain.settings.production")

app = Celery("notifychain")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_always_eager=False,
    task_eager_propagates=False,
    task_ignore_result=False,
    task_store_eager_result=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")


if __name__ == "__main__":
    app.start()
