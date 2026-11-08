from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.exceptions import ValidationError
from accounts.decorators import role_required
from core.models import Warehouse, ASCCentre, FertilizerProduct
from .models import FertilizerBatch, StockDispatch, DispatchItem, ASCStock, StockMovement
from .services import generate_qr_base64, confirm_dispatch_receiving

@role_required('ADMIN', 'WAREHOUSE_OFFICER', 'ASC_OFFICER', 'AUDITOR')
def inventory_list_view(request):
    """Render FEFO-ordered ASC stock and warehouse dispatches for authorized users."""
    user = request.user
    dispatches = StockDispatch.objects.select_related('warehouse', 'asc_centre', 'created_by').order_by('-dispatched_at')
    # FEFO (First-Expired-First-Out): Sort stock by expiry date.
    stocks = ASCStock.objects.select_related('asc_centre', 'batch__product').order_by('batch__expiry_date')

    # If the user is an ASC Officer, show only data related to their ASC (FR-20).
    if user.role == 'ASC_OFFICER' and user.asc_centre:
        dispatches = dispatches.filter(asc_centre=user.asc_centre)
        stocks = stocks.filter(asc_centre=user.asc_centre)

    today = date.today()
    near_expiry_threshold = today + timedelta(days=30)
    for stock in stocks:
        if stock.batch.expiry_date < today:
            stock.expiry_label = 'EXPIRED'
            stock.expiry_badge_class = 'bg-red-100 text-red-700 font-bold'
        elif stock.batch.expiry_date <= near_expiry_threshold:
            stock.expiry_label = 'ISSUE FIRST (FEFO)'
            stock.expiry_badge_class = 'bg-amber-100 text-amber-800 font-semibold'
        else:
            stock.expiry_label = ''
            stock.expiry_badge_class = ''

    context = {
        'dispatches': dispatches,
        'stocks': stocks,
        'batches': FertilizerBatch.objects.select_related('warehouse', 'product').order_by('expiry_date'),
        'today': today,
        'near_expiry_threshold': near_expiry_threshold,
    }
    return render(request, 'inventory/inventory_list.html', context)


@role_required('ADMIN', 'WAREHOUSE_OFFICER')
def create_batch_view(request):
    """Create a unique fertilizer batch and render the batch form."""
    if request.method == 'POST':
        warehouse_id = request.POST.get('warehouse')
        product_id = request.POST.get('product')
        batch_number = request.POST.get('batch_number').strip().upper()
        expiry_date = request.POST.get('expiry_date')

        if FertilizerBatch.objects.filter(batch_number=batch_number).exists():
            messages.error(request, f"Batch number '{batch_number}' already exists in the system (Business Rule 1).")
        else:
            FertilizerBatch.objects.create(
                warehouse_id=warehouse_id,
                product_id=product_id,
                batch_number=batch_number,
                expiry_date=expiry_date
            )
            messages.success(request, f"Batch '{batch_number}' was created successfully!")
            return redirect('inventory_list')

    context = {
        'warehouses': Warehouse.objects.all(),
        'products': FertilizerProduct.objects.all(),
    }
    return render(request, 'inventory/create_batch.html', context)


@role_required('ADMIN', 'WAREHOUSE_OFFICER')
def create_dispatch_view(request):
    """Create a warehouse-to-ASC dispatch and redirect to its receiving page."""
    if request.method == 'POST':
        warehouse_id = request.POST.get('warehouse')
        asc_centre_id = request.POST.get('asc_centre')
        batch_id = request.POST.get('batch')
        dispatched_bags = int(request.POST.get('dispatched_bags', 0))

        if dispatched_bags <= 0:
            messages.error(request, "The number of dispatched bags must be greater than 0.")
        else:
            dispatch = StockDispatch.objects.create(
                warehouse_id=warehouse_id,
                asc_centre_id=asc_centre_id,
                created_by=request.user
            )
            DispatchItem.objects.create(
                dispatch=dispatch,
                batch_id=batch_id,
                dispatched_bags=dispatched_bags
            )
            messages.success(request, f"Dispatch {dispatch.dispatch_reference} was created successfully!")
            return redirect('receive_dispatch', dispatch_id=dispatch.id)

    context = {
        'warehouses': Warehouse.objects.all(),
        'asc_centres': ASCCentre.objects.all(),
        'batches': FertilizerBatch.objects.select_related('product', 'warehouse').order_by('expiry_date'),
    }
    return render(request, 'inventory/create_dispatch.html', context)


@role_required('ADMIN', 'WAREHOUSE_OFFICER', 'ASC_OFFICER', 'AUDITOR')
def receive_dispatch_view(request, dispatch_id):
    """Display a dispatch and process its received, damaged, and missing quantities."""
    dispatch = get_object_or_404(
        StockDispatch.objects.select_related('warehouse', 'asc_centre', 'created_by'),
        id=dispatch_id
    )
    items = dispatch.items.select_related('batch__product').all()
    qr_base64 = generate_qr_base64(dispatch.dispatch_reference)

    if request.method == 'POST':
        if request.user.role not in ['ADMIN', 'ASC_OFFICER']:
            messages.error(request, "Only an ASC officer can confirm that the stock has been received.")
            return redirect('receive_dispatch', dispatch_id=dispatch.id)

        received_dict = {}
        damaged_dict = {}
        for item in items:
            received_dict[str(item.id)] = request.POST.get(f"received_{item.id}", 0)
            damaged_dict[str(item.id)] = request.POST.get(f"damaged_{item.id}", 0)

        try:
            confirm_dispatch_receiving(dispatch.id, request.user, received_dict, damaged_dict)
            messages.success(request, f"Dispatch {dispatch.dispatch_reference} was confirmed successfully and the ASC stock was updated!")
            return redirect('receive_dispatch', dispatch_id=dispatch.id)
        except ValidationError as e:
            messages.error(request, e.message)

    context = {
        'dispatch': dispatch,
        'items': items,
        'qr_base64': qr_base64,
    }
    return render(request, 'inventory/receive_dispatch.html', context)