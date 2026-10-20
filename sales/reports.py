from django.db.models import Count, F

from catalog.models import Product

from .models import Payment, Sale, SaleItem, Shift
from .services import ZERO, dsum, shift_cash_sales

METHOD_LABELS = dict(Payment.METHOD_CHOICES)


def daily_report(client, day):
    sales = Sale.objects.filter(client=client, created_at__date=day)
    done = sales.filter(status=Sale.COMPLETED)

    totals = done.aggregate(count=Count("id"), total=dsum("total"), vat=dsum("vat_total"))
    by_method = [
        {"label": METHOD_LABELS.get(r["method"], r["method"]), "total": r["total"], "count": r["count"]}
        for r in Payment.objects.filter(
            client=client, sale__created_at__date=day, sale__status=Sale.COMPLETED
        )
        .values("method")
        .annotate(total=dsum("amount"), count=Count("id"))
        .order_by("method")
    ]
    by_cashier = list(
        done.values("cashier__username", "cashier__first_name")
        .annotate(count=Count("id"), total=dsum("total"))
        .order_by("-total")
    )
    top_items = list(
        SaleItem.objects.filter(sale__client=client, sale__created_at__date=day, sale__status=Sale.COMPLETED)
        .values("product_id", "name")
        .annotate(qty=dsum("quantity"), revenue=dsum("line_total"))
        .order_by("-revenue")[:10]
    )
    voided = sales.filter(status=Sale.VOIDED).aggregate(count=Count("id"), total=dsum("total"))
    unverified = Payment.objects.filter(
        client=client,
        method=Payment.MPESA,
        is_verified=False,
        sale__created_at__date=day,
        sale__status=Sale.COMPLETED,
    ).aggregate(count=Count("id"), total=dsum("amount"))
    shifts = list(Shift.objects.filter(client=client, opened_at__date=day).select_related("cashier"))
    return {
        "day": day,
        "totals": totals,
        "average": (totals["total"] / totals["count"]) if totals["count"] else ZERO,
        "by_method": by_method,
        "by_cashier": by_cashier,
        "top_items": top_items,
        "voided": voided,
        "unverified_mpesa": unverified,
        "shifts": shifts,
    }


def stock_alerts(client):
    """Products that are out of stock, negative, or at/below their reorder level."""
    qs = Product.objects.filter(client=client, is_active=True, stock__lte=F("reorder_level")).order_by("stock", "name")
    return {"count": qs.count(), "items": list(qs[:8]), "negative": qs.filter(stock__lt=0).count()}


def shift_summary(shift):
    payments = (
        Payment.objects.filter(sale__shift=shift, sale__status=Sale.COMPLETED)
        .values("method")
        .annotate(total=dsum("amount"), count=Count("id"))
        .order_by("method")
    )
    done = Sale.objects.filter(shift=shift, status=Sale.COMPLETED)
    cash_sales = shift_cash_sales(shift)
    return {
        "by_method": [
            {"label": METHOD_LABELS.get(r["method"], r["method"]), "total": r["total"], "count": r["count"]}
            for r in payments
        ],
        "sales": done.aggregate(count=Count("id"), total=dsum("total")),
        "voided": Sale.objects.filter(shift=shift, status=Sale.VOIDED).count(),
        "cash_sales": cash_sales,
        "expected_now": shift.opening_float + cash_sales,
    }
