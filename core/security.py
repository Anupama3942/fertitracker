import hmac
import hashlib
from django.conf import settings

def compute_code_hmac(raw_code: str) -> str:
    """
    Compute HMAC-SHA256 of a code (OTP or 6-digit backup code)
    using the server's OTP_SECRET_KEY.
    """
    secret = getattr(settings, 'OTP_SECRET_KEY', getattr(settings, 'SECRET_KEY', 'fertitracker-secret')).encode('utf-8')
    return hmac.new(secret, str(raw_code).strip().encode('utf-8'), hashlib.sha256).hexdigest()

def verify_code_hmac(raw_code: str, stored_hash: str) -> bool:
    """Constant-time HMAC comparison to prevent timing attacks."""
    expected_hash = compute_code_hmac(raw_code)
    return hmac.compare_digest(expected_hash, stored_hash)

def mask_phone_number(phone: str) -> str:
    """Mask phone number for audit logging (e.g., 077****501)."""
    if not phone:
        return ""
    clean = str(phone).strip()
    if len(clean) >= 7:
        return f"{clean[:3]}****{clean[-3:]}"
    return clean
