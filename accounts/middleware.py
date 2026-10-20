from django.contrib.auth import logout
from django.shortcuts import render


class ClientMiddleware:
    """Attaches request.client and blocks users whose client is missing or suspended."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.client = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not user.is_superuser:
            client = user.client
            if client is None or not client.is_active:
                logout(request)
                return render(request, "accounts/suspended.html", status=403)
            request.client = client
        return self.get_response(request)
