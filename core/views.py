from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render


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
    return render(request, "home.html")
