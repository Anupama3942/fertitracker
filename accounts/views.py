from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash, login, logout, authenticate
from core.models import Warehouse, ASCCentre, Season, FertilizerProduct
from .models import User, PasswordResetOTP
from django.utils import timezone
import hashlib
from farmers.models import Farmer
from distributions.models import AuditLog, FertilizerDistribution
from .services import SMSNotificationService
from datetime import timedelta
from django.db.models import Sum
from inventory.models import ASCStock, StockDispatch
from accounts.decorators import role_required

# Create your views here.

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        client_ip = request.META.get('REMOTE_ADDR')

        user_obj = User.objects.filter(username=username).first()

        # 1. ගිණුම Lock වී ඇත්දැයි පරීක්ෂා කිරීම
        if user_obj and user_obj.is_locked():
            remaining_mins = int((user_obj.locked_until - timezone.now()).total_seconds() // 60) + 1
            messages.error(request, f"වැරදි උත්සාහයන් වැඩි වීම නිසා ගිණුම තාවකාලිකව අගුළු දමා ඇත. මිනිත්තු {remaining_mins}කින් නැවත උත්සාහ කරන්න.")
            return render(request, 'accounts/login.html')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if not user.is_account_active:
                messages.error(request, "ඔබගේ ගිණුම තවමත් සක්‍රිය කර නොමැත. කරුණාකර OTP මඟින් සක්‍රිය කරන්න.")
                return redirect('activate_account')

            # සාර්ථක Login එකකදී වැරදි උත්සාහයන් 0 බවට පත් කිරීම
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

    today = timezone.now().date()
    near_expiry_date = today + timedelta(days=30)
    active_seasons = Season.objects.filter(status='ACTIVE')
    all_seasons = Season.objects.all().order_by('-id')

    # Role අනුව Stocks සහ Distributions පෙරීම (Filter)
    stocks_qs = ASCStock.objects.select_related('asc_centre', 'batch__product').order_by('batch__expiry_date')
    dist_qs = FertilizerDistribution.objects.select_related('farmer', 'asc_centre', 'batch__product')

    if user.role == 'ASC_OFFICER' and user.asc_centre:
        stocks_qs = stocks_qs.filter(asc_centre=user.asc_centre)
        dist_qs = dist_qs.filter(asc_centre=user.asc_centre)

    # Alerts ගණනය කිරීම (Low Stock < 10 bags, Expired & Near-Expiry FEFO)
    low_stocks = stocks_qs.filter(bags_on_hand__lt=10)
    expired_stocks = stocks_qs.filter(batch__expiry_date__lt=today, bags_on_hand__gt=0)
    near_expiry_stocks = stocks_qs.filter(batch__expiry_date__gte=today, batch__expiry_date__lte=near_expiry_date, bags_on_hand__gt=0)

    # අද දින නිකුත් කිරීම් (Today's Issues)
    today_distributions = dist_qs.filter(distributed_at__date=today).order_by('-distributed_at')
    today_total_kg = today_distributions.aggregate(total=Sum('quantity_kg'))['total'] or 0

    # Auditor සහ Admin සඳහා Discrepancy Dispatches සහ Audit Logs
    discrepancy_dispatches = (
        StockDispatch.objects.filter(status=StockDispatch.StatusChoices.DISCREPANCY)
        .select_related('warehouse', 'asc_centre')
        .annotate(
            dispatched_bags=Sum('items__dispatched_bags'),
            received_good_bags=Sum('items__received_bags'),
            damaged_bags=Sum('items__damaged_bags'),
        )
        .order_by('-dispatched_at')
    )
    recent_logs = AuditLog.objects.select_related('user').order_by('-timestamp')[:8]

    context = {
        'today': today,
        'show_operations': user.role in ['ASC_OFFICER', 'ADMIN'] or user.is_superuser,
        'active_seasons': active_seasons,
        'all_seasons': all_seasons,
        'stocks': stocks_qs,
        'low_stocks': low_stocks,
        'expired_stocks': expired_stocks,
        'near_expiry_stocks': near_expiry_stocks,
        'today_distributions': today_distributions,
        'today_total_kg': today_total_kg,
        'discrepancy_dispatches': discrepancy_dispatches,
        'recent_logs': recent_logs,
        'total_farmers': Farmer.objects.count(),
        'total_dispatches': StockDispatch.objects.count(),
    }
    return render(request, 'accounts/dashboard.html', context)


def activate_account_view(request):
    """
    Activate a farmer account with an OTP sent to the registered phone number.
    """
    step = request.session.get('activation_step', 1)
    nic = request.session.get('activation_nic', '')
    simulated_otp = request.session.get('simulated_otp', '')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'send_otp':
            nic = request.POST.get('nic', '').strip()
            farmer = Farmer.objects.filter(nic_number=nic).first()
            
            # Use a generic response so the existence of a NIC cannot be revealed.
            if farmer and farmer.user:
                raw_otp = SMSNotificationService.send_otp(farmer.user, farmer.mobile_number, purpose="ACTIVATION")
                request.session['activation_nic'] = nic
                request.session['activation_step'] = 2
                request.session['simulated_otp'] = raw_otp
                messages.success(request, f"An OTP was sent to the registered phone number. (Prototype OTP: {raw_otp})")
            else:
                messages.error(request, "No registered farmer account was found for this NIC number.")
            return redirect('activate_account')

        elif action == 'verify_and_set_password':
            entered_otp = request.POST.get('otp', '').strip()
            new_password = request.POST.get('new_password', '').strip()
            confirm_password = request.POST.get('confirm_password', '').strip()

            farmer = Farmer.objects.filter(nic_number=nic).first()
            if not farmer or not farmer.user:
                messages.error(request, "Something went wrong. Please try again.")
                return redirect('activate_account')

            user = farmer.user
            active_otp = PasswordResetOTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()

            if not active_otp or not active_otp.is_valid():
                messages.error(request, "The OTP has expired or is invalid.")
                return redirect('activate_account')

            entered_hash = hashlib.sha256(entered_otp.encode()).hexdigest()
            if active_otp.otp_hash != entered_hash:
                active_otp.attempts += 1
                active_otp.save()
                messages.error(request, f"The OTP is incorrect. Remaining attempts: {3 - active_otp.attempts}")
                return redirect('activate_account')

            if new_password != confirm_password:
                messages.error(request, "The two passwords do not match.")
                return redirect('activate_account')

            # Activate the account and set the new password.
            user.set_password(new_password)
            user.is_account_active = True
            user.save()

            active_otp.is_used = True
            active_otp.save()

            # Clear the temporary activation session data.
            request.session.pop('activation_step', None)
            request.session.pop('activation_nic', None)
            request.session.pop('simulated_otp', None)

            AuditLog.objects.create(user=user, action="ACCOUNT_ACTIVATED", details=f"Account activated via OTP for NIC: {nic}")
            messages.success(request, "Your account was activated successfully. You can now log in.")
            return redirect('login')

    return render(request, 'accounts/activate_account.html', {'step': step, 'simulated_otp': simulated_otp})


def password_reset_request_view(request):
    """
    Request a password-reset OTP using the farmer's NIC number.
    """
    if request.method == 'POST':
        nic = request.POST.get('nic', '').strip()
        farmer = Farmer.objects.filter(nic_number=nic).first()
        
        if farmer and farmer.user:
            raw_otp = PasswordResetOTP.generate_otp(farmer.user)
            request.session['reset_nic'] = nic
            request.session['simulated_reset_otp'] = raw_otp
            AuditLog.objects.create(action="PASSWORD_RESET_REQUESTED", details=f"Reset OTP requested for NIC: {nic}")
            messages.success(request, f"A password-reset OTP was sent. (Prototype OTP: {raw_otp})")
            return redirect('password_reset_confirm')
        else:
            messages.error(request, "No account was found for this NIC number.")

    return render(request, 'accounts/password_reset_request.html')


def password_reset_confirm_view(request):
    """
    Verify the password-reset OTP and set a new password.
    """
    nic = request.session.get('reset_nic')
    simulated_otp = request.session.get('simulated_reset_otp')

    if not nic:
        return redirect('password_reset_request')

    if request.method == 'POST':
        entered_otp = request.POST.get('otp', '').strip()
        new_password = request.POST.get('new_password', '').strip()

        farmer = Farmer.objects.filter(nic_number=nic).first()
        if not farmer or not farmer.user:
            messages.error(request, "Something went wrong.")
            return redirect('password_reset_request')

        user = farmer.user
        active_otp = PasswordResetOTP.objects.filter(user=user, is_used=False).order_by('-created_at').first()

        if not active_otp or not active_otp.is_valid():
            messages.error(request, "The OTP has expired.")
            return redirect('password_reset_request')

        entered_hash = hashlib.sha256(entered_otp.encode()).hexdigest()
        if active_otp.otp_hash != entered_hash:
            messages.error(request, "The OTP is incorrect.")
            return redirect('password_reset_confirm')

        user.set_password(new_password)
        user.save()
        active_otp.is_used = True
        active_otp.save()

        request.session.pop('reset_nic', None)
        request.session.pop('simulated_reset_otp', None)

        AuditLog.objects.create(user=user, action="PASSWORD_RESET_SUCCESSFUL", details=f"Password reset via OTP for NIC: {nic}")
        messages.success(request, "Your password was changed successfully. You can now log in.")
        return redirect('login')

    return render(request, 'accounts/password_reset_confirm.html', {'simulated_otp': simulated_otp})


@login_required
def force_password_change_view(request):
    """FR-A2: නිලධාරියා පළමු login එකේදී තාවකාලික මුරපදය අනිවාර්යයෙන්ම වෙනස් කළ යුතුය."""
    if request.method == 'POST':
        new_pw = request.POST.get('new_password', '').strip()
        confirm_pw = request.POST.get('confirm_password', '').strip()

        if len(new_pw) < 8:
            messages.error(request, "මුරපදය අවම වශයෙන් අකුරු 8ක් විය යුතුය.")
        elif new_pw != confirm_pw:
            messages.error(request, "මුරපද දෙක එකිනෙකට ගැළපෙන්නේ නැත.")
        else:
            request.user.set_password(new_pw)
            request.user.must_change_password = False
            request.user.save()
            update_session_auth_hash(request, request.user)
            AuditLog.objects.create(user=request.user, action="FIRST_LOGIN_PASSWORD_CHANGED", details="Officer updated temporary password.")
            messages.success(request, "මුරපදය සාර්ථකව යාවත්කාලීන කරන ලදී!")
            return redirect('dashboard')

    return render(request, 'accounts/force_password_change.html')


@role_required('ADMIN')
def toggle_season_status(request, season_id):
    """Admin හට කන්නයක් (Maha/Yala) Open (ACTIVE) හෝ Close (CLOSED) කිරීමට හැකි වීම."""
    if request.method == 'POST':
        season = get_object_or_404(Season, id=season_id)
        season.status = 'CLOSED' if season.status == 'ACTIVE' else 'ACTIVE'
        season.save()
        AuditLog.objects.create(
            user=request.user,
            action="SEASON_STATUS_CHANGED",
            details=f"Season '{season.name}' status changed to {season.status}"
        )
        messages.success(request, f"'{season.name}' කන්නයේ තත්ත්වය {season.status} ලෙස යාවත්කාලීන කරන ලදී.")
    return redirect('dashboard')
