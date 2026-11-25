"""Authenticated JSON endpoints with server-assigned owners."""

from rest_framework import generics, permissions, serializers
from django.shortcuts import get_object_or_404
from django.db.models import Exists, OuterRef

from .models import OrderLine, Product, Review, Store


class MarketplaceMember(permissions.BasePermission):
    """Permit API reads only to registered buyer or vendor accounts."""

    def has_permission(self, request, view):
        """Check login, role and model permissions."""
        return bool(
            request.user.is_authenticated
            and request.user.groups.filter(
                name__in=["Buyers", "Vendors"]
            ).exists()
            and request.user.has_perm("shop.view_store")
        )


class VendorWriter(MarketplaceMember):
    """Reserve listing creation for vendors."""

    def has_permission(self, request, view):
        """Reject buyer writes before validation."""
        return super().has_permission(request, view) and (
            request.method in permissions.SAFE_METHODS
            or (
                request.user.groups.filter(name="Vendors").exists()
                and request.user.has_perm(
                    "shop.add_product" if "store_pk" in view.kwargs
                    else "shop.add_store"
                )
            )
        )


class StoreSerializer(serializers.ModelSerializer):
    """Expose store data without accepting a caller-selected owner."""

    class Meta:
        model = Store
        fields = ["id", "vendor", "name", "description"]
        read_only_fields = ["id", "vendor"]


class ProductSerializer(serializers.ModelSerializer):
    """Validate product inputs with server-assigned stores."""

    class Meta:
        model = Product
        fields = ["id", "store", "name", "description", "price", "stock"]
        read_only_fields = ["id", "store"]


class ReviewSerializer(serializers.ModelSerializer):
    """Return purchase verification as a derived, read-only boolean."""

    verified = serializers.BooleanField(
        source="purchase_verified", read_only=True
    )

    class Meta:
        model = Review
        fields = [
            "id",
            "buyer",
            "product",
            "rating",
            "content",
            "created_at",
            "verified",
        ]
        read_only_fields = fields


class StoreCreate(generics.CreateAPIView):
    """POST a new store owned by the authenticated vendor."""

    permission_classes = [VendorWriter]
    serializer_class = StoreSerializer

    def perform_create(self, serializer):
        """Assign ownership from authentication."""
        serializer.save(vendor=self.request.user)


class VendorStores(generics.ListAPIView):
    """GET one vendor's stores for authenticated buyers and vendors."""

    permission_classes = [MarketplaceMember]
    serializer_class = StoreSerializer

    def get_queryset(self):
        """Filter stores by the requested vendor."""
        return Store.objects.filter(
            vendor_id=self.kwargs["vendor_pk"]
        ).order_by("pk")


class StoreProducts(generics.ListCreateAPIView):
    """GET store products; POST only when the vendor owns that store."""

    permission_classes = [VendorWriter]
    serializer_class = ProductSerializer

    def get_queryset(self):
        """Return products or 404 for missing stores."""
        store = get_object_or_404(Store, pk=self.kwargs["store_pk"])
        return store.products.order_by("pk")

    def perform_create(self, serializer):
        """Require the authenticated owner before creation."""
        store = get_object_or_404(
            Store, pk=self.kwargs["store_pk"], vendor=self.request.user
        )
        serializer.save(store=store)


class ProductReviews(generics.ListAPIView):
    """GET verified/unverified reviews for owned products."""

    permission_classes = [MarketplaceMember]
    serializer_class = ReviewSerializer

    def get_queryset(self):
        """Require vendor permissions and product ownership."""
        from rest_framework.exceptions import PermissionDenied

        if not (
            self.request.user.groups.filter(name="Vendors").exists()
            and self.request.user.has_perm("shop.view_review")
        ):
            raise PermissionDenied(
                "Only vendors may retrieve product reviews."
            )
        product = get_object_or_404(
            Product,
            pk=self.kwargs["product_pk"],
            store__vendor=self.request.user,
        )
        return product.reviews.select_related("buyer").annotate(
            purchase_verified=Exists(OrderLine.objects.filter(
                order__buyer_id=OuterRef("buyer_id"),
                product_id=OuterRef("product_id"),
            ))
        ).order_by("pk")
