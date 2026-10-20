"""Helpers shared by the test suites."""
from decimal import Decimal

from accounts.models import Client, User
from catalog.models import Product, StockMovement
from catalog.services import change_stock

PASSWORD = "Str0ng-test-pass!"


def make_client(name="Shop A"):
    """Create a client with an owner, admin and cashier (cashier PIN is 1234)."""
    slug = name.lower().replace(" ", "-")
    client = Client.objects.create(name=name, slug=slug)
    users = {}
    for role in ("owner", "admin", "cashier"):
        user = User(username=f"{slug}-{role}", client=client, role=role)
        user.set_password(PASSWORD)
        if role == "cashier":
            user.set_pin("1234")
        user.save()
        users[role] = user
    return client, users


def make_product(client, name="Bread", price="100.00", stock="10", vat=True, barcode="", **extra):
    product = Product.objects.create(
        client=client, name=name, price=Decimal(price), vat_applies=vat, barcode=barcode, stock=0, **extra
    )
    if Decimal(stock):
        change_stock(product=product, delta=Decimal(stock), reason=StockMovement.OPENING)
    product.refresh_from_db()
    return product
