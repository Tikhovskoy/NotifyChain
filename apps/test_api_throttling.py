from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.testing import TokenAPITestCase


class PublicPing(APIView):
    """Открытый эндпоинт: на нём видно, что анонимный throttle берётся из настроек."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"ok": True})


class ThrottlingSettingsTest(TokenAPITestCase):
    def test_throttle_classes_and_rates_are_configured(self):
        config = settings.REST_FRAMEWORK

        self.assertIn(
            "rest_framework.throttling.AnonRateThrottle", config["DEFAULT_THROTTLE_CLASSES"]
        )
        self.assertIn(
            "rest_framework.throttling.UserRateThrottle", config["DEFAULT_THROTTLE_CLASSES"]
        )
        self.assertTrue(config["DEFAULT_THROTTLE_RATES"]["anon"])
        self.assertTrue(config["DEFAULT_THROTTLE_RATES"]["user"])


class ThrottlingBehaviourTest(TokenAPITestCase):
    def setUp(self):
        super().setUp()
        self.alice = User.objects.create_user("alice")
        self.bob = User.objects.create_user("bob")

    def test_user_gets_429_after_exceeding_the_limit(self):
        api = self.client_for(self.alice)

        with mock.patch.dict(UserRateThrottle.THROTTLE_RATES, {"user": "3/min"}):
            codes = [api.get("/api/notifications/").status_code for _ in range(4)]

        self.assertEqual(codes, [200, 200, 200, status.HTTP_429_TOO_MANY_REQUESTS])

    def test_limit_applies_to_send_endpoints(self):
        api = self.client_for(self.alice)

        with mock.patch.dict(UserRateThrottle.THROTTLE_RATES, {"user": "2/min"}):
            codes = [
                api.post("/api/notifications/send/", {}, format="json").status_code
                for _ in range(3)
            ]

        self.assertEqual(codes[-1], status.HTTP_429_TOO_MANY_REQUESTS)

    def test_each_user_has_their_own_counter(self):
        alice_api = self.client_for(self.alice)
        bob_api = self.client_for(self.bob)

        with mock.patch.dict(UserRateThrottle.THROTTLE_RATES, {"user": "1/min"}):
            alice_api.get("/api/notifications/")
            blocked = alice_api.get("/api/notifications/")
            bob_response = bob_api.get("/api/notifications/")

        self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(bob_response.status_code, status.HTTP_200_OK)

    def test_anonymous_throttle_uses_configured_rate(self):
        view = PublicPing.as_view()
        factory = APIRequestFactory()

        with mock.patch.dict(AnonRateThrottle.THROTTLE_RATES, {"anon": "2/min"}):
            codes = [view(factory.get("/ping/")).status_code for _ in range(3)]

        self.assertEqual(codes, [200, 200, status.HTTP_429_TOO_MANY_REQUESTS])
