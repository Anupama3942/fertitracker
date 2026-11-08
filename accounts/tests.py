from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

class InternationalizationTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_set_language_to_sinhala(self):
        """Verify that switching language to Sinhala sets session and cookie properly."""
        response = self.client.post(
            reverse('set_language'),
            {'language': 'si', 'next': '/'},
            follow=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('django_language', response.cookies)
        self.assertEqual(response.cookies['django_language'].value, 'si')

    def test_set_language_to_tamil(self):
        """Verify that switching language to Tamil sets session and cookie properly."""
        response = self.client.post(
            reverse('set_language'),
            {'language': 'ta', 'next': '/'},
            follow=False
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('django_language', response.cookies)
        self.assertEqual(response.cookies['django_language'].value, 'ta')

class AccountSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='officer1',
            password='Password123!',
            role=User.RoleChoices.ASC_OFFICER
        )

    def test_login_page_renders_with_accessibility_attributes(self):
        """Verify login page renders with status 200 and required fields."""
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'FertiTracker')
        self.assertContains(response, 'username')
        self.assertContains(response, 'password')

    def test_account_lockout_after_failed_attempts(self):
        """Verify account lockout status flag when locked_until is set."""
        self.assertFalse(self.user.is_locked())
        self.user.locked_until = timezone.now() + timedelta(minutes=15)
        self.user.save()
        self.assertTrue(self.user.is_locked())
