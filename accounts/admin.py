from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Client, User


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "vat_rate", "receipt_width", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("receipt_seq",)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "first_name", "last_name", "client", "role", "is_active", "is_superuser")
    list_filter = ("client", "role", "is_active", "is_superuser")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("SakoraFlow", {"fields": ("client", "role", "pin_failures", "pin_locked_until")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("SakoraFlow", {"fields": ("client", "role")}),
    )
