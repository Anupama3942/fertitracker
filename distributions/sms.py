import logging
from abc import ABC, abstractmethod
from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

class BaseSMSBackend(ABC):
    """
    Abstract base class for SMS delivery backends in FertiTracker.
    Pluggable design enables swapping SimulatedSMSBackend for a commercial
    Sri Lankan SMS Gateway (e.g. Mobitel m-Space, Dialog IdeaMart, Twilio)
    without touching any business logic.
    """
    @abstractmethod
    def send_sms(self, phone_number: str, message: str, context: dict = None) -> bool:
        """
        Send an SMS message to a phone number.
        Returns True if successful, False otherwise.
        """
        pass


class SimulatedSMSBackend(BaseSMSBackend):
    """
    Simulated SMS Backend for development, testing, and university exhibition demo.
    Saves SMS to the database SMSOutbox and logs to the system console.
    """
    def send_sms(self, phone_number: str, message: str, context: dict = None) -> bool:
        from distributions.models import SMSOutbox
        farmer = context.get('farmer') if context else None
        
        # Save to database outbox
        SMSOutbox.objects.create(
            phone_number=phone_number,
            message=message,
            farmer=farmer,
            status='SENT'
        )

        # Output to console
        print(f"\n{'='*60}")
        print(f"[SIMULATED SMS GATEWAY]")
        print(f"To: {phone_number}")
        if farmer:
            print(f"Farmer: {farmer.full_name} ({farmer.masked_nic})")
        print(f"Message: {message}")
        print(f"{'='*60}\n")
        return True


def get_sms_backend() -> BaseSMSBackend:
    """Factory function returning the configured SMS backend instance."""
    backend_path = getattr(settings, 'SMS_BACKEND', 'distributions.sms.SimulatedSMSBackend')
    try:
        backend_cls = import_string(backend_path)
        return backend_cls()
    except Exception as e:
        logger.error(f"Failed to load SMS backend {backend_path}: {e}")
        return SimulatedSMSBackend()
