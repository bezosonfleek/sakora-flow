from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("till/", views.till, name="till"),
    path("api/products/", views.api_products, name="api_products"),
    path("api/sales/", views.api_sale_create, name="api_sale_create"),
    path("shifts/", views.shift_list, name="shift_list"),
    path("shifts/open/", views.shift_open, name="shift_open"),
    path("shifts/close/", views.shift_close, name="shift_close"),
    path("shifts/<int:pk>/", views.shift_detail, name="shift_detail"),
    path("sales/", views.sale_list, name="sale_list"),
    path("sales/<int:pk>/", views.sale_detail, name="sale_detail"),
    path("sales/<int:pk>/receipt/", views.sale_receipt, name="sale_receipt"),
    path("sales/<int:pk>/void/", views.sale_void, name="sale_void"),
    path("reports/daily/", views.daily_report_view, name="daily_report"),
]
