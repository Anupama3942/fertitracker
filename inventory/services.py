import io
import base64
import qrcode
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import StockDispatch, DispatchItem, ASCStock, StockMovement

def generate_qr_base64(data_string):
    """
    Generate a QR code for the provided text and convert it into a Base64 string
    that can be displayed directly on an HTML page without saving a separate image file (FR-06).
    """
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(data_string)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@transaction.atomic
def confirm_dispatch_receiving(dispatch_id, officer_user, received_bags_dict, damaged_bags_dict):
    """
    FR-07, FR-08, FR-17: Atomic transaction for confirming the fertilizer stock received by an ASC officer.
    """
    # 1. Retrieve the dispatch record using a PostgreSQL row-level lock.
    dispatch = StockDispatch.objects.select_for_update().get(id=dispatch_id)

    # Prevent the dispatch from being received again if it has already been received.
    if dispatch.status != StockDispatch.StatusChoices.DISPATCHED:
        raise ValidationError("This dispatch has already been received and confirmed.")

    # Business Rule 12 / FR-20: Only an officer from the relevant ASC can receive the stock.
    if officer_user.role == 'ASC_OFFICER' and officer_user.asc_centre != dispatch.asc_centre:
        raise ValidationError("You are only authorized to receive stock for your assigned ASC.")

    has_discrepancy = False

    for item in dispatch.items.select_related('batch__product').all():
        rec_bags = int(received_bags_dict.get(str(item.id), 0))
        dmg_bags = int(damaged_bags_dict.get(str(item.id), 0))

        # The number of received and damaged bags cannot exceed the total number of dispatched bags.
        if rec_bags + dmg_bags > item.dispatched_bags:
            raise ValidationError(
                f"{item.batch.batch_number}: The total number of received ({rec_bags}) and damaged ({dmg_bags}) bags cannot exceed the number of dispatched bags ({item.dispatched_bags})."
            )

        item.received_bags = rec_bags
        item.damaged_bags = dmg_bags
        item.save()

        # Mark the dispatch as a discrepancy if the number of good bags received is less than the number dispatched.
        if rec_bags != item.dispatched_bags:
            has_discrepancy = True

        bag_weight = item.batch.product.bag_weight_kg

        # 2. Retrieve or create the ASCStock record (FR-08).
        asc_stock, _ = ASCStock.objects.select_for_update().get_or_create(
            asc_centre=dispatch.asc_centre,
            batch=item.batch,
            defaults={'bags_on_hand': 0}
        )

        # Add only bags received in good condition to the stock available for issuing to farmers (bags_on_hand).
        if rec_bags > 0:
            asc_stock.bags_on_hand += rec_bags
            asc_stock.save()

            # FR-17: Record the INBOUND stock movement.
            StockMovement.objects.create(
                stock=asc_stock,
                movement_type=StockMovement.MovementTypeChoices.INBOUND,
                quantity_kg=Decimal(rec_bags) * bag_weight
            )

        # Record damaged bags separately as DAMAGED stock movements.
        if dmg_bags > 0:
            StockMovement.objects.create(
                stock=asc_stock,
                movement_type=StockMovement.MovementTypeChoices.DAMAGED,
                quantity_kg=Decimal(dmg_bags) * bag_weight
            )

        # Record missing bags as DISCREPANCY stock movements.
        if item.missing_bags > 0:
            StockMovement.objects.create(
                stock=asc_stock,
                movement_type=StockMovement.MovementTypeChoices.DISCREPANCY,
                quantity_kg=Decimal(item.missing_bags) * bag_weight
            )

    # 3. Update the final status of the dispatch.
    dispatch.status = (
        StockDispatch.StatusChoices.DISCREPANCY if has_discrepancy
        else StockDispatch.StatusChoices.RECEIVED
    )
    dispatch.save()
    return dispatch