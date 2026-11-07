from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from rest_framework import status


class OpenAPISchemaTest(TestCase):
    def schema(self):
        response = self.client.get("/api/schema/", {"format": "json"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.json()

    def test_schema_is_valid_and_has_no_generator_warnings(self):
        out, err = StringIO(), StringIO()

        try:
            call_command("spectacular", "--validate", "--fail-on-warn", stdout=out, stderr=err)
        except SystemExit:
            self.fail(f"Схема OpenAPI построена с предупреждениями:\n{err.getvalue()}")

    def test_schema_is_public_and_describes_the_api(self):
        schema = self.schema()

        self.assertTrue(schema["openapi"].startswith("3."))
        self.assertEqual(schema["info"]["title"], "NotifyChain API")
        for path in (
            "/api/notifications/send/",
            "/api/notifications/send_async/",
            "/api/notifications/send_bulk/",
            "/api/notifications/send_bulk_async/",
            "/api/notifications/pending/",
            "/api/providers/",
            "/api/providers/{id}/test/",
            "/api/templates/{id}/preview/",
        ):
            self.assertIn(path, schema["paths"])

    def test_token_authentication_is_documented(self):
        schemes = self.schema()["components"]["securitySchemes"]

        token_scheme = next(s for s in schemes.values() if s.get("name") == "Authorization")
        self.assertEqual(token_scheme["type"], "apiKey")
        self.assertEqual(token_scheme["in"], "header")

    def test_send_request_body_lists_the_fields(self):
        schema = self.schema()

        body = schema["paths"]["/api/notifications/send/"]["post"]["requestBody"]
        ref = body["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
        properties = schema["components"]["schemas"][ref]["properties"]
        self.assertIn("recipient_id", properties)
        self.assertIn("channel", properties)

    def test_provider_config_is_write_only_in_the_schema(self):
        schemas = self.schema()["components"]["schemas"]

        self.assertTrue(schemas["ProviderRequest"]["properties"]["config"])
        self.assertNotIn("config", schemas["Provider"]["properties"])

    def test_swagger_ui_is_served(self):
        response = self.client.get("/api/docs/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("swagger", response.content.decode().lower())
