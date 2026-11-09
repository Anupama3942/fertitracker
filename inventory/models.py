import uuid
from django.db import models
from django.conf import settings
from core.models import Warehouse, ASCCentre, FertilizerProduct

# Create your models here.

class FertilizerBatch(models.Model):
    warehouse   = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='batches')
    
    product     = models.ForeignKey(FertilizerProduct, on_delete=models.PROTECT, related_name='batches')
    
    batch_number = models.CharField(max_length=80, unique=True)
    
    expiry_date = models.DateField()
    
    def __str__(self):
        """Return the batch number, product name, and expiry date."""
        return f"{self.batch_number} - {self.product.name} (Exp: {self.expiry_date})"
    
class StockDispatch(models.Model):
    class StatusChoices(models.TextChoices):
        DISPATCHED                  = 'DISPATCHED', 'Dispatched'
        RECEIVED                    = 'RECEIVED', 'Received'
        RECEIVED_WITH_DISCREPANCY   = 'RECEIVED_WITH_DISCREPANCY', 'Received with Discrepancy'
        DISCREPANCY                 = 'DISCREPANCY', 'Received with Discrepancy'
        
    warehouse   = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='dispatches')
    
    asc_centre  = models.ForeignKey(ASCCentre, on_delete=models.PROTECT, related_name='dispatches')
    
    created_by  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_dispatches')
    
    
    dispatch_reference  = models.CharField(max_length=80, unique=True, blank=True)
    status  = models.CharField(max_length=30, choices=StatusChoices.choices, default=StatusChoices.DISPATCHED)
    dispatched_at   = models.DateTimeField(auto_now_add=True)
    
    
    def save(self, *args, **kwargs):
        """Generate a dispatch reference when needed, then save the dispatch."""
        if not self.dispatch_reference:
            self.dispatch_reference = f"{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)
        
    def __str__(self):
        """Return the dispatch reference and its warehouse-to-ASC route."""
        return f"{self.dispatch_reference} ({self.warehouse.name} -> {self.asc_centre.name})"
    
class DispatchItem(models.Model):
    dispatch = models.ForeignKey(StockDispatch, on_delete=models.CASCADE, related_name='items')
    batch = models.ForeignKey(FertilizerBatch, on_delete=models.PROTECT, related_name='dispatch_items')
    dispatched_bags = models.PositiveIntegerField()
    received_bags = models.PositiveIntegerField(default=0)
    damaged_bags = models.PositiveIntegerField(default=0)

    @property
    def missing_bags(self):
        """Return dispatched bags not accounted for as received or damaged."""
        # FR-07: Missing bags are calculated by subtracting received and damaged bags from dispatched bags.
        diff = self.dispatched_bags - (self.received_bags + self.damaged_bags)
        return max(diff, 0)

    def __str__(self):
        """Return the dispatch reference, batch number, and dispatched quantity."""
        return f"{self.dispatch.dispatch_reference} - {self.batch.batch_number} ({self.dispatched_bags} bags)"


class ASCStock(models.Model):
    asc_centre = models.ForeignKey(ASCCentre, on_delete=models.PROTECT, related_name='stocks')
    batch = models.ForeignKey(FertilizerBatch, on_delete=models.PROTECT, related_name='asc_stocks')
    bags_on_hand = models.PositiveIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        # Business Rule 4: Each ASC can have only one stock record for each batch.
        constraints = [
            models.UniqueConstraint(fields=['asc_centre', 'batch'], name='unique_asc_batch_stock')
        ]

    @property
    def total_weight_kg(self):
        # Calculate the total weight in kilograms by multiplying the number of bags by the weight of one bag.
        return self.bags_on_hand * self.batch.product.bag_weight_kg

    def __str__(self):
        """Return the ASC, batch, and current bag balance."""
        return f"{self.asc_centre.name} | {self.batch.batch_number}: {self.bags_on_hand} bags"

class StockMovement(models.Model):
    class MovementTypeChoices(models.TextChoices):
        INBOUND     = 'INBOUND', 'Inbound (Dispatch Received)'
        OUTBOUND    = 'OUTBOUND', 'Outbound (Issued to Farmer)'
        DAMAGED     = 'DAMAGED', 'Damaged Stock'
        DISCREPANCY = 'DISCREPANCY', 'Missing / Discrepancy'
        ADJUSTMENT  = 'ADJUSTMENT', 'Manual Adjustment'
        REVERSAL    = 'REVERSAL', 'Transaction Reversal'
        WRITE_OFF   = 'WRITE_OFF', 'Expired Stock Write-Off'

    stock           = models.ForeignKey(ASCStock, on_delete=models.PROTECT, related_name='movements')
    movement_type   = models.CharField(max_length=30, choices=MovementTypeChoices.choices)
    quantity_kg     = models.DecimalField(max_digits=10, decimal_places=2)
    dispatch        = models.ForeignKey(StockDispatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements')
    created_by      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements')
    notes           = models.CharField(max_length=255, blank=True, null=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """Return the movement type, quantity, and ASC centre."""
        return f"{self.movement_type} - {self.quantity_kg} kg ({self.stock.asc_centre.name})"


class Discrepancy(models.Model):
    dispatch = models.ForeignKey(StockDispatch, on_delete=models.CASCADE, related_name='discrepancies')
    damaged_bags = models.PositiveIntegerField(default=0)
    missing_bags = models.PositiveIntegerField(default=0)
    reason = models.TextField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='recorded_discrepancies')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Discrepancy for {self.dispatch.dispatch_reference}: {self.damaged_bags} damaged, {self.missing_bags} missing"


class StockThreshold(models.Model):
    """
    Configurable low-stock alert threshold per Agrarian Service Centre and Fertilizer Product.
    Allows administrators to customize thresholds per centre (falls back to settings default).
    """
    asc_centre = models.ForeignKey(ASCCentre, on_delete=models.CASCADE, related_name='stock_thresholds')
    product = models.ForeignKey(FertilizerProduct, on_delete=models.CASCADE, related_name='stock_thresholds')
    threshold_bags = models.PositiveIntegerField(default=10)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['asc_centre', 'product'], name='unique_asc_product_threshold')
        ]

    def __str__(self):
        return f"{self.asc_centre.name} | {self.product.name} (Threshold: {self.threshold_bags} bags)"
