import logging
from typing import Dict, Any

from decouple import config
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from .base_provider import BaseProvider

logger = logging.getLogger(__name__)


class TwilioSMSProvider(BaseProvider):
    provider_type = 'sms'
    provider_name = 'twilio'

    def __init__(self):
        super().__init__()
        self.account_sid = config('TWILIO_ACCOUNT_SID', default='')
        self.auth_token = config('TWILIO_AUTH_TOKEN', default='')
        self.from_number = config('TWILIO_FROM_NUMBER', default='')
        self.client = None

        if self.account_sid and self.auth_token:
            try:
                self.client = Client(self.account_sid, self.auth_token)
            except Exception as e:
                logger.error(f"Ошибка инициализации Twilio клиента: {str(e)}")

    def send_notification(
        self,
        recipient: str,
        message: str,
        subject: str = "",
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        try:
            if not self.client:
                raise ValueError("Twilio клиент не инициализирован")

            if not self.from_number:
                raise ValueError("Twilio номер отправителя не указан")

            if not recipient.startswith('+'):
                recipient = '+' + recipient.lstrip('+')

            sms_message = message
            if subject:
                sms_message = f"{subject}\n\n{message}"

            if len(sms_message) > 1600:
                sms_message = sms_message[:1597] + "..."

            twilio_message = self.client.messages.create(
                body=sms_message,
                from_=self.from_number,
                to=recipient
            )

            logger.info(f"Twilio SMS отправлен на {recipient}, SID: {twilio_message.sid}")
            return {
                'success': True,
                'provider': self.provider_name,
                'recipient': recipient,
                'message_id': twilio_message.sid,
                'status': twilio_message.status
            }

        except TwilioRestException as e:
            error_msg = f"Twilio ошибка {e.code}: {e.msg}"
            logger.error(f"Twilio ошибка для {recipient}: {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'provider': self.provider_name,
                'error_code': e.code
            }

        except ValueError as e:
            error_msg = f"Twilio ошибка конфигурации: {str(e)}"
            logger.error(f"Twilio ошибка конфигурации: {str(e)}")
            return {
                'success': False,
                'error': error_msg,
                'provider': self.provider_name
            }

        except Exception as e:
            error_msg = f"Twilio неожиданная ошибка: {str(e)}"
            logger.error(f"Twilio неожиданная ошибка для {recipient}: {str(e)}")
            return {
                'success': False,
                'error': error_msg,
                'provider': self.provider_name
            }

    def validate_config(self) -> Dict[str, Any]:
        errors = []

        if not self.account_sid:
            errors.append("TWILIO_ACCOUNT_SID не указан")

        if not self.auth_token:
            errors.append("TWILIO_AUTH_TOKEN не указан")

        if not self.from_number:
            errors.append("TWILIO_FROM_NUMBER не указан")

        if self.from_number and not self.from_number.startswith('+'):
            errors.append("TWILIO_FROM_NUMBER должен начинаться с +")

        return {
            'is_valid': len(errors) == 0,
            'errors': errors,
            'config': {
                'from_number': self.from_number,
                'account_configured': bool(self.account_sid and self.auth_token)
            }
        }

    def get_message_status(self, message_id: str) -> Dict[str, Any]:
        try:
            if not self.client:
                raise ValueError("Twilio клиент не инициализирован")

            message = self.client.messages(message_id).fetch()

            return {
                'success': True,
                'message_id': message_id,
                'status': message.status,
                'error_code': message.error_code,
                'error_message': message.error_message,
                'price': message.price,
                'price_unit': message.price_unit
            }

        except TwilioRestException as e:
            logger.error(f"Ошибка получения статуса Twilio сообщения {message_id}: {e.msg}")
            return {
                'success': False,
                'error': f"Ошибка получения статуса: {e.msg}",
                'error_code': e.code
            }

        except Exception as e:
            logger.error(f"Неожиданная ошибка получения статуса Twilio {message_id}: {str(e)}")
            return {
                'success': False,
                'error': f"Неожиданная ошибка: {str(e)}"
            }

    def get_delivery_status(self, message_id: str) -> Dict[str, Any]:
        return self.get_message_status(message_id)