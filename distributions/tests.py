import gettext
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.models import ASCCentre, Warehouse, Season, FertilizerProduct
from inventory.models import FertilizerBatch, ASCStock
from farmers.models import Farmer, FarmerEntitlement, QRToken
from distributions.models import FertilizerDistribution, AuditLog
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
        self.assertContains(response, "already been used or has expired")

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
        self.assertContains(response, "already been used or has expired")

    def test_i18n_mo_roundtrip(self):
        """Bug 1: Verify .mo binary catalog correctly loads pristine Sinhala and Tamil strings without mojibake."""
        t_si = gettext.translation('django', localedir='locale', languages=['si'])
        t_ta = gettext.translation('django', localedir='locale', languages=['ta'])

        self.assertEqual(t_si.gettext("Login"), "ඇතුල් වන්න")
        self.assertEqual(t_ta.gettext("Login"), "உள்நுழைக")
        self.assertEqual(t_si.gettext("My QR & Quota"), "මගේ QR කේතය සහ හිමිකම")
        self.assertEqual(t_ta.gettext("My QR & Quota"), "எனது QR & உரிமை அளவு")
