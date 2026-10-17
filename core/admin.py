from django.contrib import admin
from .models import ASCCentre, FertilizerProduct, Season, Warehouse


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "location")
    search_fields = ("name", "location")


@admin.register(ASCCentre)
class ASCCentreAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "district", "address")
    search_fields = ("name", "district", "address")


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "start_date",
        "end_date",
        "status",
    )

    list_filter = ("status",)
    search_fields = ("name",)


@admin.register(FertilizerProduct)
class FertilizerProductAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "bag_weight_kg")
    search_fields = ("name",)