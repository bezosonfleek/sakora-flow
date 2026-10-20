"""Create a demo supermarket with staff and products. For development and demos only."""
import secrets
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Client, User
from catalog.models import Category, Product, StockMovement
from catalog.services import change_stock

SLUG = "kijani-mini-mart"

# name, category, price (KES, VAT-inclusive), cost, VAT applies, stock, reorder level
# Prices are realistic ballparks for a small Kenyan supermarket, not a price list.
# VAT flags are for demonstration only: confirm the correct treatment of each product before real use.
PRODUCTS = [
    # Beverages
    ("Coca-Cola 300ml", "Beverages", 40, 31, True, 48, 12),
    ("Coca-Cola 500ml", "Beverages", 60, 48, True, 60, 12),
    ("Coca-Cola 1.25L", "Beverages", 130, 105, True, 24, 6),
    ("Coca-Cola 2L", "Beverages", 200, 165, True, 18, 6),
    ("Fanta Orange 300ml", "Beverages", 40, 31, True, 36, 12),
    ("Fanta Orange 500ml", "Beverages", 60, 48, True, 48, 12),
    ("Fanta Passion 500ml", "Beverages", 60, 48, True, 30, 12),
    ("Sprite 500ml", "Beverages", 60, 48, True, 36, 12),
    ("Sprite 2L", "Beverages", 200, 165, True, 0, 6),
    ("Stoney Tangawizi 500ml", "Beverages", 60, 48, True, 24, 12),
    ("Minute Maid Mango 400ml", "Beverages", 80, 64, True, 30, 10),
    ("Minute Maid Pulpy Orange 400ml", "Beverages", 80, 64, True, 28, 10),
    ("Minute Maid Mango 1L", "Beverages", 200, 165, True, 12, 4),
    ("Del Monte Mixed Fruit Juice 1L", "Beverages", 250, 210, True, 10, 4),
    ("Keringet Water 500ml", "Beverages", 50, 38, True, 60, 18),
    ("Keringet Water 1.5L", "Beverages", 100, 78, True, 36, 12),
    ("Dasani Water 500ml", "Beverages", 40, 30, True, 48, 18),
    ("Red Bull 250ml", "Beverages", 280, 240, True, 2, 4),
    # Bakery
    ("Supaloaf White Bread 400g", "Bakery", 65, 56, False, 18, 8),
    ("Supaloaf Brown Bread 400g", "Bakery", 70, 60, False, 12, 6),
    ("Supaloaf White Bread 800g", "Bakery", 130, 112, False, 8, 4),
    ("Chocolate Cake Slice", "Bakery", 60, 48, True, 15, 5),
    # Dairy & eggs
    ("Brookside Fresh Milk 500ml", "Dairy & Eggs", 70, 63, False, 36, 12),
    ("Brookside Fresh Milk 1L", "Dairy & Eggs", 130, 117, False, 24, 8),
    ("Tuzo Long Life Milk 500ml", "Dairy & Eggs", 75, 66, False, 24, 8),
    ("Brookside Yoghurt Strawberry 250ml", "Dairy & Eggs", 65, 52, True, 20, 6),
    ("Mala 500ml", "Dairy & Eggs", 75, 62, True, 16, 6),
    ("Blue Band Margarine 250g", "Dairy & Eggs", 170, 145, True, 20, 6),
    ("Blue Band Margarine 500g", "Dairy & Eggs", 320, 280, True, 10, 4),
    ("Eggs Tray (30)", "Dairy & Eggs", 480, 430, False, 1, 3),
    ("Egg (single)", "Dairy & Eggs", 18, 15, False, 90, 30),
    # Staples
    ("Jogoo Maize Flour 2kg", "Staples", 195, 175, False, 40, 12),
    ("Pembe Maize Flour 1kg", "Staples", 105, 94, False, 30, 10),
    ("Exe Wheat Flour 2kg", "Staples", 215, 190, True, 20, 8),
    ("Pishori Rice 1kg", "Staples", 220, 190, True, 25, 8),
    ("Mumias Sugar 1kg", "Staples", 195, 175, True, 30, 10),
    ("Kabras Sugar 2kg", "Staples", 380, 345, True, 15, 6),
    ("Kensalt Table Salt 500g", "Staples", 35, 27, True, 40, 10),
    ("Elianto Cooking Oil 1L", "Staples", 340, 300, True, 18, 6),
    ("Fresh Fri Cooking Oil 500ml", "Staples", 190, 165, True, 14, 6),
    ("Santa Lucia Spaghetti 400g", "Staples", 110, 90, True, 24, 8),
    ("Ketepa Pride Tea 100g", "Staples", 100, 82, True, 25, 8),
    ("Nescafe Classic 50g", "Staples", 300, 255, True, 8, 4),
    ("Royco Mchuzi Mix 75g", "Staples", 40, 32, True, 40, 12),
    ("Kellogg's Corn Flakes 250g", "Staples", 330, 280, True, 8, 3),
    # Biscuits & snacks
    ("Oreo Biscuits Single Pack", "Biscuits & Snacks", 40, 32, True, 40, 12),
    ("McVitie's Digestive 400g", "Biscuits & Snacks", 330, 280, True, 10, 4),
    ("Glucose Biscuits 100g", "Biscuits & Snacks", 40, 31, True, 36, 12),
    ("Cream Sandwich Biscuits 200g", "Biscuits & Snacks", 100, 80, True, 24, 8),
    ("Marie Biscuits 250g", "Biscuits & Snacks", 120, 96, True, 18, 6),
    ("Krackjack Biscuits 200g", "Biscuits & Snacks", 100, 80, True, 20, 6),
    ("Pringles Original 110g", "Biscuits & Snacks", 400, 340, True, 6, 3),
    ("Salted Peanuts 100g", "Biscuits & Snacks", 60, 45, True, 24, 8),
    ("Crisps Salted 50g", "Biscuits & Snacks", 50, 38, True, 30, 10),
    ("Cadbury Dairy Milk 80g", "Biscuits & Snacks", 160, 130, True, 3, 5),
    ("Lollipop", "Biscuits & Snacks", 10, 7, True, 100, 30),
    # Household
    ("Bella Tissue 4 Pack", "Household", 140, 110, True, 30, 8),
    ("Bella Tissue 2 Pack", "Household", 75, 58, True, 36, 10),
    ("Toilet Paper Single Roll", "Household", 40, 30, True, 60, 20),
    ("Omo Washing Powder 500g", "Household", 150, 125, True, 20, 6),
    ("Omo Washing Powder 1kg", "Household", 280, 240, True, 12, 4),
    ("Menengai Bar Soap 800g", "Household", 190, 160, True, 16, 6),
    ("Geisha Soap 175g", "Household", 100, 80, True, 24, 8),
    ("Jik Bleach 500ml", "Household", 120, 98, True, 14, 5),
    ("Dishwashing Liquid 500ml", "Household", 140, 110, True, 12, 4),
    ("AA Batteries 2 Pack", "Household", 100, 70, True, 20, 6),
    # Personal care
    ("Colgate Toothpaste 100ml", "Personal Care", 170, 140, True, 18, 6),
    ("Toothbrush", "Personal Care", 80, 60, True, 24, 8),
    ("Always Sanitary Pads 8s", "Personal Care", 140, 115, True, 20, 6),
    ("Vaseline Petroleum Jelly 100ml", "Personal Care", 160, 135, True, 12, 4),
]


def ean13(body12: str) -> str:
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body12))
    return body12 + str((10 - total % 10) % 10)


class Command(BaseCommand):
    help = "Create the demo client 'Kijani Mini Mart' with staff and sample products (development only)."

    @transaction.atomic
    def handle(self, *args, **options):
        if Client.objects.filter(slug=SLUG).exists():
            self.stdout.write("Demo client already exists. Nothing to do.")
            return

        client = Client.objects.create(
            name="Kijani Mini Mart",
            slug=SLUG,
            phone="0700 000 000",
            address="Demo Street, Nairobi",
        )

        creds = []
        for username, role, first in [
            ("kijani_owner", User.Role.OWNER, "Owner"),
            ("kijani_admin", User.Role.ADMIN, "Admin"),
            ("kijani_cashier", User.Role.CASHIER, "Cashier"),
        ]:
            password = secrets.token_urlsafe(12)
            user = User(username=username, first_name=first, client=client, role=role)
            user.set_password(password)
            pin = ""
            if role == User.Role.CASHIER:
                pin = f"{secrets.randbelow(10000):04d}"
                user.set_pin(pin)
            user.save()
            creds.append((username, role, password, pin))

        categories = {}
        for index, (name, category, price, cost, vat, stock, reorder) in enumerate(PRODUCTS, start=1):
            if category not in categories:
                categories[category] = Category.objects.create(client=client, name=category)
            product = Product.objects.create(
                client=client,
                name=name,
                barcode=ean13(f"2{index:011d}"),
                category=categories[category],
                price=Decimal(price),
                cost=Decimal(cost),
                vat_applies=vat,
                stock=0,
                reorder_level=Decimal(reorder),
            )
            if stock:
                change_stock(product=product, delta=Decimal(stock), reason=StockMovement.OPENING, note="Demo data")

        self.stdout.write(self.style.SUCCESS(f"Created demo client with {len(PRODUCTS)} products."))
        self.stdout.write("Sign-in details (shown once, save them now):")
        for username, role, password, pin in creds:
            extra = f"   PIN: {pin}" if pin else ""
            self.stdout.write(f"  {role:8} username: {username:16} password: {password}{extra}")
        self.stdout.write("Demo barcodes are internal-use EAN-13 codes starting with 2.")
