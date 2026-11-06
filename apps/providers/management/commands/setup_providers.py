from django.core.management.base import BaseCommand
from apps.providers.models import Provider


class Command(BaseCommand):
    help = "Создает реальные провайдеры в базе данных"

    def handle(self, *args, **options):
        providers_config = [
            {
                "name": "smtp_email",
                "provider_type": "email",
                "is_active": True,
                "is_default": True,
                "priority": 1,
                "config": {"class_name": "smtp"},
                "rate_limit_per_minute": 30,
                "rate_limit_per_hour": 500,
            },
            {
                "name": "sendgrid_email",
                "provider_type": "email",
                "is_active": True,
                "is_default": False,
                "priority": 2,
                "config": {"class_name": "sendgrid"},
                "rate_limit_per_minute": 100,
                "rate_limit_per_hour": 2000,
            },
            {
                "name": "twilio_sms",
                "provider_type": "sms",
                "is_active": True,
                "is_default": True,
                "priority": 1,
                "config": {"class_name": "twilio"},
                "rate_limit_per_minute": 60,
                "rate_limit_per_hour": 1000,
            },
            {
                "name": "telegram_bot",
                "provider_type": "push",
                "is_active": True,
                "is_default": True,
                "priority": 1,
                "config": {"class_name": "telegram"},
                "rate_limit_per_minute": 30,
                "rate_limit_per_hour": 300,
            },
        ]

        for provider_config in providers_config:
            provider, created = Provider.objects.get_or_create(
                name=provider_config["name"], defaults=provider_config
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f"Создан провайдер: {provider.name}"))
            else:
                self.stdout.write(self.style.WARNING(f"Провайдер уже существует: {provider.name}"))

        self.stdout.write(self.style.SUCCESS("Настройка провайдеров завершена"))
