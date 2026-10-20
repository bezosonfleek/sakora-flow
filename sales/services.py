"""Selling logic. The server is the authority on prices, VAT, totals and stock;
the till only says which products, how many, and how the customer paid."""
import re
import uuid as uuid_lib
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from catalog.models import Product, StockMovement
from catalog.services import change_stock

from .models import Payment, Sale, SaleItem, Shift

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
MPESA_RE = re.compile(r"^[A-Z0-9]{10}$")


class SaleError(Exception):
    """A problem the cashier or manager can understand and fix."""


def money(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def dsum(field):
    """Sum that gives 0.00 instead of None."""
    return Coalesce(Sum(field), Value(ZERO), output_field=DecimalField(max_digits=14, decimal_places=2))


def _decimal(value, label):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise SaleError(f"{label} is not a valid number.")
    if not number.is_finite():
        raise SaleError(f"{label} is not a valid number.")
    return number


def _quantity(value) -> Decimal:
    qty = _decimal(value, "Quantity")
    if qty <= 0 or qty > 10000:
        raise SaleError("Quantity must be more than 0.")
    if qty.as_tuple().exponent < -3:
        raise SaleError("Quantity can have at most 3 decimal places.")
    return qty


def _check_payments(payments, total, client):
    """Returns (rows to save, cash tendered, change). Cash covers whatever other methods do not."""
    if not payments:
        raise SaleError("Add a payment before completing the sale.")
    cash_tendered = ZERO
    other = []
    seen_codes = set()
    for row in payments:
        method = row.get("method")
        if method not in Payment.METHODS:
            raise SaleError("Unknown payment method.")
        amount = money(_decimal(row.get("amount"), "Payment amount"))
        if amount < 0:
            raise SaleError("Payment amounts cannot be negative.")
        if amount == 0:
            continue
        reference = str(row.get("reference") or "").strip().upper()[:40]
        if method == Payment.CASH:
            cash_tendered += amount
            continue
        if method == Payment.MPESA:
            if not MPESA_RE.match(reference):
                raise SaleError("Enter the 10-character M-Pesa code (letters and numbers).")
            if reference in seen_codes or Payment.objects.filter(
                client=client, method=Payment.MPESA, reference=reference
            ).exists():
                raise SaleError(f"M-Pesa code {reference} has already been used.")
            seen_codes.add(reference)
        other.append({"method": method, "amount": amount, "reference": reference})

    other_total = sum((r["amount"] for r in other), ZERO)
    if other_total > total:
        raise SaleError("The M-Pesa, card and bank amounts are more than the total.")
    cash_due = total - other_total
    if cash_tendered < cash_due:
        raise SaleError(f"Payment is short by {money(cash_due - cash_tendered)}.")
    if cash_due == 0 and cash_tendered > 0:
        raise SaleError("The sale is already fully paid without cash. Remove the cash amount.")
    change = cash_tendered - cash_due
    rows = list(other)
    if cash_due > 0:
        rows.insert(0, {"method": Payment.CASH, "amount": cash_due, "reference": ""})
    return rows, cash_tendered, change


def _build_sale(*, client, cashier, shift, sale_uuid, items, payments):
    if not items:
        raise SaleError("The cart is empty.")
    wanted = {}
    for row in items:
        try:
            product_id = int(row.get("product_id"))
        except (TypeError, ValueError, AttributeError):
            raise SaleError("A product in the cart is not valid.")
        wanted[product_id] = wanted.get(product_id, Decimal("0")) + _quantity(row.get("quantity"))

    products = {
        p.pk: p
        for p in Product.objects.select_for_update()
        .filter(client=client, is_active=True, pk__in=wanted.keys())
        .order_by("pk")
    }
    if len(products) != len(wanted):
        raise SaleError("A product in the cart is no longer available. Refresh the till and try again.")

    rate = client.vat_rate
    lines, total, vat_total = [], ZERO, ZERO
    for product_id in sorted(wanted):
        product, qty = products[product_id], wanted[product_id]
        line_total = money(product.price * qty)
        vat = money(line_total * rate / (Decimal(100) + rate)) if product.vat_applies else ZERO
        total += line_total
        vat_total += vat
        lines.append((product, qty, line_total, vat))
    if total <= 0:
        raise SaleError("The sale total must be more than zero.")

    pay_rows, cash_tendered, change = _check_payments(payments, total, client)

    sale = Sale.objects.create(
        client=client,
        uuid=sale_uuid,
        receipt_no=client.allocate_receipt_no(),
        cashier=cashier,
        shift=shift,
        total=total,
        vat_total=vat_total,
        cash_tendered=cash_tendered,
        change_given=change,
    )
    SaleItem.objects.bulk_create(
        [
            SaleItem(
                sale=sale,
                product=product,
                name=product.name,
                barcode=product.barcode,
                unit_price=product.price,
                quantity=qty,
                vat_applies=product.vat_applies,
                vat_rate=rate if product.vat_applies else ZERO,
                line_total=line_total,
                vat_amount=vat,
            )
            for product, qty, line_total, vat in lines
        ]
    )
    Payment.objects.bulk_create(
        [
            Payment(
                client=client,
                sale=sale,
                method=row["method"],
                amount=row["amount"],
                reference=row["reference"],
                is_verified=row["method"] != Payment.MPESA,
            )
            for row in pay_rows
        ]
    )
    for product, qty, _line_total, _vat in lines:
        change_stock(product=product, delta=-qty, reason=StockMovement.SALE, user=cashier, reference=sale.receipt_no)
    return sale


def create_sale(*, client, cashier, shift, sale_uuid, items, payments):
    """Record a sale. Returns (sale, created). Sending the same uuid again returns the original sale."""
    try:
        sale_uuid = uuid_lib.UUID(str(sale_uuid))
    except ValueError:
        raise SaleError("Invalid sale reference. Reload the till and try again.")
    existing = Sale.objects.filter(client=client, uuid=sale_uuid).first()
    if existing:
        return existing, False
    try:
        with transaction.atomic():
            sale = _build_sale(
                client=client, cashier=cashier, shift=shift, sale_uuid=sale_uuid, items=items, payments=payments
            )
    except IntegrityError:
        existing = Sale.objects.filter(client=client, uuid=sale_uuid).first()
        if existing:
            return existing, False
        raise SaleError("The sale clashed with another one (for example a reused M-Pesa code). Check and try again.")
    return sale, True


def void_sale(*, sale_id, client, user, reason):
    reason = (reason or "").strip()
    if not reason:
        raise SaleError("Give a reason for voiding this sale.")
    with transaction.atomic():
        sale = Sale.objects.select_for_update().get(pk=sale_id, client=client)
        if sale.status == Sale.VOIDED:
            raise SaleError("This sale is already voided.")
        for item in sale.items.select_related("product"):
            change_stock(
                product=item.product,
                delta=item.quantity,
                reason=StockMovement.VOID,
                user=user,
                reference=sale.receipt_no,
                note=reason,
            )
        sale.status = Sale.VOIDED
        sale.voided_at = timezone.now()
        sale.voided_by = user
        sale.void_reason = reason[:200]
        sale.save(update_fields=["status", "voided_at", "voided_by", "void_reason"])
    return sale


def current_shift(user):
    return Shift.objects.filter(cashier=user, closed_at__isnull=True).first()


def open_shift(*, user, opening_float):
    try:
        with transaction.atomic():
            return Shift.objects.create(client=user.client, cashier=user, opening_float=opening_float)
    except IntegrityError:
        return current_shift(user)


def shift_cash_sales(shift):
    return Payment.objects.filter(
        sale__shift=shift, sale__status=Sale.COMPLETED, method=Payment.CASH
    ).aggregate(total=dsum("amount"))["total"]


def close_shift(*, shift_id, user, counted_cash, note=""):
    with transaction.atomic():
        shift = Shift.objects.select_for_update().get(pk=shift_id, cashier=user)
        if shift.closed_at:
            raise SaleError("This shift is already closed.")
        shift.expected_cash = shift.opening_float + shift_cash_sales(shift)
        shift.counted_cash = counted_cash
        shift.closed_at = timezone.now()
        shift.note = note[:200]
        shift.save(update_fields=["expected_cash", "counted_cash", "closed_at", "note"])
    return shift
