from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import MANAGERS, role_required

from .forms import CategoryForm, ImportForm, ProductForm, StockActionForm
from .importer import SAMPLE_CSV, ImportProblem, import_products
from .models import Category, Product, StockMovement
from .services import adjust_stock, change_stock


@role_required(*MANAGERS)
def product_list(request):
    q = request.GET.get("q", "").strip()
    view = request.GET.get("view", "")
    products = Product.objects.filter(client=request.client).select_related("category")
    if q:
        products = products.filter(Q(name__icontains=q) | Q(barcode__startswith=q))
    if view == "low":
        products = products.filter(is_active=True, stock__lte=F("reorder_level"))
    elif view == "inactive":
        products = products.filter(is_active=False)
    total = products.count()
    return render(
        request,
        "catalog/product_list.html",
        {"products": products[:300], "q": q, "view": view, "total": total},
    )


@role_required(*MANAGERS)
def product_edit(request, pk=None):
    instance = get_object_or_404(Product, pk=pk, client=request.client) if pk else None
    form = ProductForm(request.POST or None, instance=instance, client=request.client)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            product = form.save(commit=False)
            product.client = request.client
            if not instance:
                product.stock = 0
            product.save()
            opening = form.cleaned_data.get("opening_stock")
            if not instance and opening:
                change_stock(product=product, delta=opening, reason=StockMovement.OPENING, user=request.user)
        messages.success(request, "Product saved.")
        return redirect("product_detail", pk=product.pk)
    return render(
        request,
        "form_page.html",
        {"title": "Edit product" if instance else "Add product", "form": form, "back": "/products/"},
    )


@role_required(*MANAGERS)
def product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related("category"), pk=pk, client=request.client)
    form = StockActionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        adjust_stock(
            product_id=product.pk,
            client=request.client,
            kind=form.cleaned_data["kind"],
            quantity=form.cleaned_data["quantity"],
            user=request.user,
            note=form.cleaned_data["note"],
        )
        messages.success(request, "Stock updated.")
        return redirect("product_detail", pk=product.pk)
    movements = product.movements.select_related("user")[:50]
    return render(request, "catalog/product_detail.html", {"product": product, "form": form, "movements": movements})


@role_required(*MANAGERS)
def category_list(request):
    form = CategoryForm(request.POST or None)
    if request.method == "POST":
        if "delete" in request.POST:
            Category.objects.filter(client=request.client, pk=request.POST["delete"]).delete()
            messages.success(request, "Category removed. Its products are now uncategorised.")
            return redirect("category_list")
        if form.is_valid():
            name = form.cleaned_data["name"].strip()
            category, created = Category.objects.get_or_create(client=request.client, name=name)
            messages.success(request, "Category added." if created else "That category already exists.")
            return redirect("category_list")
    categories = Category.objects.filter(client=request.client)
    return render(request, "catalog/category_list.html", {"categories": categories, "form": form})


@role_required(*MANAGERS)
def product_import(request):
    form = ImportForm(request.POST or None, request.FILES or None)
    errors, result = [], None
    if request.method == "POST" and form.is_valid():
        raw = form.cleaned_data["file"].read()
        try:
            result = import_products(client=request.client, raw=raw, user=request.user)
            messages.success(
                request, f"Import finished: {result['created']} added, {result['updated']} updated."
            )
            return redirect("product_list")
        except ImportProblem as exc:
            errors = exc.errors
    return render(request, "catalog/product_import.html", {"form": form, "errors": errors})


@role_required(*MANAGERS)
def import_sample(request):
    response = HttpResponse(SAMPLE_CSV, content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="products-sample.csv"'
    return response
