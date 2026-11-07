"""Поведение эндпоинтов отправки: send, send_async, send_bulk, send_bulk_async, retry, stats.

Тесты фиксируют контракт API перед рефакторингом представлений: URL и формат ответов
не должны меняться.
"""

from unittest import mock

from django.contrib.auth.models import User
from rest_framework import status

from apps.notifications.exceptions import ProviderException
from apps.notifications.models import Notification, NotificationTemplate
from apps.notifications.services import NotificationService
from apps.providers.services import ProviderManager
from apps.testing import TokenAPITestCase
from apps.users.models import UserProfile


class SendingApiTest(TokenAPITestCase):
    def setUp(self):
        super().setUp()
        self.alice = User.objects.create_user("alice", email="alice@example.com")
        self.bob = User.objects.create_user("bob", email="bob@example.com")
        self.no_email = User.objects.create_user("silent")
        UserProfile.objects.create(user=self.alice, phone_number="+15551234567")
        self.api = self.client_for(self.alice)

    def payload(self, **extra):
        return {"recipient_id": self.bob.id, "channel": "email", "message": "Привет", **extra}

    def bulk_payload(self, ids=None, **extra):
        ids = ids if ids is not None else [self.alice.id, self.bob.id]
        return {"recipient_ids": ids, "channel": "email", "message": "Новости", **extra}

    # send -------------------------------------------------------------------------------

    def test_send_delivers_immediately(self):
        with mock.patch.object(
            ProviderManager, "send_notification", return_value={"success": True}
        ) as manager:
            response = self.api.post("/api/notifications/send/", self.payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["sent_immediately"])
        self.assertEqual(response.data["status"], "sent")
        self.assertEqual(response.data["recipient"], self.bob.id)
        self.assertEqual(manager.call_args.kwargs["recipient"], "bob@example.com")

    def test_send_reports_failed_delivery_without_an_error_status(self):
        with mock.patch.object(
            ProviderManager, "send_notification", side_effect=ProviderException("всё лежит")
        ):
            response = self.api.post("/api/notifications/send/", self.payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data["sent_immediately"])
        self.assertEqual(response.data["status"], "failed")

    def test_send_renders_template_when_context_is_given(self):
        template = NotificationTemplate.objects.create(
            name="hello",
            subject="Привет, {{ name }}",
            body="Здравствуйте, {{ name }}",
            template_type="email",
            variables=["name"],
        )
        payload = self.payload(template_id=template.id, context_data={"name": "Боб"})

        with mock.patch.object(
            ProviderManager, "send_notification", return_value={"success": True}
        ) as manager:
            response = self.api.post("/api/notifications/send/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(manager.call_args.kwargs["subject"], "Привет, Боб")
        self.assertEqual(manager.call_args.kwargs["message"], "Здравствуйте, Боб")

    # send_async -------------------------------------------------------------------------

    def test_send_async_queues_the_notification(self):
        with mock.patch("tasks.notification_tasks.send_notification_task.delay") as delay:
            delay.return_value = mock.Mock(id="task-1")
            response = self.api.post(
                "/api/notifications/send_async/", self.payload(), format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["task_id"], "task-1")
        self.assertTrue(response.data["queued_for_async_processing"])
        self.assertEqual(response.data["status"], "queued")
        delay.assert_called_once_with(response.data["id"])

    # send_bulk --------------------------------------------------------------------------

    def test_send_bulk_creates_notifications_and_skips_unreachable_recipients(self):
        response = self.api.post(
            "/api/notifications/send_bulk/",
            self.bulk_payload([self.alice.id, self.bob.id, self.no_email.id]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["message"], "Created 2 notifications")
        usernames = {item["recipient"] for item in response.data["notifications"]}
        self.assertEqual(usernames, {"alice", "bob"})
        self.assertEqual(Notification.objects.filter(status="pending").count(), 2)

    def test_send_bulk_rejects_unknown_recipients(self):
        response = self.api.post(
            "/api/notifications/send_bulk/",
            self.bulk_payload([self.alice.id, 99999]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("recipient_ids", response.data)

    # send_bulk_async --------------------------------------------------------------------

    def test_send_bulk_async_queues_every_notification(self):
        with mock.patch("tasks.notification_tasks.send_bulk_notifications_task.delay") as delay:
            delay.return_value = mock.Mock(id="bulk-1")
            response = self.api.post(
                "/api/notifications/send_bulk_async/", self.bulk_payload(), format="json"
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["task_id"], "bulk-1")
        self.assertEqual(response.data["recipient_count"], 2)
        self.assertTrue(response.data["queued_for_async_processing"])
        self.assertEqual(Notification.objects.filter(status="queued").count(), 2)
        queued_ids = set(Notification.objects.values_list("id", flat=True))
        self.assertEqual(set(delay.call_args.args[0]), queued_ids)

    def test_send_bulk_async_uses_the_template(self):
        template = NotificationTemplate.objects.create(
            name="news", subject="s", body="b", template_type="email"
        )

        with mock.patch("tasks.notification_tasks.send_bulk_notifications_task.delay") as delay:
            delay.return_value = mock.Mock(id="bulk-2")
            response = self.api.post(
                "/api/notifications/send_bulk_async/",
                self.bulk_payload(template_id=template.id),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Notification.objects.filter(template=template).count(), 2)

    # retry и stats ----------------------------------------------------------------------

    def test_retry_returns_the_outcome_of_the_attempt(self):
        notification = Notification.objects.create(
            recipient=self.alice,
            channel="email",
            message="x",
            recipient_address="alice@example.com",
            status="failed",
            retry_count=1,
        )

        with mock.patch.object(
            NotificationService, "retry_failed_notification", return_value=True
        ) as retry:
            response = self.api.post(f"/api/notifications/{notification.id}/retry/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["retry_successful"])
        self.assertEqual(response.data["notification_id"], notification.id)
        retry.assert_called_once()

    def test_global_stats_for_administrator(self):
        admin = User.objects.create_user("admin", is_staff=True)
        for status_value in ("sent", "sent", "failed"):
            Notification.objects.create(
                recipient=self.alice,
                channel="email",
                message="x",
                recipient_address="a@b.c",
                status=status_value,
            )

        response = self.client_for(admin).get("/api/notifications/stats/?days=3")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["period_days"], 3)
        self.assertEqual(response.data["total_notifications"], 3)
        self.assertEqual(response.data["by_status"], {"sent": 2, "failed": 1})
        self.assertEqual(response.data["by_channel"], {"email": 3})

    def test_stats_rejects_invalid_period(self):
        response = self.api.get("/api/notifications/stats/?days=0")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
