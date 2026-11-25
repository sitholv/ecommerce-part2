"""Named web routes; mutations use CSRF-protected POST requests."""

from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("", views.catalogue, name="catalogue"),
    path("accounts/register/", views.register, name="register"),
    path(
        "accounts/login/",
        LoginView.as_view(template_name="shop/login.html"),
        name="login",
    ),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("accounts/reset/", views.reset_request, name="reset_request"),
    path("accounts/reset/<str:secret>/", views.reset_confirm, name="reset"),
    path("stores/", views.stores, name="stores"),
    path("my-stores/", views.my_stores, name="my_stores"),
    path("stores/new/", views.store_edit, name="store_create"),
    path("stores/<int:pk>/", views.store_detail, name="store"),
    path("stores/<int:pk>/edit/", views.store_edit, name="store_edit"),
    path(
        "stores/<int:pk>/delete/",
        views.delete_listing,
        {"kind": "store"},
        name="store_delete",
    ),
    path(
        "stores/<int:store_pk>/products/new/",
        views.product_edit,
        name="product_create",
    ),
    path(
        "stores/<int:store_pk>/products/<int:pk>/edit/",
        views.product_edit,
        name="product_edit",
    ),
    path("products/<int:pk>/", views.product_detail, name="product"),
    path(
        "products/<int:pk>/delete/",
        views.delete_listing,
        {"kind": "product"},
        name="product_delete",
    ),
    path("products/<int:pk>/review/", views.review, name="review"),
    path("cart/", views.cart_detail, name="cart"),
    path("cart/add/<int:pk>/", views.cart_add, name="cart_add"),
    path("cart/remove/<int:pk>/", views.cart_remove, name="cart_remove"),
    path("checkout/", views.checkout_view, name="checkout"),
    path("invoices/<int:pk>/", views.invoice, name="invoice"),
    path("invoices/", views.invoices, name="invoices"),
]
