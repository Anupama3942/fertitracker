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


class QRToken(models.Model):
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='qr_tokens')
    token_hash = models.CharField(max_length=255, unique=True)  # Store only a hash of the QR data on the server.
    expires_at = models.DateTimeField()
    is_redeemed = models.BooleanField(default=False)

    @classmethod
    def generate_token_for_farmer(cls, farmer):
        """
        Generate a dynamic opaque token that expires in 60 seconds and store its cryptographic hash (FR-10, Section 11.2).
        """
        import uuid
        raw_token = uuid.uuid4().hex + uuid.uuid4().hex
        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()
        expiry = timezone.now() + timedelta(seconds=60)  # Set a 60-second lifetime.

        # Invalidate any previous unused tokens for this farmer.
        cls.objects.filter(farmer=farmer, is_redeemed=False).update(is_redeemed=True)

        obj = cls.objects.create(
            farmer=farmer,
            token_hash=hashed_token,
            expires_at=expiry
        )
        return raw_token, obj

    def is_valid(self):
        """Return whether the token is unused and has not expired."""
        return not self.is_redeemed and timezone.now() <= self.expires_at

    def __str__(self):
        """Return a readable description of the token and its current status."""
        status = "Redeemed" if self.is_redeemed else ("Expired" if timezone.now() > self.expires_at else "Active")
        return f"QR for {self.farmer.full_name} [{status}]"