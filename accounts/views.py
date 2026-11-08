from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from core.models import Warehouse, ASCCentre, Season, FertilizerProduct
from .models import User

# Create your views here.

@login_required
def dashboard_view(request):
    user = request.user
    
    if user.is_superuser and user.role != User.RoleChoices.ADMIN:
        user.role = User.RoleChoices.ADMIN
        user.save(update_fields=['role'])
        
    context = {
        'warehouse_count': Warehouse.objects.count(),
        'asc_count': ASCCentre.objects.count(),
        'active_seasons': Season.objects.filter(status='ACTIVE'),
        'products': FertilizerProduct.objects.all(),
    }
    
    return render(request, 'accounts/dashboard.html', context)