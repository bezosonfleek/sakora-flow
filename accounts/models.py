from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

PIN_MAX_FAILURES = 5
PIN_LOCK_MINUTES = 5


def validate_pin(raw: str) -> None:
    if not raw.isdigit() or not (4 <= len(raw) <= 6):
        raise ValidationError("PIN must be 4 to 6 digits.")


class Client(models.Model):
    """One business (e.g. a supermarket). Every other record belongs to a client."""

    RECEIPT_WIDTHS = [(58, "58 mm"), (80, "80 mm")]

    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=200, blank=True)
    currency = models.CharField(max_length=3, default="KES")
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("16.00"))
    receipt_width = models.PositiveSmallIntegerField(choices=RECEIPT_WIDTHS, default=80)
    receipt_header = models.CharField(max_length=200, blank=True)
    receipt_footer = models.CharField(max_length=200, blank=True, default="Thank you for shopping with us!")
    receipt_seq = models.PositiveBigIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def allocate_receipt_no(self) -> str:
        """Next receipt number. Locks the client row, so call inside the sale transaction."""
        with transaction.atomic():
            locked = Client.objects.select_for_update().get(pk=self.pk)
            locked.receipt_seq += 1
            locked.save(update_fields=["receipt_seq"])
        return f"R-{locked.receipt_seq:06d}"


class User(AbstractUser):
    """SUPERADMIN = is_superuser with no client. Everyone else belongs to one client."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        CASHIER = "cashier", "Cashier"

    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.PROTECT, related_name="users")
    role = models.CharField(max_length=10, choices=Role.choices, blank=True)
    pin_hash = models.CharField(max_length=128, blank=True)
    pin_failures = models.PositiveSmallIntegerField(default=0)
    pin_locked_until = models.DateTimeField(null=True, blank=True)

    def clean(self):
        super().clean()
        if not self.is_superuser:
            if not self.client_id:
                raise ValidationError({"client": "Staff must belong to a client."})
            if not self.role:
                raise ValidationError({"role": "Staff must have a role."})

    @property
    def is_manager(self) -> bool:
        return self.role in (self.Role.OWNER, self.Role.ADMIN)

    @property
    def has_pin(self) -> bool:
        return bool(self.pin_hash)

    def set_pin(self, raw: str) -> None:
        validate_pin(raw)
        self.pin_hash = make_password(raw)
        self.pin_failures = 0
        self.pin_locked_until = None

    def check_pin(self, raw: str) -> bool:
        """Check a PIN with a lockout after repeated failures."""
        now = timezone.now()
        if self.pin_locked_until and self.pin_locked_until > now:
            return False
        if self.pin_hash and check_password(raw, self.pin_hash):
            if self.pin_failures or self.pin_locked_until:
                self.pin_failures = 0
                self.pin_locked_until = None
                self.save(update_fields=["pin_failures", "pin_locked_until"])
            return True
        self.pin_failures += 1
        if self.pin_failures >= PIN_MAX_FAILURES:
            self.pin_locked_until = now + timedelta(minutes=PIN_LOCK_MINUTES)
            self.pin_failures = 0
        self.save(update_fields=["pin_failures", "pin_locked_until"])
        return False
