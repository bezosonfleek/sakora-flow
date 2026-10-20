from django.contrib import admin

from .models import Category, Product, StockMovement


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "client")
    list_filter = ("client",)
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "barcode", "price", "stock", "is_active")
    list_filter = ("client", "is_active", "category")
    search_fields = ("name", "barcode")
    readonly_fields = ("stock",)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "client", "product", "change", "reason", "reference", "user")
    list_filter = ("client", "reason")
    search_fields = ("product__name", "reference")
    readonly_fields = [f.name for f in StockMovement._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
