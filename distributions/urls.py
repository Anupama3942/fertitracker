from django.urls import path
from . import views

urlpatterns = [
    path('farmer/dashboard/', views.farmer_qr_dashboard, name='farmer_dashboard'),
    path('asc/scan/', views.asc_scanner_view, name='asc_scanner'),
    path('receipt/<str:receipt_number>/', views.distribution_receipt_view, name='distribution_receipt'),
    path('audit/logs/', views.audit_logs_view, name='audit_logs'),
    path('reports/', views.reports_and_search_view, name='reports_search'),
    path('reports/export-csv/', views.export_report_csv, name='export_report_csv'),
    path('farmers/manage/', views.manage_farmers_and_bulk_import_view, name='manage_farmers'),
]