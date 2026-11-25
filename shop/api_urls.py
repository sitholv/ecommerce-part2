"""Namespaced marketplace API routes."""

from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token

from . import api

app_name = "api"

urlpatterns = [
    path("token/", obtain_auth_token, name="token"),
    path("stores/", api.StoreCreate.as_view(), name="store-create"),
    path(
        "vendors/<int:vendor_pk>/stores/",
        api.VendorStores.as_view(),
        name="vendor-stores",
    ),
    path(
        "stores/<int:store_pk>/products/",
        api.StoreProducts.as_view(),
        name="store-products",
    ),
    path(
        "products/<int:product_pk>/reviews/",
        api.ProductReviews.as_view(),
        name="product-reviews",
    ),
]
