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
    ගොවියාට තමන්ගේ QR token එක උත්පාදනය කර ගැනීමට සහ කෝටා තත්ත්වය බලාගැනීමට ඇති පිටුව (FR-10).
    """
    farmer = get_object_or_404(Farmer, user=request.user)
    entitlements = farmer.entitlements.select_related('season', 'product').all()
    
    raw_token = None
    if request.method == 'POST':
        # නව QR ටෝකනයක් උත්පාදනය කිරීම (තත්පර 60ක ආයු කාලයක් සහිතව)
        raw_token, qr_obj = QRToken.generate_token_for_farmer(farmer)
        messages.success(request, "තත්පර 60ක් සඳහා වලංගු නව QR ටෝකනයක් උත්පාදනය කරන ලදී!")

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
    ASC නිලධාරියාට ගොවියාගේ QR ටෝකනය scan කර පොහොර නිකුත් කිරීමට ඇති පිටුව (FR-11, FR-12).
    """
    seasons = Season.objects.filter(status='ACTIVE')
    distribution = None

    if request.method == 'POST':
        token_string = request.POST.get('token_string', '').strip()
        season_id = request.POST.get('season')
        client_ip = request.META.get('REMOTE_ADDR')

        try:
            distribution = process_qr_distribution(token_string, request.user, season_id, client_ip)
            messages.success(request, f"පොහොර නිකුත් කිරීම සාර්ථකයි! රිසිට්පත් අංකය: {distribution.receipt_number}")
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
    නිකුත් කළ පොහොර සඳහා ඩිජිටල් රිසිට්පත පෙන්වීම (FR-18).
    """
    distribution = get_object_or_404(
        FertilizerDistribution.objects.select_related('farmer', 'asc_centre', 'batch__product', 'season', 'issued_by'),
        receipt_number=receipt_number
    )
    return render(request, 'distributions/receipt.html', {'distribution': distribution})


@role_required('ADMIN', 'AUDITOR')
def audit_logs_view(request):
    """
    විගණකාධිපති (Auditor) සඳහා Append-only Audit Logs පෙන්වන පිටුව (FR-17).
    """
    logs = AuditLog.objects.select_related('user').order_by('-timestamp')[:100]
    return render(request, 'distributions/audit_logs.html', {'logs': logs})