import uuid
from django.db import models
from django.conf import settings
from core.models import ASCCentre, Season, FertilizerProduct
from farmers.models import Farmer
from inventory.models import FertilizerBatch, ASCStock

class FertilizerDistribution(models.Model):
    farmer = models.ForeignKey(Farmer, on_delete=models.PROTECT, related_name='distributions')
    asc_centre = models.ForeignKey(ASCCentre, on_delete=models.PROTECT, related_name='distributions')
    batch = models.ForeignKey(FertilizerBatch, on_delete=models.PROTECT, related_name='distributions')
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name='distributions')
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='issued_distributions')
    
    quantity_kg = models.DecimalField(max_digits=10, decimal_places=2)
    receipt_number = models.CharField(max_length=100, unique=True, blank=True)
    distributed_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = f"REC-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.receipt_number} - {self.farmer.full_name} ({self.quantity_kg} kg)"


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.TextField(blank=True, null=True)

    def __str__(self):
        username = self.user.username if self.user else "System"
        return f"[{self.timestamp}] {username}: {self.action}"