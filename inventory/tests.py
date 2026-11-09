from decimal import Decimal
from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from core.models import ASCCentre, Warehouse, FertilizerProduct
from inventory.models import FertilizerBatch, StockDispatch, DispatchItem, ASCStock, StockMovement, Discrepancy
from inventory.services import confirm_dispatch_receiving
from distributions.models import AuditLog

User = get_user_model()

class ReceivingAndReconciliationTests(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Master Data
        self.asc1 = ASCCentre.objects.create(
            name="Vavuniya South ASC",
            district="Vavuniya",
            address="Kandy Road, Vavuniya"
        )
        self.asc2 = ASCCentre.objects.create(
            name="Cheddikulam ASC",
            district="Vavuniya",
            address="Mannar Road, Cheddikulam"
        )
        self.warehouse = Warehouse.objects.create(
            name="Central Port Warehouse",
            location="Colombo Port"
        )
        self.product = FertilizerProduct.objects.create(
            name="Urea",
            bag_weight_kg=Decimal("50.00")
        )

        # 2. Users
        self.warehouse_officer = User.objects.create_user(
            username="wh_officer",
            password="Password123!",
            role=User.RoleChoices.WAREHOUSE_OFFICER
        )
        self.asc_officer1 = User.objects.create_user(
            username="asc1_officer",
            password="Password123!",
            role=User.RoleChoices.ASC_OFFICER,
            asc_centre=self.asc1
        )
        self.asc_officer2 = User.objects.create_user(
            username="asc2_officer",
            password="Password123!",
            role=User.RoleChoices.ASC_OFFICER,
            asc_centre=self.asc2
        )
        self.auditor = User.objects.create_user(
            username="auditor1",
            password="Password123!",
            role=User.RoleChoices.AUDITOR
        )

        # 3. Batch & Dispatch of 100 bags to ASC 1
        self.batch = FertilizerBatch.objects.create(
            warehouse=self.warehouse,
            product=self.product,
            batch_number="BATCH-UREA-2026-X",
            expiry_date=date(2027, 6, 30)
        )
        self.dispatch = StockDispatch.objects.create(
            warehouse=self.warehouse,
            asc_centre=self.asc1,
            created_by=self.warehouse_officer
        )
        self.item = DispatchItem.objects.create(
            dispatch=self.dispatch,
            batch=self.batch,
            dispatched_bags=100
        )

    def test_receiving_good_bags_increases_usable_stock(self):
        """Rule 4: Good bags are added to ASC stock bags_on_hand."""
        confirm_dispatch_receiving(
            dispatch_id=self.dispatch.id,
            officer_user=self.asc_officer1,
            received_bags_dict={str(self.item.id): 100},
            damaged_bags_dict={str(self.item.id): 0}
        )
        self.dispatch.refresh_from_db()
        self.assertEqual(self.dispatch.status, StockDispatch.StatusChoices.RECEIVED)

        stock = ASCStock.objects.get(asc_centre=self.asc1, batch=self.batch)
        self.assertEqual(stock.bags_on_hand, 100)

        # Inbound StockMovement created
        movement = StockMovement.objects.filter(stock=stock, movement_type=StockMovement.MovementTypeChoices.INBOUND).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity_kg, Decimal("5000.00"))

        # AuditLog created
        audit = AuditLog.objects.filter(action__contains=self.dispatch.dispatch_reference).first()
        self.assertIsNotNone(audit)

    def test_damaged_and_missing_bags_create_discrepancy_and_not_added_to_usable_stock(self):
        """Rule 4 & 5: Only good bags added to stock; discrepancy record created."""
        # 80 Good, 10 Damaged, 10 Missing
        confirm_dispatch_receiving(
            dispatch_id=self.dispatch.id,
            officer_user=self.asc_officer1,
            received_bags_dict={str(self.item.id): 80},
            damaged_bags_dict={str(self.item.id): 10},
            discrepancy_reason="10 bags torn by transport hook, 10 bags missing from lorry."
        )
        self.dispatch.refresh_from_db()
        self.assertEqual(self.dispatch.status, StockDispatch.StatusChoices.RECEIVED_WITH_DISCREPANCY)

        # Usable stock is ONLY 80
        stock = ASCStock.objects.get(asc_centre=self.asc1, batch=self.batch)
        self.assertEqual(stock.bags_on_hand, 80)

        # Discrepancy record verified
        disc = Discrepancy.objects.get(dispatch=self.dispatch)
        self.assertEqual(disc.damaged_bags, 10)
        self.assertEqual(disc.missing_bags, 10)
        self.assertIn("transport hook", disc.reason)
        self.assertEqual(disc.recorded_by, self.asc_officer1)

    def test_discrepancy_without_reason_is_rejected(self):
        """Rule 5: Discrepancy requires a mandatory reason note."""
        with self.assertRaises(ValidationError):
            confirm_dispatch_receiving(
                dispatch_id=self.dispatch.id,
                officer_user=self.asc_officer1,
                received_bags_dict={str(self.item.id): 90},
                damaged_bags_dict={str(self.item.id): 10},
                discrepancy_reason=""  # Missing reason
            )

    def test_receiving_twice_is_rejected(self):
        """Rule 6: Receiving can happen only once per dispatch."""
        confirm_dispatch_receiving(
            dispatch_id=self.dispatch.id,
            officer_user=self.asc_officer1,
            received_bags_dict={str(self.item.id): 100},
            damaged_bags_dict={str(self.item.id): 0}
        )
        with self.assertRaises(ValidationError):
            confirm_dispatch_receiving(
                dispatch_id=self.dispatch.id,
                officer_user=self.asc_officer1,
                received_bags_dict={str(self.item.id): 100},
                damaged_bags_dict={str(self.item.id): 0}
            )

    def test_officer_from_another_asc_cannot_receive(self):
        """Rule 2: Officer from another ASC must be rejected."""
        with self.assertRaises(ValidationError):
            confirm_dispatch_receiving(
                dispatch_id=self.dispatch.id,
                officer_user=self.asc_officer2,  # Officer from Cheddikulam ASC
                received_bags_dict={str(self.item.id): 100},
                damaged_bags_dict={str(self.item.id): 0}
            )

    def test_totals_above_dispatched_or_negative_values_rejected(self):
        """Rule 3: Rejects totals > dispatched and negative numbers."""
        with self.assertRaises(ValidationError):
            confirm_dispatch_receiving(
                dispatch_id=self.dispatch.id,
                officer_user=self.asc_officer1,
                received_bags_dict={str(self.item.id): 105},  # > 100
                damaged_bags_dict={str(self.item.id): 0}
            )

        with self.assertRaises(ValidationError):
            confirm_dispatch_receiving(
                dispatch_id=self.dispatch.id,
                officer_user=self.asc_officer1,
                received_bags_dict={str(self.item.id): -5},
                damaged_bags_dict={str(self.item.id): 0}
            )

    def test_auditor_cannot_receive_via_ui(self):
        """Rule 9: Auditor has read-only access and cannot POST receiving."""
        self.client.login(username="auditor1", password="Password123!")
        response = self.client.post(
            reverse('receive_dispatch', kwargs={'dispatch_id': self.dispatch.id}),
            {
                f"received_{self.item.id}": 100,
                f"damaged_{self.item.id}": 0
            }
        )
        # Should redirect back with error message
        self.dispatch.refresh_from_db()
        self.assertEqual(self.dispatch.status, StockDispatch.StatusChoices.DISPATCHED)


from django.test import TransactionTestCase
import threading

class DispatchConcurrencyTransactionTests(TransactionTestCase):
    """
    Concurrency test verifying that two simultaneous receiving transactions
    cannot double-receive the same dispatch under PostgreSQL select_for_update() locking.
    """
    def setUp(self):
        self.asc = ASCCentre.objects.create(name="Vavuniya South ASC", district="Vavuniya", address="Kandy Rd")
        self.warehouse = Warehouse.objects.create(name="Colombo Port Warehouse", location="Colombo")
        self.product = FertilizerProduct.objects.create(name="Urea", bag_weight_kg=Decimal("50.00"))
        self.officer = User.objects.create_user(
            username="concurrent_officer", password="Password123!",
            role=User.RoleChoices.ASC_OFFICER, asc_centre=self.asc
        )
        self.batch = FertilizerBatch.objects.create(
            warehouse=self.warehouse, product=self.product,
            batch_number="CONCURRENT-BATCH-1", expiry_date=date(2027, 12, 31)
        )
        self.dispatch = StockDispatch.objects.create(
            warehouse=self.warehouse, asc_centre=self.asc, created_by=self.officer
        )
        self.item = DispatchItem.objects.create(
            dispatch=self.dispatch, batch=self.batch, dispatched_bags=50
        )

    def test_concurrent_dispatch_receiving_prevented(self):
        """
        Two concurrent threads execute confirm_dispatch_receiving simultaneously.
        Result: Exactly one succeeds; the second receives ValidationError.
        Stock bags_on_hand is incremented exactly once.
        """
        results = []
        errors = []

        def worker():
            from django.db import connection
            try:
                # Open separate database connection for thread
                res = confirm_dispatch_receiving(
                    dispatch_id=self.dispatch.id,
                    officer_user=self.officer,
                    received_bags_dict={str(self.item.id): 50},
                    damaged_bags_dict={str(self.item.id): 0}
                )
                results.append(res)
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

        # Exactly one thread succeeds
        self.assertEqual(len(results), 1, "Exactly one receiving transaction must succeed.")
        self.assertEqual(len(errors), 1, "The competing transaction must be rejected by row-level locking.")
        self.assertIn("already been received", str(errors[0]))

        # Stock is incremented exactly once by 50 bags
        stock = ASCStock.objects.get(asc_centre=self.asc, batch=self.batch)
        self.assertEqual(stock.bags_on_hand, 50)

