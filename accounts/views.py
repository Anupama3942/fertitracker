from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from core.models import Warehouse, ASCCentre, Season, FertilizerProduct
from .models import User, PasswordResetOTP
from django.utils import timezone
import hashlib
from farmers.models import Farmer
from distributions.models import AuditLog
from .services import SMSNotificationService

# Create your views here.

@login_required
def dashboard_view(request):
    """Render the authenticated user's role-specific dashboard summary."""
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