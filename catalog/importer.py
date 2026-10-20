"""CSV import of products. All-or-nothing: if any row is bad, nothing is imported."""
import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import Category, Product, StockMovement
from .services import change_stock

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 20000
MAX_ERRORS = 50
TRUE_WORDS = {"1", "true", "yes", "y", "t"}
FALSE_WORDS = {"0", "false", "no", "n", "f", "exempt"}

SAMPLE_CSV = (
    "name,barcode,category,price,cost,stock,vat\n"
    "Bella Tissue 4 Pack,2000000000015,Household,140,110,24,yes\n"
    "Bella Tissue 2 Pack,2000000000022,Household,75,58,30,yes\n"
    "Bread White 400g,2000000000039,Bakery,65,55,20,no\n"
)


class ImportProblem(Exception):
    def __init__(self, errors):
        super().__init__("Import problems")
        self.errors = errors


def _decimal(value, label, row_no, errors, *, places, required=False):
    value = (value or "").strip().replace(",", "")
    if value == "":
        if required:
            errors.append(f"Row {row_no}: {label} is required.")
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        errors.append(f"Row {row_no}: {label} '{value}' is not a number.")
        return None
    if not number.is_finite() or number < 0 and label != "stock":
        errors.append(f"Row {row_no}: {label} must be zero or more.")
        return None
    if number.as_tuple().exponent < -places:
        errors.append(f"Row {row_no}: {label} has too many decimal places.")
        return None
    return number


def parse_rows(raw: bytes):
    if len(raw) > MAX_BYTES:
        raise ImportProblem(["The file is larger than 2 MB. Split it into smaller files."])
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportProblem(["The file is not UTF-8. In Excel use Save As > CSV UTF-8."])
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ImportProblem(["The file is empty."])
    reader.fieldnames = [(h or "").strip().lower() for h in reader.fieldnames]
    missing = [h for h in ("name", "price") if h not in reader.fieldnames]
    if missing:
        raise ImportProblem([f"Missing required column(s): {', '.join(missing)}."])

    errors, rows, seen_barcodes = [], [], set()
    for index, row in enumerate(reader, start=2):  # row 1 is the header
        if index - 1 > MAX_ROWS:
            errors.append(f"More than {MAX_ROWS} rows. Split the file.")
            break
        if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
            continue
        name = (row.get("name") or "").strip()
        if not name:
            errors.append(f"Row {index}: name is required.")
        elif len(name) > 200:
            errors.append(f"Row {index}: name is longer than 200 characters.")
        barcode = (row.get("barcode") or "").strip()
        if barcode:
            if len(barcode) > 64:
                errors.append(f"Row {index}: barcode is too long.")
            if barcode in seen_barcodes:
                errors.append(f"Row {index}: barcode {barcode} appears twice in the file.")
            seen_barcodes.add(barcode)
        price = _decimal(row.get("price"), "price", index, errors, places=2, required=True)
        cost = _decimal(row.get("cost"), "cost", index, errors, places=2)
        stock = _decimal(row.get("stock"), "stock", index, errors, places=3)
        vat_word = (row.get("vat") or "").strip().lower()
        if vat_word == "" or vat_word in TRUE_WORDS:
            vat = True
        elif vat_word in FALSE_WORDS:
            vat = False
        else:
            errors.append(f"Row {index}: vat must be yes or no.")
            vat = True
        category = (row.get("category") or "").strip()[:80]
        rows.append(
            {"name": name, "barcode": barcode, "price": price, "cost": cost, "stock": stock, "vat": vat, "category": category}
        )
        if len(errors) >= MAX_ERRORS:
            errors.append("Too many problems; fix these first and try again.")
            break
    if not errors and not rows:
        errors.append("No product rows found.")
    if errors:
        raise ImportProblem(errors)
    return rows


def import_products(*, client, raw: bytes, user):
    rows = parse_rows(raw)
    created = updated = 0
    with transaction.atomic():
        categories = {c.name.lower(): c for c in Category.objects.filter(client=client)}
        by_barcode = {p.barcode: p for p in Product.objects.select_for_update().filter(client=client) if p.barcode}
        by_name = {p.name.lower(): p for p in Product.objects.filter(client=client)}
        for row in rows:
            category = None
            if row["category"]:
                category = categories.get(row["category"].lower())
                if category is None:
                    category = Category.objects.create(client=client, name=row["category"])
                    categories[row["category"].lower()] = category
            product = by_barcode.get(row["barcode"]) if row["barcode"] else None
            if product is None and not row["barcode"]:
                product = by_name.get(row["name"].lower())
            if product is None:
                product = Product.objects.create(
                    client=client,
                    name=row["name"],
                    barcode=row["barcode"],
                    category=category,
                    price=row["price"],
                    cost=row["cost"] or 0,
                    vat_applies=row["vat"],
                    stock=0,
                )
                if row["barcode"]:
                    by_barcode[row["barcode"]] = product
                by_name[row["name"].lower()] = product
                created += 1
                if row["stock"]:
                    change_stock(product=product, delta=row["stock"], reason=StockMovement.OPENING, user=user, note="CSV import")
            else:
                product.name = row["name"]
                product.price = row["price"]
                if row["cost"] is not None:
                    product.cost = row["cost"]
                product.vat_applies = row["vat"]
                if category:
                    product.category = category
                product.save(update_fields=["name", "price", "cost", "vat_applies", "category", "updated_at"])
                updated += 1
                if row["stock"] is not None:
                    delta = row["stock"] - product.stock
                    if delta:
                        change_stock(product=product, delta=delta, reason=StockMovement.IMPORT, user=user, note="CSV import")
    return {"created": created, "updated": updated}
