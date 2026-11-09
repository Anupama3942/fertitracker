import secrets
import string
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash, login, logout, authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.conf import settings
from core.models import Warehouse, ASCCentre, Season, FertilizerProduct
from .models import User, PasswordResetOTP
from django.utils import timezone
from farmers.models import Farmer
from distributions.models import AuditLog, FertilizerDistribution
from .services import SMSNotificationService
from datetime import timedelta
from django.db.models import Sum
from inventory.models import ASCStock, StockDispatch
from accounts.decorators import role_required

# Create your views here.

def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        client_ip = request.META.get('REMOTE_ADDR')

        user_obj = User.objects.filter(username=username).first()

        # Check deactivated account
        if user_obj and not user_obj.is_active:
            AuditLog.objects.create(user=user_obj, action="LOGIN_DEACTIVATED_USER", ip_address=client_ip, details="Attempted login on deactivated account.")
            messages.error(request, _("This account has been deactivated. Please contact your system administrator."))
            return render(request, 'accounts/login.html')

        # 1. Check if account is locked out
        if user_obj and user_obj.is_locked():
            remaining_mins = int((user_obj.locked_until - timezone.now()).total_seconds() // 60) + 1
            messages.error(request, _("Too many failed attempts. Account locked. Please try again in %(mins)d minutes.") % {'mins': remaining_mins})
            return render(request, 'accounts/login.html')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if not user.is_account_active:
                messages.error(request, _("Your account is not activated yet. Please activate using OTP."))
                return redirect('activate_account')

            # Successful login resets failure counters
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save()

            login(request, user)
            AuditLog.objects.create(user=user, action="USER_LOGIN_SUCCESS", ip_address=client_ip, details="User logged in successfully.")

            # නිලධාරියෙකුගේ පළමු login එක නම් මුරපදය වෙනස් කිරීමට යොමු කිරීම (FR-A2)
            if user.must_change_password:
                messages.warning(request, "ආරක්ෂක හේතූන් මත කරුණාකර ඔබගේ තාවකාලික මුරපදය දැන් වෙනස් කරන්න.")
                return redirect('force_password_change')

            if user.role == 'FARMER':
                return redirect('farmer_dashboard')
            return redirect('dashboard')
        else:
            # වැරදි මුරපදයක් නම් attempts ගණන වැඩි කිරීම සහ 5 වූ විට Lock කිරීම
            if user_obj:
                user_obj.failed_login_attempts += 1
                if user_obj.failed_login_attempts >= 5:
                    user_obj.locked_until = timezone.now() + timedelta(minutes=15)
                    AuditLog.objects.create(user=user_obj, action="ACCOUNT_LOCKED", ip_address=client_ip, details="Locked for 15 mins after 5 failed attempts.")
                    messages.error(request, "වැරදි උත්සාහයන් 5ක් සිදු කළ බැවින් ගිණුම මිනිත්තු 15කට අගුළු දමන ලදී.")
                else:
                    remaining = 5 - user_obj.failed_login_attempts
                    messages.error(request, f"Username හෝ Password වැරදිය. (ඉතිරි උත්සාහයන්: {remaining})")
                user_obj.save()
            else:
                messages.error(request, "Username හෝ Password වැරදිය.")

    return render(request, 'accounts/login.html')


@login_required
def dashboard_view(request):
    user = request.user
    if user.role == 'FARMER':
        return redirect('farmer_dashboard')

    today = timezone.localdate()
    is_asc_head = getattr(user, 'is_asc_head', False) or user.role == 'ADMIN' or user.is_superuser
    active_seasons = Season.objects.filter(status='ACTIVE')
    open_season = active_seasons.first()

    # Alerts using stock alerts service (near-expiry 60 days, low stock per threshold, expired)
    from inventory.services import get_stock_alerts
    from inventory.models import Discrepancy, FertilizerBatch
    from distributions.models import AssistedIssueApproval

    asc_filter = user.asc_centre if user.role == 'ASC_OFFICER' and user.asc_centre else None
    stock_alerts = get_stock_alerts(asc_centre=asc_filter)
    expired_stocks = stock_alerts['expired_stocks']
    near_expiry_stocks = stock_alerts['near_expiry_stocks']
    low_stocks = stock_alerts['low_stocks']

    # Stocks QuerySet
    stocks_qs = ASCStock.objects.select_related('asc_centre', 'batch__product').order_by('batch__expiry_date')
    if asc_filter:
        stocks_qs = stocks_qs.filter(asc_centre=asc_filter)

    for st in stocks_qs:
        if st.batch.expiry_date < today:
            st.alert_badge = 'EXPIRED'
            st.badge_color = 'bg-rose-100 text-rose-800 border-rose-300'
        elif st.batch.expiry_date <= stock_alerts['near_expiry_date']:
            st.alert_badge = 'NEAR EXPIRY'
            st.badge_color = 'bg-amber-100 text-amber-800 border-amber-300'
        elif st.bags_on_hand < getattr(settings, 'LOW_STOCK_THRESHOLD_BAGS', 10):
            st.alert_badge = 'LOW STOCK'
            st.badge_color = 'bg-orange-100 text-orange-800 border-orange-300'
        else:
            st.alert_badge = 'HEALTHY'
            st.badge_color = 'bg-emerald-100 text-emerald-800 border-emerald-300'

    # Role-specific Data Preparation
    context = {
        'today': today,
        'user': user,
        'is_asc_head': is_asc_head,
        'active_seasons': active_seasons,
        'open_season': open_season,
        'stocks': stocks_qs,
        'expired_stocks': expired_stocks,
        'near_expiry_stocks': near_expiry_stocks,
        'low_stocks': low_stocks,
    }

    # 1. ASC OFFICER & ASC HEAD Context
    if user.role in ['ASC_OFFICER', 'ADMIN'] or user.is_superuser:
        dist_qs = FertilizerDistribution.objects.select_related('farmer', 'asc_centre', 'batch__product')
        if asc_filter:
            dist_qs = dist_qs.filter(asc_centre=asc_filter)
        today_distributions = dist_qs.filter(distributed_at__date=today).order_by('-distributed_at')
        today_total_kg = today_distributions.aggregate(total=Sum('quantity_kg'))['total'] or 0

        incoming_dispatches = StockDispatch.objects.filter(
            status=StockDispatch.StatusChoices.DISPATCHED
        ).select_related('warehouse', 'asc_centre')
        if asc_filter:
            incoming_dispatches = incoming_dispatches.filter(asc_centre=asc_filter)

        pending_assisted_qs = AssistedIssueApproval.objects.filter(
            status=AssistedIssueApproval.StatusChoices.PENDING,
            expires_at__gt=timezone.now()
        ).select_related('farmer', 'asc_centre', 'requested_by')
        if asc_filter:
            pending_assisted_qs = pending_assisted_qs.filter(asc_centre=asc_filter)

        context.update({
            'today_distributions': today_distributions[:25],
            'today_total_kg': today_total_kg,
            'today_issue_count': today_distributions.count(),
            'incoming_dispatches': incoming_dispatches.order_by('-dispatched_at')[:10],
            'incoming_count': incoming_dispatches.count(),
            'pending_assisted_requests': pending_assisted_qs[:10],
            'pending_assisted_count': pending_assisted_qs.count(),
        })

    # 2. WAREHOUSE OFFICER Context
    if user.role in ['WAREHOUSE_OFFICER', 'ADMIN'] or user.is_superuser:
        wh_dispatches = StockDispatch.objects.select_related('warehouse', 'asc_centre', 'created_by').order_by('-dispatched_at')
        if getattr(user, 'warehouse', None) and user.role == 'WAREHOUSE_OFFICER':
            wh_dispatches = wh_dispatches.filter(warehouse=user.warehouse)

        wh_batches = FertilizerBatch.objects.select_related('warehouse', 'product').order_by('expiry_date')
        if getattr(user, 'warehouse', None) and user.role == 'WAREHOUSE_OFFICER':
            wh_batches = wh_batches.filter(warehouse=user.warehouse)

        context.update({
            'wh_dispatches': wh_dispatches[:15],
            'wh_batches': wh_batches[:15],
            'dispatched_count': wh_dispatches.filter(status=StockDispatch.StatusChoices.DISPATCHED).count(),
            'received_count': wh_dispatches.filter(status=StockDispatch.StatusChoices.RECEIVED).count(),
            'discrepancy_count': wh_dispatches.filter(status=StockDispatch.StatusChoices.RECEIVED_WITH_DISCREPANCY).count(),
        })

    # 3. ADMINISTRATOR Context
    if user.role == 'ADMIN' or user.is_superuser:
        all_seasons = Season.objects.all().order_by('-id')
        context.update({
            'total_users': User.objects.count(),
            'total_farmers': Farmer.objects.count(),
            'total_ascs': ASCCentre.objects.count(),
            'total_warehouses': Warehouse.objects.count(),
            'all_seasons': all_seasons,
        })

    # 4. AUDITOR Context
    if user.role in ['AUDITOR', 'ADMIN'] or user.is_superuser:
        total_issues = FertilizerDistribution.objects.count()
        assisted_issues = FertilizerDistribution.objects.filter(issue_method=FertilizerDistribution.IssueMethodChoices.ASSISTED).count()
        assisted_pct = round((assisted_issues / total_issues * 100), 1) if total_issues > 0 else 0

        discrepancies_list = Discrepancy.objects.select_related(
            'dispatch__asc_centre', 'dispatch__warehouse', 'recorded_by'
        ).order_by('-created_at')[:10]

        context.update({
            'total_issues': total_issues,
            'assisted_issues_count': assisted_issues,
            'assisted_pct': assisted_pct,
            'discrepancy_records': discrepancies_list,
            'total_discrepancies': Discrepancy.objects.count(),
            'expired_stock_count': len(stock_alerts['expired_stocks']),
            'recent_logs': AuditLog.objects.select_related('user').order_by('-timestamp')[:12],
        })

    return render(request, 'accounts/dashboard.html', context)


def activate_account_view(request):
    """
    Activate a farmer account with an OTP sent to the registered phone number.
    Rate limited (max 3/hr, 60s cooldown), 5-attempt lock, generic response for privacy.
    """
    step = request.session.get('activation_step', 1)
    nic = request.session.get('activation_nic', '')
    simulated_otp = request.session.get('simulated_otp', '')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'send_otp':
            nic = request.POST.get('nic', '').strip()
            farmer = Farmer.objects.filter(nic_number__iexact=nic).first()

            # Generic response ensures NIC existence is never leaked to unauthenticated users
            if farmer and farmer.user:
                try:
                    raw_otp = SMSNotificationService.send_otp(farmer.user, farmer.mobile_number, purpose="ACTIVATION")
                    request.session['activation_nic'] = nic
                    request.session['activation_step'] = 2
                    request.session['simulated_otp'] = raw_otp
                except ValidationError as e:
                    messages.error(request, e.message if hasattr(e, 'message') else str(e))
                    return redirect('activate_account')
            else:
                request.session['activation_nic'] = nic
                request.session['activation_step'] = 2
                request.session['simulated_otp'] = ''

            messages.success(request, _("If this National Identity Card (NIC) is registered, an OTP has been sent to the registered mobile number."))
            return redirect('activate_account')

        elif action == 'verify_and_set_password':
            entered_otp = request.POST.get('otp', '').strip()
            new_password = request.POST.get('new_password', '').strip()
            confirm_password = request.POST.get('confirm_password', '').strip()

            farmer = Farmer.objects.filter(nic_number__iexact=nic).first()
            if not farmer or not farmer.user:
                messages.error(request, _("Invalid verification session. Please try again."))
                return redirect('activate_account')

            user = farmer.user
            active_otp = PasswordResetOTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()

            if not active_otp or not active_otp.is_valid():
                messages.error(request, _("The OTP has expired or exceeded maximum failed attempts (5). Please request a new OTP."))
                return redirect('activate_account')

            if not active_otp.verify_entered_otp(entered_otp):
                remaining = max(0, 5 - active_otp.attempts)
                messages.error(request, _("The OTP is incorrect. Remaining attempts: %(remaining)d") % {'remaining': remaining})
                return redirect('activate_account')

            if new_password != confirm_password:
                messages.error(request, _("The passwords do not match."))
                return redirect('activate_account')

            try:
                validate_password(new_password, user=user)
            except ValidationError as e:
                for msg in e.messages:
                    messages.error(request, msg)
                return redirect('activate_account')

            # Activate account and store hashed password
            user.set_password(new_password)
            user.is_account_active = True
            user.save()

            active_otp.is_used = True
            active_otp.save()

            request.session.pop('activation_step', None)
            request.session.pop('activation_nic', None)
            request.session.pop('simulated_otp', None)

            AuditLog.objects.create(
                user=user,
                action="ACCOUNT_ACTIVATED",
                details=f"Farmer {farmer.masked_nic} activated account via HMAC-SHA256 OTP."
            )
            messages.success(request, _("Your account was activated successfully! You can now log in."))
            return redirect('login')

    return render(request, 'accounts/activate_account.html', {'step': step, 'simulated_otp': simulated_otp})


def password_reset_request_view(request):
    """
    Request a password-reset OTP using the farmer's NIC number.
    Returns generic response to prevent user enumeration attacks.
    """
    if request.method == 'POST':
        nic = request.POST.get('nic', '').strip()
        farmer = Farmer.objects.filter(nic_number__iexact=nic).first()

        if farmer and farmer.user:
            try:
                raw_otp = SMSNotificationService.send_otp(farmer.user, farmer.mobile_number, purpose="PASSWORD_RESET")
                request.session['reset_nic'] = nic
                request.session['simulated_reset_otp'] = raw_otp
                AuditLog.objects.create(
                    user=farmer.user,
                    action="PASSWORD_RESET_REQUESTED",
                    details=f"Password reset OTP requested for NIC {farmer.masked_nic}."
                )
            except ValidationError as e:
                messages.error(request, e.message if hasattr(e, 'message') else str(e))
                return redirect('password_reset_request')
        else:
            request.session['reset_nic'] = nic
            request.session['simulated_reset_otp'] = ''

        messages.success(request, _("If this National Identity Card (NIC) is registered, a password-reset OTP has been sent to the registered mobile number."))
        return redirect('password_reset_confirm')

    return render(request, 'accounts/password_reset_request.html')


def password_reset_confirm_view(request):
    """
    Verify the password-reset OTP (HMAC-SHA256, max 5 attempts) and set a new compliant password.
    """
    nic = request.session.get('reset_nic')
    simulated_otp = request.session.get('simulated_reset_otp')

    if not nic:
        return redirect('password_reset_request')

    if request.method == 'POST':
        entered_otp = request.POST.get('otp', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()

        farmer = Farmer.objects.filter(nic_number__iexact=nic).first()
        if not farmer or not farmer.user:
            messages.error(request, _("Invalid reset session. Please request a new OTP."))
            return redirect('password_reset_request')

        user = farmer.user
        active_otp = PasswordResetOTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()

        if not active_otp or not active_otp.is_valid():
            messages.error(request, _("The OTP has expired or exceeded maximum failed attempts (5). Please request a new OTP."))
            return redirect('password_reset_request')

        if not active_otp.verify_entered_otp(entered_otp):
            remaining = max(0, 5 - active_otp.attempts)
            messages.error(request, _("The OTP is incorrect. Remaining attempts: %(remaining)d") % {'remaining': remaining})
            return redirect('password_reset_confirm')

        if new_password != confirm_password:
            messages.error(request, _("The passwords do not match."))
            return redirect('password_reset_confirm')

        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            for msg in e.messages:
                messages.error(request, msg)
            return redirect('password_reset_confirm')

        user.set_password(new_password)
        user.save()
        active_otp.is_used = True
        active_otp.save()

        request.session.pop('reset_nic', None)
        request.session.pop('simulated_reset_otp', None)

        AuditLog.objects.create(
            user=user,
            action="PASSWORD_RESET_SUCCESSFUL",
            details=f"Farmer {farmer.masked_nic} reset password via OTP."
        )
        messages.success(request, _("Your password was changed successfully. You can now log in."))
        return redirect('login')

    return render(request, 'accounts/password_reset_confirm.html', {'simulated_otp': simulated_otp})


@login_required
def force_password_change_view(request):
    """
    Enforce mandatory password update upon first login for newly created officers.
    Validates against Django password validators (min 8, not common, not purely numeric).
    """
    if request.method == 'POST':
        new_pw = request.POST.get('new_password', '').strip()
        confirm_pw = request.POST.get('confirm_password', '').strip()

        if new_pw != confirm_pw:
            messages.error(request, _("The passwords do not match."))
            return render(request, 'accounts/force_password_change.html')

        try:
            validate_password(new_pw, user=request.user)
        except ValidationError as e:
            for msg in e.messages:
                messages.error(request, msg)
            return render(request, 'accounts/force_password_change.html')

        request.user.set_password(new_pw)
        request.user.must_change_password = False
        request.user.save()
        update_session_auth_hash(request, request.user)

        AuditLog.objects.create(
            user=request.user,
            action="FIRST_LOGIN_PASSWORD_CHANGED",
            details=f"Officer '{request.user.username}' changed initial temporary password."
        )
        messages.success(request, _("Your password was updated successfully!"))
        return redirect('dashboard')

    return render(request, 'accounts/force_password_change.html')


@role_required('ADMIN')
def toggle_season_status(request, season_id):
    """
    Admin toggle season status.
    Enforces invariant: Only one season can be OPEN (ACTIVE) at a time across the system.
    """
    if request.method == 'POST':
        season = get_object_or_404(Season, id=season_id)
        if season.status != 'ACTIVE':
            # Setting this season to ACTIVE closes all other active seasons
            Season.objects.exclude(id=season.id).update(status='CLOSED')
            season.status = 'ACTIVE'
        else:
            season.status = 'CLOSED'
        season.save()

        AuditLog.objects.create(
            user=request.user,
            action="SEASON_STATUS_CHANGED",
            details=f"Season '{season.name}' status changed to {season.status}. Single active season invariant enforced."
        )
        messages.success(request, _("Season '%(name)s' status updated to %(status)s.") % {'name': season.name, 'status': season.status})
    return redirect('dashboard')


@role_required('ADMIN')
def admin_officers_view(request):
    """
    Admin-only management of system officers (Warehouse Officer, ASC Officer, ASC Head, Auditor):
    - Creation with 12-char random temp password displayed once
    - Forced password change on first login (must_change_password=True)
    - Deactivation / reactivation (never delete, preserves immutable audit log)
    - Password reset with temporary password
    - Comprehensive audit logging
    """
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_officer':
            username = request.POST.get('username', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            role = request.POST.get('role', '').strip()
            asc_centre_id = request.POST.get('asc_centre')
            is_asc_head = request.POST.get('is_asc_head') == 'on'

            allowed_roles = [
                User.RoleChoices.WAREHOUSE_OFFICER,
                User.RoleChoices.ASC_OFFICER,
                User.RoleChoices.AUDITOR
            ]

            if role not in allowed_roles:
                messages.error(request, _("Invalid role selected."))
                return redirect('admin_officers')

            if not username:
                messages.error(request, _("Username is required."))
                return redirect('admin_officers')

            if User.objects.filter(username__iexact=username).exists():
                messages.error(request, _("A user with username '%(username)s' already exists.") % {'username': username})
                return redirect('admin_officers')

            # Generate random 12-character compliant temporary password
            alphabet = string.ascii_letters + string.digits + "!@#$%"
            temp_password = "".join(secrets.choice(alphabet) for _ in range(12))

            asc_obj = None
            if role == User.RoleChoices.ASC_OFFICER and asc_centre_id:
                asc_obj = ASCCentre.objects.filter(id=asc_centre_id).first()

            new_officer = User.objects.create(
                username=username,
                first_name=first_name,
                last_name=last_name,
                email=email,
                role=role,
                asc_centre=asc_obj,
                is_asc_head=is_asc_head if role == User.RoleChoices.ASC_OFFICER else False,
                must_change_password=True,
                is_account_active=True,
                is_active=True
            )
            new_officer.set_password(temp_password)
            new_officer.save()

            AuditLog.objects.create(
                user=request.user,
                action="OFFICER_CREATED",
                details=f"Admin created officer '{new_officer.username}' (Role: {new_officer.get_role_display()}, ASC: {asc_obj.name if asc_obj else 'None'}). Temp password issued."
            )

            messages.success(
                request,
                _("Officer '%(user)s' created successfully! Temporary Password: %(pw)s (Please copy and share securely — it will not be displayed again.)")
                % {'user': new_officer.username, 'pw': temp_password}
            )
            return redirect('admin_officers')

        elif action == 'toggle_status':
            officer_id = request.POST.get('officer_id')
            officer = get_object_or_404(User, id=officer_id)

            if officer == request.user or officer.is_superuser:
                messages.error(request, _("You cannot deactivate your own account or the superuser."))
                return redirect('admin_officers')

            officer.is_active = not officer.is_active
            officer.save()

            AuditLog.objects.create(
                user=request.user,
                action="OFFICER_STATUS_TOGGLED",
                details=f"Admin set officer '{officer.username}' active status to {officer.is_active}."
            )
            status_text = _("activated") if officer.is_active else _("deactivated")
            messages.success(request, _("Officer '%(user)s' has been %(status)s.") % {'user': officer.username, 'status': status_text})
            return redirect('admin_officers')

        elif action == 'reset_password':
            officer_id = request.POST.get('officer_id')
            officer = get_object_or_404(User, id=officer_id)

            alphabet = string.ascii_letters + string.digits + "!@#$%"
            temp_password = "".join(secrets.choice(alphabet) for _ in range(12))

            officer.set_password(temp_password)
            officer.must_change_password = True
            officer.save()

            AuditLog.objects.create(
                user=request.user,
                action="OFFICER_PASSWORD_RESET",
                details=f"Admin reset temporary password for officer '{officer.username}'."
            )
            messages.success(
                request,
                _("Temporary password for '%(user)s' has been reset to: %(pw)s (User will be forced to change it at next login).")
                % {'user': officer.username, 'pw': temp_password}
            )
            return redirect('admin_officers')

    officers = User.objects.exclude(role=User.RoleChoices.FARMER).order_by('-date_joined')
    ascs = ASCCentre.objects.all().order_by('name')

    context = {
        'officers': officers,
        'ascs': ascs,
        'roles': [
            (User.RoleChoices.ASC_OFFICER, _("ASC Officer")),
            (User.RoleChoices.WAREHOUSE_OFFICER, _("Warehouse Officer")),
            (User.RoleChoices.AUDITOR, _("Auditor")),
        ]
    }
    return render(request, 'accounts/admin_officers.html', context)

