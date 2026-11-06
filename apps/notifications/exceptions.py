class NotificationException(Exception):
    pass


class TemplateException(NotificationException):
    pass


class ProviderException(NotificationException):
    pass


class ValidationException(NotificationException):
    pass


class DeliveryException(NotificationException):
    pass


class RateLimitException(NotificationException):
    pass


class UserPreferenceException(NotificationException):
    pass
