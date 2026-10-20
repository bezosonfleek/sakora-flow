from decimal import Decimal

from django import forms


class OpenShiftForm(forms.Form):
    opening_float = forms.DecimalField(
        min_value=Decimal("0"), max_digits=12, decimal_places=2, initial=0, label="Cash in the drawer now (KES)"
    )


class CloseShiftForm(forms.Form):
    counted_cash = forms.DecimalField(
        min_value=Decimal("0"), max_digits=12, decimal_places=2, label="Cash counted in the drawer (KES)"
    )
    note = forms.CharField(required=False, max_length=200, label="Note (optional)")
