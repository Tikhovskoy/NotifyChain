import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.notifications.exceptions import NotificationException

logger = logging.getLogger("notifychain.api")


def api_exception_handler(exc, context):
    """Единый обработчик ошибок API.

    * доменные исключения отдают своё сообщение и статус (400, 404, 409);
    * исключения DRF и Django (401, 403, 404, ошибки валидации) обрабатываются как обычно;
    * всё остальное считается внутренней ошибкой: полный traceback уходит в лог,
      а клиент получает 500 без подробностей.
    """

    if isinstance(exc, NotificationException):
        return Response({"error": str(exc), "code": exc.code}, status=exc.status_code)

    response = drf_exception_handler(exc, context)
    if response is not None:
        return response

    request = context.get("request")
    view = context.get("view")
    logger.error(
        "Необработанное исключение в %s (%s %s)",
        type(view).__name__,
        getattr(request, "method", "-"),
        getattr(request, "path", "-"),
        exc_info=exc,
    )
    return Response(
        {"error": "Внутренняя ошибка сервера", "code": "server_error"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
