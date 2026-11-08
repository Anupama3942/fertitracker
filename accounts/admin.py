from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display    = ('username', 'email', 'role', 'asc_centre', "is_active", 'is_staff')
    list_filter     = ('role', 'is_active', 'asc_centre')
    search_fields   = ('username', 'email', 'first_name', 'last_name')
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('FertiTracker Role & Assignment', {'fields': ('role', 'asc_centre')}),
    )
    
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('FertiTracker Role & Assignment', {'fields': ('role', 'asc_centre')}),
    )
    