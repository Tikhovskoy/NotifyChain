from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger('notifychain.providers')


class BaseProvider(ABC):

    def __init__(self, provider_config: Dict[str, Any]):
        self.config = provider_config
        self.name = provider_config.get('name', 'Unknown')
        self.provider_type = provider_config.get('provider_type', 'unknown')

    @abstractmethod
    def send(
        self,
        recipient: str,
        message: str,
        subject: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:

        pass

    @abstractmethod
    def validate_config(self) -> bool:

        pass

    @abstractmethod
    def get_delivery_status(self, message_id: str) -> Dict[str, Any]:

        pass

    def get_rate_limit_info(self) -> Dict[str, int]:

        return {
            'requests_per_minute': self.config.get('rate_limit_per_minute', 60),
            'requests_per_hour': self.config.get('rate_limit_per_hour', 1000)
        }

    def format_recipient(self, recipient: str) -> str:

        return recipient

    def prepare_message(
        self,
        message: str,
        subject: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:

        return {
            'message': message,
            'subject': subject,
            'metadata': metadata or {}
        }

    def log_send_attempt(
        self,
        recipient: str,
        success: bool,
        response: Dict[str, Any],
        error: Optional[str] = None
    ):

        if success:
            logger.info(f"{self.name}: Успешно отправлено к {recipient}")
        else:
            logger.error(f"{self.name}: Ошибка отправки к {recipient}. Ошибка: {error}")


class MockEmailProvider(BaseProvider):

    def send(
        self,
        recipient: str,
        message: str,
        subject: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:

        logger.info(f"Mock Email: Отправка '{subject}' к {recipient}")

        response = {
            'success': True,
            'message_id': f"email_{hash(recipient + message)}_mock",
            'provider': self.name,
            'recipient': recipient,
            'timestamp': 'mock_timestamp'
        }

        self.log_send_attempt(recipient, True, response)
        return response

    def validate_config(self) -> bool:
        return True

    def get_delivery_status(self, message_id: str) -> Dict[str, Any]:
        return {
            'status': 'delivered',
            'delivered_at': 'mock_timestamp',
            'message_id': message_id
        }


class MockSMSProvider(BaseProvider):

    def send(
        self,
        recipient: str,
        message: str,
        subject: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:

        logger.info(f"Mock SMS: Отправка к {recipient}: {message[:50]}...")

        response = {
            'success': True,
            'message_id': f"sms_{hash(recipient + message)}_mock",
            'provider': self.name,
            'recipient': recipient,
            'timestamp': 'mock_timestamp'
        }

        self.log_send_attempt(recipient, True, response)
        return response

    def validate_config(self) -> bool:
        return True

    def get_delivery_status(self, message_id: str) -> Dict[str, Any]:
        return {
            'status': 'delivered',
            'delivered_at': 'mock_timestamp',
            'message_id': message_id
        }


class MockPushProvider(BaseProvider):

    def send(
        self,
        recipient: str,
        message: str,
        subject: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:

        logger.info(f"Mock Push: Отправка '{subject}' на устройство {recipient}")

        response = {
            'success': True,
            'message_id': f"push_{hash(recipient + message)}_mock",
            'provider': self.name,
            'recipient': recipient,
            'timestamp': 'mock_timestamp'
        }

        self.log_send_attempt(recipient, True, response)
        return response

    def validate_config(self) -> bool:
        return True

    def get_delivery_status(self, message_id: str) -> Dict[str, Any]:
        return {
            'status': 'delivered',
            'delivered_at': 'mock_timestamp',
            'message_id': message_id
        }