"""
Centralized Role-Based Access Control (RBAC) Permissions Table and Policy Helpers.

This module defines the single source of truth for all role permissions across FertiTracker,
enforcing separation of duties per SRS BR-02 and FR-12:
- Administrator: System configuration, master data, user accounts, seasons, farmer entitlements, read-only audit/reports.
                 Strictly forbidden from operational actions (receiving, issuing, QR scanning, write-offs).
- Warehouse Officer: Registering batches, creating dispatches, viewing warehouse dispatches.
                     Strictly forbidden from receiving, issuing, and farmer functions.
- ASC Officer: Receiving incoming dispatches for their assigned ASC only, farmer registration,
               QR scan/issue, SMS codes, assisted issue requests.
- ASC Head: Everything an ASC Officer can do, plus approving/rejecting assisted issue requests
            (Two-Officer rule: never their own) and writing off expired stock in their assigned ASC.
- Auditor: Read-only reports, audit logs, discrepancy reports, batch traceability. All POST/write operations blocked.
- Farmer: Personal dashboard, dynamic single-use QR code, digital receipts only.
"""

from enum import Enum


class Permission(str, Enum):
    # Administrative & Management
    MANAGE_USERS = 'manage_users'
    MANAGE_SEASONS = 'manage_seasons'
    MANAGE_ENTITLEMENTS = 'manage_entitlements'

    # Warehouse Operations
    CREATE_BATCH = 'create_batch'
    CREATE_DISPATCH = 'create_dispatch'

    # ASC Counter & Receiving Operations
    RECEIVE_DISPATCH = 'receive_dispatch'
    QR_SCANNER = 'qr_scanner'
    FIND_FARMER = 'find_farmer'
    SEND_SMS_CODE = 'send_sms_code'
    REQUEST_ASSISTED_ISSUE = 'request_assisted_issue'
    ISSUE_ASSISTED = 'issue_assisted'

    # ASC Head Authorizations
    APPROVE_ASSISTED_ISSUE = 'approve_assisted_issue'
    WRITE_OFF_STOCK = 'write_off_stock'

    # Read-Only & Inspection
    VIEW_INVENTORY = 'view_inventory'
    VIEW_DISPATCH = 'view_dispatch'
    VIEW_REPORTS = 'view_reports'
    VIEW_DISCREPANCIES = 'view_discrepancies'
    VIEW_ASSISTED_REPORT = 'view_assisted_report'
    VIEW_AUDIT_LOGS = 'view_audit_logs'
    VIEW_RECEIPT = 'view_receipt'

    # Farmer Functions
    FARMER_DASHBOARD = 'farmer_dashboard'


# Canonical Role Permissions Mapping
ROLE_PERMISSIONS = {
    'ADMIN': {
        Permission.MANAGE_USERS,
        Permission.MANAGE_SEASONS,
        Permission.MANAGE_ENTITLEMENTS,
        Permission.VIEW_INVENTORY,
        Permission.VIEW_DISPATCH,
        Permission.VIEW_REPORTS,
        Permission.VIEW_DISCREPANCIES,
        Permission.VIEW_ASSISTED_REPORT,
        Permission.VIEW_AUDIT_LOGS,
        Permission.VIEW_RECEIPT,
    },
    'WAREHOUSE_OFFICER': {
        Permission.CREATE_BATCH,
        Permission.CREATE_DISPATCH,
        Permission.VIEW_INVENTORY,
        Permission.VIEW_DISPATCH,
        Permission.VIEW_REPORTS,
        Permission.VIEW_DISCREPANCIES,
    },
    'ASC_OFFICER': {
        Permission.RECEIVE_DISPATCH,
        Permission.VIEW_DISPATCH,
        Permission.VIEW_INVENTORY,
        Permission.MANAGE_ENTITLEMENTS,
        Permission.QR_SCANNER,
        Permission.FIND_FARMER,
        Permission.SEND_SMS_CODE,
        Permission.REQUEST_ASSISTED_ISSUE,
        Permission.ISSUE_ASSISTED,
        Permission.VIEW_REPORTS,
        Permission.VIEW_RECEIPT,
        Permission.VIEW_DISCREPANCIES,
    },
    'ASC_HEAD': {
        Permission.RECEIVE_DISPATCH,
        Permission.VIEW_DISPATCH,
        Permission.VIEW_INVENTORY,
        Permission.MANAGE_ENTITLEMENTS,
        Permission.QR_SCANNER,
        Permission.FIND_FARMER,
        Permission.SEND_SMS_CODE,
        Permission.REQUEST_ASSISTED_ISSUE,
        Permission.ISSUE_ASSISTED,
        Permission.APPROVE_ASSISTED_ISSUE,
        Permission.WRITE_OFF_STOCK,
        Permission.VIEW_REPORTS,
        Permission.VIEW_RECEIPT,
        Permission.VIEW_DISCREPANCIES,
    },
    'AUDITOR': {
        Permission.VIEW_INVENTORY,
        Permission.VIEW_DISPATCH,
        Permission.VIEW_REPORTS,
        Permission.VIEW_DISCREPANCIES,
        Permission.VIEW_ASSISTED_REPORT,
        Permission.VIEW_AUDIT_LOGS,
        Permission.VIEW_RECEIPT,
    },
    'FARMER': {
        Permission.FARMER_DASHBOARD,
        Permission.VIEW_RECEIPT,
    },
}


def get_effective_role(user):
    """Return 'ASC_HEAD' if user is an ASC Officer with head approver authority, else user.role."""
    if not user or not user.is_authenticated:
        return None
    if user.role == 'ASC_OFFICER' and getattr(user, 'is_asc_head', False):
        return 'ASC_HEAD'
    return getattr(user, 'role', None)


def has_permission(user, permission):
    """Check if the user has the specified permission based on their effective role."""
    if not user or not user.is_authenticated:
        return False
    effective_role = get_effective_role(user)
    allowed = ROLE_PERMISSIONS.get(effective_role, set())
    if isinstance(permission, Permission):
        return permission in allowed
    try:
        perm_enum = Permission(permission)
        return perm_enum in allowed
    except ValueError:
        return permission in allowed


def can_receive_dispatch(user, dispatch):
    """
    BR-02: Only an ASC Officer or ASC Head belonging to the dispatch's destination ASC
    may confirm receipt of a dispatch.
    """
    if not user or not user.is_authenticated:
        return False
    if user.role != 'ASC_OFFICER':
        return False
    if not getattr(user, 'asc_centre_id', None):
        return False
    if not dispatch or getattr(dispatch, 'asc_centre_id', None) != user.asc_centre_id:
        return False
    return True


def can_approve_assisted_request(user, request_obj):
    """
    Two-Officer Rule: Only an authorized ASC Head of the same ASC may approve or reject.
    The approver can NEVER be the same person who requested the issue.
    """
    if not user or not user.is_authenticated:
        return False
    if user.role != 'ASC_OFFICER' or not getattr(user, 'is_asc_head', False):
        return False
    if not getattr(user, 'asc_centre_id', None):
        return False
    if not request_obj or getattr(request_obj, 'asc_centre_id', None) != user.asc_centre_id:
        return False
    if getattr(request_obj, 'requested_by_id', None) == user.id:
        return False
    return True


def can_write_off_stock(user, stock):
    """
    Only an authorized ASC Head belonging to the stock's ASC may write off expired stock.
    """
    if not user or not user.is_authenticated:
        return False
    if user.role != 'ASC_OFFICER' or not getattr(user, 'is_asc_head', False):
        return False
    if not getattr(user, 'asc_centre_id', None):
        return False
    if not stock or getattr(stock, 'asc_centre_id', None) != user.asc_centre_id:
        return False
    return True
