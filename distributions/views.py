import io
import csv
import codecs
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.db.models import Q, Count
from django.utils import timezone
from django.utils.translation import gettext as _
from django.conf import settings
from django.db import transaction

from accounts.decorators import role_required, require_asc_head, forbid_response
from accounts.permissions import can_approve_assisted_request
from accounts.models import User
from core.models import Season, FertilizerProduct, ASCCentre
from core.validators import validate_sri_lankan_nic, validate_sri_lankan_phone
from core.security import mask_phone_number
from farmers.models import Farmer, QRToken, FarmerEntitlement
from .models import FertilizerDistribution, AuditLog, AssistedIssueApproval, SMSOutbox
from .services import process_qr_distribution
import inventory.models as inv_models
from inventory.models import ASCStock



@role_required('FARMER')
def farmer_qr_dashboard(request):
    """
    ගොවියාට තමන්ගේ QR token එක උත්පාදනය කර ගැනීමට, කෝටා තත්ත්වය සහ පෙර ලබාගත් පොහොර ඉතිහාසය (Issue History)
    සිංහල / දෙමළ / ඉංග්‍රීසි භාෂා 3න්ම බලාගැනීමට ඇති පිටුව (FR-10, Usability).
    """
    farmer = Farmer.objects.filter(user=request.user).first()
    if not farmer:
        messages.error(request, "ඔබගේ User ගිණුමට අදාළ Farmer Profile එකක් තවමත් Admin මඟින් සම්බන්ධ කර නොමැත.")
        return redirect('dashboard')

    entitlements = farmer.entitlements.select_related('season', 'product').all()
    issue_history = farmer.distributions.select_related('asc_centre', 'batch__product', 'season').order_by('-distributed_at')
    latest_issue = issue_history.first()

    raw_token = None
    raw_code = None
    if request.method == 'POST':
        raw_token, raw_code, qr_obj = QRToken.generate_token_for_farmer(farmer)
        messages.success(request, "Dynamic QR code generated (valid for 60 seconds).")

    active_token = farmer.qr_tokens.filter(is_redeemed=False).order_by('-expires_at').first()
    is_active_valid = active_token.is_valid() if active_token else False

    context = {
        'farmer': farmer,
        'entitlements': entitlements,
        'issue_history': issue_history,
        'latest_issue': latest_issue,
        'raw_token': raw_token,
        'raw_code': raw_code,
        'is_active_valid': is_active_valid,
    }
    return render(request, 'distributions/farmer_dashboard.html', context)


@role_required('ASC_OFFICER')
def asc_scanner_view(request):
    """
    Allow an ASC officer to scan/enter a farmer QR or 6-digit code.
    Flow: Scan/Code -> Verify (no redemption) -> Confirmation Screen -> Confirm & Issue.
    """
    from .services import verify_farmer_token, confirm_issue_distribution

    seasons = Season.objects.filter(status='ACTIVE')
    verification = None
    distribution = None

    if request.method == 'POST':
        action = request.POST.get('action', 'verify')
        token_string = request.POST.get('token_string', '').strip()
        season_id = request.POST.get('season')
        client_ip = request.META.get('REMOTE_ADDR')

        if action == 'verify':
            # Step 1 & 2: Verify without redeeming
            try:
                verification = verify_farmer_token(token_string, request.user, season_id)
            except ValidationError as e:
                messages.error(request, e.message)

        elif action == 'confirm':
            # Step 3 & 4: Execute atomic issue
            quantity_kg = request.POST.get('quantity_kg')
            try:
                distribution = confirm_issue_distribution(
                    raw_input_string=token_string,
                    asc_officer_user=request.user,
                    season_id=season_id,
                    quantity_kg=Decimal(quantity_kg) if quantity_kg else None,
                    client_ip=client_ip
                )
                messages.success(request, f"Fertilizer issued successfully. Receipt number: {distribution.receipt_number}")
            except (ValidationError, Exception) as e:
                messages.error(request, getattr(e, 'message', str(e)))

    pending_assisted_count = 0
    if request.user.is_authenticated and getattr(request.user, 'asc_centre', None):
        pending_assisted_count = AssistedIssueApproval.objects.filter(
            asc_centre=request.user.asc_centre,
            status=AssistedIssueApproval.StatusChoices.PENDING,
            expires_at__gt=timezone.now()
        ).count()

    context = {
        'seasons': seasons,
        'verification': verification,
        'distribution': distribution,
        'pending_assisted_count': pending_assisted_count,
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
    if request.user.role == 'FARMER' and distribution.farmer.user_id != request.user.id:
        return render(request, '403.html', status=403)
    return render(request, 'distributions/receipt.html', {'distribution': distribution})


@role_required('ADMIN', 'AUDITOR')
def audit_logs_view(request):
    """
    Searchable and filterable append-only audit logs viewer for Auditors and Administrators.
    Strictly read-only: no edit or delete capability.
    Filterable by user, action, date range, and keyword search. Supports CSV export with UTF-8 BOM.
    """
    user_id = request.GET.get('user')
    action_filter = request.GET.get('action', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    q = request.GET.get('q', '').strip()

    logs_qs = AuditLog.objects.select_related('user').order_by('-timestamp')

    if user_id:
        logs_qs = logs_qs.filter(user_id=user_id)
    if action_filter:
        logs_qs = logs_qs.filter(action__icontains=action_filter)
    if start_date:
        logs_qs = logs_qs.filter(timestamp__date__gte=start_date)
    if end_date:
        logs_qs = logs_qs.filter(timestamp__date__lte=end_date)
    if q:
        logs_qs = logs_qs.filter(Q(action__icontains=q) | Q(details__icontains=q) | Q(ip_address__icontains=q))

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="fertitracker_audit_logs.csv"'
        response.write('\ufeff')
        writer = csv.writer(response)
        writer.writerow(['Timestamp', 'User', 'Action', 'IP Address', 'Details'])
        for log in logs_qs[:1000]:
            writer.writerow([
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                log.user.username if log.user else 'System',
                log.action,
                log.ip_address or 'N/A',
                log.details or ''
            ])
        return response

    context = {
        'logs': logs_qs[:200],
        'total_count': logs_qs.count(),
        'users': User.objects.all().order_by('username'),
        'selected_user': user_id,
        'action_filter': action_filter,
        'start_date': start_date,
        'end_date': end_date,
        'q': q,
    }
    return render(request, 'distributions/audit_logs.html', context)


@role_required('ADMIN', 'AUDITOR', 'WAREHOUSE_OFFICER', 'ASC_OFFICER')
def batch_traceability_view(request):
    """
    Key Demo Feature: End-to-End Batch Traceability Lifecycle.
    Traces a fertilizer batch through its entire life:
    1. Batch Master & Expiry Status (Warehouse, Product, Expiry date)
    2. Dispatches to ASC Centres (Dispatched bags, date, warehouse officer)
    3. Receiving & Discrepancies (Good bags received, damaged, missing, notes)
    4. Current Usable Stock Balances across ASCs
    5. Distributions to Farmers (Receipt, farmer name, masked NIC, bags, kg, method, timestamp)
    6. Expired Stock Write-Offs (Bags written off, justification, authorized ASC Head)
    7. Supply chain reconciliation summary
    """
    from inventory.models import FertilizerBatch, StockDispatch, DispatchItem, ASCStock, StockMovement, Discrepancy

    batch_query = request.GET.get('batch_number', '').strip().upper()
    all_batches = FertilizerBatch.objects.select_related('warehouse', 'product').order_by('expiry_date')

    batch_obj = None
    dispatches = []
    current_stocks = []
    farmer_distributions = []
    write_offs = []
    total_dispatched_bags = 0
    total_received_bags = 0
    total_damaged_bags = 0
    total_missing_bags = 0
    total_issued_bags = 0
    total_issued_kg = Decimal('0.00')
    total_written_off_bags = 0
    total_on_hand_bags = 0

    if batch_query:
        batch_obj = FertilizerBatch.objects.filter(batch_number__iexact=batch_query).select_related('warehouse', 'product').first()
        if not batch_obj:
            batch_obj = FertilizerBatch.objects.filter(batch_number__icontains=batch_query).select_related('warehouse', 'product').first()

    if batch_obj:
        today = timezone.localdate()
        batch_obj.is_expired = batch_obj.expiry_date < today
        batch_obj.days_to_expiry = (batch_obj.expiry_date - today).days

        # 1. Dispatches
        dispatch_items = DispatchItem.objects.filter(batch=batch_obj).select_related(
            'dispatch__warehouse', 'dispatch__asc_centre', 'dispatch__created_by'
        ).order_by('-dispatch__dispatched_at')

        dispatches = dispatch_items
        for item in dispatch_items:
            total_dispatched_bags += item.dispatched_bags
            total_received_bags += item.received_bags
            total_damaged_bags += item.damaged_bags
            total_missing_bags += item.missing_bags

        # 2. ASC Stocks on hand
        current_stocks = ASCStock.objects.filter(batch=batch_obj).select_related('asc_centre')
        total_on_hand_bags = sum(s.bags_on_hand for s in current_stocks)

        # 3. Farmer Distributions
        farmer_distributions = FertilizerDistribution.objects.filter(batch=batch_obj).select_related(
            'farmer', 'asc_centre', 'issued_by'
        ).order_by('-distributed_at')
        total_issued_kg = sum(d.quantity_kg for d in farmer_distributions)
        bag_weight = batch_obj.product.bag_weight_kg
        total_issued_bags = int(total_issued_kg / bag_weight) if bag_weight else 0

        # 4. Expired Stock Write-offs
        write_offs = StockMovement.objects.filter(
            stock__batch=batch_obj,
            movement_type=StockMovement.MovementTypeChoices.WRITE_OFF
        ).select_related('stock__asc_centre', 'created_by').order_by('-created_at')
        for wo in write_offs:
            wo_bags = int(wo.quantity_kg / bag_weight) if bag_weight else 0
            total_written_off_bags += wo_bags

    context = {
        'batch_query': batch_query,
        'all_batches': all_batches[:50],
        'batch': batch_obj,
        'dispatches': dispatches,
        'current_stocks': current_stocks,
        'farmer_distributions': farmer_distributions[:100],
        'write_offs': write_offs,
        'total_dispatched_bags': total_dispatched_bags,
        'total_received_bags': total_received_bags,
        'total_damaged_bags': total_damaged_bags,
        'total_missing_bags': total_missing_bags,
        'total_issued_bags': total_issued_bags,
        'total_issued_kg': total_issued_kg,
        'total_written_off_bags': total_written_off_bags,
        'total_on_hand_bags': total_on_hand_bags,
    }
    return render(request, 'distributions/batch_traceability.html', context)


@role_required('ADMIN', 'AUDITOR', 'ASC_OFFICER', 'WAREHOUSE_OFFICER')
def reports_and_search_view(request):
    """
    Search & Filter Reports (Distributions, Stock & FEFO, Dispatches).
    Supports comprehensive filtering: season, ASC, product, issue method, status, date range.
    """
    from inventory.models import StockDispatch, ASCStock, FertilizerBatch
    today = timezone.localdate()
    q = request.GET.get('q', '').strip()
    date_filter = request.GET.get('date', '').strip()
    season_id = request.GET.get('season')
    asc_id = request.GET.get('asc')
    product_id = request.GET.get('product')
    issue_method = request.GET.get('issue_method')
    status_filter = request.GET.get('status')
    report_type = request.GET.get('type', 'distributions')

    distributions = FertilizerDistribution.objects.select_related(
        'farmer', 'asc_centre', 'batch__product', 'season', 'issued_by'
    ).order_by('-distributed_at')

    stocks = ASCStock.objects.select_related(
        'asc_centre', 'batch__product'
    ).order_by('batch__expiry_date')

    dispatches = StockDispatch.objects.select_related(
        'warehouse', 'asc_centre', 'created_by'
    ).order_by('-dispatched_at')

    # ASC Officer restriction
    if request.user.role == 'ASC_OFFICER' and request.user.asc_centre:
        distributions = distributions.filter(asc_centre=request.user.asc_centre)
        stocks = stocks.filter(asc_centre=request.user.asc_centre)
        dispatches = dispatches.filter(asc_centre=request.user.asc_centre)

    # General Search Query
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
        dispatches = dispatches.filter(
            Q(dispatch_reference__icontains=q) |
            Q(asc_centre__name__icontains=q) |
            Q(items__batch__batch_number__icontains=q)
        ).distinct()

    # Parametric Filters
    if asc_id:
        distributions = distributions.filter(asc_centre_id=asc_id)
        stocks = stocks.filter(asc_centre_id=asc_id)
        dispatches = dispatches.filter(asc_centre_id=asc_id)

    if season_id:
        distributions = distributions.filter(season_id=season_id)

    if product_id:
        distributions = distributions.filter(batch__product_id=product_id)
        stocks = stocks.filter(batch__product_id=product_id)
        dispatches = dispatches.filter(items__batch__product_id=product_id).distinct()

    if issue_method:
        distributions = distributions.filter(issue_method=issue_method)

    if status_filter:
        dispatches = dispatches.filter(status=status_filter)

    if date_filter:
        distributions = distributions.filter(distributed_at__date=date_filter)
        dispatches = dispatches.filter(dispatched_at__date=date_filter)

    # Annotate stock expiry health badges
    near_window = today + timezone.timedelta(days=60)
    for st in stocks:
        if st.batch.expiry_date < today:
            st.health_badge = 'EXPIRED'
            st.health_color = 'bg-rose-100 text-rose-800'
        elif st.batch.expiry_date <= near_window:
            st.health_badge = 'NEAR EXPIRY'
            st.health_color = 'bg-amber-100 text-amber-800'
        elif st.bags_on_hand < 10:
            st.health_badge = 'LOW STOCK'
            st.health_color = 'bg-orange-100 text-orange-800'
        else:
            st.health_badge = 'HEALTHY'
            st.health_color = 'bg-emerald-100 text-emerald-800'

    context = {
        'q': q,
        'date_filter': date_filter,
        'season_id': season_id,
        'asc_id': asc_id,
        'product_id': product_id,
        'issue_method': issue_method,
        'status_filter': status_filter,
        'report_type': report_type,
        'distributions': distributions[:250],
        'stocks': stocks,
        'dispatches': dispatches[:150],
        'seasons': Season.objects.all().order_by('-id'),
        'asc_centres': ASCCentre.objects.all(),
        'products': FertilizerProduct.objects.all(),
        'issue_methods': FertilizerDistribution.IssueMethodChoices.choices,
        'dispatch_statuses': StockDispatch.StatusChoices.choices,
    }
    return render(request, 'distributions/reports.html', context)


@role_required('ADMIN', 'AUDITOR', 'ASC_OFFICER', 'WAREHOUSE_OFFICER')
def export_report_csv(request):
    """
    Download filtered reports as CSV with UTF-8 BOM (\ufeff) for flawless Excel display
    of Sinhala, Tamil, and English Unicode text.
    """
    from inventory.models import StockDispatch, ASCStock
    report_type = request.GET.get('type', 'distributions')
    q = request.GET.get('q', '').strip()
    date_filter = request.GET.get('date', '').strip()
    asc_id = request.GET.get('asc')
    season_id = request.GET.get('season')
    product_id = request.GET.get('product')
    issue_method = request.GET.get('issue_method')
    status_filter = request.GET.get('status')

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="fertitracker_{report_type}_report.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)

    today = timezone.localdate()
    near_window = today + timezone.timedelta(days=60)

    if report_type == 'stocks':
        writer.writerow(['ASC Centre', 'Product', 'Batch Number', 'Expiry Date', 'Bags on Hand', 'Total Weight (kg)', 'Expiry Health Status'])
        qs = ASCStock.objects.select_related('asc_centre', 'batch__product').order_by('batch__expiry_date')
        if request.user.role == 'ASC_OFFICER' and request.user.asc_centre:
            qs = qs.filter(asc_centre=request.user.asc_centre)
        if asc_id:
            qs = qs.filter(asc_centre_id=asc_id)
        if product_id:
            qs = qs.filter(batch__product_id=product_id)
        if q:
            qs = qs.filter(Q(batch__batch_number__icontains=q) | Q(asc_centre__name__icontains=q))

        for st in qs:
            if st.batch.expiry_date < today:
                status = 'EXPIRED'
            elif st.batch.expiry_date <= near_window:
                status = 'NEAR EXPIRY (<60d)'
            elif st.bags_on_hand < 10:
                status = 'LOW STOCK'
            else:
                status = 'HEALTHY'

            writer.writerow([
                st.asc_centre.name,
                st.batch.product.name,
                st.batch.batch_number,
                st.batch.expiry_date,
                st.bags_on_hand,
                st.total_weight_kg,
                status
            ])

    elif report_type == 'dispatches':
        writer.writerow([
            'Dispatch Reference', 'Warehouse', 'ASC Centre', 'Status',
            'Dispatched Date', 'Batch Numbers', 'Dispatched Bags', 'Received Bags', 'Damaged Bags', 'Missing Bags'
        ])
        qs = StockDispatch.objects.select_related('warehouse', 'asc_centre').prefetch_related('items__batch').order_by('-dispatched_at')
        if request.user.role == 'ASC_OFFICER' and request.user.asc_centre:
            qs = qs.filter(asc_centre=request.user.asc_centre)
        if asc_id:
            qs = qs.filter(asc_centre_id=asc_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if date_filter:
            qs = qs.filter(dispatched_at__date=date_filter)
        if q:
            qs = qs.filter(Q(dispatch_reference__icontains=q) | Q(items__batch__batch_number__icontains=q)).distinct()

        for d in qs:
            items = list(d.items.all())
            batches_str = ", ".join(i.batch.batch_number for i in items)
            dispatched = sum(i.dispatched_bags for i in items)
            received = sum(i.received_bags for i in items)
            damaged = sum(i.damaged_bags for i in items)
            missing = sum(i.missing_bags for i in items)
            writer.writerow([
                d.dispatch_reference, d.warehouse.name, d.asc_centre.name,
                d.get_status_display(), d.dispatched_at.strftime('%Y-%m-%d %H:%M'),
                batches_str, dispatched, received, damaged, missing
            ])

    else:
        # Farmer Distribution Report
        writer.writerow([
            'Receipt No', 'Farmer Name', 'Masked NIC', 'ASC Centre', 'Product',
            'Batch No', 'Quantity (kg)', 'Issue Method', 'Season', 'Issued By', 'Distributed Date'
        ])
        qs = FertilizerDistribution.objects.select_related(
            'farmer', 'asc_centre', 'batch__product', 'season', 'issued_by'
        ).order_by('-distributed_at')

        if request.user.role == 'ASC_OFFICER' and request.user.asc_centre:
            qs = qs.filter(asc_centre=request.user.asc_centre)
        if asc_id:
            qs = qs.filter(asc_centre_id=asc_id)
        if season_id:
            qs = qs.filter(season_id=season_id)
        if product_id:
            qs = qs.filter(batch__product_id=product_id)
        if issue_method:
            qs = qs.filter(issue_method=issue_method)
        if date_filter:
            qs = qs.filter(distributed_at__date=date_filter)
        if q:
            qs = qs.filter(
                Q(farmer__nic_number__icontains=q) |
                Q(farmer__full_name__icontains=q) |
                Q(batch__batch_number__icontains=q) |
                Q(receipt_number__icontains=q)
            )

        for dist in qs[:1000]:
            writer.writerow([
                dist.receipt_number,
                dist.farmer.full_name,
                dist.farmer.masked_nic,
                dist.asc_centre.name,
                dist.batch.product.name,
                dist.batch.batch_number,
                dist.quantity_kg,
                dist.get_issue_method_display(),
                dist.season.name,
                dist.issued_by.username if dist.issued_by else 'System',
                dist.distributed_at.strftime('%Y-%m-%d %H:%M')
            ])

    AuditLog.objects.create(
        user=request.user,
        action="REPORT_EXPORTED_CSV",
        details=f"Exported {report_type} report to CSV with UTF-8 BOM."
    )
    return response

@role_required('ADMIN', 'ASC_OFFICER')
def manage_farmers_and_bulk_import_view(request):
    """
    1. CSV මඟින් ගොවීන් සහ Entitlements තොග වශයෙන් (Bulk) ඇතුළත් කිරීම.
    2. තනි ගොවියෙකු ලියාපදිංචි කිරීම (FR-A3).
    3. ගොවියෙකුගේ දුරකථන අංකය NIC පරීක්ෂාවෙන් පසු ආරක්ෂිතව වෙනස් කිරීම.
    """
    seasons = Season.objects.all().order_by('-id')
    products = FertilizerProduct.objects.all()
    farmers_list = Farmer.objects.select_related('user').order_by('-id')[:50]

    if request.method == 'POST':
        action = request.POST.get('action')

@role_required('ADMIN', 'ASC_OFFICER')
def manage_farmers_and_bulk_import_view(request):
    """
    Manage farmer registrations, phone updates, and entitlement CSV imports:
    - Single registration with strict Sri Lankan NIC & phone validation (account starts INACTIVE)
    - Phone number updates require in-person NIC verification checkbox, audited with masked numbers
    - Two-phase CSV import: upload -> validation preview with errors highlighted -> all-or-nothing atomic import
    """
    seasons = Season.objects.all().order_by('-id')
    products = FertilizerProduct.objects.all()
    farmers_list = Farmer.objects.select_related('user').prefetch_related('entitlements__season', 'entitlements__product').order_by('-id')[:50]

    if request.method == 'POST':
        action = request.POST.get('action')

        # A. CSV Bulk Import Phase 1: Upload and Validation Preview
        if action == 'bulk_csv_import':
            csv_file = request.FILES.get('csv_file')
            season_id = request.POST.get('season')

            if not csv_file or not csv_file.name.endswith('.csv'):
                messages.error(request, _("Please select a valid .csv file."))
                return redirect('manage_farmers')

            season = get_object_or_404(Season, id=season_id)

            try:
                # Read with utf-8-sig to handle both UTF-8 with and without BOM
                raw_bytes = csv_file.read()
                decoded_text = raw_bytes.decode('utf-8-sig')
                reader = csv.DictReader(io.StringIO(decoded_text))

                validated_rows = []
                has_errors = False
                valid_count = 0
                error_count = 0

                for row_idx, row in enumerate(reader, start=2):  # row 1 is header
                    # Support flexible header variations: nic, nic_number, NIC
                    raw_nic = (row.get('nic') or row.get('nic_number') or row.get('NIC') or '').strip()
                    raw_product = (row.get('product') or row.get('product_name') or row.get('Product') or '').strip()
                    raw_qty = (row.get('quantity_kg') or row.get('approved_kg') or row.get('quota_kg') or row.get('Quantity') or '').strip()

                    row_errors = []

                    # 1. Validate NIC
                    clean_nic = ""
                    try:
                        clean_nic = validate_sri_lankan_nic(raw_nic)
                    except ValidationError as e:
                        row_errors.append(str(e.message if hasattr(e, 'message') else e))

                    # 2. Check Farmer Existence
                    farmer = None
                    if clean_nic and not row_errors:
                        farmer = Farmer.objects.filter(nic_number__iexact=clean_nic).first()
                        if not farmer:
                            row_errors.append(_("Farmer with NIC '%(nic)s' is not registered in the system.") % {'nic': clean_nic})

                    # 3. Check Product Existence
                    product = None
                    if raw_product:
                        product = FertilizerProduct.objects.filter(name__iexact=raw_product).first()
                        if not product:
                            row_errors.append(_("Product '%(prod)s' was not found.") % {'prod': raw_product})
                    else:
                        row_errors.append(_("Product name is required."))

                    # 4. Check Quantity
                    qty_val = None
                    try:
                        qty_val = Decimal(raw_qty)
                        if qty_val <= 0:
                            row_errors.append(_("Quantity must be greater than 0 kg."))
                    except Exception:
                        row_errors.append(_("Invalid numeric quantity: '%(qty)s'.") % {'qty': raw_qty})

                    is_valid = len(row_errors) == 0
                    if is_valid:
                        valid_count += 1
                    else:
                        has_errors = True
                        error_count += 1

                    validated_rows.append({
                        'row_num': row_idx,
                        'nic': clean_nic or raw_nic,
                        'farmer_name': farmer.full_name if farmer else "-",
                        'product_name': product.name if product else raw_product,
                        'product_id': product.id if product else None,
                        'farmer_id': farmer.id if farmer else None,
                        'quantity_kg': str(qty_val) if qty_val is not None else raw_qty,
                        'is_valid': is_valid,
                        'errors': row_errors,
                    })

                if not validated_rows:
                    messages.error(request, _("The uploaded CSV file is empty."))
                    return redirect('manage_farmers')

                request.session['entitlement_csv_preview'] = {
                    'season_id': season.id,
                    'season_name': season.name,
                    'rows': validated_rows,
                    'has_errors': has_errors,
                    'valid_count': valid_count,
                    'error_count': error_count,
                }
                return redirect('preview_entitlement_csv')

            except Exception as e:
                messages.error(request, _("Error reading CSV file: %(err)s") % {'err': str(e)})
                return redirect('manage_farmers')

        # B. Single Farmer Registration (Strict NIC & Mobile Validation, Account starts INACTIVE)
        elif action == 'register_single_farmer':
            nic = request.POST.get('nic_number', '').strip()
            full_name = request.POST.get('full_name', '').strip()
            mobile = request.POST.get('mobile_number', '').strip()
            arpa = request.POST.get('arpa_division', '').strip()
            season_id = request.POST.get('season')
            product_id = request.POST.get('product')

            # 1. Validate Sri Lankan NIC format
            try:
                clean_nic = validate_sri_lankan_nic(nic)
            except ValidationError as e:
                messages.error(request, e.message if hasattr(e, 'message') else str(e))
                return redirect('manage_farmers')

            # 2. Check NIC uniqueness
            if Farmer.objects.filter(nic_number__iexact=clean_nic).exists() or User.objects.filter(username__iexact=clean_nic).exists():
                messages.error(request, _("A farmer with NIC '%(nic)s' is already registered.") % {'nic': clean_nic})
                return redirect('manage_farmers')

            # 3. Validate Sri Lankan Mobile format
            try:
                clean_mobile = validate_sri_lankan_phone(mobile)
            except ValidationError as e:
                messages.error(request, e.message if hasattr(e, 'message') else str(e))
                return redirect('manage_farmers')

            # 4. Validate quota
            try:
                quota_kg = Decimal(request.POST.get('approved_kg', '50.00').strip())
                if quota_kg <= 0:
                    raise ValueError()
            except Exception:
                messages.error(request, _("Quota must be a valid positive number."))
                return redirect('manage_farmers')

            with transaction.atomic():
                # Account starts INACTIVE (must activate via simulated SMS OTP)
                user_obj = User.objects.create(
                    username=clean_nic,
                    role=User.RoleChoices.FARMER,
                    is_account_active=False,
                    asc_centre=request.user.asc_centre if request.user.asc_centre else None
                )
                user_obj.set_unusable_password()
                user_obj.save()

                farmer_obj = Farmer.objects.create(
                    user=user_obj,
                    nic_number=clean_nic,
                    full_name=full_name,
                    mobile_number=clean_mobile,
                    arpa_division=arpa,
                )

                if season_id and product_id:
                    FarmerEntitlement.objects.create(
                        farmer=farmer_obj,
                        season_id=season_id,
                        product_id=product_id,
                        approved_kg=quota_kg,
                        remaining_kg=quota_kg
                    )

                AuditLog.objects.create(
                    user=request.user,
                    action="FARMER_REGISTERED",
                    details=f"Registered farmer {full_name} (NIC: {clean_nic}, Phone: {mask_phone_number(clean_mobile)}). Initial status: INACTIVE (Pending OTP activation)."
                )

            messages.success(
                request,
                _("Farmer %(name)s (%(nic)s) registered successfully! Account is INACTIVE until activated via OTP.")
                % {'name': full_name, 'nic': clean_nic}
            )
            return redirect('manage_farmers')

        # C. Phone Number Update by ASC Officer (Requires In-Person NIC Verification, Masked Audit Log)
        elif action == 'update_phone':
            if request.user.role != 'ASC_OFFICER':
                return forbid_response(request, _("Only counter officers at the Agrarian Service Centre may update farmer phone numbers following in-person NIC verification."))

            nic = request.POST.get('nic_number', '').strip()
            new_mobile = request.POST.get('new_mobile', '').strip()
            reason = request.POST.get('reason', 'In-person NIC verification at ASC').strip()
            in_person_verified = request.POST.get('in_person_verified') == 'on'

            if not in_person_verified:
                messages.error(request, _("Security policy requires confirming in-person verification of the original National Identity Card."))
                return redirect('manage_farmers')

            farmer_obj = Farmer.objects.filter(nic_number__iexact=nic).first()
            if not farmer_obj:
                messages.error(request, _("No registered farmer found with NIC '%(nic)s'.") % {'nic': nic})
                return redirect('manage_farmers')

            try:
                clean_new_mobile = validate_sri_lankan_phone(new_mobile)
            except ValidationError as e:
                messages.error(request, e.message if hasattr(e, 'message') else str(e))
                return redirect('manage_farmers')

            old_mobile = farmer_obj.mobile_number
            farmer_obj.mobile_number = clean_new_mobile
            farmer_obj.save()

            AuditLog.objects.create(
                user=request.user,
                action="FARMER_PHONE_UPDATED",
                details=(
                    f"NIC {farmer_obj.masked_nic}: Phone changed from {mask_phone_number(old_mobile)} "
                    f"to {mask_phone_number(clean_new_mobile)}. In-person verification: Verified. Reason: {reason}"
                )
            )
            messages.success(
                request,
                _("Phone number for farmer %(nic)s updated to %(phone)s and recorded in audit log.")
                % {'nic': farmer_obj.masked_nic, 'phone': clean_new_mobile}
            )
            return redirect('manage_farmers')

    context = {
        'seasons': seasons,
        'products': products,
        'farmers_list': farmers_list,
    }
    return render(request, 'distributions/manage_farmers.html', context)


@role_required('ADMIN', 'ASC_OFFICER')
def preview_entitlement_csv_view(request):
    """
    Phase 2 of CSV Import:
    Render preview table with invalid rows highlighted in red and specific errors displayed.
    Enforces all-or-nothing atomic commit (commits only if 100% of rows are valid).
    """
    preview_data = request.session.get('entitlement_csv_preview')
    if not preview_data:
        messages.warning(request, _("No CSV preview session found. Please upload a CSV file."))
        return redirect('manage_farmers')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'cancel':
            request.session.pop('entitlement_csv_preview', None)
            messages.info(request, _("CSV import cancelled."))
            return redirect('manage_farmers')

        elif action == 'confirm_import':
            if preview_data.get('has_errors'):
                messages.error(
                    request,
                    _("Cannot import: The file contains errors. All-or-nothing policy requires correcting all errors before import.")
                )
                return render(request, 'distributions/entitlement_csv_preview.html', {'preview': preview_data})

            season_id = preview_data['season_id']
            rows = preview_data['rows']
            imported_count = 0

            with transaction.atomic():
                for r in rows:
                    FarmerEntitlement.objects.update_or_create(
                        farmer_id=r['farmer_id'],
                        season_id=season_id,
                        product_id=r['product_id'],
                        defaults={
                            'approved_kg': Decimal(r['quantity_kg']),
                            'remaining_kg': Decimal(r['quantity_kg']),
                        }
                    )
                    imported_count += 1

                AuditLog.objects.create(
                    user=request.user,
                    action="BULK_ENTITLEMENT_CSV_IMPORT",
                    details=f"All-or-nothing atomic import: {imported_count} entitlements committed for Season ID {season_id}."
                )

            request.session.pop('entitlement_csv_preview', None)
            messages.success(
                request,
                _("All-or-nothing atomic import successful! %(count)d farmer entitlements created/updated.") % {'count': imported_count}
            )
            return redirect('manage_farmers')

    return render(request, 'distributions/entitlement_csv_preview.html', {'preview': preview_data})


@role_required('ADMIN', 'ASC_OFFICER', 'AUDITOR')
def download_sample_entitlement_csv(request):
    """
    Download sample UTF-8 CSV with BOM for farmer entitlements (nic, product, quantity_kg).
    """
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="fertitracker_sample_entitlements.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['nic', 'product', 'quantity_kg'])
    writer.writerow(['198512345678', 'Urea', '50.00'])
    writer.writerow(['199023456789', 'Urea', '100.00'])
    writer.writerow(['751234567V', 'TSP', '50.00'])
    writer.writerow(['197812345678', 'MOP', '50.00'])
    return response


@role_required('ADMIN', 'ASC_OFFICER')
def edit_entitlement_view(request, entitlement_id):
    """
    Edit individual farmer entitlement quota.
    Every change records old and new values in the immutable AuditLog.
    """
    entitlement = get_object_or_404(
        FarmerEntitlement.objects.select_related('farmer', 'season', 'product'),
        id=entitlement_id
    )

    if request.method == 'POST':
        try:
            new_approved_kg = Decimal(request.POST.get('approved_kg', '0').strip())
            if new_approved_kg <= 0:
                raise ValidationError(_("Approved quota must be greater than 0 kg."))
        except Exception:
            messages.error(request, _("Please enter a valid positive number for approved quota."))
            return render(request, 'distributions/edit_entitlement.html', {'entitlement': entitlement})

        old_approved = entitlement.approved_kg
        old_remaining = entitlement.remaining_kg
        delta = new_approved_kg - old_approved
        new_remaining = max(Decimal('0.00'), old_remaining + delta)

        entitlement.approved_kg = new_approved_kg
        entitlement.remaining_kg = new_remaining
        entitlement.save()

        AuditLog.objects.create(
            user=request.user,
            action="ENTITLEMENT_EDITED",
            details=(
                f"Farmer {entitlement.farmer.masked_nic} quota for {entitlement.product.name} ({entitlement.season.name}) "
                f"updated by {request.user.username}: Approved {old_approved}kg -> {new_approved_kg}kg, "
                f"Remaining {old_remaining}kg -> {new_remaining}kg."
            )
        )
        messages.success(
            request,
            _("Entitlement updated! Approved: %(old)skg -> %(new)skg.") % {'old': old_approved, 'new': new_approved_kg}
        )
        return redirect('manage_farmers')

    return render(request, 'distributions/edit_entitlement.html', {'entitlement': entitlement})


# ==============================================================================
# PART 1: SMS BACKUP CODE (Keypad Phone Farmers)
# ==============================================================================

@role_required('ASC_OFFICER')
def farmer_search_view(request):
    """
    Search farmers by NIC or name for Keypad Phone SMS Code or Officer-Assisted Issue.
    Shows name and masked NIC only for privacy protection (Data Protection Principle).
    """
    q = request.GET.get('q', '').strip()
    farmers = []
    active_season = Season.objects.filter(status='ACTIVE').first()
    if q:
        farmers = Farmer.objects.filter(
            Q(nic_number__icontains=q) | Q(full_name__icontains=q)
        ).prefetch_related('entitlements')[:20]

    context = {
        'q': q,
        'farmers': farmers,
        'active_season': active_season,
    }
    return render(request, 'distributions/farmer_search.html', context)


@role_required('ASC_OFFICER')
def send_sms_code_view(request, farmer_id):
    """
    Generates a 6-digit backup code and sends via SMS to the farmer's registered phone number.
    Rate limited: max 3/hour, 60s cooldown. Bound to farmer and officer's ASC.
    """
    if request.method != 'POST':
        return redirect('farmer_search')

    farmer = get_object_or_404(Farmer, id=farmer_id)
    asc_centre = request.user.asc_centre or ASCCentre.objects.first()

    from .services import generate_sms_code_for_farmer
    try:
        raw_token, raw_code, token_obj = generate_sms_code_for_farmer(
            farmer=farmer,
            asc_centre=asc_centre,
            requested_by_user=request.user
        )
        messages.success(
            request,
            f"SMS verification code sent to {farmer.full_name}'s phone ({farmer.mobile_number}). "
            f"Ask the farmer for the 6-digit code and enter it below."
        )
    except ValidationError as e:
        messages.error(request, e.message)
        return redirect(f"{redirect('farmer_search').url}?q={farmer.nic_number}")

    return redirect('asc_scanner')


def demo_sms_inbox_view(request):
    """
    Demo SMS Inbox: displays simulated SMS messages when DEMO_MODE=True.
    Used for exhibition demonstration without a real SMS gateway.
    """
    if not getattr(settings, 'DEMO_MODE', False):
        return HttpResponse("Demo mode is disabled in production.", status=403)

    phone_filter = request.GET.get('phone', '').strip()
    messages_qs = SMSOutbox.objects.select_related('farmer').order_by('-created_at')
    if request.user.is_authenticated and request.user.role == 'FARMER':
        farmer_profile = Farmer.objects.filter(user=request.user).first()
        if farmer_profile:
            messages_qs = messages_qs.filter(
                Q(farmer=farmer_profile) | Q(phone_number=farmer_profile.mobile_number)
            )
        else:
            messages_qs = messages_qs.none()
    if phone_filter:
        messages_qs = messages_qs.filter(phone_number__icontains=phone_filter)

    context = {
        'sms_messages': messages_qs[:50],
        'phone_filter': phone_filter,
    }
    return render(request, 'distributions/demo_sms_inbox.html', context)


# ==============================================================================
# PART 2: OFFICER-ASSISTED ISSUE (Farmers with No Phone)
# ==============================================================================

@role_required('ASC_OFFICER')
def create_assisted_request_view(request, farmer_id):
    """
    Create an Officer-Assisted Issue request for a farmer with no phone,
    lost phone, or elderly/disabled status.
    Requires selecting a mandatory reason (and explanation note if 'OTHER').
    """
    farmer = get_object_or_404(Farmer, id=farmer_id)
    active_seasons = Season.objects.filter(status='ACTIVE')
    asc_centre = request.user.asc_centre or ASCCentre.objects.first()

    if request.method == 'POST':
        season_id = request.POST.get('season')
        reason = request.POST.get('reason')
        reason_note = request.POST.get('reason_note', '').strip()
        season = get_object_or_404(Season, id=season_id)

        from .services import create_assisted_issue_request
        try:
            approval = create_assisted_issue_request(
                farmer=farmer,
                asc_centre=asc_centre,
                season=season,
                requested_by_user=request.user,
                reason=reason,
                reason_note=reason_note
            )
            messages.success(
                request,
                f"Assisted issue request #{approval.id} submitted for {farmer.full_name}. "
                f"Pending approval from the ASC Head (valid for 30 minutes)."
            )
            return redirect('pending_assisted_requests')
        except ValidationError as e:
            messages.error(request, e.message)

    context = {
        'farmer': farmer,
        'seasons': active_seasons,
        'asc_centre': asc_centre,
        'reasons': AssistedIssueApproval.ReasonChoices.choices,
    }
    return render(request, 'distributions/create_assisted_request.html', context)


@role_required('ASC_OFFICER')
def pending_assisted_requests_view(request):
    """
    Dashboard for pending and approved assisted issues at the ASC Centre.
    ASC Heads can approve/reject; counter officers can issue approved requests.
    """
    asc_centre = request.user.asc_centre
    now = timezone.now()

    qs = AssistedIssueApproval.objects.select_related(
        'farmer', 'asc_centre', 'season', 'requested_by', 'approved_by'
    ).order_by('-created_at')

    if asc_centre and request.user.role != 'ADMIN' and not request.user.is_superuser:
        qs = qs.filter(asc_centre=asc_centre)

    pending_requests = qs.filter(status=AssistedIssueApproval.StatusChoices.PENDING, expires_at__gt=now)
    approved_requests = qs.filter(status=AssistedIssueApproval.StatusChoices.APPROVED, expires_at__gt=now)
    recent_history = qs.exclude(status__in=[AssistedIssueApproval.StatusChoices.PENDING, AssistedIssueApproval.StatusChoices.APPROVED])[:20]

    is_head = getattr(request.user, 'is_asc_head', False) and request.user.role == 'ASC_OFFICER'

    context = {
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'recent_history': recent_history,
        'is_head': is_head,
    }
    return render(request, 'distributions/pending_assisted_requests.html', context)


@require_asc_head
def approve_assisted_request_view(request, request_id):
    """
    Approve an assisted issue request under the Two-Officer Rule.
    Enforces requester != approver and approver is ASC Head of the same ASC.
    """
    if request.method != 'POST':
        return redirect('pending_assisted_requests')

    approval = get_object_or_404(AssistedIssueApproval, id=request_id)
    if not can_approve_assisted_request(request.user, approval):
        return forbid_response(request, _("Two-Officer Rule Violation: You cannot approve this request."))

    from .services import approve_assisted_issue_request
    try:
        approval = approve_assisted_issue_request(request_id, request.user)
        messages.success(request, f"Assisted issue #{approval.id} for {approval.farmer.full_name} has been APPROVED.")
    except ValidationError as e:
        messages.error(request, e.message)

    return redirect('pending_assisted_requests')


@require_asc_head
def reject_assisted_request_view(request, request_id):
    """Reject an assisted issue request with an optional note."""
    if request.method != 'POST':
        return redirect('pending_assisted_requests')

    approval = get_object_or_404(AssistedIssueApproval, id=request_id)
    if not can_approve_assisted_request(request.user, approval):
        return forbid_response(request, _("Two-Officer Rule Violation: You cannot reject this request."))

    rejection_reason = request.POST.get('rejection_reason', '').strip()
    from .services import reject_assisted_issue_request
    try:
        approval = reject_assisted_issue_request(request_id, request.user, rejection_reason)
        messages.success(request, f"Assisted issue #{approval.id} has been REJECTED.")
    except ValidationError as e:
        messages.error(request, e.message)

    return redirect('pending_assisted_requests')


@role_required('ASC_OFFICER')
def assisted_issue_confirm_view(request, approval_id):
    """
    Confirmation screen for issuing fertilizer under an approved assisted issue.
    """
    approval = get_object_or_404(
        AssistedIssueApproval.objects.select_related('farmer', 'asc_centre', 'season', 'approved_by'),
        id=approval_id
    )

    if request.user.asc_centre_id != approval.asc_centre_id:
        return forbid_response(request, _("You can only issue fertilizer for your assigned Agrarian Service Centre."))

    if not approval.is_valid_for_issue():
        messages.error(request, "This approval is no longer valid or has expired.")
        return redirect('pending_assisted_requests')

    farmer = approval.farmer
    entitlement = FarmerEntitlement.objects.filter(
        farmer=farmer,
        season=approval.season,
        product__name__iexact='Urea'
    ).first()

    asc_stock = ASCStock.objects.filter(
        asc_centre=approval.asc_centre,
        batch__product=entitlement.product if entitlement else None,
        bags_on_hand__gt=0
    ).order_by('batch__expiry_date').first()

    if request.method == 'POST':
        quantity_kg = request.POST.get('quantity_kg')
        from .services import confirm_issue_distribution
        try:
            distribution = confirm_issue_distribution(
                assisted_approval_id=approval.id,
                asc_officer_user=request.user,
                quantity_kg=Decimal(quantity_kg) if quantity_kg else None,
                client_ip=request.META.get('REMOTE_ADDR')
            )
            messages.success(
                request,
                f"Fertilizer issued under Assisted Issue approval. Receipt: {distribution.receipt_number}"
            )
            return redirect('distribution_receipt', receipt_number=distribution.receipt_number)
        except (ValidationError, Exception) as e:
            messages.error(request, getattr(e, 'message', str(e)))

    context = {
        'approval': approval,
        'farmer': farmer,
        'entitlement': entitlement,
        'asc_stock': asc_stock,
    }
    return render(request, 'distributions/confirm_assisted_issue.html', context)


@role_required('ADMIN', 'AUDITOR')
def assisted_issues_report_view(request):
    """
    Auditor and Admin report tracking all officer-assisted issues.
    Calculates:
    - Total issues and assisted issues count
    - Percentage of all issues that were assisted
    - Per-officer breakdown: officer name, total issues, assisted count, assisted %
    - Breakdown by reason
    """
    asc_centre_id = request.GET.get('asc_centre')
    officer_id = request.GET.get('officer')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    distributions_qs = FertilizerDistribution.objects.select_related(
        'farmer', 'asc_centre', 'issued_by', 'assisted_approval__approved_by'
    ).order_by('-distributed_at')

    if asc_centre_id:
        distributions_qs = distributions_qs.filter(asc_centre_id=asc_centre_id)
    if officer_id:
        distributions_qs = distributions_qs.filter(issued_by_id=officer_id)
    if start_date:
        distributions_qs = distributions_qs.filter(distributed_at__date__gte=start_date)
    if end_date:
        distributions_qs = distributions_qs.filter(distributed_at__date__lte=end_date)

    total_count = distributions_qs.count()
    assisted_qs = distributions_qs.filter(issue_method=FertilizerDistribution.IssueMethodChoices.ASSISTED)
    assisted_count = assisted_qs.count()
    assisted_pct = round((assisted_count / total_count * 100), 1) if total_count > 0 else 0

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="fertitracker_assisted_issues_report.csv"'
        response.write('\ufeff')
        writer = csv.writer(response)
        writer.writerow([
            'Receipt No', 'Farmer Name', 'Masked NIC', 'ASC Centre', 'Season',
            'Reason', 'Reason Note', 'Requested By', 'Approved By', 'Quantity (kg)', 'Issued Date'
        ])
        for dist in assisted_qs:
            app = dist.assisted_approval
            writer.writerow([
                dist.receipt_number,
                dist.farmer.full_name,
                dist.farmer.masked_nic,
                dist.asc_centre.name,
                dist.season.name,
                app.get_reason_display() if app else 'N/A',
                app.reason_note if app and app.reason_note else '',
                app.requested_by.username if app and app.requested_by else (dist.issued_by.username if dist.issued_by else ''),
                app.approved_by.username if app and app.approved_by else 'N/A',
                dist.quantity_kg,
                dist.distributed_at.strftime('%Y-%m-%d %H:%M')
            ])
        return response

    # Breakdown by reason
    reason_breakdown = AssistedIssueApproval.objects.filter(
        distributions__in=assisted_qs
    ).values('reason').annotate(count=Count('id')).order_by('-count')

    # Breakdown by officer
    officers = User.objects.filter(role__in=['ASC_OFFICER', 'ADMIN'])
    officer_stats = []
    for off in officers:
        off_total = distributions_qs.filter(issued_by=off).count()
        if off_total > 0:
            off_assisted = distributions_qs.filter(
                issued_by=off,
                issue_method=FertilizerDistribution.IssueMethodChoices.ASSISTED
            ).count()
            off_pct = round((off_assisted / off_total * 100), 1)
            officer_stats.append({
                'officer': off,
                'total_issues': off_total,
                'assisted_issues': off_assisted,
                'assisted_pct': off_pct,
            })

    context = {
        'distributions': assisted_qs[:100],
        'total_count': total_count,
        'assisted_count': assisted_count,
        'assisted_pct': assisted_pct,
        'reason_breakdown': reason_breakdown,
        'officer_stats': officer_stats,
        'asc_centres': ASCCentre.objects.all(),
        'officers': officers,
        'selected_asc': asc_centre_id,
        'selected_officer': officer_id,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'distributions/assisted_issues_report.html', context)

