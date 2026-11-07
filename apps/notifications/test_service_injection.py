"""Сервисы подставляются через атрибуты класса: в тестах не нужно патчить импорты."""

from unittest import mock

from django.contrib.auth.models import User
from rest_framework import status

from apps.notifications.models import NotificationTemplate
from apps.notifications.services import NotificationService, TemplateService
from apps.notifications.views import NotificationTemplateViewSet, NotificationViewSet
from apps.testing import TokenAPITestCase


class RecordingService(NotificationService):
    """Настоящий сервис, который запоминает вызовы и ничего не отправляет."""

    calls = []

    def create_notification(self, **kwargs):
        RecordingService.calls.append("create_notification")
        return super().create_notification(**kwargs)

    def send_notification(self, notification):
        RecordingService.calls.append("send_notification")
        return True


class NotificationServiceInjectionTest(TokenAPITestCase):
    def setUp(self):
        super().setUp()
        RecordingService.calls = []
        self.user = User.objects.create_user("client", email="client@example.com")
        self.api = self.client_for(self.user)

    def test_view_and_serializer_use_the_substituted_service(self):
        payload = {"recipient_id": self.user.id, "channel": "email", "message": "Привет"}

        with mock.patch.object(NotificationViewSet, "service_class", RecordingService):
            response = self.api.post("/api/notifications/send/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["sent_immediately"])
        self.assertEqual(RecordingService.calls, ["create_notification", "send_notification"])

    def test_default_service_is_the_real_one(self):
        self.assertIs(NotificationViewSet.service_class, NotificationService)
        self.assertIs(NotificationTemplateViewSet.template_service_class, TemplateService)


class FakeTemplateService(TemplateService):
    def validate_template(self, template):
        return {
            "is_valid": False,
            "errors": ["подставленный сервис"],
            "warnings": [],
            "required_variables": [],
        }

    def get_template_preview(self, template, sample_data=None):
        return {"subject": "из подставленного сервиса", "body": "тело"}


class TemplateServiceInjectionTest(TokenAPITestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user("admin", is_staff=True)
        self.api = self.client_for(self.admin)
        self.template = NotificationTemplate.objects.create(
            name="hello", subject="s", body="b", template_type="email"
        )

    def test_substituted_service_is_used_by_preview_and_validation_actions(self):
        with mock.patch.object(
            NotificationTemplateViewSet, "template_service_class", FakeTemplateService
        ):
            preview = self.api.post(
                f"/api/templates/{self.template.id}/preview/",
                {"template_id": self.template.id},
                format="json",
            )
            validation = self.api.post(f"/api/templates/{self.template.id}/validate_template/")

        self.assertEqual(preview.data["rendered_subject"], "из подставленного сервиса")
        self.assertEqual(validation.data["errors"], ["подставленный сервис"])

    def test_substituted_service_is_used_when_saving_a_template(self):
        payload = {"name": "new", "subject": "s", "body": "b", "template_type": "email"}

        with mock.patch.object(
            NotificationTemplateViewSet, "template_service_class", FakeTemplateService
        ):
            response = self.api.post("/api/templates/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("подставленный сервис", str(response.data))
        self.assertFalse(NotificationTemplate.objects.filter(name="new").exists())
