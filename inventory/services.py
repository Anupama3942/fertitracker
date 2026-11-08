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