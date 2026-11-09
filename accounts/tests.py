from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

User = get_user_model()
from core.models import Season

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
        self.client = Client()
        self.user = User.objects.create_user(
            username='officer1',
            password='Password123!',
            role=User.RoleChoices.ASC_OFFICER,
            must_change_password=False
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

    def test_forced_password_change_flow(self):
        """Verify officer with must_change_password=True is redirected to force-change upon login."""
        self.user.must_change_password = True
        self.user.save()

        # Login
        response = self.client.post(reverse('login'), {
            'username': 'officer1',
            'password': 'Password123!'
        })
        self.assertRedirects(response, reverse('force_password_change'))

        # Submit compliant new password
        post_response = self.client.post(reverse('force_password_change'), {
            'new_password': 'NewSecurePassword2026!',
            'confirm_password': 'NewSecurePassword2026!'
        })
        self.assertRedirects(post_response, reverse('dashboard'))
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertTrue(self.user.check_password('NewSecurePassword2026!'))

    def test_deactivated_user_blocked_from_login(self):
        """Verify that a deactivated officer cannot log in."""
        self.user.is_active = False
        self.user.save()

        response = self.client.post(reverse('login'), {
            'username': 'officer1',
            'password': 'Password123!'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "deactivated")

    def test_inactive_account_blocked_from_login(self):
        """Verify that an inactive farmer (unverified OTP) is redirected to activate."""
        farmer_user = User.objects.create_user(
            username='farmer_unverified',
            password='Password123!',
            role=User.RoleChoices.FARMER,
            is_account_active=False
        )
        response = self.client.post(reverse('login'), {
            'username': 'farmer_unverified',
            'password': 'Password123!'
        })
        self.assertRedirects(response, reverse('activate_account'))


class FarmerActivationOTPTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.farmer_user = User.objects.create_user(
            username='198512345678',
            password='InitialPassword123!',
            role=User.RoleChoices.FARMER,
            is_account_active=False
        )
        from farmers.models import Farmer
        self.farmer = Farmer.objects.create(
            user=self.farmer_user,
            full_name="M. Sivapalan",
            nic_number="198512345678",
            mobile_number="0771234567"
        )

    def test_generic_response_for_unknown_nic(self):
        """Unknown NIC must return the exact same generic message to prevent user enumeration."""
        response = self.client.post(reverse('activate_account'), {
            'action': 'send_otp',
            'nic': '999999999999'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If this National Identity Card (NIC) is registered")

    def test_otp_rate_limiting_and_60s_cooldown(self):
        """Verify 60s cooldown between requests and max 3 requests per hour."""
        from accounts.models import PasswordResetOTP
        from django.core.exceptions import ValidationError

        # 1st OTP succeeds
        otp1 = PasswordResetOTP.generate_otp(self.farmer_user)
        self.assertEqual(len(otp1), 6)

        # Immediate 2nd attempt fails due to 60s cooldown
        with self.assertRaises(ValidationError) as cm:
            PasswordResetOTP.generate_otp(self.farmer_user)
        self.assertIn("Please wait", str(cm.exception))

        # Fast forward created_at by 65 seconds
        first_otp_record = PasswordResetOTP.objects.get(user=self.farmer_user, is_used=False)
        first_otp_record.created_at = timezone.now() - timedelta(seconds=65)
        first_otp_record.save(update_fields=['created_at'])

        # 2nd OTP succeeds
        otp2 = PasswordResetOTP.generate_otp(self.farmer_user)
        self.assertEqual(len(otp2), 6)

        # Fast forward 2nd OTP
        second_otp_record = PasswordResetOTP.objects.filter(user=self.farmer_user).order_by('-created_at').first()
        second_otp_record.created_at = timezone.now() - timedelta(seconds=65)
        second_otp_record.save(update_fields=['created_at'])

        # 3rd OTP succeeds
        otp3 = PasswordResetOTP.generate_otp(self.farmer_user)
        self.assertEqual(len(otp3), 6)

        # Fast forward 3rd OTP
        third_otp_record = PasswordResetOTP.objects.filter(user=self.farmer_user).order_by('-created_at').first()
        third_otp_record.created_at = timezone.now() - timedelta(seconds=65)
        third_otp_record.save(update_fields=['created_at'])

        # 4th OTP within 1 hour fails (Max 3 per hour limit)
        with self.assertRaises(ValidationError) as cm2:
            PasswordResetOTP.generate_otp(self.farmer_user)
        self.assertIn("Rate limit exceeded", str(cm2.exception))

    def test_otp_lock_after_5_failed_attempts(self):
        """Verify OTP is invalidated and locked after 5 consecutive incorrect attempts."""
        from accounts.models import PasswordResetOTP

        raw_otp = PasswordResetOTP.generate_otp(self.farmer_user)
        otp_record = PasswordResetOTP.objects.get(user=self.farmer_user, is_used=False)

        # 4 wrong attempts
        for _ in range(4):
            self.assertFalse(otp_record.verify_entered_otp("000000"))
            self.assertFalse(otp_record.is_used)

        # 5th wrong attempt locks it
        self.assertFalse(otp_record.verify_entered_otp("000000"))
        self.assertTrue(otp_record.is_used)
        self.assertFalse(otp_record.is_valid())


class AdminOfficerManagementTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username='system_admin',
            password='AdminPassword123!',
            email='admin@fertitracker.lk',
            role=User.RoleChoices.ADMIN
        )
        self.regular_officer = User.objects.create_user(
            username='regular_officer',
            password='Password123!',
            role=User.RoleChoices.ASC_OFFICER
        )

    def test_non_admin_forbidden_from_officer_management(self):
        """Regular officer is denied access (HTTP 403) to admin officer creation endpoint."""
        self.client.force_login(self.regular_officer)
        response = self.client.get(reverse('admin_officers'))
        self.assertEqual(response.status_code, 403)

    def test_admin_creates_officer_with_temp_password(self):
        """Admin can create new officers with temporary passwords and must_change_password=True."""
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse('admin_officers'), {
            'action': 'create_officer',
            'username': 'new_wh_officer',
            'first_name': 'Kamal',
            'last_name': 'Perera',
            'email': 'kamal@port.lk',
            'role': User.RoleChoices.WAREHOUSE_OFFICER
        }, follow=True)
        self.assertEqual(response.status_code, 200)

        created_officer = User.objects.filter(username='new_wh_officer').first()
        self.assertIsNotNone(created_officer)
        self.assertTrue(created_officer.must_change_password)
        self.assertEqual(created_officer.role, User.RoleChoices.WAREHOUSE_OFFICER)

    def test_admin_toggles_officer_status(self):
        """Admin can deactivate and reactivate officers without deleting records."""
        self.client.force_login(self.admin_user)
        self.assertTrue(self.regular_officer.is_active)

        # Deactivate
        self.client.post(reverse('admin_officers'), {
            'action': 'toggle_status',
            'officer_id': self.regular_officer.id
        })
        self.regular_officer.refresh_from_db()
        self.assertFalse(self.regular_officer.is_active)

        # Reactivate
        self.client.post(reverse('admin_officers'), {
            'action': 'toggle_status',
            'officer_id': self.regular_officer.id
        })
        self.regular_officer.refresh_from_db()
        self.assertTrue(self.regular_officer.is_active)


class SeasonInvariantTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            username='admin_season',
            password='AdminPassword123!',
            role=User.RoleChoices.ADMIN
        )
        self.season1 = Season.objects.create(
            name="Maha 2026/2027",
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=180),
            status=Season.StstusChoices.ACTIVE
        )
        self.season2 = Season.objects.create(
            name="Yala 2027",
            start_date=timezone.localdate() + timedelta(days=181),
            end_date=timezone.localdate() + timedelta(days=360),
            status=Season.StstusChoices.CLOSED
        )

    def test_single_active_season_invariant(self):
        """When Season 2 is activated, Season 1 must automatically transition to CLOSED."""
        self.client.force_login(self.admin)

        # Toggle Season 2 to ACTIVE
        self.client.post(reverse('toggle_season_status', kwargs={'season_id': self.season2.id}))
        self.season1.refresh_from_db()
        self.season2.refresh_from_db()

        self.assertEqual(self.season2.status, 'ACTIVE')
        self.assertEqual(self.season1.status, 'CLOSED')
        self.assertEqual(Season.objects.filter(status='ACTIVE').count(), 1)

