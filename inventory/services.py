import io
import base64
import qrcode
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import StockDispatch, DispatchItem, ASCStock, StockMovement, Discrepancy
from distributions.models import AuditLog

def generate_qr_base64(data_string):
    """
    Generate a QR code and return it as an embeddable Base64 PNG string (FR-06).
    """
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(data_string)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@transaction.atomic
def confirm_dispatch_receiving(dispatch_id, officer_user, received_bags_dict, damaged_bags_dict, discrepancy_reason=""):
    """
    Atomic transaction for receiving stock dispatch at the Agrarian Service Centre.
    Enforces business rules:
    - Only good bags are added to usable bags_on_hand.
    - If damaged or missing > 0, requires a reason note, records Discrepancy, sets status to RECEIVED_WITH_DISCREPANCY.
    - Strict row-level lock on dispatch and ASC stock.
    - Creates append-only StockMovement and AuditLog records.
    """
    # 1. Row-level lock on dispatch
    dispatch = StockDispatch.objects.select_for_update().get(id=dispatch_id)

    if dispatch.status != StockDispatch.StatusChoices.DISPATCHED:
        raise ValidationError("This dispatch has already been received and confirmed.")

    if officer_user.role == 'ASC_OFFICER' and officer_user.asc_centre != dispatch.asc_centre:
        raise ValidationError("You are only authorized to receive stock for your assigned ASC.")

    has_discrepancy = False
    total_damaged = 0
    total_missing = 0

    for item in dispatch.items.select_related('batch__product').all():
        try:
            rec_bags = int(received_bags_dict.get(str(item.id), 0))
            dmg_bags = int(damaged_bags_dict.get(str(item.id), 0))
        except (ValueError, TypeError):
            raise ValidationError("Bag counts must be valid integers.")

        if rec_bags < 0 or dmg_bags < 0:
            raise ValidationError("Received and damaged bag quantities cannot be negative.")

        if rec_bags + dmg_bags > item.dispatched_bags:
            raise ValidationError(
                f"{item.batch.batch_number}: Total of received ({rec_bags}) and damaged ({dmg_bags}) bags cannot exceed dispatched ({item.dispatched_bags})."
            )

        item.received_bags = rec_bags
        item.damaged_bags = dmg_bags
        item.save()

        missing_count = item.missing_bags
        if dmg_bags > 0 or missing_count > 0:
            has_discrepancy = True
            total_damaged += dmg_bags
            total_missing += missing_count

        bag_weight = item.batch.product.bag_weight_kg

        # 2. Row-level lock on ASC stock
        asc_stock, _ = ASCStock.objects.select_for_update().get_or_create(
            asc_centre=dispatch.asc_centre,
            batch=item.batch,
            defaults={'bags_on_hand': 0}
        )

        # Usable stock: ONLY good bags added
        if rec_bags > 0:
            asc_stock.bags_on_hand += rec_bags
            asc_stock.save()

            StockMovement.objects.create(
                stock=asc_stock,
                movement_type=StockMovement.MovementTypeChoices.INBOUND,
                quantity_kg=Decimal(rec_bags) * bag_weight,
                dispatch=dispatch,
                created_by=officer_user,
                notes=f"Inbound receiving from Dispatch {dispatch.dispatch_reference}"
            )

        if dmg_bags > 0:
            StockMovement.objects.create(
                stock=asc_stock,
                movement_type=StockMovement.MovementTypeChoices.DAMAGED,
                quantity_kg=Decimal(dmg_bags) * bag_weight,
                dispatch=dispatch,
                created_by=officer_user,
                notes=f"Damaged in transit - Dispatch {dispatch.dispatch_reference}"
            )

        if missing_count > 0:
            StockMovement.objects.create(
                stock=asc_stock,
                movement_type=StockMovement.MovementTypeChoices.DISCREPANCY,
                quantity_kg=Decimal(missing_count) * bag_weight,
                dispatch=dispatch,
                created_by=officer_user,
                notes=f"Missing in transit - Dispatch {dispatch.dispatch_reference}"
            )

    # 3. Discrepancy handling
    if has_discrepancy:
        clean_reason = (discrepancy_reason or "").strip()
        if not clean_reason:
            raise ValidationError("A required note/reason must be provided when there is damaged or missing stock.")

        Discrepancy.objects.create(
            dispatch=dispatch,
            damaged_bags=total_damaged,
            missing_bags=total_missing,
            reason=clean_reason,
            recorded_by=officer_user
        )
        dispatch.status = StockDispatch.StatusChoices.RECEIVED_WITH_DISCREPANCY
    else:
        dispatch.status = StockDispatch.StatusChoices.RECEIVED

    dispatch.save()

    # 4. Append-only Audit Log
    AuditLog.objects.create(
        user=officer_user,
        action=f"DISPATCH_RECEIVED: {dispatch.dispatch_reference}",
        details=f"Status: {dispatch.get_status_display()} | Good: {dispatch.items.first().received_bags if dispatch.items.exists() else 0}, Damaged: {total_damaged}, Missing: {total_missing}"
    )

    return dispatch


@transaction.atomic
def write_off_expired_stock(stock_id, head_user, reason, bags_to_write_off=None):
    """
    Expired Stock Write-Off Action (ASC Head only):
    Instead of deleting records, marks stock as written off via an append-only
    StockMovement (type=WRITE_OFF) and writes an immutable AuditLog record.
    Enforces:
    - Authorizer must be ASC Head (is_asc_head=True or Admin).
    - Authorizer must belong to the stock's ASC Centre.
    - Batch MUST be past expiry date (today > batch.expiry_date).
    - Mandatory non-empty reason.
    """
    from django.utils import timezone
    from datetime import date
    from .models import ASCStock, StockMovement

    stock = ASCStock.objects.select_for_update().get(id=stock_id)

    # 1. Permission check: ASC Head or Admin
    is_head = getattr(head_user, 'is_asc_head', False) or head_user.role == 'ADMIN' or head_user.is_superuser
    if not is_head:
        raise ValidationError("Only an authorized ASC Head or Administrator can write off expired stock.")

    # 2. Centre check
    if head_user.role != 'ADMIN' and not head_user.is_superuser:
        if head_user.asc_centre != stock.asc_centre:
            raise ValidationError("You can only write off stock for your assigned Agrarian Service Centre.")

    # 3. Expiry check: Must be expired
    today = timezone.now().date()
    if stock.batch.expiry_date >= today:
        raise ValidationError(f"Batch {stock.batch.batch_number} has not expired yet (Expiry: {stock.batch.expiry_date}). Only expired batches can be written off.")

    # 4. Reason check
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValidationError("A mandatory justification reason must be provided for writing off expired fertilizer.")

    # 5. Quantity deduction
    write_off_count = int(bags_to_write_off) if bags_to_write_off is not None else stock.bags_on_hand
    if write_off_count <= 0:
        raise ValidationError("Write-off quantity must be greater than zero.")
    if write_off_count > stock.bags_on_hand:
        raise ValidationError(f"Cannot write off {write_off_count} bags. Available bags on hand: {stock.bags_on_hand}.")

    bag_weight = stock.batch.product.bag_weight_kg
    quantity_kg = Decimal(write_off_count) * bag_weight

    stock.bags_on_hand -= write_off_count
    stock.save()

    movement = StockMovement.objects.create(
        stock=stock,
        movement_type=StockMovement.MovementTypeChoices.WRITE_OFF,
        quantity_kg=quantity_kg,
        created_by=head_user,
        notes=f"Expired Stock Write-Off: {write_off_count} bags ({quantity_kg}kg). Reason: {clean_reason}"
    )

    AuditLog.objects.create(
        user=head_user,
        action=f"STOCK_WRITE_OFF: {stock.batch.batch_number}",
        details=f"Wrote off {write_off_count} bags ({quantity_kg}kg) at {stock.asc_centre.name}. Reason: {clean_reason}"
    )

    return movement


def get_stock_alerts(asc_centre=None):
    """
    Calculate stock alert metrics for dashboard and reports:
    - Low stock (< threshold bags, customizable per ASC or setting)
    - Near-expiry stock (within NEAR_EXPIRY_DAYS, default 60)
    - Expired stock (past expiry date with bags_on_hand > 0)
    """
    from datetime import date, timedelta
    from django.conf import settings
    from .models import ASCStock, StockThreshold

    today = date.today()
    near_expiry_window_days = getattr(settings, 'NEAR_EXPIRY_DAYS', 60)
    default_low_threshold = getattr(settings, 'LOW_STOCK_THRESHOLD_BAGS', 10)
    near_expiry_date = today + timedelta(days=near_expiry_window_days)

    stocks_qs = ASCStock.objects.select_related('asc_centre', 'batch__product').order_by('batch__expiry_date')
    if asc_centre:
        stocks_qs = stocks_qs.filter(asc_centre=asc_centre)

    expired_stocks = []
    near_expiry_stocks = []
    low_stocks = []

    # Map custom thresholds per (asc_id, product_id)
    threshold_map = {
        (t.asc_centre_id, t.product_id): t.threshold_bags
        for t in StockThreshold.objects.all()
    }

    for stock in stocks_qs:
        # Check expired
        if stock.batch.expiry_date < today:
            if stock.bags_on_hand > 0:
                expired_stocks.append(stock)
        # Check near-expiry
        elif stock.batch.expiry_date <= near_expiry_date:
            if stock.bags_on_hand > 0:
                near_expiry_stocks.append(stock)

        # Check low stock threshold
        threshold = threshold_map.get((stock.asc_centre_id, stock.batch.product_id), default_low_threshold)
        if stock.bags_on_hand < threshold:
            stock.threshold_applied = threshold
            low_stocks.append(stock)

    return {
        'expired_stocks': expired_stocks,
        'near_expiry_stocks': near_expiry_stocks,
        'low_stocks': low_stocks,
        'today': today,
        'near_expiry_date': near_expiry_date,
    }