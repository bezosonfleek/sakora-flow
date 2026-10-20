from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core.testutils import PASSWORD, make_client, make_product

from .forms import ProductForm
from .importer import ImportProblem, import_products
from .models import Product, StockMovement
from .services import adjust_stock


class ImportTests(TestCase):
    def setUp(self):
        self.shop, self.users = make_client("Shop A")
        self.user = self.users["owner"]

    def run_import(self, text):
        return import_products(client=self.shop, raw=text.encode("utf-8"), user=self.user)

    def test_creates_and_updates_products(self):
        existing = make_product(self.shop, "Bella Tissue 4 Pack", "130.00", "5", barcode="111")
        result = self.run_import(
            "name,barcode,category,price,cost,stock,vat\n"
            "Bella Tissue 4 Pack,111,Household,140,110,24,yes\n"
            "Bread,222,Bakery,65,55,10,no\n"
        )
        self.assertEqual(result, {"created": 1, "updated": 1})
        existing.refresh_from_db()
        self.assertEqual(existing.price, Decimal("140.00"))
        self.assertEqual(existing.stock, Decimal("24"))
        bread = Product.objects.get(client=self.shop, barcode="222")
        self.assertFalse(bread.vat_applies)
        self.assertEqual(bread.stock, Decimal("10"))
        self.assertEqual(bread.category.name, "Bakery")

    def test_one_bad_row_imports_nothing(self):
        with self.assertRaises(ImportProblem) as ctx:
            self.run_import("name,price\nGood,10\nBad,notanumber\n")
        self.assertTrue(any("Row 3" in e for e in ctx.exception.errors))
        self.assertEqual(Product.objects.filter(client=self.shop).count(), 0)

    def test_missing_columns_and_duplicate_barcodes_are_reported(self):
        with self.assertRaises(ImportProblem):
            self.run_import("name,barcode\nA,1\n")
        with self.assertRaises(ImportProblem) as ctx:
            self.run_import("name,barcode,price\nA,1,10\nB,1,20\n")
        self.assertTrue(any("twice" in e for e in ctx.exception.errors))

    def test_blank_stock_keeps_current_stock(self):
        product = make_product(self.shop, "Milk", "70.00", "12", barcode="333")
        self.run_import("name,barcode,price,stock\nMilk,333,75,\n")
        product.refresh_from_db()
        self.assertEqual(product.price, Decimal("75.00"))
        self.assertEqual(product.stock, Decimal("12"))

    def test_import_through_the_page(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.login(username="shop-a-owner", password=PASSWORD)
        upload = SimpleUploadedFile("p.csv", b"name,price\nTea,100\n", content_type="text/csv")
        response = self.client.post(reverse("product_import"), {"file": upload})
        self.assertRedirects(response, reverse("product_list"))
        self.assertTrue(Product.objects.filter(client=self.shop, name="Tea").exists())


class ProductTests(TestCase):
    def setUp(self):
        self.shop, self.users = make_client("Shop A")
        self.other, _ = make_client("Shop B")

    def form(self, client, **extra):
        data = {"name": "Item", "barcode": "999", "price": "10", "cost": "5", "reorder_level": "0", "vat_applies": "on", "is_active": "on"}
        data.update(extra)
        return ProductForm(data, client=client)

    def test_barcode_unique_within_a_client_but_not_across_clients(self):
        make_product(self.shop, "Existing", "10.00", "0", barcode="999")
        self.assertFalse(self.form(self.shop).is_valid())
        self.assertTrue(self.form(self.other).is_valid())

    def test_stock_actions_write_the_ledger(self):
        product = make_product(self.shop, "Milk", "70.00", "10")
        owner = self.users["owner"]
        adjust_stock(product_id=product.pk, client=self.shop, kind="receive", quantity=Decimal("5"), user=owner)
        adjust_stock(product_id=product.pk, client=self.shop, kind="loss", quantity=Decimal("2"), user=owner, note="Spilled")
        adjust_stock(product_id=product.pk, client=self.shop, kind="count", quantity=Decimal("20"), user=owner)
        product.refresh_from_db()
        self.assertEqual(product.stock, Decimal("20"))
        reasons = list(product.movements.order_by("id").values_list("reason", flat=True))
        self.assertEqual(reasons, ["opening", "receive", "loss", "count"])
        self.assertEqual(sum(m.change for m in product.movements.all()), Decimal("20"))

    def test_low_stock_flag(self):
        product = make_product(self.shop, "Eggs", "480.00", "2", reorder_level=Decimal("3"))
        self.assertTrue(product.is_low)

    def test_product_pages_for_a_manager(self):
        product = make_product(self.shop, "Milk", "70.00", "10")
        self.client.login(username="shop-a-admin", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("product_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("product_detail", args=[product.pk])).status_code, 200)
        response = self.client.post(
            reverse("product_detail", args=[product.pk]), {"kind": "receive", "quantity": "5", "note": "Delivery"}
        )
        self.assertRedirects(response, reverse("product_detail", args=[product.pk]))
        product.refresh_from_db()
        self.assertEqual(product.stock, Decimal("15"))
        self.assertEqual(StockMovement.objects.filter(product=product, reason="receive").count(), 1)

    def test_manager_creates_product_with_opening_stock(self):
        self.client.login(username="shop-a-owner", password=PASSWORD)
        response = self.client.post(
            reverse("product_new"),
            {"name": "Sugar", "barcode": "555", "price": "195", "cost": "170", "reorder_level": "5", "opening_stock": "30", "vat_applies": "on", "is_active": "on"},
        )
        product = Product.objects.get(client=self.shop, name="Sugar")
        self.assertRedirects(response, reverse("product_detail", args=[product.pk]))
        self.assertEqual(product.stock, Decimal("30"))
