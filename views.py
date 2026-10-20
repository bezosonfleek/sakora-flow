from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect


def healthz(request):
    """Liveness + database check. Used by Docker and uptime monitors. No auth."""
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except Exception:
        return JsonResponse({"status": "error", "db": "down"}, status=503)
    return JsonResponse({"status": "ok", "db": "up"})


@login_required
def home(request):
    """Send each person to the right starting page for their role."""
    user = request.user
    if user.is_superuser:
        return redirect("admin:index")
    if user.role == "cashier":
        return redirect("till")
    if user.role in ("owner", "admin"):
        return redirect("dashboard")
    raise PermissionDenied
