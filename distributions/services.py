import hashlib
import hmac
from datetime import timedelta
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings
from farmers.models import QRToken, FarmerEntitlement, Farmer, compute_code_hmac
from inventory.models import ASCStock, StockMovement
from .models import FertilizerDistribution, AuditLog, AssistedIssueApproval
from .sms import get_sms_backend
from core.models import Season, ASCCentre

def get_qr_token_by_input(raw_input_string, select_for_update=False, officer=None):
    """
    Find and validate a QRToken by either:
    1. 64-character hex token string (SHA-256 hash match), OR
    2. 6-digit backup/SMS verification code (HMAC-SHA256 keyed hash match).

    Security & Hardening Rules:
    - Officer lockout: max 5 wrong code attempts per officer per 10 minutes.
    - Token invalidation: max 5 failed attempts per token.
    - Bound ASC check: token bound to an ASC cannot be redeemed at a different ASC.
    - Constant-time HMAC comparison (hmac.compare_digest).
    """
    # 1. Check if the officer is currently locked out from manual code entry
    if officer and hasattr(officer, 'is_code_locked') and officer.is_code_locked():
        raise ValidationError(
            "Manual code entry is temporarily locked due to multiple failed attempts. Please try again after 10 minutes."
        )

    clean_input = str(raw_input_string).strip().replace(" ", "").replace("-", "")
    if not clean_input:
        raise ValidationError("Please provide a valid QR code or 6-digit backup code.")

    qs = QRToken.objects.select_for_update() if select_for_update else QRToken.objects
    token_obj = None

    # Check whether the input is a 6-digit numeric code
    if clean_input.isdigit() and len(clean_input) == 6:
        input_hmac = compute_code_hmac(clean_input)
        # Search candidate tokens
        candidate = qs.filter(code_hash=input_hmac).first()
        if candidate and candidate.code_hash:
            if hmac.compare_digest(candidate.code_hash, input_hmac):
                token_obj = candidate
    else:
        # Standard 64-character QR token hash
        hashed_input = hashlib.sha256(clean_input.encode('utf-8')).hexdigest()
        token_obj = qs.filter(token_hash=hashed_input).first()

    # If no token matched, record failed attempt against officer
    if not token_obj:
        if officer and hasattr(officer, 'record_failed_code_attempt'):
            officer.record_failed_code_attempt()
            if officer.is_code_locked():
                AuditLog.objects.create(
                    user=officer,
                    action="OFFICER_CODE_ENTRY_LOCKED",
                    details=f"Officer {officer.username} locked out of code entry for 10 minutes after 5 failed attempts."
                )
        raise ValidationError("The provided QR token or 6-digit code is invalid.")

    # Check token's own attempt limit (brute-force invalidation)
    if token_obj.failed_attempts >= 5 or token_obj.is_redeemed:
        raise ValidationError("This verification code has already been used or has been invalidated due to exceeding failed attempts.")

    # Check expiration
    if timezone.now() > token_obj.expires_at:
        token_obj.record_failed_attempt()
        if officer and hasattr(officer, 'record_failed_code_attempt'):
            officer.record_failed_code_attempt()
        raise ValidationError("This verification code has expired.")

    # Check bound ASC Centre (Security Rule: Bound to specific farmer AND specific ASC)
    if token_obj.asc_centre and officer and getattr(officer, 'asc_centre', None):
        if token_obj.asc_centre != officer.asc_centre and officer.role != 'ADMIN' and not officer.is_superuser:
            token_obj.record_failed_attempt()
            if officer and hasattr(officer, 'record_failed_code_attempt'):
                officer.record_failed_code_attempt()
            raise ValidationError(
                f"This code is bound to '{token_obj.asc_centre.name}' and cannot be redeemed at '{officer.asc_centre.name}'."
            )

    # Valid token found! Reset officer's failed attempt counter
    if officer and hasattr(officer, 'reset_failed_code_attempts'):
        officer.reset_failed_code_attempts()

    return token_obj


def generate_sms_code_for_farmer(farmer, asc_centre, requested_by_user):
    """
    Generates a 6-digit verification code bound to the farmer and ASC centre,
    applies rate limiting, sends via the configured SMS backend, and logs to AuditLog.

    Rate limits:
    - Maximum 3 codes per farmer per hour.
    - 60-second cooldown between requests for the same farmer.
    """
    now = timezone.now()
    one_hour_ago = now - timedelta(hours=1)

    # Rate Limit 1: Max 3 codes per farmer per hour
    hourly_count = QRToken.objects.filter(
        farmer=farmer,
        channel=QRToken.ChannelChoices.SMS,
        expires_at__gte=one_hour_ago
    ).count()

    if hourly_count >= 3:
        raise ValidationError(
            "Rate limit exceeded: A maximum of 3 SMS verification codes can be generated per hour for this farmer."
        )

    # Rate Limit 2: 60-second cooldown between requests
    latest_sms_token = QRToken.objects.filter(
        farmer=farmer,
        channel=QRToken.ChannelChoices.SMS
    ).order_by('-id').first()

    if latest_sms_token:
        # Token lifetime is 300s, so created_at = expires_at - 300s
        estimated_created_at = latest_sms_token.expires_at - timedelta(seconds=300)
        seconds_since_last = (now - estimated_created_at).total_seconds()
        if seconds_since_last < 60:
            remaining = int(60 - seconds_since_last)
            raise ValidationError(
                f"Please wait {remaining} seconds before requesting another SMS code for this farmer."
            )

    # Generate token + 6-digit code with 5-minute validity (300 seconds), bound to ASC
    raw_token, raw_code, qr_token = QRToken.generate_token_for_farmer(
        farmer=farmer,
        asc_centre=asc_centre,
        channel=QRToken.ChannelChoices.SMS,
        expiry_seconds=300
    )

    # Plain short SMS message: ONLY code and ASC name
    sms_text = f"FertiTracker: Your verification code for {asc_centre.name} is {raw_code}. Valid for 5 minutes. Do not share."

    # Dispatch via SMS backend
    sms_backend = get_sms_backend()
    sms_backend.send_sms(farmer.mobile_number, sms_text, context={'farmer': farmer, 'code': raw_code})

    # Audit log
    AuditLog.objects.create(
        user=requested_by_user,
        action="SMS_BACKUP_CODE_SENT",
        details=f"Sent 5-minute SMS verification code to farmer {farmer.full_name} ({farmer.masked_nic}) for ASC {asc_centre.name}"
    )

    return raw_token, raw_code, qr_token


def verify_farmer_token(raw_input_string, asc_officer_user, season_id):
    """
    Step 1 & 2: VERIFY token/code, officer, season, farmer quota, and available stock.
    Does NOT redeem the token or modify database state.
    """
    qr_token = get_qr_token_by_input(raw_input_string, select_for_update=False, officer=asc_officer_user)
    farmer = qr_token.farmer

    # Verify ASC assignment
    if (asc_officer_user.role in ['ASC_OFFICER', 'ADMIN'] or asc_officer_user.is_superuser) and asc_officer_user.asc_centre:
        asc_centre = asc_officer_user.asc_centre
    elif asc_officer_user.role == 'ADMIN' or asc_officer_user.is_superuser:
        asc_centre = ASCCentre.objects.first()
        if not asc_centre:
            raise ValidationError("No ASC Centre is configured in the system.")
    else:
        raise ValidationError("Only an officer from the relevant ASC can issue fertilizer.")

    # Verify active season
    season_obj = Season.objects.filter(id=season_id).first()
    if not season_obj or season_obj.status != 'ACTIVE':
        raise ValidationError("The selected season is not active. Fertilizer cannot be issued for a closed season.")

    # Retrieve entitlement
    entitlement = FarmerEntitlement.objects.filter(
        farmer=farmer,
        season_id=season_id,
        product__name__iexact='Urea'
    ).first()

    if not entitlement:
        raise ValidationError(f"No fertilizer quota found for farmer {farmer.full_name} in season {season_obj.name}.")

    if entitlement.remaining_kg <= 0:
        raise ValidationError(f"Farmer {farmer.full_name} has already exhausted their fertilizer quota for this season.")

    # Check available stock (FEFO: Earliest expiry first, skip expired batches)
    today = timezone.localdate()
    unexpired_stocks = list(ASCStock.objects.filter(
        asc_centre=asc_centre,
        batch__product=entitlement.product,
        batch__expiry_date__gte=today,
        bags_on_hand__gt=0
    ).order_by('batch__expiry_date'))

    if not unexpired_stocks:
        raise ValidationError(f"ASC '{asc_centre.name}' has no usable unexpired stock for {entitlement.product.name}.")

    first_stock = unexpired_stocks[0]
    bag_weight = first_stock.batch.product.bag_weight_kg
    total_unexpired_bags = sum(s.bags_on_hand for s in unexpired_stocks)
    max_deliverable_kg = min(entitlement.remaining_kg, total_unexpired_bags * bag_weight)
    default_issue_kg = min(bag_weight, entitlement.remaining_kg)

    return {
        'qr_token': qr_token,
        'token_string': raw_input_string,
        'farmer': farmer,
        'asc_centre': asc_centre,
        'season': season_obj,
        'entitlement': entitlement,
        'asc_stock': first_stock,
        'batch': first_stock.batch,
        'total_unexpired_bags': total_unexpired_bags,
        'bag_weight': bag_weight,
        'max_deliverable_kg': max_deliverable_kg,
        'default_issue_kg': default_issue_kg,
        'seconds_remaining': max(0, int((qr_token.expires_at - timezone.now()).total_seconds())),
    }



def create_assisted_issue_request(farmer, asc_centre, season, requested_by_user, reason, reason_note=""):
    """
    Creates an officer-assisted issue request for a farmer without a phone/QR.
    Enforces required explanation if reason is 'OTHER'.
    Expires in 30 minutes.
    """
    if reason not in AssistedIssueApproval.ReasonChoices.values:
        raise ValidationError("Please select a valid assisted issue reason.")

    clean_note = (reason_note or "").strip()
    if reason == AssistedIssueApproval.ReasonChoices.OTHER and not clean_note:
        raise ValidationError("An explanatory note is mandatory when selecting 'Other reason'.")

    # Verify quota exists
    entitlement = FarmerEntitlement.objects.filter(
        farmer=farmer,
        season=season,
        product__name__iexact='Urea'
    ).first()
    if not entitlement or entitlement.remaining_kg <= 0:
        raise ValidationError(f"Farmer {farmer.full_name} has no remaining fertilizer quota for season {season.name}.")

    approval = AssistedIssueApproval.objects.create(
        farmer=farmer,
        asc_centre=asc_centre,
        season=season,
        requested_by=requested_by_user,
        reason=reason,
        reason_note=clean_note,
        status=AssistedIssueApproval.StatusChoices.PENDING,
        expires_at=timezone.now() + timedelta(minutes=30)
    )

    AuditLog.objects.create(
        user=requested_by_user,
        action=f"ASSISTED_ISSUE_REQUESTED: #{approval.id}",
        details=f"Officer {requested_by_user.username} requested assisted issue for farmer {farmer.full_name} ({farmer.masked_nic}). Reason: {approval.get_reason_display()}"
    )

    return approval


@transaction.atomic
def approve_assisted_issue_request(request_id, approving_user):
    """
    Approve an assisted issue request under the Two-Officer Rule.
    Enforces:
    - Approver must be ASC Head (is_asc_head=True or Admin).
    - Approver cannot be the same officer who requested (requester != approver).
    - Approver must belong to the same ASC.
    - Request must be PENDING and within the 30-minute validity period.
    """
    approval = AssistedIssueApproval.objects.select_for_update().get(id=request_id)

    # Two-Officer Rule: requester cannot approve own request
    if approval.requested_by == approving_user:
        raise ValidationError("Two-Officer Rule Violation: You cannot approve your own assisted issue request.")

    # Must be ASC Head
    is_head = getattr(approving_user, 'is_asc_head', False) or approving_user.role == 'ADMIN' or approving_user.is_superuser
    if not is_head:
        raise ValidationError("Only an authorized ASC Head can approve assisted issue requests.")

    # Must belong to the same ASC Centre
    if approving_user.role != 'ADMIN' and not approving_user.is_superuser:
        if approving_user.asc_centre != approval.asc_centre:
            raise ValidationError("You can only approve requests for your assigned Agrarian Service Centre.")

    if approval.status != AssistedIssueApproval.StatusChoices.PENDING:
        raise ValidationError(f"This request cannot be approved because it is already {approval.get_status_display()}.")

    if timezone.now() > approval.expires_at:
        approval.status = AssistedIssueApproval.StatusChoices.EXPIRED
        approval.save()
        raise ValidationError("This request has expired (30-minute validity limit exceeded).")

    approval.status = AssistedIssueApproval.StatusChoices.APPROVED
    approval.approved_by = approving_user
    approval.save()

    AuditLog.objects.create(
        user=approving_user,
        action=f"ASSISTED_ISSUE_APPROVED: #{approval.id}",
        details=f"ASC Head {approving_user.username} approved assisted issue for farmer {approval.farmer.full_name} ({approval.farmer.masked_nic})"
    )

    return approval


@transaction.atomic
def reject_assisted_issue_request(request_id, rejecting_user, rejection_reason=""):
    """Reject a pending assisted issue request."""
    approval = AssistedIssueApproval.objects.select_for_update().get(id=request_id)

    is_head = getattr(rejecting_user, 'is_asc_head', False) or rejecting_user.role == 'ADMIN' or rejecting_user.is_superuser
    if not is_head:
        raise ValidationError("Only an authorized ASC Head can reject assisted issue requests.")

    if rejecting_user.role != 'ADMIN' and not rejecting_user.is_superuser:
        if rejecting_user.asc_centre != approval.asc_centre:
            raise ValidationError("You can only reject requests for your assigned Agrarian Service Centre.")

    if approval.status != AssistedIssueApproval.StatusChoices.PENDING:
        raise ValidationError(f"This request is already {approval.get_status_display()}.")

    clean_reason = (rejection_reason or "").strip()
    approval.status = AssistedIssueApproval.StatusChoices.REJECTED
    approval.approved_by = rejecting_user
    approval.rejection_reason = clean_reason
    approval.save()

    AuditLog.objects.create(
        user=rejecting_user,
        action=f"ASSISTED_ISSUE_REJECTED: #{approval.id}",
        details=f"Assisted issue #{approval.id} rejected by {rejecting_user.username}. Reason: {clean_reason}"
    )

    return approval


@transaction.atomic
def confirm_issue_distribution(raw_input_string=None, asc_officer_user=None, season_id=None,
                               quantity_kg=None, client_ip=None, assisted_approval_id=None):
    """
    Step 4: Execute the atomic issue transaction.
    Supports:
    - QR token redemption (issue_method='QR')
    - SMS 6-digit backup code redemption (issue_method='SMS_CODE')
    - Approved Officer-Assisted Issue (issue_method='ASSISTED')

    Row-level locks:
    - QRToken / AssistedIssueApproval (select_for_update)
    - Entitlement (select_for_update)
    - ASCStock (select_for_update)
    """
    qr_token = None
    approval = None

    if assisted_approval_id:
        # Flow A: Officer-Assisted Issue
        approval = AssistedIssueApproval.objects.select_for_update().get(id=assisted_approval_id)
        if not approval.is_valid_for_issue():
            raise ValidationError("This assisted issue approval is not active or has expired.")

        farmer = approval.farmer
        season_id = approval.season_id
        issue_method = FertilizerDistribution.IssueMethodChoices.ASSISTED
        asc_centre = approval.asc_centre
    else:
        # Flow B: QR / SMS Code Issue
        if not raw_input_string:
            raise ValidationError("Missing verification token or backup code.")

        qr_token = get_qr_token_by_input(raw_input_string, select_for_update=True, officer=asc_officer_user)
        farmer = qr_token.farmer

        if qr_token.channel == QRToken.ChannelChoices.SMS:
            issue_method = FertilizerDistribution.IssueMethodChoices.SMS_CODE
        else:
            issue_method = FertilizerDistribution.IssueMethodChoices.QR

        # Verify officer ASC assignment
        if (asc_officer_user.role in ['ASC_OFFICER', 'ADMIN'] or asc_officer_user.is_superuser) and asc_officer_user.asc_centre:
            asc_centre = asc_officer_user.asc_centre
        elif asc_officer_user.role == 'ADMIN' or asc_officer_user.is_superuser:
            asc_centre = ASCCentre.objects.first()
            if not asc_centre:
                raise ValidationError("No ASC Centre is configured in the system.")
        else:
            raise ValidationError("Only an officer from the relevant ASC can issue fertilizer.")

    # Verify active season
    season_obj = Season.objects.filter(id=season_id).first()
    if not season_obj or season_obj.status != 'ACTIVE':
        raise ValidationError("The selected season is not currently active.")

    # Acquire row-level lock on Entitlement
    try:
        entitlement = FarmerEntitlement.objects.select_for_update().get(
            farmer=farmer,
            season_id=season_id,
            product__name__iexact='Urea'
        )
    except FarmerEntitlement.DoesNotExist:
        raise ValidationError("No fertilizer entitlement exists for this farmer and season.")

    issue_kg = Decimal(str(quantity_kg)) if quantity_kg else Decimal('50.00')

    if issue_kg <= 0:
        raise ValidationError("Issued quantity must be greater than zero.")

    if entitlement.remaining_kg < issue_kg:
        raise ValidationError(f"The farmer's remaining quota ({entitlement.remaining_kg} kg) is less than requested ({issue_kg} kg).")

    # Acquire row-level locks on candidate ASC stocks using FEFO (Earliest expiry date first, skip expired batches)
    today = timezone.localdate()
    candidate_stocks = list(ASCStock.objects.select_for_update().filter(
        asc_centre=asc_centre,
        batch__product=entitlement.product,
        batch__expiry_date__gte=today,
        bags_on_hand__gt=0
    ).order_by('batch__expiry_date', 'id'))

    if not candidate_stocks:
        raise ValidationError(f"ASC '{asc_centre.name}' has no usable unexpired stock for {entitlement.product.name}.")

    bag_weight = entitlement.product.bag_weight_kg
    bags_to_deduct = max(1, int(issue_kg / bag_weight))

    total_available_bags = sum(s.bags_on_hand for s in candidate_stocks)
    if total_available_bags < bags_to_deduct:
        raise ValidationError(f"Not enough unexpired bags on hand. Available: {total_available_bags}, Needed: {bags_to_deduct}")

    # FEFO Multi-batch allocation: allocate from earliest expiry date first, splitting across batches if necessary
    remaining_bags = bags_to_deduct
    remaining_kg = issue_kg
    allocated_records = []  # tuples: (stock, bags_deducted, kg_deducted)

    for stock in candidate_stocks:
        if remaining_bags <= 0:
            break
        deduct_bags = min(stock.bags_on_hand, remaining_bags)
        deduct_kg = min(remaining_kg, Decimal(deduct_bags) * bag_weight)

        stock.bags_on_hand -= deduct_bags
        stock.save()

        allocated_records.append((stock, deduct_bags, deduct_kg))
        remaining_bags -= deduct_bags
        remaining_kg -= deduct_kg

    if remaining_kg > 0 and allocated_records:
        last_stock, last_b, last_kg = allocated_records[-1]
        allocated_records[-1] = (last_stock, last_b, last_kg + remaining_kg)

    primary_stock, _, _ = allocated_records[0]
    batch = primary_stock.batch

    # Execute atomic mutations
    entitlement.remaining_kg -= issue_kg
    entitlement.save()

    if qr_token:
        qr_token.is_redeemed = True
        qr_token.save()

    if approval:
        approval.status = AssistedIssueApproval.StatusChoices.USED
        approval.save()

    distribution = FertilizerDistribution.objects.create(
        farmer=farmer,
        asc_centre=asc_centre,
        batch=batch,
        season_id=season_id,
        issued_by=asc_officer_user,
        issue_method=issue_method,
        assisted_approval=approval,
        quantity_kg=issue_kg
    )

    for stock, b_deducted, kg_deducted in allocated_records:
        StockMovement.objects.create(
            stock=stock,
            movement_type=StockMovement.MovementTypeChoices.OUTBOUND,
            quantity_kg=kg_deducted,
            created_by=asc_officer_user,
            notes=f"Issued to Farmer {farmer.masked_nic} via {distribution.get_issue_method_display()} (Receipt: {distribution.receipt_number}, Batch: {stock.batch.batch_number}, Bags: {b_deducted})"
        )

    batch_summary = ", ".join([f"{s.batch.batch_number} ({b} bags, {kg}kg)" for s, b, kg in allocated_records])
    AuditLog.objects.create(
        user=asc_officer_user,
        action=f"DISTRIBUTION_ISSUED: {distribution.receipt_number}",
        ip_address=client_ip,
        details=f"Issued {issue_kg}kg ({bags_to_deduct} bags) to {farmer.full_name} ({farmer.masked_nic}) via {distribution.get_issue_method_display()} from Batches: {batch_summary}"
    )

    return distribution


def process_qr_distribution(raw_token_string, asc_officer_user, season_id, client_ip=None):
    """
    Backwards-compatible convenience wrapper for automated tests and direct issue.
    """
    return confirm_issue_distribution(
        raw_input_string=raw_token_string,
        asc_officer_user=asc_officer_user,
        season_id=season_id,
        quantity_kg=Decimal('50.00'),
        client_ip=client_ip
    )