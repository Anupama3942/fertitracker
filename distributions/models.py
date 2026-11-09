import uuid
from django.db import models
from django.conf import settings
from core.models import ASCCentre, Season, FertilizerProduct
from farmers.models import Farmer
from inventory.models import FertilizerBatch, ASCStock

class SMSOutbox(models.Model):
    """
    Outbox table storing simulated or sent SMS messages for farmer verification codes.
    """
    phone_number = models.CharField(max_length=20)
    message = models.TextField()
    farmer = models.ForeignKey(Farmer, on_delete=models.SET_NULL, null=True, blank=True, related_name='sms_messages')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='SENT')

    def __str__(self):
        return f"SMS to {self.phone_number} at {self.created_at} [{self.status}]"


class AssistedIssueApproval(models.Model):
    """
    Two-officer approval for issuing fertilizer to farmers without phones/QR.
    Requires an ASC Head approval, valid for 30 minutes.
    """
    class ReasonChoices(models.TextChoices):
        NO_PHONE = 'NO_PHONE', 'Farmer has no phone'
        PHONE_LOST_BROKEN = 'PHONE_LOST_BROKEN', 'Phone lost or damaged'
        NETWORK_BATTERY = 'NETWORK_BATTERY', 'No network / battery flat'
        ELDERLY_DISABLED = 'ELDERLY_DISABLED', 'Elderly or disabled farmer assisted'
        OTHER = 'OTHER', 'Other reason - requires explanation'

    class StatusChoices(models.TextChoices):
        PENDING = 'PENDING', 'Pending Approval'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        USED = 'USED', 'Completed & Used'
        EXPIRED = 'EXPIRED', 'Expired'

    farmer = models.ForeignKey(Farmer, on_delete=models.PROTECT, related_name='assisted_requests')
    asc_centre = models.ForeignKey(ASCCentre, on_delete=models.PROTECT, related_name='assisted_requests')
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name='assisted_requests')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='assisted_requests_created')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='assisted_requests_approved')
    
    reason = models.CharField(max_length=50, choices=ReasonChoices.choices)
    reason_note = models.TextField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_valid_for_issue(self):
        from django.utils import timezone
        return self.status == self.StatusChoices.APPROVED and timezone.now() <= self.expires_at

    def __str__(self):
        return f"Assisted Issue #{self.id} for {self.farmer.full_name} [{self.get_status_display()}]"


class FertilizerDistribution(models.Model):
    class IssueMethodChoices(models.TextChoices):
        QR = 'QR', 'QR Code'
        SMS_CODE = 'SMS_CODE', 'SMS Backup Code'
        ASSISTED = 'ASSISTED', 'Officer Assisted'

    farmer = models.ForeignKey(Farmer, on_delete=models.PROTECT, related_name='distributions')
    asc_centre = models.ForeignKey(ASCCentre, on_delete=models.PROTECT, related_name='distributions')
    batch = models.ForeignKey(FertilizerBatch, on_delete=models.PROTECT, related_name='distributions')
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name='distributions')
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='issued_distributions')
    
    issue_method = models.CharField(max_length=20, choices=IssueMethodChoices.choices, default=IssueMethodChoices.QR)
    assisted_approval = models.ForeignKey(AssistedIssueApproval, on_delete=models.SET_NULL, null=True, blank=True, related_name='distributions')

    quantity_kg = models.DecimalField(max_digits=10, decimal_places=2)
    receipt_number = models.CharField(max_length=100, unique=True, blank=True)
    distributed_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        """Generate a receipt number when needed, then save the distribution."""
        if not self.receipt_number:
            self.receipt_number = f"REC-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        """Return the receipt number, farmer, and issued quantity."""
        return f"{self.receipt_number} - {self.farmer.full_name} ({self.quantity_kg} kg) [{self.get_issue_method_display()}]"


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.TextField(blank=True, null=True)

    def __str__(self):
        """Return a readable timestamped audit action description."""
        username = self.user.username if self.user else "System"
        return f"[{self.timestamp}] {username}: {self.action}"