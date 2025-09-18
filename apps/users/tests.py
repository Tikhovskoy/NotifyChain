from django.test import TestCase
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com'
        )

    def test_profile_creation(self):
        profile = UserProfile.objects.create(
            user=self.user,
            phone_number='+79991234567',
            timezone='Europe/Moscow'
        )
        self.assertEqual(profile.user, self.user)
        self.assertEqual(profile.phone_number, '+79991234567')
        self.assertEqual(profile.timezone, 'Europe/Moscow')

    def test_profile_str_method(self):
        profile = UserProfile.objects.create(
            user=self.user,
            phone_number='+79991234567'
        )
        self.assertEqual(str(profile), f'Profile of {self.user.username}')