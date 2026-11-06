"""Доменные исключения.

Их сообщения написаны для клиента API и безопасны для показа, а HTTP-статус берётся из
`status_code`. Любое другое исключение API считает внутренней ошибкой и отдаёт 500 без деталей.
"""


class NotificationException(Exception):
    status_code = 400
    code = "notification_error"


class ValidationException(NotificationException):
    code = "validation_error"


class TemplateException(NotificationException):
    code = "template_error"


class NotFoundException(NotificationException):
    status_code = 404
    code = "not_found"


class ConflictException(NotificationException):
    status_code = 409
    code = "conflict"


class ProviderException(ConflictException):
    """Нет подходящего провайдера, он неактивен или все провайдеры канала недоступны."""

    code = "provider_unavailable"


class ProviderNotFoundException(ProviderException, NotFoundException):
    status_code = 404
    code = "provider_not_found"


class DeliveryException(NotificationException):
    """Неудачная попытка отправки у одного провайдера. Используется внутри fallback."""

    code = "delivery_failed"


class RateLimitException(NotificationException):
    code = "rate_limited"


class UserPreferenceException(ConflictException):
    """Получатель отключил этот канал уведомлений."""

    code = "user_preference"


class NotificationNotReadyException(ConflictException):
    code = "notification_not_ready"


class RetryNotAllowedException(ConflictException):
    code = "retry_not_allowed"
