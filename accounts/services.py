import hashlib
import random
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from .models import PasswordResetOTP
from distributions.models import AuditLog

class SMSNotificationService:
    @staticmethod
    def send_otp(user, phone_number, purpose="OTP"):
        """
        Generate and store an OTP, then send it through the simulated notification gateway.
        """
        # Invalidate any previous unused OTPs for this user.
        PasswordResetOTP.objects.filter(user=user, is_used=False).update(is_used=True)

        # Generate a six-digit OTP.
        raw_otp = str(random.randint(100000, 999999))
        hashed = hashlib.sha256(raw_otp.encode()).hexdigest()
        expiry = timezone.now() + timedelta(minutes=5)

        PasswordResetOTP.objects.create(
            user=user,
            otp_hash=hashed,
            expires_at=expiry
        )

        # Check whether the application is running in demo mode.
        is_demo = getattr(settings, 'DEMO_MODE', True)
        
        if is_demo:
            print(f"\n[DEMO SMS GATEWAY] To: {phone_number} | Purpose: {purpose} | CODE: {raw_otp}\n")
            AuditLog.objects.create(
                user=user,
                action=f"SMS_SENT_{purpose}",
                details=f"Simulated SMS sent to {phone_number} with OTP."
            )
            return raw_otp  # Return the raw OTP for display in the demo screen.
        
        return None