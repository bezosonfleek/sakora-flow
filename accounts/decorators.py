from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect

OWNER, ADMIN, CASHIER = "owner", "admin", "cashier"
MANAGERS = (OWNER, ADMIN)
ALL_STAFF = (OWNER, ADMIN, CASHIER)


def role_required(*roles):
    """Page views: sign-in required, and the user must have one of the roles.
    SUPERADMIN has no client, so they are sent to the admin site instead."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if user.is_superuser:
                return redirect("admin:index")
            if user.role not in roles or request.client is None:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return login_required(wrapper)

    return decorator


def api_role_required(*roles):
    """JSON endpoints: same rules, but answer with JSON errors instead of redirects."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return JsonResponse({"error": "Your session has ended. Please sign in again."}, status=401)
            if user.is_superuser or user.role not in roles or request.client is None:
                return JsonResponse({"error": "You are not allowed to do this."}, status=403)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
