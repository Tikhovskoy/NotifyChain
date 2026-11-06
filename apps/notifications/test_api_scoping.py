from django.contrib.auth.models import User
from rest_framework import status

from apps.notifications.models import Notification
from apps.testing import TokenAPITestCase


class NotificationScopingTest(TokenAPITestCase):
    """Обычный пользователь видит только свои уведомления, администратор — все."""

    def setUp(self):
        self.alice = User.objects.create_user("alice", email="alice@example.com")
        self.bob = User.objects.create_user("bob", email="bob@example.com")
        self.admin = User.objects.create_user("admin", is_staff=True)

        self.alice_pending = self.make(self.alice, "pending")
        self.bob_pending = self.make(self.bob, "pending")
        self.alice_failed = self.make(self.alice, "failed")
        self.bob_failed = self.make(self.bob, "failed")

    def make(self, user, status_value):
        return Notification.objects.create(
            recipient=user,
            channel="email",
            message="Тест",
            recipient_address=user.email or "x@example.com",
            status=status_value,
        )

    @staticmethod
    def ids(response):
        return {item["id"] for item in response.data["notifications"]}

    def test_pending_shows_only_own_notifications(self):
        response = self.client_for(self.alice).get("/api/notifications/pending/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.ids(response), {self.alice_pending.id})

    def test_failed_shows_only_own_notifications(self):
        response = self.client_for(self.alice).get("/api/notifications/failed/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.ids(response), {self.alice_failed.id})

    def test_admin_sees_pending_and_failed_of_everyone(self):
        client = self.client_for(self.admin)

        pending = client.get("/api/notifications/pending/")
        failed = client.get("/api/notifications/failed/")

        self.assertEqual(self.ids(pending), {self.alice_pending.id, self.bob_pending.id})
        self.assertEqual(self.ids(failed), {self.alice_failed.id, self.bob_failed.id})

    def test_list_shows_only_own_notifications(self):
        response = self.client_for(self.alice).get("/api/notifications/")

        ids = {item["id"] for item in response.data["results"]}
        self.assertEqual(ids, {self.alice_pending.id, self.alice_failed.id})

    def test_user_stats_cover_only_the_caller(self):
        response = self.client_for(self.alice).get("/api/notifications/stats/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 2)

    def test_user_cannot_request_stats_of_another_user(self):
        response = self.client_for(self.alice).get(
            f"/api/notifications/stats/?user_id={self.bob.id}"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_can_request_own_stats_by_id(self):
        response = self.client_for(self.alice).get(
            f"/api/notifications/stats/?user_id={self.alice.id}"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 2)

    def test_admin_gets_global_stats_and_stats_of_any_user(self):
        client = self.client_for(self.admin)

        overall = client.get("/api/notifications/stats/")
        of_bob = client.get(f"/api/notifications/stats/?user_id={self.bob.id}")

        self.assertEqual(overall.data["total_notifications"], 4)
        self.assertEqual(of_bob.data["total"], 2)

    def test_user_cannot_retry_foreign_notification(self):
        response = self.client_for(self.alice).post(
            f"/api/notifications/{self.bob_failed.id}/retry/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
