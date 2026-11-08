from django.contrib import admin
from .models import FertilizerBatch, StockDispatch, DispatchItem, ASCStock, StockMovement

class DispatchItemInline(admin.TabularInline):
    model = DispatchItem
    extra = 1

@admin.register(FertilizerBatch)
class FertilizerBatchAdmin(admin.ModelAdmin):
    list_display = ('batch_number', 'product', 'warehouse', 'expiry_date')
    list_filter = ('warehouse', 'product')
    search_fields = ('batch_number',)

@admin.register(StockDispatch)
class StockDispatchAdmin(admin.ModelAdmin):
    list_display = ('dispatch_reference', 'warehouse', 'asc_centre', 'status', 'created_by', 'dispatched_at')
    list_filter = ('status', 'warehouse', 'asc_centre')
    search_fields = ('dispatch_reference',)
    inlines = [DispatchItemInline]

@admin.register(ASCStock)
class ASCStockAdmin(admin.ModelAdmin):
    list_display = ('asc_centre', 'batch', 'bags_on_hand', 'total_weight_kg', 'last_updated')
    list_filter = ('asc_centre',)

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('stock', 'movement_type', 'quantity_kg', 'created_at')
    list_filter = ('movement_type',)