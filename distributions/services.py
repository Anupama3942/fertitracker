from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from farmers.models import QRToken, FarmerEntitlement
from inventory.models import ASCStock, StockMovement
from .models import FertilizerDistribution, AuditLog

@transaction.atomic
def process_qr_distribution(raw_token_string, asc_officer_user, season_id, client_ip=None):
    """
    Validate a farmer QR token and issue fertilizer in an atomic transaction (FR-11, FR-12, FR-17).
    """
    import hashlib
    hashed_input = hashlib.sha256(raw_token_string.encode()).hexdigest()

    # 1. Find the token and verify its validity within the 60-second lifetime.
    try:
        qr_token = QRToken.objects.select_for_update().get(token_hash=hashed_input)
    except QRToken.DoesNotExist:
        raise ValidationError("The QR token is invalid or has expired.")

    if not qr_token.is_valid():
        raise ValidationError("This QR token has already been used or has expired.")

    farmer = qr_token.farmer

    # 2. Verify that the requesting officer belongs to the relevant ASC (Business Rule 12 / FR-20).
    if asc_officer_user.role == 'ASC_OFFICER' and asc_officer_user.asc_centre:
        asc_centre = asc_officer_user.asc_centre
    else:
        raise ValidationError("Only an officer from the relevant ASC can issue fertilizer.")

    # 3. Retrieve the farmer's entitlement for the selected season.
    try:
        entitlement = FarmerEntitlement.objects.select_for_update().get(
            farmer=farmer,
            season_id=season_id,
            product__name__iexact='Urea'  # Urea is the primary fertilizer product for this workflow.
        )
    except FarmerEntitlement.DoesNotExist:
        raise ValidationError("No fertilizer entitlement exists for this farmer and season.")

    # Set the issue quantity to one 50 kg bag for this workflow.
    issue_kg = Decimal('50.00')

    if entitlement.remaining_kg < issue_kg:
        raise ValidationError(f"The farmer's remaining quota is insufficient. Remaining: {entitlement.remaining_kg} kg.")

    # 4. Select ASC stock using FEFO: the batch with the earliest expiry date.
    asc_stock = ASCStock.objects.select_for_update().filter(
        asc_centre=asc_centre,
        bags_on_hand__gt=0
    ).order_by('batch__expiry_date').first()

    if not asc_stock or asc_stock.bags_on_hand < 1:
        raise ValidationError("The ASC has insufficient fertilizer stock for issue to farmers.")

    batch = asc_stock.batch

    # 5. Update stock and quota atomically.
    # a) Reduce the farmer's remaining quota.
    entitlement.remaining_kg -= issue_kg
    entitlement.save()

    # b) Reduce ASC stock by one bag.
    asc_stock.bags_on_hand -= 1
    asc_stock.save()

    # c) Mark the QR token as redeemed.
    qr_token.is_redeemed = True
    qr_token.save()

    # d) Create the fertilizer distribution record.
    distribution = FertilizerDistribution.objects.create(
        farmer=farmer,
        asc_centre=asc_centre,
        batch=batch,
        season_id=season_id,
        issued_by=asc_officer_user,
        quantity_kg=issue_kg
    )

    # e) Record the OUTBOUND stock movement in the ledger (FR-17).
    StockMovement.objects.create(
        stock=asc_stock,
        movement_type=StockMovement.MovementTypeChoices.OUTBOUND,
        quantity_kg=issue_kg
    )

    # f) Write an append-only audit log entry.
    AuditLog.objects.create(
        user=asc_officer_user,
        action=f"DISTRIBUTION_ISSUED: {distribution.receipt_number}",
        ip_address=client_ip,
        details=f"Issued {issue_kg}kg to Farmer {farmer.nic_number} from Batch {batch.batch_number}"
    )

    return distribution