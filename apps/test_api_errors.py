from unittest import mock

from django.contrib.auth.models import User
from django.http import Http404
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.exception_handler import api_exception_handler
from apps.notifications import exceptions as domain
from apps.notifications.models import Notification
from apps.notifications.services import NotificationService
from apps.providers.models import Provider
from apps.providers.services import ProviderManager
from apps.testing import TokenAPITestCase
from apps.users.models import NotificationPreference

SECRET_DETAIL = "password=hunter2 host=10.0.0.5"


class DomainExceptionStatusTest(SimpleTestCase):
    def test_every_domain_exception_maps_to_400_404_or_409(self):
        expected = {
            domain.NotificationException: 400,
            domain.ValidationException: 400,
            domain.TemplateException: 400,
            domain.NotFoundException: 404,
            domain.ProviderNotFoundException: 404,
            domain.ConflictException: 409,
            domain.ProviderException: 409,
            domain.UserPreferenceException: 409,
            domain.NotificationNotReadyException: 409,
            domain.RetryNotAllowedException: 409,
        }

        for exception_class, status_code in expected.items():
            with self.subTest(exception=exception_class.__name__):
                self.assertEqual(exception_class.status_code, status_code)
                self.assertTrue(exception_class.code)

    def test_missing_provider_is_both_a_provider_error_and_not_found(self):
        self.assertTrue(issubclass(domain.ProviderNotFoundException, domain.ProviderException))
        self.assertTrue(issubclass(domain.ProviderNotFoundException, domain.NotFoundException))


class ExceptionHandlerTest(SimpleTestCase):
    context = {"view": mock.Mock(), "request": mock.Mock(method="POST", path="/api/x/")}

    def test_domain_exception_keeps_its_message_status_and_code(self):
        response = api_exception_handler(domain.ConflictException("Уже есть"), self.context)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data, {"error": "Уже есть", "code": "conflict"})

    def test_drf_exceptions_keep_the_standard_format(self):
        cases = [
            (NotAuthenticated(), 401),
            (PermissionDenied(), 403),
            (Http404(), 404),
            (DRFValidationError({"channel": ["Обязательное поле"]}), 400),
        ]

        for exc, status_code in cases:
            with self.subTest(exc=type(exc).__name__):
                response = api_exception_handler(exc, self.context)

                self.assertEqual(response.status_code, status_code)

    def test_unexpected_exception_gives_500_without_details_and_logs_traceback(self):
        error = RuntimeError(SECRET_DETAIL)

        with self.assertLogs("notifychain.api", level="ERROR") as logs:
            response = api_exception_handler(error, self.context)

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("hunter2", str(response.data))
        self.assertEqual(response.data["code"], "server_error")
        record = logs.records[0]
        self.assertIs(record.exc_info[1], error)


class ApiErrorResponsesTest(TokenAPITestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("client", email="client@example.com")
        self.admin = User.objects.create_user("admin", is_staff=True)
        self.api = self.client_for(self.user)
        self.admin_api = self.client_for(self.admin)

    def send_payload(self, **extra):
        return {"recipient_id": self.user.id, "channel": "email", "message": "Привет", **extra}

    def test_unexpected_error_in_send_is_a_500_without_internal_details(self):
        with (
            mock.patch.object(
                NotificationService, "send_notification", side_effect=RuntimeError(SECRET_DETAIL)
            ),
            self.assertLogs("notifychain.api", level="ERROR") as logs,
        ):
            response = self.api.post("/api/notifications/send/", self.send_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertNotIn("hunter2", response.content.decode())
        self.assertIn("RuntimeError", "".join(logs.output))

    def test_unexpected_error_in_every_sending_endpoint_is_a_500(self):
        endpoints = [
            ("send_async", self.send_payload()),
            (
                "send_bulk",
                {"recipient_ids": [self.user.id], "channel": "email", "message": "Привет"},
            ),
            (
                "send_bulk_async",
                {"recipient_ids": [self.user.id], "channel": "email", "message": "Привет"},
            ),
        ]
        broken = RuntimeError(SECRET_DETAIL)

        for action, payload in endpoints:
            with self.subTest(action=action):
                with (
                    mock.patch.object(
                        NotificationService, "create_notification", side_effect=broken
                    ),
                    mock.patch.object(
                        NotificationService, "send_bulk_notifications", side_effect=broken
                    ),
                    mock.patch.object(
                        NotificationService, "send_notification_async", side_effect=broken
                    ),
                    mock.patch.object(
                        NotificationService, "send_bulk_notifications_async", side_effect=broken
                    ),
                    self.assertLogs("notifychain.api", level="ERROR"),
                ):
                    response = self.api.post(
                        f"/api/notifications/{action}/", payload, format="json"
                    )

                self.assertEqual(response.status_code, 500)
                self.assertNotIn("hunter2", response.content.decode())

    def test_channel_disabled_by_the_recipient_is_a_409(self):
        NotificationPreference.objects.create(user=self.user, email_enabled=False)

        response = self.api.post("/api/notifications/send/", self.send_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "user_preference")
        self.assertFalse(Notification.objects.exists())

    def test_async_send_of_a_notification_that_is_not_ready_is_a_409(self):
        future = (timezone.now() + timezone.timedelta(days=1)).isoformat()

        response = self.api.post(
            "/api/notifications/send_async/", self.send_payload(scheduled_at=future), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "notification_not_ready")

    def test_retry_of_a_notification_that_cannot_be_retried_is_a_409(self):
        notification = Notification.objects.create(
            recipient=self.user, channel="email", message="x", recipient_address="a@b.c"
        )

        response = self.api.post(f"/api/notifications/{notification.id}/retry/")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "retry_not_allowed")

    def test_retry_of_an_unknown_notification_is_a_404(self):
        response = self.api.post("/api/notifications/999999/retry/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_available_providers_without_channel_is_a_400(self):
        response = self.admin_api.get("/api/providers/available/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "validation_error")

    def test_provider_test_with_unknown_class_is_a_409_with_its_message(self):
        provider = Provider.objects.create(
            name="ghost", provider_type="email", config={"class_name": "ghost"}
        )

        response = self.admin_api.post(f"/api/providers/{provider.id}/test/")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("ghost", response.data["error"])

    def test_unexpected_error_in_provider_endpoints_is_a_500(self):
        provider = Provider.objects.create(name="smtp", provider_type="email")
        broken = RuntimeError(SECRET_DETAIL)
        cases = [
            ("post", f"/api/providers/{provider.id}/test/", "test_provider"),
            ("get", f"/api/providers/{provider.id}/stats/", "get_provider_statistics"),
            ("get", "/api/providers/available/?channel=email", "get_available_providers"),
        ]

        for method, url, manager_method in cases:
            with self.subTest(url=url):
                with (
                    mock.patch.object(ProviderManager, manager_method, side_effect=broken),
                    self.assertLogs("notifychain.api", level="ERROR"),
                ):
                    response = getattr(self.admin_api, method)(url)

                self.assertEqual(response.status_code, 500)
                self.assertNotIn("hunter2", response.content.decode())

    def test_domain_validation_error_from_validator_is_a_400_with_its_message(self):
        response = self.api.post(
            "/api/notifications/send/", self.send_payload(message="   "), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("не может быть пустым", str(response.data))

    def test_unexpected_error_inside_validator_is_not_leaked_as_a_400(self):
        with (
            mock.patch(
                "apps.notifications.serializers.NotificationValidator.validate_channel",
                side_effect=RuntimeError(SECRET_DETAIL),
            ),
            self.assertLogs("notifychain.api", level="ERROR"),
        ):
            response = self.api.post("/api/notifications/send/", self.send_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertNotIn("hunter2", response.content.decode())

    def test_validation_errors_keep_the_drf_format(self):
        response = self.api.post("/api/notifications/send/", {"channel": "email"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("recipient_id", response.data)
