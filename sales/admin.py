from django.contrib import admin

from .models import Payment, Sale, SaleItem, Shift


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in SaleItem._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in Payment._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("receipt_no", "client", "cashier", "total", "status", "created_at")
    list_filter = ("client", "status")
    search_fields = ("receipt_no",)
    inlines = [SaleItemInline, PaymentInline]
    readonly_fields = [f.name for f in Sale._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("id", "client", "cashier", "opened_at", "closed_at", "expected_cash", "counted_cash")
    list_filter = ("client",)
