from django.contrib.auth.models import User
from rest_framework import status

from apps.providers.models import Provider
from apps.testing import TokenAPITestCase

SECRET_CONFIG = {"class_name": "smtp", "password": "s3cret-value"}


class ProviderConfigIsWriteOnlyTest(TokenAPITestCase):
    def setUp(self):
        admin = User.objects.create_user("admin", is_staff=True)
        self.api = self.client_for(admin)
        self.provider = Provider.objects.create(
            name="smtp_email", provider_type="email", config=SECRET_CONFIG
        )

    def assertNoConfigLeak(self, response):
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("s3cret-value", response.content.decode())

    def test_list_does_not_expose_config(self):
        response = self.api.get("/api/providers/")

        self.assertNoConfigLeak(response)
        self.assertNotIn("config", response.data["results"][0])

    def test_detail_does_not_expose_config(self):
        response = self.api.get(f"/api/providers/{self.provider.id}/")

        self.assertNoConfigLeak(response)
        self.assertNotIn("config", response.data)

    def test_available_does_not_expose_config(self):
        response = self.api.get("/api/providers/available/?channel=email")

        self.assertNoConfigLeak(response)
        self.assertNotIn("config", response.data["providers"][0])

    def test_config_is_still_accepted_on_create(self):
        payload = {"name": "second", "provider_type": "email", "config": SECRET_CONFIG}

        response = self.api.post("/api/providers/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("config", response.data)
        self.assertEqual(Provider.objects.get(name="second").config, SECRET_CONFIG)

    def test_config_is_still_accepted_on_update(self):
        new_config = {"class_name": "sendgrid"}

        response = self.api.patch(
            f"/api/providers/{self.provider.id}/", {"config": new_config}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("config", response.data)
        self.provider.refresh_from_db()
        self.assertEqual(self.provider.config, new_config)
