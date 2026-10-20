from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from accounts.management.commands.seed_demo import PRODUCTS
from accounts.models import Client
from catalog.models import Product


class CoreTests(TestCase):
    def test_healthz_reports_database_up(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "db": "up"})

    def test_no_model_changes_are_missing_a_migration(self):
        # Fails (SystemExit) if a model changed without its migration file being generated and committed.
        call_command("makemigrations", "--check", "--dry-run", stdout=StringIO())

    def test_login_pages_render(self):
        for url in ("/login/", "/pin-login/"):
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_seed_demo_creates_a_usable_client_and_is_repeatable(self):
        out = StringIO()
        call_command("seed_demo", stdout=out)
        call_command("seed_demo", stdout=StringIO())
        client = Client.objects.get(slug="kijani-mini-mart")
        self.assertEqual(Product.objects.filter(client=client).count(), len(PRODUCTS))
        barcodes = list(Product.objects.filter(client=client).values_list("barcode", flat=True))
        self.assertEqual(len(barcodes), len(set(barcodes)))
        self.assertIn("kijani_cashier", out.getvalue())
        self.assertTrue(Product.objects.filter(client=client, name="Bella Tissue 4 Pack", price=140).exists())
