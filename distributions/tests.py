import gettext
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.models import ASCCentre, Warehouse, Season, FertilizerProduct
from inventory.models import FertilizerBatch, ASCStock, StockMovement
from farmers.models import Farmer, FarmerEntitlement, QRToken, compute_code_hmac
from distributions.models import FertilizerDistribution, AuditLog, AssistedIssueApproval, SMSOutbox
from distributions.services import process_qr_distribution, verify_farmer_token, confirm_issue_distribution


User = get_user_model()

class QRDistributionWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Master Data
        self.asc = ASCCentre.objects.create(
            name="Vavuniya South ASC",
            district="Vavuniya",
            address="Kandy Road, Vavuniya"
        )
        self.warehouse = Warehouse.objects.create(
            name="Central Fertilizer Warehouse",
            location="Colombo Port"
        )
        self.season = Season.objects.create(
            name="Maha 2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 3, 31),
            status=Season.StstusChoices.ACTIVE
        )
        self.product = FertilizerProduct.objects.create(
            name="Urea",
            bag_weight_kg=Decimal("50.00")
        )

        # 2. Officer User
        self.officer = User.objects.create_user(
            username="asc_officer1",
            password="Password123!",
            role=User.RoleChoices.ASC_OFFICER,
            asc_centre=self.asc
        )

        # 3. Farmer & Entitlement
        self.farmer_user = User.objects.create_user(
            username="farmer1",
            password="Password123!",
            role=User.RoleChoices.FARMER
        )
        self.farmer = Farmer.objects.create(
            user=self.farmer_user,
            full_name="K. Ramanathan",
            nic_number="198512345678",
            mobile_number="0771234567",
            arpa_division="Vavuniya South"
        )
        self.entitlement = FarmerEntitlement.objects.create(
            farmer=self.farmer,
            season=self.season,
            product=self.product,
            approved_kg=Decimal("200.00"),
            remaining_kg=Decimal("200.00")
        )

        # 4. Inventory / FEFO Stock
        self.batch = FertilizerBatch.objects.create(
            warehouse=self.warehouse,
            product=self.product,
            batch_number="BATCH-UREA-2026-A",
            expiry_date=date(2027, 12, 31)
        )
        self.stock = ASCStock.objects.create(
            asc_centre=self.asc,
            batch=self.batch,
            bags_on_hand=50
        )

    def test_scanner_page_loads_for_asc_officer(self):
        """Verify ASC officer can access the scanner page."""
        self.client.login(username="asc_officer1", password="Password123!")
        response = self.client.get(reverse('asc_scanner'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "html5-qrcode")
        self.assertContains(response, "Vavuniya South ASC")

    def test_verify_step_does_not_consume_token(self):
        """Fix A: Verify step validates farmer and quota but does NOT redeem token."""
        raw_token, raw_code, qr_obj = QRToken.generate_token_for_farmer(self.farmer)

        self.client.login(username="asc_officer1", password="Password123!")
        response = self.client.post(reverse('asc_scanner'), {
            'action': 'verify',
            'token_string': raw_token,
            'season': self.season.id
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Step 2: Confirm Farmer & Issue Details")
        self.assertContains(response, self.farmer.full_name)

        # Token is STILL NOT REDEEMED
        qr_obj.refresh_from_db()
        self.assertFalse(qr_obj.is_redeemed)

        # Quota and stock are UNTOUCHED
        self.entitlement.refresh_from_db()
        self.assertEqual(self.entitlement.remaining_kg, Decimal("200.00"))
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.bags_on_hand, 50)

    def test_confirm_step_consumes_token_and_deducts_stock(self):
        """Fix A: Confirm step executes atomic transaction, consumes token and issues receipt."""
        raw_token, raw_code, qr_obj = QRToken.generate_token_for_farmer(self.farmer)

        self.client.login(username="asc_officer1", password="Password123!")
        response = self.client.post(reverse('asc_scanner'), {
            'action': 'confirm',
            'token_string': raw_token,
            'season': self.season.id,
            'quantity_kg': '50.00'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Distribution Successful!")

        # Token IS REDEEMED
        qr_obj.refresh_from_db()
        self.assertTrue(qr_obj.is_redeemed)

        # Entitlement and stock deducted
        self.entitlement.refresh_from_db()
        self.assertEqual(self.entitlement.remaining_kg, Decimal("150.00"))
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.bags_on_hand, 49)

    def test_6_digit_backup_code_works_identically(self):
        """Fix C: 6-digit backup code verifies and issues properly."""
        raw_token, raw_code, qr_obj = QRToken.generate_token_for_farmer(self.farmer)

        self.client.login(username="asc_officer1", password="Password123!")
        # 1. Verify with 6-digit code
        resp1 = self.client.post(reverse('asc_scanner'), {
            'action': 'verify',
            'token_string': raw_code,
            'season': self.season.id
        })
        self.assertEqual(resp1.status_code, 200)
        self.assertContains(resp1, self.farmer.full_name)

        # 2. Confirm with 6-digit code
        resp2 = self.client.post(reverse('asc_scanner'), {
            'action': 'confirm',
            'token_string': raw_code,
            'season': self.season.id,
            'quantity_kg': '50.00'
        })
        self.assertEqual(resp2.status_code, 200)
        self.assertContains(resp2, "Distribution Successful!")

    def test_replay_attack_prevention(self):
        """Verify that reusing an already redeemed token is strictly rejected."""
        raw_token, raw_code, qr_obj = QRToken.generate_token_for_farmer(self.farmer)

        # First issue succeeds
        process_qr_distribution(raw_token, self.officer, self.season.id)

        # Second issue with identical token must be rejected
        self.client.login(username="asc_officer1", password="Password123!")
        response = self.client.post(reverse('asc_scanner'), {
            'action': 'verify',
            'token_string': raw_token,
            'season': self.season.id
        })
        self.assertContains(response, "already been used or has been invalidated")

    def test_expired_token_is_rejected(self):
        """Verify token older than 60 seconds is rejected."""
        raw_token, raw_code, qr_obj = QRToken.generate_token_for_farmer(self.farmer)
        # Manually expire token
        qr_obj.expires_at = timezone.now() - timedelta(seconds=10)
        qr_obj.save()

        self.client.login(username="asc_officer1", password="Password123!")
        response = self.client.post(reverse('asc_scanner'), {
            'action': 'verify',
            'token_string': raw_token,
            'season': self.season.id
        })
        self.assertContains(response, "verification code has expired")


    def test_i18n_mo_roundtrip(self):
        """Bug 1: Verify .mo binary catalog correctly loads pristine Sinhala and Tamil strings without mojibake."""
        t_si = gettext.translation('django', localedir='locale', languages=['si'])
        t_ta = gettext.translation('django', localedir='locale', languages=['ta'])

        self.assertEqual(t_si.gettext("Login"), "ඇතුල් වන්න")
        self.assertEqual(t_ta.gettext("Login"), "உள்நுழைக")
        self.assertEqual(t_si.gettext("My QR & Quota"), "මගේ QR කේතය සහ හිමිකම")
        self.assertEqual(t_ta.gettext("My QR & Quota"), "எனது QR & உரிமை அளவு")


# ==============================================================================
# PART 0: HARDENING & SECURITY UNIT TESTS
# ==============================================================================

class HardeningAndSecurityTests(TestCase):
    def setUp(self):
        self.asc = ASCCentre.objects.create(name="Vavuniya South ASC", district="Vavuniya", address="Kandy Rd")
        self.asc2 = ASCCentre.objects.create(name="Cheddikulam ASC", district="Vavuniya", address="Mannar Rd")
        self.farmer_user = User.objects.create_user(username="farmer_h1", password="Password123!", role=User.RoleChoices.FARMER)
        self.farmer = Farmer.objects.create(
            user=self.farmer_user, full_name="S. Perera",
            nic_number="199011112222", mobile_number="0779876543"
        )
        self.officer = User.objects.create_user(
            username="security_officer", password="Password123!",
            role=User.RoleChoices.ASC_OFFICER, asc_centre=self.asc
        )

    def test_hmac_6_digit_code_keyed_hash_cannot_be_plain_sha(self):
        """Hardening 3: 6-digit backup code is stored as HMAC-SHA256, not plain SHA-256."""
        import hashlib
        raw_token, raw_code, qr_token = QRToken.generate_token_for_farmer(self.farmer)

        plain_sha = hashlib.sha256(raw_code.encode()).hexdigest()
        self.assertNotEqual(qr_token.code_hash, plain_sha, "HMAC-keyed hash must not equal plain unkeyed SHA-256.")

        # Re-computing with the server secret must match
        expected_hmac = compute_code_hmac(raw_code)
        self.assertEqual(qr_token.code_hash, expected_hmac)

    def test_officer_lockout_after_5_failed_code_attempts(self):
        """Hardening 4: Max 5 wrong code attempts locks the officer out for 10 minutes and logs audit entry."""
        from distributions.services import get_qr_token_by_input
        from django.core.exceptions import ValidationError

        self.assertFalse(self.officer.is_code_locked())
        self.assertEqual(self.officer.failed_code_attempts, 0)

        # 4 wrong attempts
        for i in range(4):
            with self.assertRaises(ValidationError):
                get_qr_token_by_input("000000", officer=self.officer)

        self.officer.refresh_from_db()
        self.assertEqual(self.officer.failed_code_attempts, 4)
        self.assertFalse(self.officer.is_code_locked())

        # 5th wrong attempt triggers lockout
        with self.assertRaises(ValidationError):
            get_qr_token_by_input("000000", officer=self.officer)

        self.officer.refresh_from_db()
        self.assertEqual(self.officer.failed_code_attempts, 5)
        self.assertTrue(self.officer.is_code_locked())

        # Further attempts are blocked immediately
        with self.assertRaises(ValidationError) as ctx:
            get_qr_token_by_input("111111", officer=self.officer)
        self.assertIn("temporarily locked", str(ctx.exception))

        # AuditLog entry created
        lock_log = AuditLog.objects.filter(user=self.officer, action="OFFICER_CODE_ENTRY_LOCKED").first()
        self.assertIsNotNone(lock_log)

    def test_token_invalidated_after_5_failed_attempts_on_it(self):
        """Hardening 4: Token is invalidated (is_redeemed=True) after 5 failed attempts."""
        raw_token, raw_code, qr_token = QRToken.generate_token_for_farmer(self.farmer)
        self.assertEqual(qr_token.failed_attempts, 0)

        for _ in range(4):
            qr_token.record_failed_attempt()
        qr_token.refresh_from_db()
        self.assertEqual(qr_token.failed_attempts, 4)
        self.assertFalse(qr_token.is_redeemed)

        # 5th failure invalidates token
        qr_token.record_failed_attempt()
        qr_token.refresh_from_db()
        self.assertEqual(qr_token.failed_attempts, 5)
        self.assertTrue(qr_token.is_redeemed)
        self.assertFalse(qr_token.is_valid())

    def test_token_bound_to_specific_asc_cannot_be_redeemed_elsewhere(self):
        """Hardening 4: Code bound to Vavuniya South cannot be redeemed by officer at Cheddikulam ASC."""
        from distributions.services import get_qr_token_by_input
        from django.core.exceptions import ValidationError

        raw_token, raw_code, qr_token = QRToken.generate_token_for_farmer(
            self.farmer, asc_centre=self.asc, channel=QRToken.ChannelChoices.SMS
        )

        other_officer = User.objects.create_user(
            username="cheddikulam_officer", password="Password123!",
            role=User.RoleChoices.ASC_OFFICER, asc_centre=self.asc2
        )

        with self.assertRaises(ValidationError) as ctx:
            get_qr_token_by_input(raw_code, officer=other_officer)
        self.assertIn("cannot be redeemed at 'Cheddikulam ASC'", str(ctx.exception))


# ==============================================================================
# PART 1: SMS BACKUP CODE TESTS
# ==============================================================================

class SMSBackupCodeTests(TestCase):
    def setUp(self):
        self.asc = ASCCentre.objects.create(name="Vavuniya South ASC", district="Vavuniya", address="Kandy Rd")
        self.warehouse = Warehouse.objects.create(name="Central Warehouse", location="Colombo")
        self.season = Season.objects.create(
            name="Maha 2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 3, 31),
            status=Season.StstusChoices.ACTIVE
        )
        self.product = FertilizerProduct.objects.create(name="Urea", bag_weight_kg=Decimal("50.00"))
        self.batch = FertilizerBatch.objects.create(
            warehouse=self.warehouse, product=self.product,
            batch_number="SMS-BATCH-1", expiry_date=date(2027, 12, 31)
        )
        self.stock = ASCStock.objects.create(asc_centre=self.asc, batch=self.batch, bags_on_hand=50)

        self.officer = User.objects.create_user(
            username="sms_officer", password="Password123!",
            role=User.RoleChoices.ASC_OFFICER, asc_centre=self.asc
        )
        self.farmer_user = User.objects.create_user(username="farmer_sms", password="Password123!", role=User.RoleChoices.FARMER)
        self.farmer = Farmer.objects.create(
            user=self.farmer_user, full_name="A. Bandara",
            nic_number="197500001111", mobile_number="0715556677"
        )
        self.entitlement = FarmerEntitlement.objects.create(
            farmer=self.farmer, season=self.season, product=self.product,
            approved_kg=Decimal("100.00"), remaining_kg=Decimal("100.00")
        )

    def test_sms_generation_dispatches_to_outbox_and_logs(self):
        """SMS Part 1: Simulated backend saves to SMSOutbox with code and ASC name."""
        from distributions.services import generate_sms_code_for_farmer
        from distributions.models import SMSOutbox

        raw_token, raw_code, qr_token = generate_sms_code_for_farmer(
            farmer=self.farmer,
            asc_centre=self.asc,
            requested_by_user=self.officer
        )
        self.assertEqual(len(raw_code), 6)
        self.assertTrue(raw_code.isdigit())

        # Outbox entry exists
        msg = SMSOutbox.objects.filter(phone_number="0715556677").first()
        self.assertIsNotNone(msg)
        self.assertIn(raw_code, msg.message)
        self.assertIn(self.asc.name, msg.message)
        self.assertEqual(msg.farmer, self.farmer)

        # AuditLog recorded
        audit = AuditLog.objects.filter(action="SMS_BACKUP_CODE_SENT", user=self.officer).first()
        self.assertIsNotNone(audit)

    def test_sms_rate_limit_cooldown_60_seconds(self):
        """SMS Part 1: Cooldown prevents requesting 2 codes in under 60 seconds."""
        from distributions.services import generate_sms_code_for_farmer
        from django.core.exceptions import ValidationError

        generate_sms_code_for_farmer(self.farmer, self.asc, self.officer)

        with self.assertRaises(ValidationError) as ctx:
            generate_sms_code_for_farmer(self.farmer, self.asc, self.officer)
        self.assertIn("Please wait", str(ctx.exception))

    def test_sms_issue_records_sms_issue_method(self):
        """SMS Part 1: Redeeming an SMS code sets issue_method='SMS_CODE' on FertilizerDistribution."""
        from distributions.services import generate_sms_code_for_farmer

        raw_token, raw_code, qr_token = generate_sms_code_for_farmer(self.farmer, self.asc, self.officer)

        dist = confirm_issue_distribution(
            raw_input_string=raw_code,
            asc_officer_user=self.officer,
            season_id=self.season.id,
            quantity_kg=Decimal("50.00")
        )
        self.assertEqual(dist.issue_method, FertilizerDistribution.IssueMethodChoices.SMS_CODE)
        self.assertEqual(dist.get_issue_method_display(), "SMS Backup Code")


# ==============================================================================
# PART 2: OFFICER-ASSISTED ISSUE TESTS
# ==============================================================================

class AssistedIssueWorkflowTests(TestCase):
    def setUp(self):
        self.asc = ASCCentre.objects.create(name="Vavuniya South ASC", district="Vavuniya", address="Kandy Rd")
        self.asc2 = ASCCentre.objects.create(name="Cheddikulam ASC", district="Vavuniya", address="Mannar Rd")
        self.season = Season.objects.create(
            name="Maha 2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 3, 31),
            status=Season.StstusChoices.ACTIVE
        )
        self.product = FertilizerProduct.objects.create(name="Urea", bag_weight_kg=Decimal("50.00"))
        self.warehouse = Warehouse.objects.create(name="Central Warehouse", location="Colombo")
        self.batch = FertilizerBatch.objects.create(
            warehouse=self.warehouse, product=self.product,
            batch_number="ASSISTED-BATCH-1", expiry_date=date(2027, 12, 31)
        )
        self.stock = ASCStock.objects.create(asc_centre=self.asc, batch=self.batch, bags_on_hand=50)

        # Counter officer who creates request
        self.requester = User.objects.create_user(
            username="counter_officer", password="Password123!",
            role=User.RoleChoices.ASC_OFFICER, asc_centre=self.asc, is_asc_head=False
        )
        # ASC Head who approves
        self.head_officer = User.objects.create_user(
            username="asc_head_user", password="Password123!",
            role=User.RoleChoices.ASC_OFFICER, asc_centre=self.asc, is_asc_head=True
        )
        # Regular officer without Head role
        self.non_head = User.objects.create_user(
            username="non_head_officer", password="Password123!",
            role=User.RoleChoices.ASC_OFFICER, asc_centre=self.asc, is_asc_head=False
        )

        self.farmer = Farmer.objects.create(
            full_name="M. Selvaraj", nic_number="196012349999",
            mobile_number="0770001122", arpa_division="Vavuniya South"
        )
        self.entitlement = FarmerEntitlement.objects.create(
            farmer=self.farmer, season=self.season, product=self.product,
            approved_kg=Decimal("100.00"), remaining_kg=Decimal("100.00")
        )

    def test_assisted_issue_creation_and_mandatory_reason_note(self):
        """Assisted Issue: 'OTHER' requires an explanatory note."""
        from distributions.services import create_assisted_issue_request
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError) as ctx:
            create_assisted_issue_request(
                farmer=self.farmer, asc_centre=self.asc, season=self.season,
                requested_by_user=self.requester,
                reason=AssistedIssueApproval.ReasonChoices.OTHER,
                reason_note=""
            )
        self.assertIn("mandatory when selecting 'Other reason'", str(ctx.exception))

        # Valid with note
        req = create_assisted_issue_request(
            farmer=self.farmer, asc_centre=self.asc, season=self.season,
            requested_by_user=self.requester,
            reason=AssistedIssueApproval.ReasonChoices.OTHER,
            reason_note="Farmer lost phone in flood; physical NIC verified."
        )
        self.assertEqual(req.status, AssistedIssueApproval.StatusChoices.PENDING)

    def test_two_officer_rule_requester_cannot_approve_own_request(self):
        """Assisted Issue: Counter officer CANNOT approve their own request."""
        from distributions.services import create_assisted_issue_request, approve_assisted_issue_request
        from django.core.exceptions import ValidationError

        req = create_assisted_issue_request(
            farmer=self.farmer, asc_centre=self.asc, season=self.season,
            requested_by_user=self.requester,
            reason=AssistedIssueApproval.ReasonChoices.NO_PHONE
        )

        with self.assertRaises(ValidationError) as ctx:
            approve_assisted_issue_request(req.id, approving_user=self.requester)
        self.assertIn("cannot approve your own assisted issue request", str(ctx.exception))

    def test_non_head_officer_cannot_approve(self):
        """Assisted Issue: Only an officer with is_asc_head=True can approve."""
        from distributions.services import create_assisted_issue_request, approve_assisted_issue_request
        from django.core.exceptions import ValidationError

        req = create_assisted_issue_request(
            farmer=self.farmer, asc_centre=self.asc, season=self.season,
            requested_by_user=self.requester,
            reason=AssistedIssueApproval.ReasonChoices.ELDERLY_DISABLED
        )

        with self.assertRaises(ValidationError) as ctx:
            approve_assisted_issue_request(req.id, approving_user=self.non_head)
        self.assertIn("Only an authorized ASC Head can approve", str(ctx.exception))

        # ASC Head approval succeeds
        approved = approve_assisted_issue_request(req.id, approving_user=self.head_officer)
        self.assertEqual(approved.status, AssistedIssueApproval.StatusChoices.APPROVED)
        self.assertEqual(approved.approved_by, self.head_officer)

    def test_expired_assisted_request_cannot_be_approved(self):
        """Assisted Issue: Requests expire after 30 minutes."""
        from distributions.services import create_assisted_issue_request, approve_assisted_issue_request
        from django.core.exceptions import ValidationError

        req = create_assisted_issue_request(
            farmer=self.farmer, asc_centre=self.asc, season=self.season,
            requested_by_user=self.requester,
            reason=AssistedIssueApproval.ReasonChoices.PHONE_LOST_BROKEN
        )
        # Manually expire
        req.expires_at = timezone.now() - timedelta(minutes=5)
        req.save()

        with self.assertRaises(ValidationError) as ctx:
            approve_assisted_issue_request(req.id, approving_user=self.head_officer)
        self.assertIn("expired", str(ctx.exception))

    def test_full_assisted_issue_distribution_execution(self):
        """Assisted Issue: Execution records issue_method=ASSISTED, marks approval USED, deducts stock and quota."""
        from distributions.services import create_assisted_issue_request, approve_assisted_issue_request

        req = create_assisted_issue_request(
            farmer=self.farmer, asc_centre=self.asc, season=self.season,
            requested_by_user=self.requester,
            reason=AssistedIssueApproval.ReasonChoices.NO_PHONE
        )
        approve_assisted_issue_request(req.id, approving_user=self.head_officer)

        dist = confirm_issue_distribution(
            assisted_approval_id=req.id,
            asc_officer_user=self.requester,
            quantity_kg=Decimal("50.00")
        )

        self.assertEqual(dist.issue_method, FertilizerDistribution.IssueMethodChoices.ASSISTED)
        self.assertEqual(dist.assisted_approval, req)

        # Approval marked USED
        req.refresh_from_db()
        self.assertEqual(req.status, AssistedIssueApproval.StatusChoices.USED)

        # Entitlement deducted
        self.entitlement.refresh_from_db()
        self.assertEqual(self.entitlement.remaining_kg, Decimal("50.00"))


# ==============================================================================
# CONCURRENCY TESTS (TransactionTestCase with PostgreSQL Row Locks)
# ==============================================================================

from django.test import TransactionTestCase
import threading

class DistributionConcurrencyTransactionTests(TransactionTestCase):
    """
    Concurrency test verifying that select_for_update() row locking prevents
    double-redemption of the same token and over-issue of entitlement.
    """
    def setUp(self):
        self.asc = ASCCentre.objects.create(name="Vavuniya South ASC", district="Vavuniya", address="Kandy Rd")
        self.warehouse = Warehouse.objects.create(name="Central Warehouse", location="Colombo")
        self.season = Season.objects.create(
            name="Maha 2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 3, 31),
            status=Season.StstusChoices.ACTIVE
        )
        self.product = FertilizerProduct.objects.create(name="Urea", bag_weight_kg=Decimal("50.00"))
        self.batch = FertilizerBatch.objects.create(
            warehouse=self.warehouse, product=self.product,
            batch_number="CONCURRENT-DIST-1", expiry_date=date(2027, 12, 31)
        )
        self.stock = ASCStock.objects.create(asc_centre=self.asc, batch=self.batch, bags_on_hand=50)

        self.officer = User.objects.create_user(
            username="dist_concurrent_officer", password="Password123!",
            role=User.RoleChoices.ASC_OFFICER, asc_centre=self.asc
        )
        self.farmer_user = User.objects.create_user(username="farmer_c", password="Password123!", role=User.RoleChoices.FARMER)
        self.farmer = Farmer.objects.create(
            user=self.farmer_user, full_name="S. Concurrency Farmer",
            nic_number="199988887777", mobile_number="0779998888"
        )
        self.entitlement = FarmerEntitlement.objects.create(
            farmer=self.farmer, season=self.season, product=self.product,
            approved_kg=Decimal("50.00"), remaining_kg=Decimal("50.00")
        )

    def test_concurrent_token_double_redemption_prevented(self):
        """
        Two concurrent threads attempt to redeem the exact same token simultaneously.
        Result: Exactly ONE succeeds; the second fails due to select_for_update() row lock.
        Entitlement is deducted exactly once (remaining reaches 0, not -50).
        """
        raw_token, raw_code, qr_token = QRToken.generate_token_for_farmer(self.farmer)

        results = []
        errors = []

        def worker():
            from django.db import connection
            try:
                dist = confirm_issue_distribution(
                    raw_input_string=raw_token,
                    asc_officer_user=self.officer,
                    season_id=self.season.id,
                    quantity_kg=Decimal("50.00")
                )
                results.append(dist)
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        self.assertEqual(len(results), 1, "Exactly one token redemption transaction must succeed.")
        self.assertEqual(len(errors), 1, "The competing transaction must be rejected.")

        # Entitlement deducted exactly once to 0 kg
        self.entitlement.refresh_from_db()
        self.assertEqual(self.entitlement.remaining_kg, Decimal("0.00"))

        # Stock deducted exactly once by 1 bag
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.bags_on_hand, 49)


class FEFOExpiryAndWriteOffTests(TestCase):
    """
    Unit and integration tests for:
    1. FEFO multi-batch splitting across batches (earliest expiry first).
    2. Skipping expired batches during issue transactions.
    3. Expired stock write-off action (append-only WRITE_OFF movement & audit log).
    4. seed_demo_data command execution.
    """
    def setUp(self):
        self.client = Client()
        self.today = timezone.now().date()

        self.asc = ASCCentre.objects.create(name="Vavuniya South ASC", district="Vavuniya", address="Kandy Rd")
        self.warehouse = Warehouse.objects.create(name="Colombo Terminal", location="Colombo")
        self.product = FertilizerProduct.objects.create(name="Urea", bag_weight_kg=Decimal("50.00"))
        self.season = Season.objects.create(
            name="Maha 2026/2027", start_date=self.today - timedelta(days=10),
            end_date=self.today + timedelta(days=120), status=Season.StstusChoices.ACTIVE
        )

        self.officer = User.objects.create_user(
            username="fefo_officer", password="Password123!",
            role=User.RoleChoices.ASC_OFFICER, asc_centre=self.asc, is_asc_head=False
        )
        self.head = User.objects.create_user(
            username="fefo_head", password="Password123!",
            role=User.RoleChoices.ASC_OFFICER, asc_centre=self.asc, is_asc_head=True
        )

        self.farmer = Farmer.objects.create(
            full_name="K. Selvaratnam", nic_number="197812345678",
            mobile_number="0771234501", arpa_division="Vavuniya South"
        )
        self.entitlement = FarmerEntitlement.objects.create(
            farmer=self.farmer, season=self.season, product=self.product,
            approved_kg=Decimal("200.00"), remaining_kg=Decimal("200.00")
        )

        # Batch 1: Expiring in 20 days (Earliest unexpired, 1 bag = 50kg)
        self.batch_near = FertilizerBatch.objects.create(
            batch_number="BATCH-NEAR-20D", product=self.product, warehouse=self.warehouse,
            expiry_date=self.today + timedelta(days=20)
        )
        self.stock_near = ASCStock.objects.create(
            asc_centre=self.asc, batch=self.batch_near, bags_on_hand=1
        )

        # Batch 2: Expiring in 90 days (Later expiry, 5 bags = 250kg)
        self.batch_fresh = FertilizerBatch.objects.create(
            batch_number="BATCH-FRESH-90D", product=self.product, warehouse=self.warehouse,
            expiry_date=self.today + timedelta(days=90)
        )
        self.stock_fresh = ASCStock.objects.create(
            asc_centre=self.asc, batch=self.batch_fresh, bags_on_hand=5
        )

        # Batch 3: Expired 10 days ago (Expired, 8 bags = 400kg)
        self.batch_expired = FertilizerBatch.objects.create(
            batch_number="BATCH-EXPIRED-10D", product=self.product, warehouse=self.warehouse,
            expiry_date=self.today - timedelta(days=10)
        )
        self.stock_expired = ASCStock.objects.create(
            asc_centre=self.asc, batch=self.batch_expired, bags_on_hand=8
        )

    def test_fefo_multi_batch_split_and_expired_batch_skip(self):
        """
        When farmer takes 100kg (2 bags):
        - Batch 3 (Expired) MUST be skipped completely.
        - Batch 1 (Near expiry, 1 bag available) is exhausted to 0 bags.
        - Batch 2 (Later expiry) provides remaining 1 bag (reduced from 5 to 4).
        - StockMovements are recorded for both allocated batches.
        - Entitlement is deducted to 100kg.
        """
        raw_token, _, _ = QRToken.generate_token_for_farmer(self.farmer)

        dist = confirm_issue_distribution(
            raw_input_string=raw_token,
            asc_officer_user=self.officer,
            season_id=self.season.id,
            quantity_kg=Decimal("100.00")
        )

        # 1. Batch near-expiry is exhausted
        self.stock_near.refresh_from_db()
        self.assertEqual(self.stock_near.bags_on_hand, 0)

        # 2. Batch fresh provided remaining 1 bag
        self.stock_fresh.refresh_from_db()
        self.assertEqual(self.stock_fresh.bags_on_hand, 4)

        # 3. Expired batch was completely untouched
        self.stock_expired.refresh_from_db()
        self.assertEqual(self.stock_expired.bags_on_hand, 8)

        # 4. Entitlement deducted by 100kg
        self.entitlement.refresh_from_db()
        self.assertEqual(self.entitlement.remaining_kg, Decimal("100.00"))

        # 5. Outbound StockMovement created for both batches
        movements = StockMovement.objects.filter(
            movement_type=StockMovement.MovementTypeChoices.OUTBOUND,
            notes__contains=dist.receipt_number
        ).order_by('id')
        self.assertEqual(movements.count(), 2)
        self.assertEqual(movements[0].stock, self.stock_near)
        self.assertEqual(movements[0].quantity_kg, Decimal("50.00"))
        self.assertEqual(movements[1].stock, self.stock_fresh)
        self.assertEqual(movements[1].quantity_kg, Decimal("50.00"))

    def test_cannot_issue_from_expired_stock_when_no_fresh_stock(self):
        """
        If all unexpired stocks have 0 bags, issue is blocked even if expired stock exists.
        """
        from django.core.exceptions import ValidationError

        self.stock_near.bags_on_hand = 0
        self.stock_near.save()
        self.stock_fresh.bags_on_hand = 0
        self.stock_fresh.save()

        raw_token, _, _ = QRToken.generate_token_for_farmer(self.farmer)

        with self.assertRaises(ValidationError) as ctx:
            confirm_issue_distribution(
                raw_input_string=raw_token,
                asc_officer_user=self.officer,
                season_id=self.season.id,
                quantity_kg=Decimal("50.00")
            )
        self.assertIn("no usable unexpired stock", str(ctx.exception))

    def test_expired_stock_write_off_by_asc_head(self):
        """
        ASC Head writes off expired stock:
        - Deducts bags from ASCStock.
        - Creates append-only StockMovement(movement_type='WRITE_OFF').
        - Creates AuditLog entry.
        - Non-head officer cannot write off.
        """
        from inventory.services import write_off_expired_stock
        from django.core.exceptions import ValidationError

        # Non-head officer fails
        with self.assertRaises(ValidationError) as ctx:
            write_off_expired_stock(
                stock_id=self.stock_expired.id,
                head_user=self.officer,
                reason="Disposal required"
            )
        self.assertIn("Only an authorized ASC Head or Administrator", str(ctx.exception))

        # Unexpired stock cannot be written off as expired
        with self.assertRaises(ValidationError) as ctx:
            write_off_expired_stock(
                stock_id=self.stock_fresh.id,
                head_user=self.head,
                reason="Disposal required"
            )
        self.assertIn("has not expired yet", str(ctx.exception))

        # Empty reason fails
        with self.assertRaises(ValidationError) as ctx:
            write_off_expired_stock(
                stock_id=self.stock_expired.id,
                head_user=self.head,
                reason="   "
            )
        self.assertIn("mandatory justification reason", str(ctx.exception))

        # Successful write-off of all 8 bags
        movement = write_off_expired_stock(
            stock_id=self.stock_expired.id,
            head_user=self.head,
            reason="Approved chemical disposal after expiration"
        )
        self.stock_expired.refresh_from_db()
        self.assertEqual(self.stock_expired.bags_on_hand, 0)
        self.assertEqual(movement.movement_type, StockMovement.MovementTypeChoices.WRITE_OFF)
        self.assertEqual(movement.quantity_kg, Decimal("400.00"))

        # AuditLog recorded
        log = AuditLog.objects.filter(action__startswith="STOCK_WRITE_OFF").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.head)

    def test_seed_demo_data_command_execution(self):
        """
        The seed_demo_data management command runs without errors and sets up required records.
        """
        from django.core.management import call_command
        call_command('seed_demo_data')

        self.assertTrue(ASCCentre.objects.filter(name__icontains="Vavuniya").exists())
        self.assertTrue(FertilizerBatch.objects.filter(batch_number="UREA-2026-B01").exists())
        self.assertTrue(Farmer.objects.filter(full_name="K. Selvaratnam").exists())


