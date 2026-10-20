from django.urls import path

from . import views

urlpatterns = [
    path("pin-login/", views.pin_login, name="pin_login"),
    path("staff/", views.staff_list, name="staff_list"),
    path("staff/new/", views.staff_edit, name="staff_new"),
    path("staff/<int:pk>/edit/", views.staff_edit, name="staff_edit"),
    path("settings/", views.client_settings, name="client_settings"),
]
