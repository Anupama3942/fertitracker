from django.contrib import admin

from .models import (
    ASCStock,
    DispatchItem,
    FertilizerBatch,
    StockDispatch,
    StockMovement,
)


# 1. Fertilizer Batch Admin
@admin.register(FertilizerBatch)
class FertilizerBatchAdmin(admin.ModelAdmin):
    list_display = (
        "batch_number",
        "product",
        "warehouse",
        "initial_quantity_kg",
        "received_date",
        "is_active",
    )

    list_filter = (
        "product",
        "warehouse",
        "is_active",
    )

    search_fields = (
        "batch_number",
        "product__name",
        "warehouse__name",
    )


# 2. Dispatch Item Inline
class DispatchItemInline(admin.TabularInline):
    model = DispatchItem
    extra = 1


# 3. Stock Dispatch Admin
@admin.register(StockDispatch)
class StockDispatchAdmin(admin.ModelAdmin):
    list_display = (
        "dispatch_reference",
        "warehouse",
        "destination_asc",
        "status",
        "dispatch_date",
        "created_by",
    )

    list_filter = (
        "status",
        "warehouse",
        "destination_asc",
    )

    search_fields = (
        "dispatch_reference",
        "warehouse__name",
        "destination_asc__name",
    )

    readonly_fields = (
        "dispatch_reference",
        "created_at",
    )

    inlines = [
        DispatchItemInline,
    ]


# 4. Dispatch Item Admin
@admin.register(DispatchItem)
class DispatchItemAdmin(admin.ModelAdmin):
    list_display = (
        "dispatch",
        "batch",
        "dispatched_quantity_kg",
        "received_quantity_kg",
        "damaged_quantity_kg",
        "missing_quantity_kg",
    )


# 5. ASC Stock Admin
@admin.register(ASCStock)
class ASCStockAdmin(admin.ModelAdmin):
    list_display = (
        "asc",
        "batch",
        "quantity_kg",
        "updated_at",
    )

    list_filter = (
        "asc",
        "batch__product",
    )

    search_fields = (
        "asc__name",
        "batch__batch_number",
        "batch__product__name",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# 6. Stock Movement Admin
@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "asc",
        "batch",
        "movement_type",
        "quantity_kg",
        "balance_after_kg",
        "created_by",
    )

    list_filter = (
        "movement_type",
        "asc",
        "created_at",
    )

    search_fields = (
        "batch__batch_number",
        "asc__name",
        "source_reference",
        "created_by__username",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False