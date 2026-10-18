from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import (
    ASCStock,
    DispatchItem,
    StockDispatch,
    StockMovement,
)


ZERO = Decimal("0.00")
MAX_KG = Decimal("9999999999.99")


def validate_kg(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Invalid quantity.")

    if not amount.is_finite():
        raise ValidationError("Quantity must be finite.")

    if amount < ZERO or amount > MAX_KG:
        raise ValidationError("Quantity is out of range.")

    if amount != amount.quantize(Decimal("0.01")):
        raise ValidationError("Use at most 2 decimal places.")

    return amount


@transaction.atomic
def receive_dispatch(*, dispatch_id, receiver, quantities):

    # Step 1: Check the officer.
    if (
        receiver is None
        or not receiver.is_authenticated
        or not receiver.is_active
    ):
        raise PermissionDenied("Login required.")

    allowed_roles = {"ASC_OFFICER", "SYSTEM_ADMIN"}

    if not (
        receiver.is_superuser
        or receiver.role in allowed_roles
    ):
        raise PermissionDenied("Not allowed to receive stock.")

    # Step 2: Lock the dispatch record.
    dispatch = (
        StockDispatch.objects
        .select_for_update()
        .get(pk=dispatch_id)
    )

    if dispatch.status != StockDispatch.Status.DISPATCHED:
        raise ValidationError("Dispatch is not awaiting receipt.")

    if dispatch.dispatch_date is None:
        raise ValidationError("Dispatch date is missing.")

    # Step 3: Load the dispatch items.
    items = list(
        DispatchItem.objects
        .select_related("batch")
        .filter(dispatch=dispatch)
        .order_by("batch_id", "id")
    )

    if not items:
        raise ValidationError("Dispatch has no items.")

    expected_ids = {item.id for item in items}

    if set(quantities.keys()) != expected_ids:
        raise ValidationError("Provide quantities for every item.")

    # Step 4: Validate everything before updating stock.
    validated_items = []

    for item in items:
        data = quantities[item.id]

        if not isinstance(data, dict):
            raise ValidationError("Invalid receiving details.")

        try:
            received = validate_kg(data["received"])
            damaged = validate_kg(data["damaged"])
            missing = validate_kg(data["missing"])
        except KeyError:
            raise ValidationError("Receiving quantities are incomplete.")

        total = received + damaged + missing

        if total != item.dispatched_quantity_kg:
            raise ValidationError(
                f"Quantities do not match for batch {item.batch}."
            )

        if item.batch.warehouse_id != dispatch.warehouse_id:
            raise ValidationError(
                "Batch does not belong to dispatch warehouse."
            )

        validated_items.append(
            (item, received, damaged, missing)
        )

    # Step 5: Update stock and record history.
    for item, received, damaged, missing in validated_items:

        if received > ZERO:
            stock, created = (
                ASCStock.objects
                .select_for_update()
                .get_or_create(
                    asc_id=dispatch.destination_asc_id,
                    batch_id=item.batch_id,
                    defaults={"quantity_kg": ZERO},
                )
            )

            stock.quantity_kg += received

            stock.save(
                update_fields=["quantity_kg", "updated_at"]
            )

            StockMovement.objects.create(
                asc_id=dispatch.destination_asc_id,
                batch_id=item.batch_id,
                movement_type=StockMovement.MovementType.RECEIPT,
                quantity_kg=received,
                balance_after_kg=stock.quantity_kg,
                source_reference=str(dispatch.dispatch_reference),
                created_by=receiver,
            )

        item.received_quantity_kg = received
        item.damaged_quantity_kg = damaged
        item.missing_quantity_kg = missing

        item.save(
            update_fields=[
                "received_quantity_kg",
                "damaged_quantity_kg",
                "missing_quantity_kg",
            ]
        )

    # Step 6: Finish the dispatch.
    dispatch.status = StockDispatch.Status.RECEIVED
    dispatch.save(update_fields=["status"])

    return dispatch