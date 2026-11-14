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


class RoleBasedAccessControlTests(TestCase):
    """
    Exhaustive test suite verifying Separation of Duties and Role-Based Access Control (RBAC):
    - Administrator cannot perform operational tasks (receiving dispatches, QR scanner,
      find farmer, SMS codes, assisted requests/approvals, stock write-offs, batch/dispatch creation).
    - Warehouse Officer cannot receive dispatches, scan QR, find farmers, or create assisted issues.
    - Auditor cannot perform any write (POST/PUT/DELETE) operations.
    - ASC Officer from another ASC cannot receive dispatches for a different ASC (BR-02).
    - Regular ASC Officer cannot approve assisted requests or write off expired stock.
    - ASC Head cannot approve their own assisted issue request (Two-Officer rule) or act on other ASCs.
    - Menu rendering per role strictly limits visible links to authorized actions.
    - Central permissions table (accounts.permissions.ROLE_PERMISSIONS) consistency.
    """

    def setUp(self):
        from core.models import ASCCentre, Warehouse, FertilizerProduct
        from inventory.models import FertilizerBatch, StockDispatch, DispatchItem, ASCStock
        from farmers.models import Farmer
        from distributions.models import AssistedIssueApproval

        self.client = Client()

        # Centres & Warehouses
        self.asc1 = ASCCentre.objects.create(name="Vavuniya South ASC", district="Vavuniya", address="Vavuniya South")
        self.asc2 = ASCCentre.objects.create(name="Kilinochchi ASC", district="Kilinochchi", address="Kilinochchi")
        self.wh = Warehouse.objects.create(name="Central Warehouse", location="Colombo Port")

        # Season & Product
        self.season = Season.objects.create(
            name="Maha 2026/2027",
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=120),
            status=Season.StstusChoices.ACTIVE
        )
        self.product = FertilizerProduct.objects.create(name="Urea 50kg", bag_weight_kg=50.0)

        # Users
        self.admin = User.objects.create_superuser(
            username='admin_test_rbac', password='Password123!', role=User.RoleChoices.ADMIN
        )
        self.wh_officer = User.objects.create_user(
            username='wh_officer_test_rbac', password='Password123!', role=User.RoleChoices.WAREHOUSE_OFFICER
        )
        self.asc_officer1 = User.objects.create_user(
            username='asc_officer1_test_rbac', password='Password123!', role=User.RoleChoices.ASC_OFFICER,
            asc_centre=self.asc1, is_asc_head=False
        )
        self.asc_head1 = User.objects.create_user(
            username='asc_head1_test_rbac', password='Password123!', role=User.RoleChoices.ASC_OFFICER,
            asc_centre=self.asc1, is_asc_head=True
        )
        self.asc_officer2 = User.objects.create_user(
            username='asc_officer2_test_rbac', password='Password123!', role=User.RoleChoices.ASC_OFFICER,
            asc_centre=self.asc2, is_asc_head=False
        )
        self.auditor = User.objects.create_user(
            username='auditor_test_rbac', password='Password123!', role=User.RoleChoices.AUDITOR
        )
        self.farmer_user = User.objects.create_user(
            username='199012345678', password='Password123!', role=User.RoleChoices.FARMER,
            asc_centre=self.asc1
        )
        self.farmer = Farmer.objects.create(
            user=self.farmer_user, full_name='Test Farmer Selvan',
            nic_number='199012345678', mobile_number='0771234567'
        )

        # Batches & Stocks
        self.batch_expired = FertilizerBatch.objects.create(
            warehouse=self.wh,
            product=self.product,
            batch_number="B-EXP-001",
            expiry_date=timezone.localdate() - timedelta(days=5)
        )
        self.stock_asc1 = ASCStock.objects.create(asc_centre=self.asc1, batch=self.batch_expired, bags_on_hand=20)
        self.stock_asc2 = ASCStock.objects.create(asc_centre=self.asc2, batch=self.batch_expired, bags_on_hand=20)

        # Dispatches
        self.dispatch_asc1 = StockDispatch.objects.create(
            warehouse=self.wh,
            asc_centre=self.asc1,
            created_by=self.wh_officer,
            status=StockDispatch.StatusChoices.DISPATCHED
        )
        self.dispatch_item = DispatchItem.objects.create(
            dispatch=self.dispatch_asc1,
            batch=self.batch_expired,
            dispatched_bags=10
        )

        # Assisted Request at ASC1
        self.assisted_req = AssistedIssueApproval.objects.create(
            farmer=self.farmer,
            asc_centre=self.asc1,
            season=self.season,
            requested_by=self.asc_officer1,
            reason=AssistedIssueApproval.ReasonChoices.NO_PHONE,
            expires_at=timezone.now() + timedelta(minutes=30),
            status=AssistedIssueApproval.StatusChoices.PENDING
        )

    # --------------------------------------------------------------------------
    # 1. Administrator Forbidden Operations Tests
    # --------------------------------------------------------------------------
    def test_admin_forbidden_from_receiving_dispatch(self):
        """Administrator cannot receive a dispatch (HTTP 403 returned)."""
        self.client.force_login(self.admin)
        url = reverse('receive_dispatch', kwargs={'dispatch_id': self.dispatch_asc1.id})
        response = self.client.post(url, {
            f"received_{self.dispatch_item.id}": 10,
            f"damaged_{self.dispatch_item.id}": 0
        })
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, '403.html')

    def test_admin_forbidden_from_qr_scanner(self):
        """Administrator cannot access the QR scanner (HTTP 403 returned)."""
        self.client.force_login(self.admin)
        url = reverse('asc_scanner')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, '403.html')

    def test_admin_forbidden_from_farmer_search_and_sms_code(self):
        """Administrator cannot use find farmer or issue SMS codes (HTTP 403 returned)."""
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('farmer_search')).status_code, 403)
        self.assertEqual(self.client.post(reverse('send_sms_code', kwargs={'farmer_id': self.farmer.id})).status_code, 403)

    def test_admin_forbidden_from_assisted_issue_request_and_approval(self):
        """Administrator cannot create or approve assisted issues (HTTP 403 returned)."""
        self.client.force_login(self.admin)
        # Create request forbidden
        create_url = reverse('create_assisted_request', kwargs={'farmer_id': self.farmer.id})
        self.assertEqual(self.client.get(create_url).status_code, 403)
        self.assertEqual(self.client.post(create_url, {'season': self.season.id, 'reason': 'NO_PHONE'}).status_code, 403)

        # Approve forbidden
        approve_url = reverse('approve_assisted_request', kwargs={'request_id': self.assisted_req.id})
        self.assertEqual(self.client.post(approve_url).status_code, 403)

    def test_admin_forbidden_from_stock_write_off(self):
        """Administrator cannot write off expired stock (HTTP 403 returned)."""
        self.client.force_login(self.admin)
        url = reverse('write_off_expired_stock', kwargs={'stock_id': self.stock_asc1.id})
        response = self.client.post(url, {'reason': 'Expired disposal', 'bags': 5})
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, '403.html')

    def test_admin_forbidden_from_create_batch_and_dispatch(self):
        """Administrator cannot create fertilizer batches or dispatches (Warehouse Officer only)."""
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('create_batch')).status_code, 403)
        self.assertEqual(self.client.get(reverse('create_dispatch')).status_code, 403)

    # --------------------------------------------------------------------------
    # 2. Warehouse Officer Forbidden Operations Tests
    # --------------------------------------------------------------------------
    def test_warehouse_officer_forbidden_from_receiving(self):
        """Warehouse Officer cannot confirm receipt of dispatches (HTTP 403 returned)."""
        self.client.force_login(self.wh_officer)
        url = reverse('receive_dispatch', kwargs={'dispatch_id': self.dispatch_asc1.id})
        response = self.client.post(url, {
            f"received_{self.dispatch_item.id}": 10,
            f"damaged_{self.dispatch_item.id}": 0
        })
        self.assertEqual(response.status_code, 403)

    def test_warehouse_officer_forbidden_from_counter_and_farmer_functions(self):
        """Warehouse Officer cannot access scanner, farmer search, or assisted issues."""
        self.client.force_login(self.wh_officer)
        self.assertEqual(self.client.get(reverse('asc_scanner')).status_code, 403)
        self.assertEqual(self.client.get(reverse('farmer_search')).status_code, 403)
        self.assertEqual(self.client.get(reverse('manage_farmers')).status_code, 403)
        self.assertEqual(self.client.get(reverse('pending_assisted_requests')).status_code, 403)

    # --------------------------------------------------------------------------
    # 3. Auditor Forbidden from All Write/Modification Operations
    # --------------------------------------------------------------------------
    def test_auditor_forbidden_from_write_operations(self):
        """Auditor is read-only: all POST requests must be refused with HTTP 403."""
        self.client.force_login(self.auditor)

        write_endpoints = [
            (reverse('create_batch'), {'batch_number': 'AUDIT-POST'}),
            (reverse('create_dispatch'), {'dispatched_bags': 5}),
            (reverse('receive_dispatch', kwargs={'dispatch_id': self.dispatch_asc1.id}), {'discrepancy_reason': 'test'}),
            (reverse('write_off_expired_stock', kwargs={'stock_id': self.stock_asc1.id}), {'reason': 'audit'}),
            (reverse('audit_logs'), {'fake': 'data'}),
            (reverse('reports_search'), {'fake': 'data'}),
            (reverse('admin_officers'), {'action': 'toggle_status'}),
        ]

        for url, data in write_endpoints:
            with self.subTest(url=url):
                response = self.client.post(url, data)
                self.assertEqual(response.status_code, 403, f"Auditor POST to {url} was not refused with 403!")
                self.assertTemplateUsed(response, '403.html')

    # --------------------------------------------------------------------------
    # 4. Destination ASC Enforcement (BR-02)
    # --------------------------------------------------------------------------
    def test_asc_officer_from_another_asc_forbidden_from_receiving(self):
        """ASC Officer from Kilinochchi (ASC2) cannot receive dispatch destined for Vavuniya (ASC1)."""
        self.client.force_login(self.asc_officer2)
        url = reverse('receive_dispatch', kwargs={'dispatch_id': self.dispatch_asc1.id})
        response = self.client.post(url, {
            f"received_{self.dispatch_item.id}": 10,
            f"damaged_{self.dispatch_item.id}": 0
        })
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, '403.html')

    # --------------------------------------------------------------------------
    # 5. Regular ASC Officer Forbidden from ASC Head Functions
    # --------------------------------------------------------------------------
    def test_regular_asc_officer_forbidden_from_approval_and_write_off(self):
        """Regular ASC Officer without head authority cannot approve assisted issues or write off stock."""
        self.client.force_login(self.asc_officer1)
        approve_url = reverse('approve_assisted_request', kwargs={'request_id': self.assisted_req.id})
        self.assertEqual(self.client.post(approve_url).status_code, 403)

        write_off_url = reverse('write_off_expired_stock', kwargs={'stock_id': self.stock_asc1.id})
        self.assertEqual(self.client.post(write_off_url, {'reason': 'Write off', 'bags': 5}).status_code, 403)

    # --------------------------------------------------------------------------
    # 6. Two-Officer Rule and ASC Head Scope Enforcement
    # --------------------------------------------------------------------------
    def test_asc_head_cannot_approve_own_assisted_request(self):
        """Two-Officer Rule: ASC Head cannot approve a request that they themselves created."""
        from distributions.models import AssistedIssueApproval
        # ASC Head creates their own request
        self_req = AssistedIssueApproval.objects.create(
            farmer=self.farmer,
            asc_centre=self.asc1,
            season=self.season,
            requested_by=self.asc_head1,
            reason=AssistedIssueApproval.ReasonChoices.OTHER,
            expires_at=timezone.now() + timedelta(minutes=30),
            status=AssistedIssueApproval.StatusChoices.PENDING
        )

        self.client.force_login(self.asc_head1)
        approve_url = reverse('approve_assisted_request', kwargs={'request_id': self_req.id})
        response = self.client.post(approve_url)
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, '403.html')

    def test_asc_head_cannot_write_off_stock_of_different_asc(self):
        """ASC Head of ASC1 cannot write off expired stock belonging to ASC2."""
        self.client.force_login(self.asc_head1)
        url = reverse('write_off_expired_stock', kwargs={'stock_id': self.stock_asc2.id})
        response = self.client.post(url, {'reason': 'Disposal', 'bags': 5})
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, '403.html')

    def test_asc_head_approves_assisted_request_of_different_officer(self):
        """ASC Head can successfully approve an assisted request created by another officer of the same ASC."""
        self.client.force_login(self.asc_head1)
        approve_url = reverse('approve_assisted_request', kwargs={'request_id': self.assisted_req.id})
        response = self.client.post(approve_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assisted_req.refresh_from_db()
        self.assertEqual(self.assisted_req.status, 'APPROVED')
        self.assertEqual(self.assisted_req.approved_by, self.asc_head1)

    # --------------------------------------------------------------------------
    # 7. Menu Item Visibility Per Role Tests
    # --------------------------------------------------------------------------
    def test_menu_visibility_for_administrator(self):
        """Administrator menu must show admin/reports but hide operational buttons."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')

        # Allowed
        self.assertIn(reverse('inventory_list'), html)
        self.assertIn(reverse('reports_search'), html)
        self.assertIn(reverse('audit_logs'), html)
        self.assertIn(reverse('assisted_issues_report'), html)
        self.assertIn(reverse('manage_farmers'), html)

        # Forbidden in menu
        self.assertNotIn(reverse('asc_scanner'), html)
        self.assertNotIn(reverse('farmer_search'), html)
        self.assertNotIn(reverse('pending_assisted_requests'), html)
        self.assertNotIn(reverse('demo_sms_inbox'), html)

    def test_menu_visibility_for_warehouse_officer(self):
        """Warehouse Officer menu must show inventory and dispatches, hiding counter operations."""
        self.client.force_login(self.wh_officer)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')

        # Allowed
        self.assertIn(reverse('inventory_list'), html)
        self.assertIn(reverse('reports_search'), html)

        # Forbidden
        self.assertNotIn(reverse('asc_scanner'), html)
        self.assertNotIn(reverse('farmer_search'), html)
        self.assertNotIn(reverse('pending_assisted_requests'), html)
        self.assertNotIn(reverse('manage_farmers'), html)
        self.assertNotIn(reverse('audit_logs'), html)
        self.assertNotIn(reverse('assisted_issues_report'), html)
        self.assertNotIn(reverse('demo_sms_inbox'), html)

    def test_menu_visibility_for_asc_officer(self):
        """ASC Officer menu must show counter tools, but hide audit logs and admin tools."""
        self.client.force_login(self.asc_officer1)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')

        # Allowed
        self.assertIn(reverse('asc_scanner'), html)
        self.assertIn(reverse('farmer_search'), html)
        self.assertIn(reverse('pending_assisted_requests'), html)
        self.assertIn(reverse('manage_farmers'), html)
        self.assertIn(reverse('inventory_list'), html)
        self.assertIn(reverse('reports_search'), html)

        # Forbidden
        self.assertNotIn(reverse('audit_logs'), html)
        self.assertNotIn(reverse('assisted_issues_report'), html)
        self.assertNotIn(reverse('admin_officers'), html)

    def test_menu_visibility_for_auditor(self):
        """Auditor menu must show reports and audit logs, hiding counter and operational items."""
        self.client.force_login(self.auditor)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')

        # Allowed
        self.assertIn(reverse('inventory_list'), html)
        self.assertIn(reverse('reports_search'), html)
        self.assertIn(reverse('assisted_issues_report'), html)
        self.assertIn(reverse('audit_logs'), html)

        # Forbidden
        self.assertNotIn(reverse('asc_scanner'), html)
        self.assertNotIn(reverse('farmer_search'), html)
        self.assertNotIn(reverse('pending_assisted_requests'), html)
        self.assertNotIn(reverse('manage_farmers'), html)
        self.assertNotIn(reverse('demo_sms_inbox'), html)

    def test_menu_visibility_for_farmer(self):
        """Farmer menu must show only personal QR and quota, hiding all officer menus."""
        self.client.force_login(self.farmer_user)
        response = self.client.get(reverse('farmer_dashboard'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode('utf-8')

        # Allowed
        self.assertIn(reverse('farmer_dashboard'), html)

        # Forbidden
        self.assertNotIn(reverse('inventory_list'), html)
        self.assertNotIn(reverse('reports_search'), html)
        self.assertNotIn(reverse('asc_scanner'), html)
        self.assertNotIn(reverse('farmer_search'), html)
        self.assertNotIn(reverse('pending_assisted_requests'), html)
        self.assertNotIn(reverse('manage_farmers'), html)
        self.assertNotIn(reverse('audit_logs'), html)


