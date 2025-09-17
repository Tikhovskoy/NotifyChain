from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from apps.notifications.models import NotificationTemplate, Notification
from apps.providers.models import Provider, ProviderCredential
from apps.users.models import UserProfile, NotificationPreference


class Command(BaseCommand):
    help = 'Создает тестовые данные для проверки работы системы'

    def add_arguments(self, parser):
        parser.add_argument('--clean', action='store_true')

    def handle(self, *args, **options):
        if options['clean']:
            self.stdout.write('Очистка существующих данных...')
            User.objects.exclude(is_superuser=True).delete()
            NotificationTemplate.objects.all().delete()
            Notification.objects.all().delete()
            Provider.objects.all().delete()

        self.stdout.write('Создание тестовых пользователей...')
        self.create_test_users()

        self.stdout.write('Создание провайдеров...')
        self.create_providers()

        self.stdout.write('Создание шаблонов уведомлений...')
        self.create_templates()

        self.stdout.write('Создание тестовых уведомлений...')
        self.create_notifications()

        self.stdout.write(
            self.style.SUCCESS('Тестовые данные успешно созданы!')
        )

    def create_test_users(self):
        users_data = [
            {
                'username': 'john_doe',
                'email': 'john@example.com',
                'first_name': 'John',
                'last_name': 'Doe',
                'phone': '+1234567890'
            },
            {
                'username': 'jane_smith',
                'email': 'jane@example.com',
                'first_name': 'Jane',
                'last_name': 'Smith',
                'phone': '+0987654321'
            },
            {
                'username': 'test_user',
                'email': 'test@notifychain.com',
                'first_name': 'Test',
                'last_name': 'User',
                'phone': '+1122334455'
            }
        ]

        for user_data in users_data:
            if not User.objects.filter(username=user_data['username']).exists():
                user = User.objects.create_user(
                    username=user_data['username'],
                    email=user_data['email'],
                    password='testpass123',
                    first_name=user_data['first_name'],
                    last_name=user_data['last_name']
                )

                UserProfile.objects.create(
                    user=user,
                    phone_number=user_data['phone'],
                    timezone='UTC',
                    push_token=f'push_token_{user.id}_{timezone.now().timestamp()}'
                )

                NotificationPreference.objects.create(
                    user=user,
                    email_enabled=True,
                    sms_enabled=True,
                    push_enabled=True
                )

                self.stdout.write(f'Создан пользователь: {user.username}')

    def create_providers(self):
        providers_data = [
            {
                'name': 'SMTP Email',
                'provider_type': 'email',
                'config': {
                    'host': 'smtp.gmail.com',
                    'port': 587,
                    'use_tls': True
                }
            },
            {
                'name': 'Mock SMS Provider',
                'provider_type': 'sms',
                'config': {
                    'simulate_delay': True,
                    'success_rate': 0.9
                }
            },
            {
                'name': 'Mock Push Provider',
                'provider_type': 'push',
                'config': {
                    'api_version': 'v1',
                    'timeout': 30
                }
            }
        ]

        for provider_data in providers_data:
            provider, created = Provider.objects.get_or_create(
                name=provider_data['name'],
                defaults={
                    'provider_type': provider_data['provider_type'],
                    'is_active': True,
                    'is_default': True,
                    'priority': 1,
                    'config': provider_data['config']
                }
            )

            if created:
                self.stdout.write(f'Создан провайдер: {provider.name}')

    def create_templates(self):
        templates_data = [
            {
                'name': 'Добро пожаловать',
                'template_type': 'welcome',
                'subject': 'Добро пожаловать в NotifyChain, {{ user.first_name }}!',
                'body': '''
Привет {{ user.first_name }}!

Добро пожаловать в NotifyChain - нашу систему уведомлений.

Ваши данные:
- Email: {{ user.email }}
- Дата регистрации: {{ registration_date }}

С уважением,
Команда NotifyChain
'''.strip()
            },
            {
                'name': 'Напоминание о задаче',
                'template_type': 'reminder',
                'subject': 'Напоминание: {{ task_title }}',
                'body': '''
Привет {{ user.first_name }}!

Напоминаем о вашей задаче:

Название: {{ task_title }}
Дедлайн: {{ deadline }}
Описание: {{ task_description }}

Не забудьте выполнить её вовремя!

С уважением,
NotifyChain
'''.strip()
            },
            {
                'name': 'Уведомление о новом сообщении',
                'template_type': 'message',
                'subject': 'Новое сообщение от {{ sender_name }}',
                'body': '''
У вас новое сообщение!

От: {{ sender_name }}
Тема: {{ message_subject }}
Сообщение: {{ message_text }}

Время: {{ sent_at }}
'''.strip()
            }
        ]

        for template_data in templates_data:
            template, created = NotificationTemplate.objects.get_or_create(
                name=template_data['name'],
                defaults=template_data
            )

            if created:
                self.stdout.write(f'Создан шаблон: {template.name}')

    def create_notifications(self):
        users = User.objects.exclude(is_superuser=True)
        welcome_template = NotificationTemplate.objects.get(name='Добро пожаловать')
        reminder_template = NotificationTemplate.objects.get(name='Напоминание о задаче')

        for user in users:
            # Приветственное уведомление
            Notification.objects.create(
                recipient=user,
                template=welcome_template,
                channel='email',
                subject=f'Добро пожаловать в NotifyChain, {user.first_name}!',
                message='Добро пожаловать в нашу систему уведомлений!',
                recipient_address=user.email,
                priority='normal',
                status='pending',
                context_data={
                    'user': {
                        'first_name': user.first_name,
                        'email': user.email
                    },
                    'registration_date': timezone.now().strftime('%d.%m.%Y')
                }
            )

            # Напоминание (запланировано на завтра)
            tomorrow = timezone.now() + timedelta(days=1)
            Notification.objects.create(
                recipient=user,
                template=reminder_template,
                channel='sms',
                subject='Напоминание о встрече',
                message='У вас запланирована встрече завтра в 15:00',
                recipient_address=user.profile.phone_number,
                priority='high',
                status='pending',
                scheduled_at=tomorrow,
                context_data={
                    'user': {
                        'first_name': user.first_name
                    },
                    'task_title': 'Встреча с командой',
                    'deadline': tomorrow.strftime('%d.%m.%Y %H:%M'),
                    'task_description': 'Обсуждение планов на следующую неделю'
                }
            )

            # Push уведомление (готово к отправке)
            Notification.objects.create(
                recipient=user,
                channel='push',
                subject='Добро пожаловать!',
                message='Спасибо за регистрацию в NotifyChain',
                recipient_address=user.profile.push_token,
                priority='normal',
                status='pending'
            )

        self.stdout.write(f'Создано {Notification.objects.count()} уведомлений')