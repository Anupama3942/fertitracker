from django.urls import path
from . import views

urlpatterns = [
    path('', views.inventory_list_view, name='inventory_list'),
    path('batch/new/', views.create_batch_view, name='create_batch'),
    path('dispatch/new/', views.create_dispatch_view, name='create_dispatch'),
    path('dispatch/<int:dispatch_id>/', views.receive_dispatch_view, name='receive_dispatch'),
    path('discrepancies/', views.discrepancy_report_view, name='discrepancy_report'),
    path('stock/write-off/<int:stock_id>/', views.write_off_expired_stock_view, name='write_off_expired_stock'),
]