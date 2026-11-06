import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import requests
from decouple import config

from .base_provider import BaseProvider

logger = logging.getLogger(__name__)


class SMTPEmailProvider(BaseProvider):
    provider_type = "email"
    provider_name = "smtp"

    def __init__(self):
        super().__init__()
        self.smtp_host = config("SMTP_HOST", default="smtp.gmail.com")
        self.smtp_port = config("SMTP_PORT", default=587, cast=int)
        self.smtp_username = config("SMTP_USERNAME", default="")
        self.smtp_password = config("SMTP_PASSWORD", default="")
        self.smtp_use_tls = config("SMTP_USE_TLS", default=True, cast=bool)
        self.from_email = config("FROM_EMAIL", default=self.smtp_username)

    def send_notification(
        self, recipient: str, message: str, subject: str = "", metadata: dict[str, Any] = None
    ) -> dict[str, Any]:
        try:
            if not self.smtp_username or not self.smtp_password:
                raise ValueError("SMTP учетные данные не настроены")

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject or "Уведомление"
            msg["From"] = self.from_email
            msg["To"] = recipient

            text_part = MIMEText(message, "plain", "utf-8")
            msg.attach(text_part)

            html_message = message.replace("\n", "<br>")
            html_part = MIMEText(f"<html><body>{html_message}</body></html>", "html", "utf-8")
            msg.attach(html_part)

            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            if self.smtp_use_tls:
                server.starttls()

            server.login(self.smtp_username, self.smtp_password)
            text = msg.as_string()
            server.sendmail(self.from_email, recipient, text)
            server.quit()

            logger.info(f"SMTP email отправлен на {recipient}")
            return {
                "success": True,
                "provider": self.provider_name,
                "recipient": recipient,
                "message_id": None,
            }

        except smtplib.SMTPAuthenticationError:
            error_msg = "SMTP ошибка аутентификации"
            logger.error(f"SMTP ошибка аутентификации для {recipient}")
            return {"success": False, "error": error_msg, "provider": self.provider_name}

        except smtplib.SMTPRecipientsRefused:
            error_msg = "SMTP получатель отклонен"
            logger.error(f"SMTP получатель {recipient} отклонен")
            return {"success": False, "error": error_msg, "provider": self.provider_name}

        except Exception as e:
            error_msg = f"SMTP ошибка отправки: {str(e)}"
            logger.error(f"SMTP ошибка отправки на {recipient}: {str(e)}")
            return {"success": False, "error": error_msg, "provider": self.provider_name}

    def validate_config(self) -> dict[str, Any]:
        errors = []

        if not self.smtp_host:
            errors.append("SMTP_HOST не указан")

        if not self.smtp_username:
            errors.append("SMTP_USERNAME не указан")

        if not self.smtp_password:
            errors.append("SMTP_PASSWORD не указан")

        if not self.from_email:
            errors.append("FROM_EMAIL не указан")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "config": {
                "smtp_host": self.smtp_host,
                "smtp_port": self.smtp_port,
                "smtp_use_tls": self.smtp_use_tls,
                "from_email": self.from_email,
            },
        }

    def get_delivery_status(self, message_id: str) -> dict[str, Any]:
        return {
            "status": "unknown",
            "message": "SMTP не предоставляет статус доставки",
            "message_id": message_id,
        }


class SendGridEmailProvider(BaseProvider):
    provider_type = "email"
    provider_name = "sendgrid"

    def __init__(self):
        super().__init__()
        self.api_key = config("SENDGRID_API_KEY", default="")
        self.from_email = config("SENDGRID_FROM_EMAIL", default="")
        self.api_url = "https://api.sendgrid.com/v3/mail/send"

    def send_notification(
        self, recipient: str, message: str, subject: str = "", metadata: dict[str, Any] = None
    ) -> dict[str, Any]:
        try:
            if not self.api_key:
                raise ValueError("SendGrid API ключ не настроен")

            if not self.from_email:
                raise ValueError("SendGrid от кого email не настроен")

            payload = {
                "personalizations": [
                    {"to": [{"email": recipient}], "subject": subject or "Уведомление"}
                ],
                "from": {"email": self.from_email},
                "content": [
                    {"type": "text/plain", "value": message},
                    {"type": "text/html", "value": message.replace("\n", "<br>")},
                ],
            }

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            response = requests.post(self.api_url, json=payload, headers=headers, timeout=30)

            if response.status_code == 202:
                logger.info(f"SendGrid email отправлен на {recipient}")
                return {
                    "success": True,
                    "provider": self.provider_name,
                    "recipient": recipient,
                    "message_id": response.headers.get("X-Message-Id"),
                }
            else:
                error_msg = f"SendGrid ошибка {response.status_code}: {response.text}"
                logger.error(f"SendGrid ошибка для {recipient}: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "provider": self.provider_name,
                    "status_code": response.status_code,
                }

        except requests.exceptions.Timeout:
            error_msg = "SendGrid таймаут запроса"
            logger.error(f"SendGrid таймаут для {recipient}")
            return {"success": False, "error": error_msg, "provider": self.provider_name}

        except requests.exceptions.RequestException as e:
            error_msg = f"SendGrid ошибка запроса: {str(e)}"
            logger.error(f"SendGrid ошибка запроса для {recipient}: {str(e)}")
            return {"success": False, "error": error_msg, "provider": self.provider_name}

        except Exception as e:
            error_msg = f"SendGrid неожиданная ошибка: {str(e)}"
            logger.error(f"SendGrid неожиданная ошибка для {recipient}: {str(e)}")
            return {"success": False, "error": error_msg, "provider": self.provider_name}

    def validate_config(self) -> dict[str, Any]:
        errors = []

        if not self.api_key:
            errors.append("SENDGRID_API_KEY не указан")

        if not self.from_email:
            errors.append("SENDGRID_FROM_EMAIL не указан")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "config": {"from_email": self.from_email, "api_configured": bool(self.api_key)},
        }

    def get_delivery_status(self, message_id: str) -> dict[str, Any]:
        return {
            "status": "unknown",
            "message": "Требуется отдельный API запрос к SendGrid",
            "message_id": message_id,
        }
