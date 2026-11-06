from django.test import TestCase

from apps.notifications.exceptions import ProviderException, ProviderNotFoundException
from apps.providers.models import Provider
from apps.providers.services.base_provider import BaseProvider, MockEmailProvider
from apps.providers.services.registry import ProviderRegistry


class StubProvider(BaseProvider):
    provider_type = "email"

    def send_notification(self, recipient, message, subject="", metadata=None):
        return {"success": True}

    def validate_config(self):
        return {"is_valid": True, "errors": []}

    def get_delivery_status(self, message_id):
        return {}


def make(name, channel="email", priority=1, **extra):
    config = extra.pop("config", {"class_name": "stub"})
    return Provider.objects.create(
        name=name, provider_type=channel, priority=priority, config=config, **extra
    )


class ProviderClassesTest(TestCase):
    def setUp(self):
        self.registry = ProviderRegistry({"stub": StubProvider})

    def test_instance_is_created_from_class_name_in_config_and_named_after_the_provider(self):
        provider = make("smtp_email")

        instance = self.registry.get_instance(provider)

        self.assertIsInstance(instance, StubProvider)
        self.assertEqual(instance.name, "smtp_email")

    def test_instance_is_cached_per_provider(self):
        provider = make("smtp_email")

        self.assertIs(self.registry.get_instance(provider), self.registry.get_instance(provider))

    def test_provider_without_class_name_falls_back_to_the_mock_of_its_channel(self):
        registry = ProviderRegistry()
        provider = make("plain", config={})

        self.assertIsInstance(registry.get_instance(provider), MockEmailProvider)

    def test_unknown_class_name_is_an_error(self):
        provider = make("ghost", config={"class_name": "ghost"})

        with self.assertRaises(ProviderException):
            self.registry.get_instance(provider)

    def test_registered_class_becomes_available(self):
        registry = ProviderRegistry({})
        provider = make("late")

        registry.register("stub", StubProvider)

        self.assertIsInstance(registry.get_instance(provider), StubProvider)

    def test_default_registry_knows_all_builtin_providers(self):
        registry = ProviderRegistry()
        names = ["smtp", "sendgrid", "twilio", "telegram", "mock_email", "mock_sms", "mock_push"]

        for name in names:
            with self.subTest(name=name):
                provider = make(f"p_{name}", config={"class_name": name})
                self.assertTrue(registry.get_instance(provider))


class ProviderSelectionTest(TestCase):
    def setUp(self):
        self.registry = ProviderRegistry({"stub": StubProvider})

    def test_available_providers_are_active_and_sorted_by_priority(self):
        make("b", priority=2)
        make("a", priority=1)
        make("off", priority=0, is_active=False)
        make("sms_one", channel="sms")

        names = [p.name for p in self.registry.get_available("email")]

        self.assertEqual(names, ["a", "b"])

    def test_default_provider_wins_over_priority(self):
        make("first", priority=1)
        chosen = make("chosen", priority=5, is_default=True)

        self.assertEqual(self.registry.resolve("email"), chosen)

    def test_without_default_the_highest_priority_provider_is_chosen(self):
        first = make("first", priority=1)
        make("second", priority=2)

        self.assertEqual(self.registry.resolve("email"), first)

    def test_resolve_by_name_ignores_the_channel_default(self):
        make("first", is_default=True)
        wanted = make("wanted", priority=3)

        self.assertEqual(self.registry.resolve("email", "wanted"), wanted)

    def test_resolve_raises_when_nothing_matches(self):
        with self.assertRaises(ProviderNotFoundException):
            self.registry.resolve("email")

        with self.assertRaises(ProviderNotFoundException):
            self.registry.resolve("email", "nope")

    def test_inactive_provider_is_not_resolved_by_name(self):
        make("sleeping", is_active=False)

        with self.assertRaises(ProviderNotFoundException):
            self.registry.resolve("email", "sleeping")


class FallbackCandidatesTest(TestCase):
    def setUp(self):
        self.registry = ProviderRegistry({"stub": StubProvider})

    def test_candidates_are_all_active_providers_in_priority_order(self):
        make("third", priority=3)
        make("first", priority=1)
        make("second", priority=2)

        names = [p.name for p in self.registry.candidates("email")]

        self.assertEqual(names, ["first", "second", "third"])

    def test_explicit_name_gives_a_single_candidate_without_fallback(self):
        make("first", priority=1)
        second = make("second", priority=2)

        self.assertEqual(self.registry.candidates("email", "second"), [second])

    def test_no_candidates_is_an_error(self):
        with self.assertRaises(ProviderException):
            self.registry.candidates("email")

        with self.assertRaises(ProviderNotFoundException):
            self.registry.candidates("email", "nope")
