from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from functools import wraps

def role_required(*allowed_roles):
    """Restrict a view to users with one of the specified roles or superusers."""
    def decorator(view_func):
        """Wrap a view with authentication and role checks."""
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            """Allow authorized users to call the view or raise a permission error."""
            if request.user.role in allowed_roles or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("You DONT HAVE Access for this Page.")
        return _wrapped_view
    return decorator