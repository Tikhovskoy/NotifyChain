from urllib.parse import urlsplit, urlunsplit

import dj_database_url
from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

# Все три значения обязательны: без них decouple выбросит UndefinedValueError при старте.
SECRET_KEY = config("SECRET_KEY")

ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv())
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS не должен быть пустым")

DATABASES = {
    "default": dj_database_url.parse(
        config("DATABASE_URL"), conn_max_age=600, conn_health_checks=True
    )
}

# Продакшен всегда без DEBUG, переменная окружения DEBUG здесь не читается
DEBUG = False

# Статику админки и DRF отдаёт WhiteNoise: gunicorn сам её раздавать не умеет
MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

REDIS_URL = config("REDIS_URL")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL


def _with_redis_db(url, db):
    return urlunsplit(urlsplit(url)._replace(path=f"/{db}"))


# Кэш (в том числе счётчики throttling) живёт в отдельной базе Redis: очистка кэша
# не должна затрагивать очередь Celery.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config("REDIS_CACHE_URL", default=_with_redis_db(REDIS_URL, 1)),
    }
}

CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())

SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
# Включайте, если приложение стоит за прокси, который завершает TLS и ставит X-Forwarded-Proto
if config("TRUST_X_FORWARDED_PROTO", default=False, cast=bool):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# В контейнере логи читают из stdout, поэтому файл не нужен
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "notifychain": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
