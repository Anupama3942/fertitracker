from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import ValidationError
from accounts.decorators import role_required
from core.models import Season
from farmers.models import Farmer, QRToken
from .models import FertilizerDistribution, AuditLog
from .services import process_qr_distribution
import csv
from django.http import HttpResponse
from django.db.models import Q
import inventory.models as inv_models
from inventory.models import ASCStock

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


DispatchModel = (
    getattr(inv_models, 'Dispatch', None)
    or getattr(inv_models, 'WarehouseDispatch', None)
    or getattr(inv_models, 'StockDispatch', None)
    or getattr(inv_models, 'FertilizerDispatch', None)
)

@role_required('ADMIN', 'AUDITOR', 'ASC_OFFICER', 'WAREHOUSE_OFFICER')
def reports_and_search_view(request):
    """
    Search & Filter (NIC, Batch No, Date) සහ Reports (Stock, Dispatch/Discrepancy, Distributions) පෙන්වන පිටුව.
    """
    q = request.GET.get('q', '').strip()
    date_filter = request.GET.get('date', '').strip()
    report_type = request.GET.get('type', 'distributions')

    distributions = FertilizerDistribution.objects.select_related(
        'farmer', 'asc_centre', 'batch__product', 'season', 'issued_by'
    ).order_by('-distributed_at')

    stocks = ASCStock.objects.select_related(
        'asc_centre', 'batch__product'
    ).order_by('batch__expiry_date')

    dispatches = DispatchModel.objects.select_related(
        'warehouse', 'asc_centre', 'batch'
    ).order_by('-dispatched_at') if DispatchModel else []

    # ASC Officer හට තමන්ගේ ASC එකේ දත්ත පමණක් පෙන්වීම
    if request.user.role == 'ASC_OFFICER' and request.user.asc_centre:
        distributions = distributions.filter(asc_centre=request.user.asc_centre)
        stocks = stocks.filter(asc_centre=request.user.asc_centre)
        if DispatchModel:
            dispatches = dispatches.filter(asc_centre=request.user.asc_centre)

    # Search Query (NIC, Name, Receipt, Batch Number)
    if q:
        distributions = distributions.filter(
            Q(farmer__nic_number__icontains=q) |
            Q(farmer__full_name__icontains=q) |
            Q(batch__batch_number__icontains=q) |
            Q(receipt_number__icontains=q)
        )
        stocks = stocks.filter(
            Q(batch__batch_number__icontains=q) |
            Q(asc_centre__name__icontains=q) |
            Q(batch__product__name__icontains=q)
        )
        if DispatchModel:
            dispatches = dispatches.filter(
                Q(dispatch_reference__icontains=q) |
                Q(batch__batch_number__icontains=q) |
                Q(asc_centre__name__icontains=q)
            )

    # Date Filter
    if date_filter:
        distributions = distributions.filter(distributed_at__date=date_filter)
        if DispatchModel:
            dispatches = dispatches.filter(dispatched_at__date=date_filter)

    context = {
        'q': q,
        'date_filter': date_filter,
        'report_type': report_type,
        'distributions': distributions[:200],
        'stocks': stocks,
        'dispatches': dispatches,
    }
    return render(request, 'distributions/reports.html', context)


@role_required('ADMIN', 'AUDITOR', 'ASC_OFFICER', 'WAREHOUSE_OFFICER')
def export_report_csv(request):
    """
    තෝරාගත් වාර්තාව (Distributions, Stock, හෝ Dispatches) CSV ගොනුවක් ලෙස Download කිරීම.
    """
    report_type = request.GET.get('type', 'distributions')
    q = request.GET.get('q', '').strip()
    date_filter = request.GET.get('date', '').strip()

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="fertitracker_{report_type}_report.csv"'
    writer = csv.writer(response)

    if report_type == 'stocks':
        writer.writerow(['ASC Centre', 'Product', 'Batch Number', 'Expiry Date', 'Bags on Hand'])
        qs = ASCStock.objects.select_related('asc_centre', 'batch__product').order_by('batch__expiry_date')
        if request.user.role == 'ASC_OFFICER' and request.user.asc_centre:
            qs = qs.filter(asc_centre=request.user.asc_centre)
        if q:
            qs = qs.filter(Q(batch__batch_number__icontains=q) | Q(asc_centre__name__icontains=q))
        for st in qs:
            writer.writerow([st.asc_centre.name, st.batch.product.name, st.batch.batch_number, st.batch.expiry_date, st.bags_on_hand])

    elif report_type == 'dispatches' and DispatchModel:
        writer.writerow(['Reference', 'Warehouse', 'ASC Centre', 'Batch', 'Dispatched Bags', 'Good Bags', 'Damaged Bags', 'Status', 'Date'])
        qs = DispatchModel.objects.select_related('warehouse', 'asc_centre', 'batch').order_by('-dispatched_at')
        if request.user.role == 'ASC_OFFICER' and request.user.asc_centre:
            qs = qs.filter(asc_centre=request.user.asc_centre)
        if q:
            qs = qs.filter(Q(dispatch_reference__icontains=q) | Q(batch__batch_number__icontains=q))
        if date_filter:
            qs = qs.filter(dispatched_at__date=date_filter)
        for d in qs:
            writer.writerow([
                d.dispatch_reference, d.warehouse.name, d.asc_centre.name,
                d.batch.batch_number, d.dispatched_bags, d.received_good_bags,
                d.damaged_bags, d.status, d.dispatched_at.strftime('%Y-%m-%d %H:%M')
            ])

    else:
        writer.writerow(['Receipt No', 'Farmer Name', 'Masked NIC', 'ASC Centre', 'Product', 'Batch No', 'Quantity (kg)', 'Season', 'Issued By', 'Date'])
        qs = FertilizerDistribution.objects.select_related('farmer', 'asc_centre', 'batch__product', 'season', 'issued_by').order_by('-distributed_at')
        if request.user.role == 'ASC_OFFICER' and request.user.asc_centre:
            qs = qs.filter(asc_centre=request.user.asc_centre)
        if q:
            qs = qs.filter(Q(farmer__nic_number__icontains=q) | Q(batch__batch_number__icontains=q) | Q(receipt_number__icontains=q))
        if date_filter:
            qs = qs.filter(distributed_at__date=date_filter)
        for dist in qs:
            writer.writerow([
                dist.receipt_number, dist.farmer.full_name, dist.farmer.masked_nic,
                dist.asc_centre.name, dist.batch.product.name, dist.batch.batch_number,
                dist.quantity_kg, dist.season.name, dist.issued_by.username,
                dist.distributed_at.strftime('%Y-%m-%d %H:%M')
            ])

    AuditLog.objects.create(
        user=request.user,
        action=f"REPORT_EXPORTED_CSV",
        details=f"Exported {report_type} report to CSV."
    )
    return response


