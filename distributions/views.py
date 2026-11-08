from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import ValidationError
from accounts.decorators import role_required
from core.models import Season
from farmers.models import Farmer, QRToken
from .models import FertilizerDistribution, AuditLog
from .services import process_qr_distribution

@role_required('FARMER')
def farmer_qr_dashboard(request):
    """
    Page for farmers to generate their QR token and view their quota status (FR-10).
    """
    farmer = Farmer.objects.filter(user=request.user).first()
    if not farmer:
        messages.error(
            request,
            "Your Farmer profile has not been linked to your user account yet. "
            "Please contact an administrator.",
        )
        return redirect('dashboard')

    entitlements = farmer.entitlements.select_related('season', 'product').all()
    
    raw_token = None
    if request.method == 'POST':
        # Generate a new QR token with a 60-second lifetime.
        raw_token, qr_obj = QRToken.generate_token_for_farmer(farmer)
        messages.success(request, "A new QR token valid for 60 seconds was generated!")

    active_token = farmer.qr_tokens.filter(is_redeemed=False).order_by('-expires_at').first()
    is_active_valid = active_token.is_valid() if active_token else False

    context = {
        'farmer': farmer,
        'entitlements': entitlements,
        'raw_token': raw_token,
        'is_active_valid': is_active_valid,
    }
    return render(request, 'distributions/farmer_dashboard.html', context)


@role_required('ADMIN', 'ASC_OFFICER')
def asc_scanner_view(request):
    """
    Allow an ASC officer to scan a farmer QR token and issue fertilizer (FR-11, FR-12).
    """
    seasons = Season.objects.filter(status='ACTIVE')
    distribution = None

    if request.method == 'POST':
        token_string = request.POST.get('token_string', '').strip()
        season_id = request.POST.get('season')
        client_ip = request.META.get('REMOTE_ADDR')

        try:
            distribution = process_qr_distribution(token_string, request.user, season_id, client_ip)
            messages.success(request, f"Fertilizer issued successfully. Receipt number: {distribution.receipt_number}")
        except ValidationError as e:
            messages.error(request, e.message)

    context = {
        'seasons': seasons,
        'distribution': distribution,
    }
    return render(request, 'distributions/asc_scanner.html', context)


@role_required('ADMIN', 'ASC_OFFICER', 'AUDITOR', 'FARMER')
def distribution_receipt_view(request, receipt_number):
    """
    Display the digital receipt for an issued fertilizer distribution (FR-18).
    """
    distribution = get_object_or_404(
        FertilizerDistribution.objects.select_related('farmer', 'asc_centre', 'batch__product', 'season', 'issued_by'),
        receipt_number=receipt_number
    )
    return render(request, 'distributions/receipt.html', {'distribution': distribution})


@role_required('ADMIN', 'AUDITOR')
def audit_logs_view(request):
    """
    Display append-only audit logs for auditors (FR-17).
    """
    logs = AuditLog.objects.select_related('user').order_by('-timestamp')[:100]
    return render(request, 'distributions/audit_logs.html', {'logs': logs})