from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class PinBackend(ModelBackend):
    """Quick cashier login with username + PIN. Cashiers only; owners/admins use passwords."""

    def authenticate(self, request, username=None, pin=None, **kwargs):
        if not username or not pin:
            return None
        User = get_user_model()
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return None
        if user.role != User.Role.CASHIER or not self.user_can_authenticate(user):
            return None
        return user if user.check_pin(pin) else None
