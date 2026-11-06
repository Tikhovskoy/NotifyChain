from django.test import TestCase

from .models import Provider
from .services.email_providers import SMTPEmailProvider
from .services.sms_providers import TwilioSMSProvider


class ProviderModelTest(TestCase):
    def test_provider_creation(self):
        provider = Provider.objects.create(
            name="SMTP Gmail",
            provider_type="email",
            is_active=True,
            config={"host": "smtp.gmail.com", "port": 587},
        )
        self.assertEqual(provider.name, "SMTP Gmail")
        self.assertEqual(provider.provider_type, "email")
        self.assertTrue(provider.is_active)


class EmailProviderTest(TestCase):
    def test_smtp_provider_init(self):
        provider = SMTPEmailProvider()
        self.assertEqual(provider.provider_type, "email")
        self.assertEqual(provider.provider_name, "smtp")


class SMSProviderTest(TestCase):
    def test_twilio_provider_init(self):
        provider = TwilioSMSProvider()
        self.assertEqual(provider.provider_type, "sms")
        self.assertEqual(provider.provider_name, "twilio")
