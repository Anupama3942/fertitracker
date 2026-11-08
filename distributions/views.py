from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import ValidationError
from accounts.decorators import role_required
from core.models import Season, FertilizerProduct
from farmers.models import Farmer, QRToken, FarmerEntitlement
from .models import FertilizerDistribution, AuditLog
from .services import process_qr_distribution
import csv
from django.http import HttpResponse
from django.db.models import Q
import inventory.models as inv_models
from inventory.models import ASCStock
import io
from decimal import Decimal
from django.db import transaction
from accounts.models import User



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
    if request.method == 'POST':
        raw_token, qr_obj = QRToken.generate_token_for_farmer(farmer)
        messages.success(request, "තත්පර 60ක් සඳහා වලංගු නව QR කේතයක් උත්පාදනය කරන ලදී! / புதிய QR குறியீடு உருவாக்கப்பட்டது!")

    active_token = farmer.qr_tokens.filter(is_redeemed=False).order_by('-expires_at').first()
    is_active_valid = active_token.is_valid() if active_token else False

    context = {
        'farmer': farmer,
        'entitlements': entitlements,
        'issue_history': issue_history,
        'latest_issue': latest_issue,
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

        # A. CSV Bulk Import
        if action == 'bulk_csv_import':
            csv_file = request.FILES.get('csv_file')
            season_id = request.POST.get('season')
            product_id = request.POST.get('product')

            if not csv_file or not csv_file.name.endswith('.csv'):
                messages.error(request, "කරුණාකර වලංගු .csv ගොනුවක් තෝරන්න.")
                return redirect('manage_farmers')

            try:
                data_set = csv_file.read().decode('UTF-8')
                io_string = io.StringIO(data_set)
                reader = csv.DictReader(io_string)
                imported_count = 0

                with transaction.atomic():
                    for row in reader:
                        nic = row.get('nic_number', '').strip()
                        full_name = row.get('full_name', '').strip()
                        mobile = row.get('mobile_number', '').strip()
                        arpa = row.get('arpa_division', 'Default ARPA').strip()
                        quota_kg = Decimal(row.get('approved_kg', '50.00').strip())

                        if not nic or not full_name:
                            continue

                        # ගොවියාට අදාළ User ගිණුමක් සෑදීම (Inactive ලෙස - OTP මඟින් සක්‍රිය කළ යුතුය)
                        user_obj, created_user = User.objects.get_or_create(
                            username=nic,
                            defaults={
                                'role': 'FARMER',
                                'is_account_active': False,
                                'asc_centre': request.user.asc_centre if request.user.asc_centre else None
                            }
                        )
                        if created_user:
                            user_obj.set_unusable_password()
                            user_obj.save()

                        # Farmer Profile සෑදීම හෝ යාවත්කාලීන කිරීම
                        farmer_obj, _ = Farmer.objects.update_or_create(
                            nic_number=nic,
                            defaults={
                                'user': user_obj,
                                'full_name': full_name,
                                'mobile_number': mobile,
                                'arpa_division': arpa,
                            }
                        )

                        # Entitlement (Quota) සෑදීම හෝ යාවත්කාලීන කිරීම
                        FarmerEntitlement.objects.update_or_create(
                            farmer=farmer_obj,
                            season_id=season_id,
                            product_id=product_id,
                            defaults={
                                'approved_kg': quota_kg,
                                'remaining_kg': quota_kg,
                            }
                        )
                        imported_count += 1

                AuditLog.objects.create(
                    user=request.user,
                    action="BULK_ENTITLEMENT_CSV_IMPORT",
                    details=f"Imported {imported_count} farmer entitlements for Season ID {season_id}."
                )
                messages.success(request, f"ගොවි වාර්තා සහ කෝටා {imported_count}ක් සාර්ථකව CSV මඟින් ඇතුළත් කරන ලදී!")
            except Exception as e:
                messages.error(request, f"CSV ගොනුව කියවීමේදී දෝෂයක් ඇති විය: {e}")

            return redirect('manage_farmers')

        # B. තනි ගොවියෙකු ලියාපදිංචි කිරීම (Single Registration - FR-A3)
        elif action == 'register_single_farmer':
            nic = request.POST.get('nic_number', '').strip()
            full_name = request.POST.get('full_name', '').strip()
            mobile = request.POST.get('mobile_number', '').strip()
            arpa = request.POST.get('arpa_division', '').strip()
            season_id = request.POST.get('season')
            product_id = request.POST.get('product')
            quota_kg = Decimal(request.POST.get('approved_kg', '50.00'))

            with transaction.atomic():
                user_obj, created = User.objects.get_or_create(
                    username=nic,
                    defaults={
                        'role': 'FARMER',
                        'is_account_active': False,
                        'asc_centre': request.user.asc_centre
                    }
                )
                if created:
                    user_obj.set_unusable_password()
                    user_obj.save()

                farmer_obj, _ = Farmer.objects.update_or_create(
                    nic_number=nic,
                    defaults={
                        'user': user_obj,
                        'full_name': full_name,
                        'mobile_number': mobile,
                        'arpa_division': arpa,
                    }
                )

                FarmerEntitlement.objects.update_or_create(
                    farmer=farmer_obj,
                    season_id=season_id,
                    product_id=product_id,
                    defaults={'approved_kg': quota_kg, 'remaining_kg': quota_kg}
                )

                AuditLog.objects.create(
                    user=request.user,
                    action="FARMER_REGISTERED",
                    details=f"Registered farmer {full_name} (NIC: {nic}) with {quota_kg}kg entitlement."
                )
            messages.success(request, f"{full_name} ({nic}) ගොවි මහතා/මහත්මිය සාර්ථකව ලියාපදිංචි කරන ලදී. දැන් OTP මඟින් ගිණුම සක්‍රිය කළ හැක.")
            return redirect('manage_farmers')

        # C. ගොවියාගේ දුරකථන අංකය නිලධාරියා විසින් ආරක්ෂිතව වෙනස් කිරීම
        elif action == 'update_phone':
            nic = request.POST.get('nic_number', '').strip()
            new_mobile = request.POST.get('new_mobile', '').strip()
            reason = request.POST.get('reason', 'In-person NIC verification at ASC').strip()

            farmer_obj = Farmer.objects.filter(nic_number=nic).first()
            if not farmer_obj:
                messages.error(request, "මෙම NIC අංකයට අදාළ ගොවියෙකු හමු නොවීය.")
            else:
                old_mobile = farmer_obj.mobile_number
                farmer_obj.mobile_number = new_mobile
                farmer_obj.save()

                AuditLog.objects.create(
                    user=request.user,
                    action="FARMER_PHONE_UPDATED",
                    details=f"NIC {nic}: Phone changed from {old_mobile} to {new_mobile}. Reason: {reason}"
                )
                messages.success(request, f"NIC {nic} හිමි ගොවියාගේ දුරකථන අංකය {new_mobile} ලෙස යාවත්කාලීන කර Audit Log හි සටහන් කරන ලදී.")
            return redirect('manage_farmers')

    context = {
        'seasons': seasons,
        'products': products,
        'farmers_list': farmers_list,
    }
    return render(request, 'distributions/manage_farmers.html', context)
