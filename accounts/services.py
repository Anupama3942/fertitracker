from django.conf import settings
from .models import PasswordResetOTP
from distributions.models import AuditLog
from distributions.sms import get_sms_backend
from core.security import mask_phone_number

class SMSNotificationService:
    @staticmethod
    def send_otp(user, phone_number, purpose="OTP"):
        """
        Generate, hash with HMAC-SHA256, and store an OTP.
        Dispatches via pluggable SMS backend (writing to SMSOutbox for demo inbox display).
        Rate-limited: max 3/hour, 60s cooldown.
        """
        # generate_otp performs rate limiting, invalidates previous OTPs, and creates new one
        raw_otp = PasswordResetOTP.generate_otp(user)

        farmer = getattr(user, 'farmer_profile', None)
        message_text = f"FertiTracker: Your OTP for {purpose} is {raw_otp}. Valid for 5 minutes. Do not share."

        sms_backend = get_sms_backend()
        sms_backend.send_sms(phone_number, message_text, context={'farmer': farmer, 'code': raw_otp})

        AuditLog.objects.create(
            user=user,
            action=f"SMS_SENT_{purpose}",
            details=f"OTP sent to {mask_phone_number(phone_number)} for purpose: {purpose}"
        )
        return raw_otp