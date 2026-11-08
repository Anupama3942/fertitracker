from django.contrib import admin
from .models import Warehouse, ASCCentre, Season, FertilizerProduct

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display    = ('id', 'name', 'location')
    search_fields   = ('name', 'location')
    
@admin.register(ASCCentre)
class ASCCentreAdmin(admin.ModelAdmin):
    list_display    = ('id', 'name', 'district', 'address')
    list_filter     = ('district',)
    search_fields   = ('name', 'district')
    
@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display    = ('id', 'name', 'start_date', 'end_date', 'status')
    list_filter     =('status',)

@admin.register(FertilizerProduct)
class FertilizerProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'bag_weight_kg') 
    
    