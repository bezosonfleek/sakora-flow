import json
import uuid
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from catalog.models import Product
from core.testutils import PASSWORD, make_client, make_product

from .models import Sale
from .services import SaleError, close_shift, create_sale, open_shift, void_sale


class SaleServiceTests(TestCase):
    def setUp(self):
        self.shop, self.users = make_client("Shop A")
        self.cashier = self.users["cashier"]
        self.shift = open_shift(user=self.cashier, opening_float=Decimal("500"))
        self.bread = make_product(self.shop, "Bread", "65.00", "10", vat=False)
        self.soda = make_product(self.shop, "Soda", "116.00", "10", vat=True)

    def sell(self, items, payments, sale_uuid=None):
        return create_sale(
            client=self.shop,
            cashier=self.cashier,
            shift=self.shift,
            sale_uuid=sale_uuid or uuid.uuid4(),
            items=items,
            payments=payments,
        )

    def lines(self, soda=0, bread=0):
        rows = []
        if soda:
            rows.append({"product_id": self.soda.pk, "quantity": str(soda)})
        if bread:
            rows.append({"product_id": self.bread.pk, "quantity": str(bread)})
        return rows

    def stock(self, product):
        product.refresh_from_db()
        return product.stock

    def test_cash_sale_totals_vat_stock_and_change(self):
        sale, created = self.sell(self.lines(soda=2, bread=1), [{"method": "cash", "amount": "300"}])
        self.assertTrue(created)
        self.assertEqual(sale.total, Decimal("297.00"))
        self.assertEqual(sale.vat_total, Decimal("32.00"))  # 232 * 16 / 116; bread is not vatable
        self.assertEqual(sale.change_given, Decimal("3.00"))
        self.assertEqual(self.stock(self.soda), Decimal("8"))
        self.assertEqual(self.stock(self.bread), Decimal("9"))
        self.assertEqual(sale.payments.get().amount, Decimal("297.00"))

    def test_split_payment(self):
        sale, _ = self.sell(
            self.lines(soda=2, bread=1),
            [
                {"method": "mpesa", "amount": "100", "reference": "sjk7abc123"},
                {"method": "card", "amount": "50", "reference": "AUTH1"},
                {"method": "cash", "amount": "200"},
            ],
        )
        by_method = {p.method: p for p in sale.payments.all()}
        self.assertEqual(by_method["cash"].amount, Decimal("147.00"))
        self.assertEqual(sale.change_given, Decimal("53.00"))
        self.assertEqual(by_method["mpesa"].reference, "SJK7ABC123")
        self.assertFalse(by_method["mpesa"].is_verified)
        self.assertTrue(by_method["card"].is_verified)

    def test_short_payment_is_rejected_and_nothing_changes(self):
        with self.assertRaises(SaleError):
            self.sell(self.lines(soda=2, bread=1), [{"method": "cash", "amount": "100"}])
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(self.stock(self.soda), Decimal("10"))

    def test_mpesa_code_must_be_valid_and_unused(self):
        with self.assertRaises(SaleError):
            self.sell(self.lines(bread=1), [{"method": "mpesa", "amount": "65", "reference": "SHORT"}])
        self.sell(self.lines(bread=1), [{"method": "mpesa", "amount": "65", "reference": "SJK7ABC123"}])
        with self.assertRaises(SaleError):
            self.sell(self.lines(bread=1), [{"method": "mpesa", "amount": "65", "reference": "SJK7ABC123"}])
        self.assertEqual(self.stock(self.bread), Decimal("9"))

    def test_same_uuid_never_records_twice(self):
        key = uuid.uuid4()
        first, created_first = self.sell(self.lines(bread=1), [{"method": "cash", "amount": "65"}], key)
        second, created_second = self.sell(self.lines(bread=1), [{"method": "cash", "amount": "65"}], key)
        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(self.stock(self.bread), Decimal("9"))

    def test_selling_past_zero_is_allowed_and_goes_negative(self):
        self.sell(self.lines(bread=15), [{"method": "cash", "amount": "975"}])
        self.assertEqual(self.stock(self.bread), Decimal("-5"))

    def test_other_clients_products_cannot_be_sold(self):
        other, _ = make_client("Shop B")
        foreign = make_product(other, "Foreign", "10.00", "5")
        with self.assertRaises(SaleError):
            self.sell([{"product_id": foreign.pk, "quantity": "1"}], [{"method": "cash", "amount": "10"}])

    def test_bad_quantities_are_rejected(self):
        for qty in ("0", "-1", "abc", "1.2345"):
            with self.assertRaises(SaleError):
                self.sell([{"product_id": self.bread.pk, "quantity": qty}], [{"method": "cash", "amount": "999"}])

    def test_receipt_numbers_are_sequential(self):
        a, _ = self.sell(self.lines(bread=1), [{"method": "cash", "amount": "65"}])
        b, _ = self.sell(self.lines(bread=1), [{"method": "cash", "amount": "65"}])
        self.assertEqual((a.receipt_no, b.receipt_no), ("R-000001", "R-000002"))

    def test_void_restores_stock_and_cannot_repeat(self):
        sale, _ = self.sell(self.lines(soda=2), [{"method": "cash", "amount": "232"}])
        self.assertEqual(self.stock(self.soda), Decimal("8"))
        void_sale(sale_id=sale.pk, client=self.shop, user=self.users["admin"], reason="Customer changed mind")
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.VOIDED)
        self.assertEqual(self.stock(self.soda), Decimal("10"))
        with self.assertRaises(SaleError):
            void_sale(sale_id=sale.pk, client=self.shop, user=self.users["admin"], reason="again")
        with self.assertRaises(SaleError):
            void_sale(sale_id=sale.pk, client=self.shop, user=self.users["admin"], reason="  ")

    def test_shift_close_expected_cash_ignores_voided_and_non_cash(self):
        self.sell(self.lines(bread=1), [{"method": "cash", "amount": "65"}])  # +65 cash
        self.sell(self.lines(bread=1), [{"method": "mpesa", "amount": "65", "reference": "AAAAAAAAAA"}])  # not cash
        voided, _ = self.sell(self.lines(bread=2), [{"method": "cash", "amount": "130"}])
        void_sale(sale_id=voided.pk, client=self.shop, user=self.users["admin"], reason="Error")
        shift = close_shift(shift_id=self.shift.pk, user=self.cashier, counted_cash=Decimal("560"))
        self.assertEqual(shift.expected_cash, Decimal("565.00"))  # 500 float + 65
        self.assertEqual(shift.variance, Decimal("-5.00"))
        with self.assertRaises(SaleError):
            close_shift(shift_id=self.shift.pk, user=self.cashier, counted_cash=Decimal("560"))


class SaleApiTests(TestCase):
    def setUp(self):
        self.shop, self.users = make_client("Shop A")
        self.bread = make_product(self.shop, "Bread", "65.00", "10", vat=False, barcode="6161100000011")
        self.other_shop, self.other_users = make_client("Shop B")
        make_product(self.other_shop, "Secret Item", "10.00", "5")

    def login(self, role="cashier", shop="Shop A"):
        username = f"{shop.lower().replace(' ', '-')}-{role}"
        self.assertTrue(self.client.login(username=username, password=PASSWORD))

    def post_sale(self, payload):
        return self.client.post(reverse("api_sale_create"), data=json.dumps(payload), content_type="application/json")

    def test_api_requires_sign_in(self):
        self.assertEqual(self.client.get(reverse("api_products")).status_code, 401)
        self.assertEqual(self.post_sale({}).status_code, 401)

    def test_products_api_only_shows_own_client(self):
        self.login()
        data = self.client.get(reverse("api_products")).json()
        self.assertEqual([p["name"] for p in data["products"]], ["Bread"])

    def test_till_redirects_to_open_shift_first(self):
        self.login()
        response = self.client.get(reverse("till"))
        self.assertRedirects(response, reverse("shift_open"))
        self.client.post(reverse("shift_open"), {"opening_float": "200"})
        self.assertEqual(self.client.get(reverse("till")).status_code, 200)

    def test_sale_flow_through_the_api(self):
        self.login()
        self.client.post(reverse("shift_open"), {"opening_float": "200"})
        payload = {
            "uuid": str(uuid.uuid4()),
            "items": [{"product_id": self.bread.pk, "quantity": "2"}],
            "payments": [{"method": "cash", "amount": "200"}],
        }
        response = self.post_sale(payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["total"], "130.00")
        self.assertEqual(body["change"], "70.00")
        receipt = self.client.get(body["receipt_url"])
        self.assertContains(receipt, body["receipt_no"])
        self.assertEqual(Product.objects.get(pk=self.bread.pk).stock, Decimal("8"))

    def test_api_refuses_sale_without_open_shift_and_bad_input(self):
        self.login()
        payload = {"uuid": str(uuid.uuid4()), "items": [], "payments": []}
        self.assertEqual(self.post_sale(payload).status_code, 400)
        self.assertEqual(self.post_sale("nonsense").status_code, 400)

    def test_cashier_cannot_use_manager_pages_or_void(self):
        self.login("cashier")
        self.assertEqual(self.client.get(reverse("product_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("staff_list")).status_code, 403)

    def test_manager_pages_work_and_void_via_view(self):
        self.login("cashier")
        self.client.post(reverse("shift_open"), {"opening_float": "0"})
        sale_payload = {
            "uuid": str(uuid.uuid4()),
            "items": [{"product_id": self.bread.pk, "quantity": "1"}],
            "payments": [{"method": "cash", "amount": "65"}],
        }
        sale_id = self.post_sale(sale_payload).json()["sale_id"]
        self.assertEqual(self.client.post(reverse("sale_void", args=[sale_id]), {"reason": "x"}).status_code, 403)
        self.client.logout()
        self.login("admin")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("daily_report")).status_code, 200)
        self.client.post(reverse("sale_void", args=[sale_id]), {"reason": "Wrong item"})
        self.assertEqual(Sale.objects.get(pk=sale_id).status, Sale.VOIDED)
        self.assertEqual(Product.objects.get(pk=self.bread.pk).stock, Decimal("10"))

    def test_sales_of_another_client_are_invisible(self):
        shop_b_cashier = self.other_users["cashier"]
        shift = open_shift(user=shop_b_cashier, opening_float=Decimal("0"))
        foreign_product = Product.objects.get(client=self.other_shop)
        sale, _ = create_sale(
            client=self.other_shop,
            cashier=shop_b_cashier,
            shift=shift,
            sale_uuid=uuid.uuid4(),
            items=[{"product_id": foreign_product.pk, "quantity": "1"}],
            payments=[{"method": "cash", "amount": "10"}],
        )
        self.login("owner")
        self.assertEqual(self.client.get(reverse("sale_detail", args=[sale.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("sale_receipt", args=[sale.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("product_detail", args=[foreign_product.pk])).status_code, 404)
