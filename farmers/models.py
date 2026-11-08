import hashlib
from datetime import timedelta
from django.utils import timezone
from django.db import models
from core.models import Season, FertilizerProduct
from accounts.models import User

class Farmer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='farmer_profile', null=True, blank=True)
    full_name = models.CharField(max_length=200)
    nic_number = models.CharField(max_length=20, unique=True)  # Business Rule 2: ගොවි NIC අංකය අනන්‍ය විය යුතුය
    mobile_number = models.CharField(max_length=20)
    arpa_division = models.CharField(max_length=150, blank=True, null=True)  # ශ්‍රී ලංකා කෘෂිකාර්මික ව්‍යුහයට අනුකූලව

    def __str__(self):
        return f"{self.full_name} ({self.nic_number})"


class FarmerEntitlement(models.Model):
    farmer = models.ForeignKey(Farmer, on_delete=models.PROTECT, related_name='entitlements')
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name='entitlements')
    product = models.ForeignKey(FertilizerProduct, on_delete=models.PROTECT, related_name='entitlements')
    approved_kg = models.DecimalField(max_digits=10, decimal_places=2)
    remaining_kg = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        # Business Rule 3: එක් ගොවියෙකුට එක් කන්නයකට සහ එක් නිෂ්පාදනයකට තිබිය හැක්කේ එක් හිමිකම් වාර්තාවක් පමණි
        constraints = [
            models.UniqueConstraint(fields=['farmer', 'season', 'product'], name='unique_farmer_season_product')
        ]

    def __str__(self):
        return f"{self.farmer.full_name} | {self.season.name} | {self.product.name}: {self.remaining_kg}/{self.approved_kg} kg"


class QRToken(models.Model):
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='qr_tokens')
    token_hash = models.CharField(max_length=255, unique=True)  # QR දත්ත සර්වර් එකේ පිරිසිදු ලෙස නොමැතිව Hash අගයක් ලෙස තබා ගැනීම
    expires_at = models.DateTimeField()
    is_redeemed = models.BooleanField(default=False)

    @classmethod
    def generate_token_for_farmer(cls, farmer):
        """
        තත්පර 60කින් කල් ඉකුත් වන dynamic opaque token එකක් සාදා එහි cryptographic hash එක DB එකේ ගබඩා කරයි (FR-10, Section 11.2).
        """
        import uuid
        raw_token = uuid.uuid4().hex + uuid.uuid4().hex
        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()
        expiry = timezone.now() + timedelta(seconds=60)  # තත්පර 60ක ආයු කාලයක්

        # පෙර පැවති භාවිත නොකළ tokens අක්‍රීය කිරීම
        cls.filter(farmer=farmer, is_redeemed=False).update(is_redeemed=True)

        obj = cls.objects.create(
            farmer=farmer,
            token_hash=hashed_token,
            expires_at=expiry
        )
        return raw_token, obj

    def is_valid(self):
        return not self.is_redeemed and timezone.now() <= self.expires_at

    def __str__(self):
        status = "Redeemed" if self.is_redeemed else ("Expired" if timezone.now() > self.expires_at else "Active")
        return f"QR for {self.farmer.full_name} [{status}]"