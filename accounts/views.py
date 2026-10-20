from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import MANAGERS, OWNER, role_required
from .forms import ClientSettingsForm, StaffForm
from .models import User


def pin_login(request):
    if request.user.is_authenticated:
        return redirect("home")
    error = ""
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username", "").strip(),
            pin=request.POST.get("pin", "").strip(),
        )
        if user is not None:
            login(request, user)
            return redirect("home")
        error = "That username and PIN did not match, or the PIN is locked for a few minutes."
    return render(request, "registration/pin_login.html", {"error": error})


def _manageable_staff(acting_user):
    """Staff the acting user may edit: owners manage admins and cashiers, admins manage cashiers."""
    qs = User.objects.filter(client=acting_user.client)
    if acting_user.role == OWNER:
        return qs.filter(role__in=[User.Role.ADMIN, User.Role.CASHIER])
    return qs.filter(role=User.Role.CASHIER)


@role_required(*MANAGERS)
def staff_list(request):
    people = User.objects.filter(client=request.client).order_by("role", "username")
    manageable_ids = set(_manageable_staff(request.user).values_list("pk", flat=True))
    return render(request, "accounts/staff_list.html", {"people": people, "manageable_ids": manageable_ids})


@role_required(*MANAGERS)
def staff_edit(request, pk=None):
    instance = get_object_or_404(_manageable_staff(request.user), pk=pk) if pk else None
    form = StaffForm(request.POST or None, instance=instance, acting_user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Staff member saved.")
        return redirect("staff_list")
    return render(
        request,
        "form_page.html",
        {"title": "Edit staff" if instance else "Add staff", "form": form, "back": "/staff/"},
    )


@role_required(OWNER)
def client_settings(request):
    form = ClientSettingsForm(request.POST or None, instance=request.client)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Settings saved.")
        return redirect("home")
    return render(
        request,
        "form_page.html",
        {"title": "Business settings", "form": form, "back": "/"},
    )
