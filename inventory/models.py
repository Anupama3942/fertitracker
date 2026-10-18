import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.models import ASCCentre, FertilizerProduct, Warehouse


class FertilizerBatch(models.Model):
    batch_number = models.CharField(
        max_length=100,
        unique=True,
    )

    product = models.ForeignKey(
        FertilizerProduct,
        on_delete=models.PROTECT,
        related_name="batches",
    )

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="fertilizer_batches",
    )

    initial_quantity_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    received_date = models.DateField()

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return self.batch_number


class StockDispatch(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        DISPATCHED = "DISPATCHED", "Dispatched"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    dispatch_reference = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="dispatches",
    )

    destination_asc = models.ForeignKey(
        ASCCentre,
        on_delete=models.PROTECT,
        related_name="incoming_dispatches",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    dispatch_date = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_dispatches",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return str(self.dispatch_reference)


class DispatchItem(models.Model):
    dispatch = models.ForeignKey(
        StockDispatch,
        on_delete=models.CASCADE,
        related_name="items",
    )

    batch = models.ForeignKey(
        FertilizerBatch,
        on_delete=models.PROTECT,
        related_name="dispatch_items",
    )

    dispatched_quantity_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    received_quantity_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    damaged_quantity_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    missing_quantity_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["dispatch", "batch"],
                name="unique_batch_per_dispatch",
            )
        ]

    def __str__(self):
        return f"{self.dispatch} - {self.batch}"
    
    
class ASCStock(models.Model):
    asc = models.ForeignKey(
        ASCCentre,
        on_delete=models.PROTECT,
        related_name="stock_records",
    )

    batch = models.ForeignKey(
        FertilizerBatch,
        on_delete=models.PROTECT,
        related_name="asc_stock_records",
    )

    quantity_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["asc", "batch"],
                name="unique_asc_batch_stock",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_kg__gte=0),
                name="asc_stock_quantity_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.asc} - {self.batch}"

# #######################################################################

class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        RECEIPT = "RECEIPT", "Receipt"
        ISSUE = "ISSUE", "Issue"
        ADJUSTMENT_IN = "ADJUSTMENT_IN", "Adjustment In"
        ADJUSTMENT_OUT = "ADJUSTMENT_OUT", "Adjustment Out"
        REVERSAL_IN = "REVERSAL_IN", "Reversal In"
        REVERSAL_OUT = "REVERSAL_OUT", "Reversal Out"

    asc = models.ForeignKey(
        ASCCentre,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )

    batch = models.ForeignKey(
        FertilizerBatch,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )

    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
    )

    quantity_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    balance_after_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    source_reference = models.CharField(
        max_length=150,
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.movement_type} - {self.quantity_kg} kg"