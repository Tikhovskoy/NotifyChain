FROM python:3.12-alpine AS builder

WORKDIR /build

RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    postgresql-dev

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-alpine

WORKDIR /app

RUN apk add --no-cache postgresql-libs \
    && addgroup -g 1001 -S django \
    && adduser -S django -u 1001 -G django

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    DJANGO_SETTINGS_MODULE=notifychain.settings.production

COPY --from=builder /install /usr/local

COPY --chown=django:django . .

# Для collectstatic достаточно, чтобы настройки импортировались. Значения ниже фиктивные
# и действуют только на время этой команды, в образ они не попадают.
RUN SECRET_KEY=build-only \
    ALLOWED_HOSTS=localhost \
    DATABASE_URL=postgresql://build:build@localhost/build \
    REDIS_URL=redis://localhost:6379/0 \
    python manage.py collectstatic --noinput \
    && chown -R django:django /app/staticfiles

USER django

EXPOSE 8000

# Любой HTTP-ответ означает, что gunicorn жив. Проверка не зависит ни от токенов,
# ни от ALLOWED_HOSTS, ни от редиректа на HTTPS.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import http.client as h; c = h.HTTPConnection('localhost', 8000, timeout=5); c.request('GET', '/'); c.getresponse()"]

CMD ["gunicorn", "notifychain.wsgi:application", "-c", "gunicorn.conf.py"]
