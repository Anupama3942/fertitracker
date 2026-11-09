from django.conf import settings

def app_settings(request):
    """
    Expose global application flags to all templates.
    """
    return {
        'DEMO_MODE': getattr(settings, 'DEMO_MODE', False),
        'NEAR_EXPIRY_DAYS': getattr(settings, 'NEAR_EXPIRY_DAYS', 60),
        'LOW_STOCK_THRESHOLD_BAGS': getattr(settings, 'LOW_STOCK_THRESHOLD_BAGS', 10),
    }
