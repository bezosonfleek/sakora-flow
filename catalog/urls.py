from django.urls import path

from . import views

urlpatterns = [
    path("products/", views.product_list, name="product_list"),
    path("products/new/", views.product_edit, name="product_new"),
    path("products/import/", views.product_import, name="product_import"),
    path("products/import/sample.csv", views.import_sample, name="import_sample"),
    path("products/<int:pk>/", views.product_detail, name="product_detail"),
    path("products/<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("categories/", views.category_list, name="category_list"),
]
