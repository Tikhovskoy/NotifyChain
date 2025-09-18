FROM python:3.11-alpine as builder

WORKDIR /build

RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    postgresql-dev \
    && addgroup -g 1001 -S django \
    && adduser -S django -u 1001

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-alpine

WORKDIR /app

RUN apk add --no-cache \
    postgresql-libs \
    curl \
    && addgroup -g 1001 -S django \
    && adduser -S django -u 1001

COPY --from=builder /install /usr/local

COPY --chown=django:django . .

USER django

ENV PYTHONPATH=/app
ENV DJANGO_SETTINGS_MODULE=notifychain.settings

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/ || exit 1

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]