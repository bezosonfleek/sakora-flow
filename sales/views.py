import json
from datetime import date

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import ALL_STAFF, CASHIER, MANAGERS, api_role_required, role_required
from catalog.models import Product

from .forms import CloseShiftForm, OpenShiftForm
from .models import Sale, Shift
from .reports import daily_report, shift_summary, stock_alerts
from .services import SaleError, close_shift, create_sale, current_shift, open_shift, void_sale


def _parse_day(value):
    try:
        return date.fromisoformat(value) if value else timezone.localdate()
    except ValueError:
        return timezone.localdate()


# ---- Till -------------------------------------------------------------------------------------


@role_required(*ALL_STAFF)
def till(request):
    shift = current_shift(request.user)
    if shift is None:
        messages.info(request, "Open your shift to start selling.")
        return redirect("shift_open")
    config = {
        "currency": request.client.currency,
        "productsUrl": reverse("api_products"),
        "saleUrl": reverse("api_sale_create"),
    }
    return render(request, "sales/till.html", {"config": config, "shift": shift})


@api_role_required(*ALL_STAFF)
def api_products(request):
    rows = [
        {"id": p.pk, "name": p.name, "barcode": p.barcode, "price": str(p.price), "stock": float(p.stock)}
        for p in Product.objects.filter(client=request.client, is_active=True).order_by("name")
    ]
    return JsonResponse({"products": rows})


@api_role_required(*ALL_STAFF)
@require_POST
def api_sale_create(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"error": "Invalid request."}, status=400)
    items = data.get("items") if isinstance(data, dict) else None
    payments = data.get("payments") if isinstance(data, dict) else None
    if (
        not isinstance(items, list)
        or not isinstance(payments, list)
        or not all(isinstance(r, dict) for r in items + payments)
    ):
        return JsonResponse({"error": "Invalid request."}, status=400)
    shift = current_shift(request.user)
    if shift is None:
        return JsonResponse({"error": "Your shift is closed. Open a new shift to keep selling."}, status=400)
    try:
        sale, created = create_sale(
            client=request.client,
            cashier=request.user,
            shift=shift,
            sale_uuid=data.get("uuid"),
            items=items,
            payments=payments,
        )
    except SaleError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "created": created,
            "sale_id": sale.pk,
            "receipt_no": sale.receipt_no,
            "total": str(sale.total),
            "change": str(sale.change_given),
            "receipt_url": reverse("sale_receipt", args=[sale.pk]),
        }
    )


# ---- Shifts -----------------------------------------------------------------------------------


@role_required(*ALL_STAFF)
def shift_open(request):
    if current_shift(request.user):
        return redirect("till")
    form = OpenShiftForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        open_shift(user=request.user, opening_float=form.cleaned_data["opening_float"])
        return redirect("till")
    return render(
        request,
        "form_page.html",
        {
            "title": "Open shift",
            "intro": "Count the cash in the drawer and enter it here before you start selling.",
            "form": form,
            "submit": "Open shift",
            "back": "/",
        },
    )


@role_required(*ALL_STAFF)
def shift_close(request):
    shift = current_shift(request.user)
    if shift is None:
        return redirect("home")
    form = CloseShiftForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            shift = close_shift(
                shift_id=shift.pk,
                user=request.user,
                counted_cash=form.cleaned_data["counted_cash"],
                note=form.cleaned_data["note"],
            )
        except SaleError as exc:
            messages.error(request, str(exc))
            return redirect("home")
        messages.success(request, "Shift closed.")
        return redirect("shift_detail", pk=shift.pk)
    return render(
        request,
        "form_page.html",
        {
            "title": "Close shift",
            "intro": "Count all the cash in the drawer and enter the total. The expected amount is shown after you close.",
            "form": form,
            "submit": "Close shift",
            "back": reverse("till"),
        },
    )


@role_required(*ALL_STAFF)
def shift_list(request):
    shifts = Shift.objects.filter(client=request.client).select_related("cashier")
    if request.user.role == CASHIER:
        shifts = shifts.filter(cashier=request.user)
    return render(request, "sales/shift_list.html", {"shifts": shifts[:100]})


@role_required(*ALL_STAFF)
def shift_detail(request, pk):
    shifts = Shift.objects.filter(client=request.client).select_related("cashier")
    if request.user.role == CASHIER:
        shifts = shifts.filter(cashier=request.user)
    shift = get_object_or_404(shifts, pk=pk)
    sales = shift.sales.select_related("cashier")[:200]
    return render(
        request,
        "sales/shift_detail.html",
        {"shift": shift, "summary": shift_summary(shift), "sales": sales},
    )


# ---- Sales and receipts -----------------------------------------------------------------------


def _visible_sales(request):
    sales = Sale.objects.filter(client=request.client)
    if request.user.role == CASHIER:
        sales = sales.filter(cashier=request.user)
    return sales


@role_required(*ALL_STAFF)
def sale_list(request):
    q = request.GET.get("q", "").strip()
    day = _parse_day(request.GET.get("date"))
    sales = _visible_sales(request).select_related("cashier")
    sales = sales.filter(receipt_no__icontains=q) if q else sales.filter(created_at__date=day)
    return render(request, "sales/sale_list.html", {"sales": sales[:300], "q": q, "day": day})


@role_required(*ALL_STAFF)
def sale_detail(request, pk):
    sale = get_object_or_404(_visible_sales(request).select_related("cashier", "voided_by"), pk=pk)
    return render(
        request,
        "sales/sale_detail.html",
        {"sale": sale, "items": sale.items.all(), "payments": sale.payments.all()},
    )


@role_required(*ALL_STAFF)
def sale_receipt(request, pk):
    sale = get_object_or_404(_visible_sales(request).select_related("cashier"), pk=pk)
    return render(
        request,
        "sales/receipt.html",
        {
            "sale": sale,
            "items": sale.items.all(),
            "payments": sale.payments.all(),
            "client": request.client,
            "width": request.client.receipt_width,
            "inner_width": request.client.receipt_width - 6,
            "autoprint": "autoprint" in request.GET,
        },
    )


@role_required(*MANAGERS)
@require_POST
def sale_void(request, pk):
    sale = get_object_or_404(Sale, pk=pk, client=request.client)
    try:
        void_sale(sale_id=sale.pk, client=request.client, user=request.user, reason=request.POST.get("reason", ""))
        messages.success(request, f"Sale {sale.receipt_no} voided and stock restored.")
    except SaleError as exc:
        messages.error(request, str(exc))
    return redirect("sale_detail", pk=sale.pk)


# ---- Manager views ----------------------------------------------------------------------------


@role_required(*MANAGERS)
def dashboard(request):
    today = timezone.localdate()
    report = daily_report(request.client, today)
    recent = Sale.objects.filter(client=request.client).select_related("cashier")[:8]
    return render(
        request,
        "sales/dashboard.html",
        {"report": report, "alerts": stock_alerts(request.client), "recent": recent, "today": today},
    )


@role_required(*MANAGERS)
def daily_report_view(request):
    day = _parse_day(request.GET.get("date"))
    return render(request, "sales/daily_report.html", {"report": daily_report(request.client, day), "day": day})
