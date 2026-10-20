from decimal import Decimal

from django.db import transaction
from django.db.models import F

from .models import Product, StockMovement


def change_stock(*, product, delta, reason, user=None, reference="", note=""):
    """Add `delta` to a product's stock and record the movement. Call inside a transaction."""
    delta = Decimal(delta)
    Product.objects.filter(pk=product.pk).update(stock=F("stock") + delta)
    return StockMovement.objects.create(
        client_id=product.client_id,
        product_id=product.pk,
        change=delta,
        reason=reason,
        reference=reference,
        note=note[:200],
        user=user,
    )


def adjust_stock(*, product_id, client, kind, quantity, user, note=""):
    """Manager stock actions: receive (+), loss (-), or count (set to the counted quantity)."""
    quantity = Decimal(quantity)
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id, client=client)
        if kind == "receive":
            delta, reason = quantity, StockMovement.RECEIVE
        elif kind == "loss":
            delta, reason = -quantity, StockMovement.LOSS
        elif kind == "count":
            delta, reason = quantity - product.stock, StockMovement.COUNT
        else:
            raise ValueError("Unknown stock action")
        if delta == 0:
            return None
        return change_stock(product=product, delta=delta, reason=reason, user=user, note=note)
