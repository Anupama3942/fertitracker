import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Sri Lankan NIC: Old (9 digits + V/X) or New (12 digits)
OLD_NIC_REGEX = re.compile(r'^[0-9]{9}[vVxX]$')
NEW_NIC_REGEX = re.compile(r'^[0-9]{12}$')
NIC_REGEX = re.compile(r'^(?:[0-9]{9}[vVxX]|[0-9]{12})$')

# Sri Lankan Mobile: Optional +94 or 0, followed by 7 and 8 digits
SL_MOBILE_REGEX = re.compile(r'^(?:\+94|0)?7[0-9]{8}$')

def validate_sri_lankan_nic(nic: str) -> str:
    """
    Validate that the given string matches Sri Lankan NIC formats:
    - Old format: 9 digits followed by 'V' or 'X' (e.g., 751234567V)
    - New format: 12 digits (e.g., 198512345678)
    Returns stripped, uppercase-normalized NIC.
    """
    if not nic:
        raise ValidationError(_("NIC number is required."))
    clean_nic = str(nic).strip().upper()
    if not NIC_REGEX.match(clean_nic):
        raise ValidationError(_("Invalid Sri Lankan NIC format. Must be 9 digits with V/X (e.g., 751234567V) or 12 digits (e.g., 198512345678)."))
    return clean_nic

def validate_sri_lankan_phone(phone: str) -> str:
    """
    Validate and normalize Sri Lankan mobile number to standard local format (07XXXXXXXX).
    """
    if not phone:
        raise ValidationError(_("Mobile phone number is required."))
    clean = str(phone).strip().replace(" ", "").replace("-", "")
    if not SL_MOBILE_REGEX.match(clean):
        raise ValidationError(_("Invalid Sri Lankan mobile phone format (e.g., 0771234567 or +94771234567)."))
    if clean.startswith("+94"):
        clean = "0" + clean[3:]
    elif clean.startswith("7") and len(clean) == 9:
        clean = "0" + clean
    return clean
