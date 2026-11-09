import hashlib
from datetime import timedelta
from django.utils import timezone
from django.db import models
from core.models import Season, FertilizerProduct
from accounts.models import User

class Farmer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='farmer_profile', null=True, blank=True)
    full_name = models.CharField(max_length=200)
    nic_number = models.CharField(max_length=20, unique=True)  # Business Rule 2: Each farmer NIC number must be unique.
    mobile_number = models.CharField(max_length=20)
    arpa_division = models.CharField(max_length=150, blank=True, null=True)  # Align with Sri Lanka's agricultural administration structure.
    
    @property
    def masked_nic(self):
        """Data Privacy: 198512345678 -> 1985****5678 ලෙස පෙන්වයි."""
        if len(self.nic_number) >= 8:
            return f"{self.nic_number[:4]}****{self.nic_number[-4:]}"
        return self.nic_number

    def __str__(self):
        """Return the farmer's name and NIC number."""
        return f"{self.full_name} ({self.nic_number})"


class FarmerEntitlement(models.Model):
    farmer = models.ForeignKey(Farmer, on_delete=models.PROTECT, related_name='entitlements')
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name='entitlements')
    product = models.ForeignKey(FertilizerProduct, on_delete=models.PROTECT, related_name='entitlements')
    approved_kg = models.DecimalField(max_digits=10, decimal_places=2)
    remaining_kg = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        # Business Rule 3: A farmer can have only one entitlement per season and product.
        constraints = [
            models.UniqueConstraint(fields=['farmer', 'season', 'product'], name='unique_farmer_season_product')
        ]

    def __str__(self):
        """Return the farmer's season, product, and remaining entitlement."""
        return f"{self.farmer.full_name} | {self.season.name} | {self.product.name}: {self.remaining_kg}/{self.approved_kg} kg"


from core.security import compute_code_hmac

class QRToken(models.Model):
    class ChannelChoices(models.TextChoices):
        QR = 'QR', 'QR Code'
        SMS = 'SMS', 'SMS Code'

    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='qr_tokens')
    asc_centre = models.ForeignKey('core.ASCCentre', on_delete=models.CASCADE, null=True, blank=True, related_name='qr_tokens')
    channel = models.CharField(max_length=20, choices=ChannelChoices.choices, default=ChannelChoices.QR)
    token_hash = models.CharField(max_length=255, unique=True)  # Store SHA-256 of 64-char QR token
    code_hash = models.CharField(max_length=255, null=True, blank=True)  # HMAC-SHA256 keyed hash of 6-digit backup code
    expires_at = models.DateTimeField()
    is_redeemed = models.BooleanField(default=False)
    failed_attempts = models.PositiveIntegerField(default=0)

    @classmethod
    def generate_token_for_farmer(cls, farmer, asc_centre=None, channel='QR', expiry_seconds=60):
        """
        Generate a dynamic opaque token and HMAC-keyed 6-digit backup code.
        Can be bound to a specific ASC and channel (QR or SMS).
        """
        import uuid
        import random
        raw_token = uuid.uuid4().hex + uuid.uuid4().hex
        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()
        raw_code = f"{random.randint(100000, 999999)}"
        hashed_code = compute_code_hmac(raw_code)
        expiry = timezone.now() + timedelta(seconds=expiry_seconds)

        # Invalidate any previous unused tokens for this farmer on this channel
        cls.objects.filter(farmer=farmer, channel=channel, is_redeemed=False).update(is_redeemed=True)

        obj = cls.objects.create(
            farmer=farmer,
            asc_centre=asc_centre,
            channel=channel,
            token_hash=hashed_token,
            code_hash=hashed_code,
            expires_at=expiry
        )
        return raw_token, raw_code, obj

    def is_valid(self):
        """Return whether the token is unused, unexpired, and not locked out."""
        return not self.is_redeemed and timezone.now() <= self.expires_at and self.failed_attempts < 5

    def record_failed_attempt(self):
        """Track wrong entry attempts against this specific token."""
        self.failed_attempts += 1
        if self.failed_attempts >= 5:
            self.is_redeemed = True  # Invalidate token after 5 failed attempts
        self.save(update_fields=['failed_attempts', 'is_redeemed'])

    def __str__(self):
        """Return a readable description of the token and its current status."""
        status = "Redeemed" if self.is_redeemed else ("Expired" if timezone.now() > self.expires_at else ("Locked" if self.failed_attempts >= 5 else "Active"))
        return f"{self.channel} for {self.farmer.full_name} [{status}]"