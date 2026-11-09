from django.urls import path
from . import views

urlpatterns = [
    path('farmer/dashboard/', views.farmer_qr_dashboard, name='farmer_dashboard'),
    path('asc/scan/', views.asc_scanner_view, name='asc_scanner'),
    path('receipt/<str:receipt_number>/', views.distribution_receipt_view, name='distribution_receipt'),
    path('audit/logs/', views.audit_logs_view, name='audit_logs'),
    path('reports/', views.reports_and_search_view, name='reports_search'),
    path('reports/export-csv/', views.export_report_csv, name='export_report_csv'),
    path('reports/batch-trace/', views.batch_traceability_view, name='batch_traceability'),
    path('farmers/manage/', views.manage_farmers_and_bulk_import_view, name='manage_farmers'),
    path('entitlements/csv-sample/', views.download_sample_entitlement_csv, name='download_sample_entitlement_csv'),
    path('entitlements/csv-preview/', views.preview_entitlement_csv_view, name='preview_entitlement_csv'),
    path('entitlements/<int:entitlement_id>/edit/', views.edit_entitlement_view, name='edit_entitlement'),

    # Part 1: SMS Backup Code (Keypad Phone Farmers)
    path('farmers/search/', views.farmer_search_view, name='farmer_search'),
    path('sms/send/<int:farmer_id>/', views.send_sms_code_view, name='send_sms_code'),
    path('demo/sms-inbox/', views.demo_sms_inbox_view, name='demo_sms_inbox'),

    # Part 2: Officer-Assisted Issue (Two-Officer Approval)
    path('assisted/request/<int:farmer_id>/', views.create_assisted_request_view, name='create_assisted_request'),
    path('assisted/pending/', views.pending_assisted_requests_view, name='pending_assisted_requests'),
    path('assisted/approve/<int:request_id>/', views.approve_assisted_request_view, name='approve_assisted_request'),
    path('assisted/reject/<int:request_id>/', views.reject_assisted_request_view, name='reject_assisted_request'),
    path('assisted/issue/<int:approval_id>/', views.assisted_issue_confirm_view, name='assisted_issue_confirm'),
    path('reports/assisted-issues/', views.assisted_issues_report_view, name='assisted_issues_report'),
]