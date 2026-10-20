from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Client, User, validate_pin


class StaffForm(forms.ModelForm):
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Required for new staff. Leave blank when editing to keep the current password.",
    )
    pin = forms.CharField(
        required=False,
        max_length=6,
        help_text="Cashiers only: 4-6 digits for quick login. Leave blank to keep the current PIN.",
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "role", "is_active"]

    def __init__(self, *args, acting_user, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user
        # Set before validation: User.clean() requires staff to belong to a client.
        self.instance.client = acting_user.client
        if acting_user.role == User.Role.OWNER:
            choices = [(User.Role.ADMIN, "Admin"), (User.Role.CASHIER, "Cashier")]
        else:
            choices = [(User.Role.CASHIER, "Cashier")]
        self.fields["role"].choices = choices
        self.fields["role"].required = True

    def clean(self):
        data = super().clean()
        password = data.get("password")
        pin = data.get("pin", "")
        if not self.instance.pk and not password:
            self.add_error("password", "A password is required for new staff.")
        if password:
            try:
                validate_password(password, self.instance)
            except ValidationError as exc:
                self.add_error("password", exc)
        if pin:
            if data.get("role") != User.Role.CASHIER:
                self.add_error("pin", "PIN login is for cashiers only.")
            else:
                try:
                    validate_pin(pin)
                except ValidationError as exc:
                    self.add_error("pin", exc)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.client = self.acting_user.client
        password = self.cleaned_data.get("password")
        pin = self.cleaned_data.get("pin")
        if password:
            user.set_password(password)
        if pin:
            user.set_pin(pin)
        if commit:
            user.save()
        return user


class ClientSettingsForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["name", "phone", "address", "vat_rate", "receipt_width", "receipt_header", "receipt_footer"]
        help_texts = {
            "vat_rate": "Percent. Shelf prices are treated as VAT-inclusive.",
            "receipt_header": "Optional extra line under the business name on receipts.",
        }

    def clean_vat_rate(self):
        rate = self.cleaned_data["vat_rate"]
        if rate < 0 or rate > 50:
            raise ValidationError("Enter a VAT rate between 0 and 50.")
        return rate
