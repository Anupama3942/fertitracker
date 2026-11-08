import hashlib
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from farmers.models import QRToken, FarmerEntitlement
from inventory.models import ASCStock, StockMovement
from .models import FertilizerDistribution, AuditLog
from core.models import Season, ASCCentre

def get_qr_token_by_input(raw_input_string, select_for_update=False):
    """
    Find a QRToken by either its 64-character token hash or its 6-digit backup code hash.
    """
    clean_input = raw_input_string.strip().replace(" ", "").replace("-", "")
    if not clean_input:
        raise ValidationError("Please provide a valid QR code or 6-digit backup code.")

    hashed_input = hashlib.sha256(clean_input.encode()).hexdigest()

    qs = QRToken.objects.select_for_update() if select_for_update else QRToken.objects

    # Match against either 64-char token_hash or 6-digit code_hash
    token_obj = qs.filter(token_hash=hashed_input).first() or qs.filter(code_hash=hashed_input).first()
    if not token_obj:
        raise ValidationError("The provided QR token or 6-digit code is invalid.")

    if not token_obj.is_valid():
        raise ValidationError("This QR token has already been used or has expired.")

    return token_obj


def verify_farmer_token(raw_input_string, asc_officer_user, season_id):
    """
    Step 1 & 2: VERIFY token, officer, season, farmer quota, and available stock.
    Does NOT redeem the token or modify database state.
    """
    qr_token = get_qr_token_by_input(raw_input_string, select_for_update=False)
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

    # Check available stock (FEFO)
    asc_stock = ASCStock.objects.filter(
        asc_centre=asc_centre,
        batch__product=entitlement.product,
        bags_on_hand__gt=0
    ).order_by('batch__expiry_date').first()

    if not asc_stock or asc_stock.bags_on_hand < 1:
        raise ValidationError(f"ASC '{asc_centre.name}' has no available stock for {entitlement.product.name}.")

    bag_weight = asc_stock.batch.product.bag_weight_kg
    max_deliverable_kg = min(entitlement.remaining_kg, asc_stock.bags_on_hand * bag_weight)
    default_issue_kg = min(bag_weight, entitlement.remaining_kg)

    return {
        'qr_token': qr_token,
        'token_string': raw_input_string,
        'farmer': farmer,
        'asc_centre': asc_centre,
        'season': season_obj,
        'entitlement': entitlement,
        'asc_stock': asc_stock,
        'batch': asc_stock.batch,
        'bag_weight': bag_weight,
        'max_deliverable_kg': max_deliverable_kg,
        'default_issue_kg': default_issue_kg,
        'seconds_remaining': max(0, int((qr_token.expires_at - timezone.now()).total_seconds())),
    }


@transaction.atomic
def confirm_issue_distribution(raw_input_string, asc_officer_user, season_id, quantity_kg=None, client_ip=None):
    """
    Step 4: Execute the atomic issue transaction.
    Uses select_for_update row-level locks, deducts stock & entitlement, marks token redeemed.
    """
    # 1. Acquire row-level lock on QRToken
    qr_token = get_qr_token_by_input(raw_input_string, select_for_update=True)
    farmer = qr_token.farmer

    # 2. Verify officer ASC assignment
    if (asc_officer_user.role in ['ASC_OFFICER', 'ADMIN'] or asc_officer_user.is_superuser) and asc_officer_user.asc_centre:
        asc_centre = asc_officer_user.asc_centre
    elif asc_officer_user.role == 'ADMIN' or asc_officer_user.is_superuser:
        asc_centre = ASCCentre.objects.first()
        if not asc_centre:
            raise ValidationError("No ASC Centre is configured in the system.")
    else:
        raise ValidationError("Only an officer from the relevant ASC can issue fertilizer.")

    # 3. Verify active season
    season_obj = Season.objects.filter(id=season_id).first()
    if not season_obj or season_obj.status != 'ACTIVE':
        raise ValidationError("The selected season is not currently active.")

    # 4. Acquire row-level lock on Entitlement
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

    # 5. Acquire row-level lock on ASC stock using FEFO
    asc_stock = ASCStock.objects.select_for_update().filter(
        asc_centre=asc_centre,
        batch__product=entitlement.product,
        bags_on_hand__gt=0
    ).order_by('batch__expiry_date').first()

    if not asc_stock or asc_stock.bags_on_hand < 1:
        raise ValidationError("The ASC has insufficient fertilizer stock for issue.")

    bag_weight = asc_stock.batch.product.bag_weight_kg
    bags_to_deduct = max(1, int(issue_kg / bag_weight))

    if asc_stock.bags_on_hand < bags_to_deduct:
        raise ValidationError(f"Not enough bags on hand. Available: {asc_stock.bags_on_hand}, Needed: {bags_to_deduct}")

    batch = asc_stock.batch

    # 6. Execute atomic mutations
    entitlement.remaining_kg -= issue_kg
    entitlement.save()

    asc_stock.bags_on_hand -= bags_to_deduct
    asc_stock.save()

    qr_token.is_redeemed = True
    qr_token.save()

    distribution = FertilizerDistribution.objects.create(
        farmer=farmer,
        asc_centre=asc_centre,
        batch=batch,
        season_id=season_id,
        issued_by=asc_officer_user,
        quantity_kg=issue_kg
    )

    StockMovement.objects.create(
        stock=asc_stock,
        movement_type=StockMovement.MovementTypeChoices.OUTBOUND,
        quantity_kg=issue_kg,
        created_by=asc_officer_user,
        notes=f"Issued to Farmer {farmer.masked_nic} (Receipt: {distribution.receipt_number})"
    )

    AuditLog.objects.create(
        user=asc_officer_user,
        action=f"DISTRIBUTION_ISSUED: {distribution.receipt_number}",
        ip_address=client_ip,
        details=f"Issued {issue_kg}kg ({bags_to_deduct} bags) to {farmer.full_name} ({farmer.masked_nic}) from Batch {batch.batch_number}"
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