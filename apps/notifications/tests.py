from django.test import TestCase
from django.contrib.auth.models import User
from .models import Notification, NotificationTemplate
from .services.notification_service import NotificationService


class NotificationModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com'
        )

    def test_notification_creation(self):
        notification = Notification.objects.create(
            recipient=self.user,
            channel='email',
            message='Тестовое сообщение',
            status='pending'
        )
        self.assertEqual(notification.recipient, self.user)
        self.assertEqual(notification.channel, 'email')
        self.assertEqual(notification.status, 'pending')


class NotificationServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com'
        )

    def test_create_notification(self):
        service = NotificationService()
        notification = service.create_notification(
            recipient=self.user,
            channel='email',
            message='Тестовое сообщение'
        )
        self.assertIsNotNone(notification)
        self.assertEqual(notification.recipient, self.user)