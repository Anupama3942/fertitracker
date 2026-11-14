from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.translation import gettext as _
from .permissions import get_effective_role, has_permission, Permission


def forbid_response(request, message=None):
    """Render the translated 403 error page with HTTP 403 status code."""
    context = {
        'error_message': message or _("You do not have permission to view this page or perform this operation.")
    }
    return render(request, '403.html', context, status=403)


def role_required(*allowed_roles):
    """
    Restrict a view strictly to users with one of the allowed roles.
    Separation of duties: does NOT bypass for admins/superusers when ADMIN is not listed.
    Auditors are strictly barred from non-safe HTTP methods (POST/PUT/DELETE/PATCH).
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            user = request.user

            # Auditor restriction: strictly read-only on all endpoints
            if user.role == 'AUDITOR' and request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
                return forbid_response(request, _("Auditors have strictly read-only access."))

            # Match on effective role (e.g. 'ASC_HEAD') or base user.role
            effective_role = get_effective_role(user)
            user_role = getattr(user, 'role', None)

            # Check if user role matches allowed roles
            is_allowed = False
            for role in allowed_roles:
                if role == 'ASC_HEAD':
                    if effective_role == 'ASC_HEAD':
                        is_allowed = True
                        break
                elif role == 'ASC_OFFICER':
                    if user_role == 'ASC_OFFICER':
                        is_allowed = True
                        break
                elif role == user_role:
                    is_allowed = True
                    break

            if not is_allowed:
                return forbid_response(request)

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def require_permission(perm):
    """Check a specific Permission from accounts.permissions."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if request.user.role == 'AUDITOR' and request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
                return forbid_response(request, _("Auditors have strictly read-only access."))

            if not has_permission(request.user, perm):
                return forbid_response(request)

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def require_asc_head(view_func):
    """Require user to be an ASC Officer with ASC Head approver privileges (not Admin)."""
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if user.role != 'ASC_OFFICER' or not getattr(user, 'is_asc_head', False):
            return forbid_response(request, _("Only an authorized ASC Head can perform this action."))
        return view_func(request, *args, **kwargs)
    return _wrapped_view