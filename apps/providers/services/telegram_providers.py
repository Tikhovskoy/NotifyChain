import logging
from typing import Any

import requests
from decouple import config

from .base_provider import BaseProvider

logger = logging.getLogger(__name__)


class TelegramProvider(BaseProvider):
    provider_type = "push"
    provider_name = "telegram"

    def __init__(self):
        super().__init__()
        self.bot_token = config("TELEGRAM_BOT_TOKEN", default="")
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_notification(
        self, recipient: str, message: str, subject: str = "", metadata: dict[str, Any] = None
    ) -> dict[str, Any]:
        try:
            if not self.bot_token:
                raise ValueError("Telegram бот токен не настроен")

            chat_id = recipient
            if not chat_id.isdigit() and not chat_id.startswith("-"):
                if chat_id.startswith("@"):
                    chat_id = chat_id[1:]

            telegram_message = message
            if subject:
                telegram_message = f"*{subject}*\n\n{message}"

            payload = {
                "chat_id": chat_id,
                "text": telegram_message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }

            response = requests.post(f"{self.api_url}/sendMessage", json=payload, timeout=30)

            response_data = response.json()

            if response.status_code == 200 and response_data.get("ok"):
                message_id = response_data["result"]["message_id"]
                logger.info(f"Telegram сообщение отправлено в чат {chat_id}, ID: {message_id}")
                return {
                    "success": True,
                    "provider": self.provider_name,
                    "recipient": chat_id,
                    "message_id": message_id,
                }
            else:
                error_description = response_data.get("description", "Неизвестная ошибка")
                error_code = response_data.get("error_code", response.status_code)
                error_msg = f"Telegram ошибка {error_code}: {error_description}"
                logger.error(f"Telegram ошибка для чата {chat_id}: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "provider": self.provider_name,
                    "error_code": error_code,
                }

        except requests.exceptions.Timeout:
            error_msg = "Telegram таймаут запроса"
            logger.error(f"Telegram таймаут для чата {recipient}")
            return {"success": False, "error": error_msg, "provider": self.provider_name}

        except requests.exceptions.RequestException as e:
            error_msg = f"Telegram ошибка запроса: {str(e)}"
            logger.error(f"Telegram ошибка запроса для чата {recipient}: {str(e)}")
            return {"success": False, "error": error_msg, "provider": self.provider_name}

        except Exception as e:
            error_msg = f"Telegram неожиданная ошибка: {str(e)}"
            logger.error(f"Telegram неожиданная ошибка для чата {recipient}: {str(e)}")
            return {"success": False, "error": error_msg, "provider": self.provider_name}

    def validate_config(self) -> dict[str, Any]:
        errors = []

        if not self.bot_token:
            errors.append("TELEGRAM_BOT_TOKEN не указан")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "config": {"bot_configured": bool(self.bot_token)},
        }

    def get_bot_info(self) -> dict[str, Any]:
        try:
            if not self.bot_token:
                raise ValueError("Telegram бот токен не настроен")

            response = requests.get(f"{self.api_url}/getMe", timeout=10)
            response_data = response.json()

            if response.status_code == 200 and response_data.get("ok"):
                bot_info = response_data["result"]
                return {
                    "success": True,
                    "bot_id": bot_info["id"],
                    "bot_username": bot_info["username"],
                    "bot_first_name": bot_info["first_name"],
                    "can_join_groups": bot_info.get("can_join_groups", False),
                    "can_read_all_group_messages": bot_info.get(
                        "can_read_all_group_messages", False
                    ),
                }
            else:
                return {
                    "success": False,
                    "error": response_data.get("description", "Ошибка получения информации о боте"),
                }

        except Exception as e:
            logger.error(f"Ошибка получения информации о Telegram боте: {str(e)}")
            return {"success": False, "error": f"Ошибка получения информации о боте: {str(e)}"}

    def get_delivery_status(self, message_id: str) -> dict[str, Any]:
        return {
            "status": "delivered",
            "message": "Telegram сообщения доставляются мгновенно",
            "message_id": message_id,
        }
