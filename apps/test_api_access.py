from unittest import mock

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient

from apps.notifications.models import NotificationTemplate
from apps.notifications.services import NotificationService
from apps.providers.models import Provider
from apps.testing import TokenAPITestCase

TEMPLATE_PAYLOAD = {
    "name": "welcome",
    "subject": "Привет, {{ name }}",
    "body": "Здравствуйте, {{ name }}",
    "template_type": "email",
    "variables": ["name"],
}
PROVIDER_PAYLOAD = {
    "name": "extra_smtp",
    "provider_type": "email",
    "config": {"class_name": "smtp"},
}

# (метод, адрес) для всех маршрутов API, включая детальные
ALL_ENDPOINTS = [
    ("get", "/api/notifications/"),
    ("post", "/api/notifications/"),
    ("get", "/api/notifications/1/"),
    ("delete", "/api/notifications/1/"),
    ("post", "/api/notifications/send/"),
    ("post", "/api/notifications/send_async/"),
    ("post", "/api/notifications/send_bulk/"),
    ("post", "/api/notifications/send_bulk_async/"),
    ("post", "/api/notifications/1/retry/"),
    ("get", "/api/notifications/stats/"),
    ("get", "/api/notifications/pending/"),
    ("get", "/api/notifications/failed/"),
    ("get", "/api/templates/"),
    ("post", "/api/templates/"),
    ("get", "/api/templates/1/"),
    ("put", "/api/templates/1/"),
    ("delete", "/api/templates/1/"),
    ("post", "/api/templates/1/preview/"),
    ("post", "/api/templates/1/validate_template/"),
    ("get", "/api/providers/"),
    ("post", "/api/providers/"),
    ("get", "/api/providers/1/"),
    ("put", "/api/providers/1/"),
    ("delete", "/api/providers/1/"),
    ("post", "/api/providers/1/test/"),
    ("get", "/api/providers/1/stats/"),
    ("get", "/api/providers/available/?channel=email"),
    ("get", "/api/usage/"),
]


class AnonymousAccessTest(TokenAPITestCase):
    def test_every_endpoint_requires_authentication(self):
        client = APIClient()

        for method, url in ALL_ENDPOINTS:
            with self.subTest(method=method, url=url):
                response = getattr(client, method)(url, {}, format="json")

                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
                self.assertIn("Token", response["WWW-Authenticate"])

    def test_wrong_token_is_rejected(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")

        response = client.get("/api/notifications/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_service_root_stays_public_for_health_checks(self):
        response = APIClient().get("/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class RegularUserAccessTest(TokenAPITestCase):
    def setUp(self):
        self.user = User.objects.create_user("client", email="client@example.com")
        self.client_api = self.client_for(self.user)
        self.template = NotificationTemplate.objects.create(**{**TEMPLATE_PAYLOAD, "name": "base"})
        self.provider = Provider.objects.create(
            name="smtp_email", provider_type="email", config={"class_name": "smtp"}
        )

    def test_user_can_send_notification(self):
        payload = {"recipient_id": self.user.id, "channel": "email", "message": "Привет"}

        with mock.patch.object(NotificationService, "send_notification", return_value=True):
            response = self.client_api.post("/api/notifications/send/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["sent_immediately"])

    def test_user_can_read_templates(self):
        response = self.client_api.get("/api/templates/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_cannot_change_templates(self):
        url = f"/api/templates/{self.template.id}/"
        attempts = [
            ("post", "/api/templates/", TEMPLATE_PAYLOAD),
            ("put", url, {**TEMPLATE_PAYLOAD, "name": "other"}),
            ("patch", url, {"subject": "взлом"}),
            ("delete", url, None),
        ]

        for method, target, data in attempts:
            with self.subTest(method=method):
                response = getattr(self.client_api, method)(target, data, format="json")

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.template.refresh_from_db()
        self.assertEqual(self.template.subject, TEMPLATE_PAYLOAD["subject"])

    def test_user_can_preview_and_validate_templates(self):
        for action, data in [
            ("preview", {"template_id": self.template.id, "context_data": {"name": "Аня"}}),
            ("validate_template", {}),
        ]:
            with self.subTest(action=action):
                url = f"/api/templates/{self.template.id}/{action}/"
                response = self.client_api.post(url, data, format="json")

                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_has_no_access_to_providers_and_usage(self):
        pid = self.provider.id
        attempts = [
            ("get", "/api/providers/"),
            ("post", "/api/providers/"),
            ("get", f"/api/providers/{pid}/"),
            ("patch", f"/api/providers/{pid}/"),
            ("delete", f"/api/providers/{pid}/"),
            ("post", f"/api/providers/{pid}/test/"),
            ("get", f"/api/providers/{pid}/stats/"),
            ("get", "/api/providers/available/?channel=email"),
            ("get", "/api/usage/"),
        ]

        for method, url in attempts:
            with self.subTest(method=method, url=url):
                response = getattr(self.client_api, method)(url, {}, format="json")

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.assertTrue(Provider.objects.filter(id=pid).exists())


class StaffAccessTest(TokenAPITestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", is_staff=True)
        self.client_api = self.client_for(self.admin)

    def test_staff_can_manage_providers(self):
        created = self.client_api.post("/api/providers/", PROVIDER_PAYLOAD, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        listed = self.client_api.get("/api/providers/")
        self.assertEqual(listed.status_code, status.HTTP_200_OK)

        deleted = self.client_api.delete(f"/api/providers/{created.data['id']}/")
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)

    def test_staff_can_manage_templates(self):
        created = self.client_api.post("/api/templates/", TEMPLATE_PAYLOAD, format="json")

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertTrue(NotificationTemplate.objects.filter(name="welcome").exists())

    def test_staff_can_read_usage(self):
        response = self.client_api.get("/api/usage/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
