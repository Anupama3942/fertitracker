from django.contrib import admin
from .models import FertilizerDistribution, AuditLog

@admin.register(FertilizerDistribution)
class FertilizerDistributionAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'farmer', 'asc_centre', 'batch', 'quantity_kg', 'issued_by', 'distributed_at')
    list_filter = ('season', 'asc_centre')
    search_fields = ('receipt_number', 'farmer__nic_number', 'farmer__full_name')

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'ip_address', 'details')
    list_filter = ('action',)
    search_fields = ('action', 'details')
    
    
    