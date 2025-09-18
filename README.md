# NotifyChain

Система управления уведомлениями с надежным механизмом fallback для критически важных приложений.

## Решаемые задачи

NotifyChain решает проблему надежности доставки уведомлений в продакшн-системах. Основные сценарии использования:

- Уведомления о критических событиях (сбои в системе, превышение лимитов)
- Транзакционные сообщения (подтверждения заказов, сбросы паролей)
- Маркетинговые кампании с гарантией доставки
- Многоканальные уведомления с автоматическим переключением

## Архитектура

Система построена на принципе максимальной надежности доставки через двухуровневый fallback:

1. **Fallback между провайдерами одного канала** - автоматическое переключение на резервного провайдера при сбое основного
2. **Межканальный fallback** - переключение Email → SMS → Push при недоступности канала

### Ключевые компоненты

- **Provider Manager** - управление провайдерами с приоритизацией и rate limiting
- **Notification Service** - центральная логика обработки уведомлений
- **Celery Workers** - асинхронная обработка очередей
- **REST API** - интеграция с внешними системами
- **Admin Panel** - управление провайдерами и мониторинг

## Установка

```bash
git clone https://github.com/your-username/notifychain.git
cd notifychain

python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

pip install -r requirements.txt


python manage.py migrate
python manage.py createsuperuser
python manage.py setup_providers
```

## Быстрый старт

```bash
# Запуск сервера
python manage.py runserver

# Запуск Celery worker (отдельный терминал)
celery -A notifychain worker -l info

# Запуск Redis (если не установлен системно)
redis-server
```

## API

### Отправка уведомления

```bash
POST /api/notifications/send/
Content-Type: application/json

{
    "recipient_id": 1,
    "channel": "email",
    "subject": "Важное уведомление",
    "message": "Ваш заказ готов к получению",
    "priority": "high"
}
```

### Получение статуса

```bash
GET /api/notifications/{id}/
```

### Массовая отправка

```bash
POST /api/notifications/bulk/
Content-Type: application/json

{
    "recipient_ids": [1, 2, 3],
    "channel": "email",
    "subject": "Новости продукта",
    "message": "Доступна новая версия"
}
```

### Управление провайдерами

```bash
# Список провайдеров
GET /api/providers/

# Тестирование провайдера
POST /api/providers/{id}/test/

# Статистика использования
GET /api/providers/{id}/stats/
```

## Конфигурация

Основные переменные окружения:

```bash
# Основные настройки
DEBUG=False
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=yourdomain.com

# База данных
DATABASE_URL=postgresql://user:pass@localhost/notifychain

# Redis для Celery
REDIS_URL=redis://localhost:6379/0

# Email провайдеры
SMTP_HOST=smtp.gmail.com
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SENDGRID_API_KEY=your-sendgrid-key

# SMS провайдеры
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_PHONE_NUMBER=+1234567890

# Telegram
TELEGRAM_BOT_TOKEN=your-bot-token

# Fallback настройки
DEFAULT_EMAIL_PROVIDER=smtp
DEFAULT_SMS_PROVIDER=twilio
DEFAULT_PUSH_PROVIDER=telegram

# Rate limiting
RATE_LIMIT_ENABLED=True
MAX_NOTIFICATIONS_PER_MINUTE=100
MAX_NOTIFICATIONS_PER_HOUR=2000
```

## Fallback механизм

Система автоматически обеспечивает доставку через резервные каналы:

```python
# Пример логики fallback
1. Попытка отправки через основной email провайдер (SMTP)
2. При сбое - переключение на SendGrid
3. При недоступности email - переход на SMS (Twilio)
4. При сбое SMS - отправка через Telegram
```

Все переключения логируются для анализа надежности.

## Мониторинг

Встроенные возможности мониторинга:

- **Статистика провайдеров** - success rate, время ответа, использованный трафик
- **Журнал событий** - полная история отправки каждого уведомления
- **Системные метрики** - загрузка очередей, производительность
- **Алерты** - уведомления о сбоях провайдеров

## Технологический стек

- **Backend**: Django 4.2, Django REST Framework
- **Очереди**: Celery + Redis
- **База данных**: PostgreSQL (поддержка SQLite для разработки)
- **HTTP клиент**: Requests
- **Внешние API**: SendGrid, Twilio
- **Конфигурация**: python-decouple, dj-database-url

## Производительность

- Асинхронная обработка через Celery
- Rate limiting на уровне провайдеров
- Кеширование конфигурации
- Batch операции для массовых отправок
- Автоматическая очистка старых записей

## Развертывание

### Docker

#### Разработка

Быстрый запуск для разработки с volume mounts:

```bash
# Сборка и запуск в режиме разработки
docker-compose -f docker-compose.dev.yml up --build

# В фоновом режиме
docker-compose -f docker-compose.dev.yml up -d

# Применение миграций
docker-compose -f docker-compose.dev.yml exec web python manage.py migrate

# Создание суперпользователя
docker-compose -f docker-compose.dev.yml exec web python manage.py createsuperuser

# Настройка провайдеров
docker-compose -f docker-compose.dev.yml exec web python manage.py setup_providers
```

#### Production развертывание

```bash
# Настройка переменных окружения
cp .env.example .env
# Отредактируйте .env для production

# Установите пароль БД в переменную окружения
export DB_PASSWORD=your_secure_password

# Запуск в production режиме
docker-compose -f docker-compose.prod.yml up --build -d

# Применение миграций
docker-compose -f docker-compose.prod.yml exec web python manage.py migrate

# Создание суперпользователя
docker-compose -f docker-compose.prod.yml exec web python manage.py createsuperuser

# Мониторинг статуса
docker-compose -f docker-compose.prod.yml ps

# Просмотр логов
docker-compose -f docker-compose.prod.yml logs -f web
docker-compose -f docker-compose.prod.yml logs -f celery
```

#### Отдельные команды

```bash
# Только сборка
docker build -t notifychain .

# Запуск контейнера
docker run -p 8000:8000 --env-file .env notifychain

# Остановка сервисов
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.prod.yml down
```

## Устранение неполадок

### Проблемы с Docker

**Контейнер не запускается:**
- Проверьте что Docker Desktop запущен
- Убедитесь что порты 8000, 5432, 6379 свободны
- Проверьте логи: `docker-compose logs web`

**База данных недоступна:**
- Дождитесь полной инициализации PostgreSQL (30-60 сек)
- Проверьте подключение: `docker-compose exec db psql -U notifychain`

**Ошибки миграций:**
```bash
# Сброс и повторное применение миграций
docker-compose exec web python manage.py migrate --fake-initial
docker-compose exec web python manage.py migrate
```

**Проблемы с зависимостями:**
```bash
# Пересборка образов
docker-compose build --no-cache web
```

### Альтернативный запуск без Docker

**Локальная разработка:**
```bash
# Убедитесь что PostgreSQL и Redis запущены локально
psql -U postgres -c "CREATE DATABASE notifychain;"

# Установка зависимостей
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
pip install -r requirements.txt

# Настройка переменных окружения
cp .env.example .env
# Отредактируйте DATABASE_URL и REDIS_URL

# Миграции и запуск
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

**Celery worker отдельно:**
```bash
# В отдельном терминале
celery -A notifychain worker -l info
```

### Частые ошибки

**ImportError: No module named 'apps'**
```bash
export PYTHONPATH=/app  # или установите в .env
```

**Redis connection refused**
```bash
# Проверьте что Redis запущен
redis-cli ping
# Должно вернуть PONG
```

**SMTP Authentication failed**
```bash
# Проверьте настройки email в .env
# Для Gmail используйте App Passwords
```

**API возвращает 500 ошибку**
```bash
# Проверьте логи Django
docker-compose logs web
# Или локально
python manage.py check
```

## Безопасность

- Валидация всех входящих данных
- Rate limiting на API endpoints
- Логирование подозрительной активности
- Безопасное хранение API ключей через переменные окружения
- CORS настройки для фронтенд интеграции