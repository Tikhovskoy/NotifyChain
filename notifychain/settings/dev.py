from decouple import Csv, config

from .base import *  # noqa: F403

DEBUG = config("DEBUG", default=True, cast=bool)

# Ключ только для локальной разработки и тестов; в продакшене используется production.py
SECRET_KEY = config("SECRET_KEY", default="dev-only-insecure-key-do-not-use-in-production")

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())
