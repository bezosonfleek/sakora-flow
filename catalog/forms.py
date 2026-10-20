from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from .models import Category, Product


class ProductForm(forms.ModelForm):
    opening_stock = forms.DecimalField(
        required=False, min_value=Decimal("0"), max_digits=12, decimal_places=3, label="Opening stock",
        help_text="How many you have now. Only used when adding a product; later use the stock actions.",
    )

    class Meta:
        model = Product
        fields = ["name", "barcode", "category", "price", "cost", "vat_applies", "reorder_level", "is_active"]

    def __init__(self, *args, client, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = client
        self.fields["category"].queryset = Category.objects.filter(client=client)
        self.fields["category"].required = False
        self.fields["price"].min_value = Decimal("0")
        if self.instance.pk:
            del self.fields["opening_stock"]

    def clean_barcode(self):
        code = self.cleaned_data["barcode"].strip()
        if code:
            qs = Product.objects.filter(client=self.client, barcode=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError("Another product already uses this barcode.")
        return code

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price < 0:
            raise ValidationError("Price cannot be negative.")
        return price

    def clean_cost(self):
        cost = self.cleaned_data["cost"]
        if cost is not None and cost < 0:
            raise ValidationError("Cost cannot be negative.")
        return cost


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name"]


class StockActionForm(forms.Form):
    KINDS = [
        ("receive", "Receive stock (add)"),
        ("count", "Stock count (set to counted quantity)"),
        ("loss", "Loss or damage (remove)"),
    ]
    kind = forms.ChoiceField(choices=KINDS, label="Action")
    quantity = forms.DecimalField(min_value=Decimal("0"), max_digits=12, decimal_places=3)
    note = forms.CharField(required=False, max_length=200)


class ImportForm(forms.Form):
    file = forms.FileField(label="CSV file")
