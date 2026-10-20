from django.test import TestCase
from django.urls import reverse

from core.testutils import PASSWORD, make_client

from .models import User


class PinLoginTests(TestCase):
    def setUp(self):
        self.shop, self.users = make_client("Shop A")

    def test_cashier_can_sign_in_with_pin(self):
        response = self.client.post(reverse("pin_login"), {"username": "shop-a-cashier", "pin": "1234"})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.users["cashier"].pk)

    def test_wrong_pin_locks_after_five_tries(self):
        for _ in range(5):
            self.client.post(reverse("pin_login"), {"username": "shop-a-cashier", "pin": "0000"})
        self.assertNotIn("_auth_user_id", self.client.session)
        user = User.objects.get(pk=self.users["cashier"].pk)
        self.assertIsNotNone(user.pin_locked_until)
        # even the right PIN is refused while locked
        self.client.post(reverse("pin_login"), {"username": "shop-a-cashier", "pin": "1234"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_pin_login_is_for_cashiers_only(self):
        owner = self.users["owner"]
        owner.set_pin("4321")
        owner.save()
        self.client.post(reverse("pin_login"), {"username": owner.username, "pin": "4321"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_pin_must_be_four_to_six_digits(self):
        from django.core.exceptions import ValidationError

        user = self.users["cashier"]
        for bad in ("123", "1234567", "12a4", ""):
            with self.assertRaises(ValidationError):
                user.set_pin(bad)


class AccessTests(TestCase):
    def setUp(self):
        self.shop, self.users = make_client("Shop A")

    def test_suspended_client_cannot_use_the_system(self):
        self.assertTrue(self.client.login(username="shop-a-owner", password=PASSWORD))
        self.shop.is_active = False
        self.shop.save()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_superadmin_is_sent_to_the_admin_site(self):
        User.objects.create_superuser("boss", password=PASSWORD)
        self.client.login(username="boss", password=PASSWORD)
        self.assertRedirects(self.client.get("/"), "/admin/", fetch_redirect_response=False)

    def test_each_role_lands_on_the_right_page(self):
        expected = {"owner": "/dashboard/", "admin": "/dashboard/", "cashier": "/till/"}
        for role, url in expected.items():
            self.client.login(username=f"shop-a-{role}", password=PASSWORD)
            self.assertRedirects(self.client.get("/"), url, fetch_redirect_response=False)
            self.client.logout()


class StaffTests(TestCase):
    def setUp(self):
        self.shop, self.users = make_client("Shop A")
        self.other, self.other_users = make_client("Shop B")

    def test_owner_can_add_a_cashier_with_pin(self):
        self.client.login(username="shop-a-owner", password=PASSWORD)
        response = self.client.post(
            reverse("staff_new"),
            {
                "username": "new-cashier",
                "first_name": "Neema",
                "last_name": "K",
                "role": "cashier",
                "is_active": "on",
                "password": "Another-strong-pass-1",
                "pin": "4321",
            },
        )
        self.assertRedirects(response, reverse("staff_list"))
        user = User.objects.get(username="new-cashier")
        self.assertEqual(user.client, self.shop)
        self.assertEqual(user.role, "cashier")
        self.assertTrue(user.check_password("Another-strong-pass-1"))
        self.assertTrue(user.check_pin("4321"))

    def test_admin_cannot_edit_owner_or_create_admins(self):
        self.client.login(username="shop-a-admin", password=PASSWORD)
        owner = self.users["owner"]
        self.assertEqual(self.client.get(reverse("staff_edit", args=[owner.pk])).status_code, 404)
        response = self.client.post(
            reverse("staff_new"),
            {"username": "sneaky", "role": "admin", "is_active": "on", "password": "Another-strong-pass-1"},
        )
        self.assertEqual(response.status_code, 200)  # form re-shown with an error
        self.assertFalse(User.objects.filter(username="sneaky").exists())

    def test_cannot_edit_staff_of_another_client(self):
        self.client.login(username="shop-a-owner", password=PASSWORD)
        foreign = self.other_users["cashier"]
        self.assertEqual(self.client.get(reverse("staff_edit", args=[foreign.pk])).status_code, 404)
