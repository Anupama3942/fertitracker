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
    ගොවියාගේ QR ටෝකනය පරීක්ෂා කර, Atomic Transaction එකක් මඟින් පොහොර නිකුත් කිරීම සිදු කරයි (FR-11, FR-12, FR-17).
    """
    import hashlib
    hashed_input = hashlib.sha256(raw_token_string.encode()).hexdigest()

    # 1. ටෝකනය සෙවීම සහ වලංගුභාවය පරීක්ෂා කිරීම (තත්පර 60ක කාල සීමාව)
    try:
        qr_token = QRToken.objects.select_for_update().get(token_hash=hashed_input)
    except QRToken.DoesNotExist:
        raise ValidationError("අවලංගු හෝ කල් ඉකුත් වූ QR ටෝකනයකි.")

    if not qr_token.is_valid():
        raise ValidationError("මෙම QR ටෝකනය දැනටමත් භාවිත කර ඇත හෝ කාලය අවසන් වී ඇත.")

    farmer = qr_token.farmer

    # 2. ASC නිලධාරියාගේ බලපත්‍රය පරීක්ෂා කිරීම (Business Rule 12 / FR-20)
    if asc_officer_user.role == 'ASC_OFFICER' and asc_officer_user.asc_centre:
        asc_centre = asc_officer_user.asc_centre
    else:
        raise ValidationError("පොහොර නිකුත් කළ හැක්කේ අදාළ ASC නිලධාරියාට පමණි.")

    # 3. ගොවියාට අදාළ කන්නයේ (Season) හිමිකම (Entitlement) ලබා ගැනීම
    try:
        entitlement = FarmerEntitlement.objects.select_for_update().get(
            farmer=farmer,
            season_id=season_id,
            product__name__iexact='Urea'  # උදාහරණයක් ලෙස ප්‍රධාන පොහොර නිෂ්පාදනය
        )
    except FarmerEntitlement.DoesNotExist:
        raise ValidationError("මෙම ගොවියාට අදාළ කන්නය සඳහා පොහොර හිමිකම් (Entitlements) වාර්තාවක් නොමැත.")

    # නිකුත් කිරීමට නියමිත ප්‍රමාණය (උදා: මල්ලක් හෝ නිශ්චිත කිලෝග්‍රෑම් ප්‍රමාණයක් - මෙහිදී මල්ලක් 50kg ලෙස සලකමු)
    issue_kg = Decimal('50.00')

    if entitlement.remaining_kg < issue_kg:
        raise ValidationError(f"ගොවියාගේ ඉතිරි කෝටාව ප්‍රමාණවත් නොවේ. ඉතිරි ප්‍රමාණය: {entitlement.remaining_kg} kg පමණි.")

    # 4. ASC ගබඩාවේ තොගය (FEFO පිළිවෙළට මුලින්ම කල් ඉකුත් වන Batch එක) ලබා ගැනීම
    asc_stock = ASCStock.objects.select_for_update().filter(
        asc_centre=asc_centre,
        bags_on_hand__gt=0
    ).order_by('batch__expiry_date').first()

    if not asc_stock or asc_stock.bags_on_hand < 1:
        raise ValidationError("මෙම ASC ගබඩාවේ ගොවීන්ට නිකුත් කිරීමට ප්‍රමාණවත් පොහොර තොග නොමැත.")

    batch = asc_stock.batch

    # 5. තොග සහ කෝටා යාවත්කාලීන කිරීම (Atomic updates)
    # අ) ගොවියාගේ ඉතිරි කෝටාව අඩු කිරීම
    entitlement.remaining_kg -= issue_kg
    entitlement.save()

    # ආ) ASC ගබඩා තොගය අඩු කිරීම (මලු 1කින්)
    asc_stock.bags_on_hand -= 1
    asc_stock.save()

    # ඇ) QR ටෝකනය පාවිච්චි කළ බවට (Redeemed) සටහන් කිරීම
    qr_token.is_redeemed = True
    qr_token.save()

    #ඈ) Distribution වාර්තාවක් සෑදීම
    distribution = FertilizerDistribution.objects.create(
        farmer=farmer,
        asc_centre=asc_centre,
        batch=batch,
        season_id=season_id,
        issued_by=asc_officer_user,
        quantity_kg=issue_kg
    )

    # ඉ) Stock Movement ලෙජරයේ OUTBOUND සටහන් කිරීම (FR-17)
    StockMovement.objects.create(
        stock=asc_stock,
        movement_type=StockMovement.MovementTypeChoices.OUTBOUND,
        quantity_kg=issue_kg
    )

    # ஈ) Append-only Audit Log එකක් ලිවීම
    AuditLog.objects.create(
        user=asc_officer_user,
        action=f"DISTRIBUTION_ISSUED: {distribution.receipt_number}",
        ip_address=client_ip,
        details=f"Issued {issue_kg}kg to Farmer {farmer.nic_number} from Batch {batch.batch_number}"
    )

    return distribution