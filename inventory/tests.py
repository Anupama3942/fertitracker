from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models import ASCCentre, FertilizerProduct, Warehouse
from .models import (
    ASCStock,
    DispatchItem,
    FertilizerBatch,
    StockDispatch,
    StockMovement,
)
from .services import receive_dispatch


User = get_user_model()


class ReceiveDispatchTests(TestCase):

    def setUp(self):
        self.officer = User.objects.create_user(
            username="test_asc_officer",
            password="test-password",
            role="ASC_OFFICER",
        )

        self.warehouse = Warehouse.objects.create(
            name="Test Warehouse",
            location="Vavuniya",
        )

        self.asc = ASCCentre.objects.create(
            name="Test ASC",
            district="Vavuniya",
            address="Test Address",
        )

        self.product = FertilizerProduct.objects.create(
            name="Urea",
            bag_weight_kg=Decimal("50.00"),
        )

        self.batch = FertilizerBatch.objects.create(
            batch_number="UREA-TEST-001",
            product=self.product,
            warehouse=self.warehouse,
            initial_quantity_kg=Decimal("1000.00"),
            received_date=timezone.localdate(),
        )

        self.dispatch = StockDispatch.objects.create(
            warehouse=self.warehouse,
            destination_asc=self.asc,
            created_by=self.officer,
            status=StockDispatch.Status.DISPATCHED,
            dispatch_date=timezone.now(),
        )

        self.item = DispatchItem.objects.create(
            dispatch=self.dispatch,
            batch=self.batch,
            dispatched_quantity_kg=Decimal("500.00"),
        )

    def receive(self, received, damaged, missing):
        return receive_dispatch(
            dispatch_id=self.dispatch.id,
            receiver=self.officer,
            quantities={
                self.item.id: {
                    "received": received,
                    "damaged": damaged,
                    "missing": missing,
                }
            },
        )

    def test_successful_receipt(self):
        self.receive("480.00", "10.00", "10.00")

        stock = ASCStock.objects.get(
            asc=self.asc,
            batch=self.batch,
        )

        self.assertEqual(
            stock.quantity_kg,
            Decimal("480.00"),
        )

        self.assertEqual(StockMovement.objects.count(), 1)

        self.dispatch.refresh_from_db()

        self.assertEqual(
            self.dispatch.status,
            StockDispatch.Status.RECEIVED,
        )

    def test_invalid_quantities(self):
        with self.assertRaises(ValidationError):
            self.receive("480.00", "10.00", "20.00")

        self.assertEqual(ASCStock.objects.count(), 0)
        self.assertEqual(StockMovement.objects.count(), 0)

        self.dispatch.refresh_from_db()

        self.assertEqual(
            self.dispatch.status,
            StockDispatch.Status.DISPATCHED,
        )

    def test_duplicate_receipt(self):
        self.receive("480.00", "10.00", "10.00")

        with self.assertRaises(ValidationError):
            self.receive("480.00", "10.00", "10.00")

        stock = ASCStock.objects.get(
            asc=self.asc,
            batch=self.batch,
        )

        self.assertEqual(stock.quantity_kg, Decimal("480.00"))
        self.assertEqual(StockMovement.objects.count(), 1)
        