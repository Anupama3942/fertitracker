from django.contrib import admin
from .models import Farmer, FarmerEntitlement, QRToken

@admin.register(Farmer)
class FarmerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'nic_number', 'mobile_number', 'arpa_division')
    search_fields = ('full_name', 'nic_number', 'mobile_number')

@admin.register(FarmerEntitlement)
class FarmerEntitlementAdmin(admin.ModelAdmin):
    list_display = ('farmer', 'season', 'product', 'approved_kg', 'remaining_kg')
    list_filter = ('season', 'product')

@admin.register(QRToken)
class QRTokenAdmin(admin.ModelAdmin):
    list_display = ('farmer', 'expires_at', 'is_redeemed')
    list_filter = ('is_redeemed',)