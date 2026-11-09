import hashlib
import random
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class RoleChoices(models.TextChoices):
        ADMIN               = 'ADMIN', 'System Administrator'
        WAREHOUSE_OFFICER   = 'WAREHOUSE_OFFICER', 'Warehouse Officer'
        ASC_OFFICER         = 'ASC_OFFICER', 'ASC Officer'
        AUDITOR             = 'AUDITOR', 'Auditor'
        FARMER              = 'FARMER', 'Farmer'

    role = models.CharField(
        max_length=30,
        choices=RoleChoices.choices,
        default=RoleChoices.FARMER
        )
    asc_centre = models.ForeignKey('core.ASCCentre', on_delete=models.SET_NULL, null=True, blank=True, related_name='officers')
    is_asc_head = models.BooleanField(default=False)
    
    # Require new officers to change their password at first login.
    must_change_password = models.BooleanField(default=False)
    
    # Track whether a farmer account has been activated through OTP verification.
    is_account_active = models.BooleanField(default=True)
    
    failed_login_attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    # Brute-force protection for 6-digit code entry by officers
    failed_code_attempts = models.PositiveIntegerField(default=0)
    code_locked_until = models.DateTimeField(null=True, blank=True)
    
    def is_locked(self):
        return bool(self.locked_until and timezone.now() < self.locked_until)

    def is_code_locked(self):
        if self.code_locked_until:
            if timezone.now() < self.code_locked_until:
                return True
            else:
                # Lockout expired; reset counters
                self.failed_code_attempts = 0
                self.code_locked_until = None
                self.save(update_fields=['failed_code_attempts', 'code_locked_until'])
        return False

    def record_failed_code_attempt(self):
        self.failed_code_attempts += 1
        if self.failed_code_attempts >= 5:
            self.code_locked_until = timezone.now() + timedelta(minutes=10)
        self.save(update_fields=['failed_code_attempts', 'code_locked_until'])

    def reset_failed_code_attempts(self):
        if self.failed_code_attempts > 0 or self.code_locked_until is not None:
            self.failed_code_attempts = 0
            self.code_locked_until = None
            self.save(update_fields=['failed_code_attempts', 'code_locked_until'])

    def __str__(self):
        """Return the username and display name of the user."""
        return f"{self.username} ({self.get_role_display()})"


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otps')
    otp_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)

    @classmethod
    def generate_otp(cls, user):
        """
        Generate a six-digit OTP, store its SHA-256 hash, and set a five-minute expiry.
        """
        # Invalidate any previous unused OTPs for this user.
        cls.objects.filter(user=user, is_used=False).update(is_used=True)

        raw_otp = str(random.randint(100000, 999999))
        hashed = hashlib.sha256(raw_otp.encode()).hexdigest()
        expiry = timezone.now() + timedelta(minutes=5)

        cls.objects.create(
            user=user,
            otp_hash=hashed,
            expires_at=expiry
        )
        return raw_otp  # Return the raw OTP for the prototype display.

    def is_valid(self):
        """Return whether the OTP is unused, unexpired, and within the attempt limit."""
        return not self.is_used and timezone.now() <= self.expires_at and self.attempts < 3