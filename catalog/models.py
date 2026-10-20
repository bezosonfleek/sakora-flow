from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Category(models.Model):
    client = models.ForeignKey("accounts.Client", on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"
        constraints = [models.UniqueConstraint(fields=["client", "name"], name="uniq_category_per_client")]

    def __str__(self):
        return self.name


class Product(models.Model):
    client = models.ForeignKey("accounts.Client", on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=200)
    barcode = models.CharField(max_length=64, blank=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Selling price, VAT included.")
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="What you pay the supplier.")
    vat_applies = models.BooleanField(default=True, help_text="Untick for VAT-exempt or zero-rated items.")
    stock = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    reorder_level = models.DecimalField(
        max_digits=12, decimal_places=3, default=0, help_text="Flag as low stock at or below this quantity."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "barcode"],
                condition=~Q(barcode=""),
                name="uniq_product_barcode_per_client",
            )
        ]
        indexes = [models.Index(fields=["client", "name"])]

    def __str__(self):
        return self.name

    @property
    def is_low(self) -> bool:
        return self.stock <= self.reorder_level


class StockMovement(models.Model):
    """Every change to a product's stock is recorded here."""

    OPENING, RECEIVE, COUNT, LOSS, SALE, VOID, IMPORT = (
        "opening", "receive", "count", "loss", "sale", "void", "import",
    )
    REASONS = [
        (OPENING, "Opening stock"),
        (RECEIVE, "Stock received"),
        (COUNT, "Stock count"),
        (LOSS, "Loss / damage"),
        (SALE, "Sale"),
        (VOID, "Voided sale"),
        (IMPORT, "CSV import"),
    ]

    client = models.ForeignKey("accounts.Client", on_delete=models.CASCADE, related_name="stock_movements")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="movements")
    change = models.DecimalField(max_digits=12, decimal_places=3)
    reason = models.CharField(max_length=10, choices=REASONS)
    reference = models.CharField(max_length=40, blank=True)
    note = models.CharField(max_length=200, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["client", "product", "-created_at"])]
