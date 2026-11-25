"""Relational marketplace records and immutable purchase evidence."""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Store(models.Model):
    """A vendor-owned store with a name and optional description.

    Names are limited to 120 characters and descriptions to 3,000.
    Removing a store removes its listings, not frozen order details. The
    views assign vendor from the session rather than form input.
    """

    vendor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    name = models.CharField(max_length=120)
    description = models.TextField(max_length=3000, blank=True)

    def __str__(self):
        """Return the store's display label."""
        return self.name


class Product(models.Model):
    """A store's product with a description, rand price and stock count.

    Prices use two decimal places and must be greater than zero; a
    database constraint also protects this rule outside the forms. Stock
    cannot be negative. Role and ownership checks belong to the views,
    while forms validate the editable listing fields.
    """

    store = models.ForeignKey(
        Store, on_delete=models.CASCADE, related_name="products"
    )
    name = models.CharField(max_length=120)
    description = models.TextField(max_length=5000)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    stock = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gt=0), name="positive_product_price"
            )
        ]

    def __str__(self):
        """Return a human-readable product label."""
        return self.name


class Order(models.Model):
    """A completed purchase linked to a buyer and frozen order lines.

    checkout_key is unique so a repeated form submission can refer to
    the same order. email_sent records mail-backend success, not a
    payment. The protected buyer relation preserves invoice ownership.
    """

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    checkout_key = models.UUIDField(unique=True)
    email_sent = models.BooleanField(default=False)

    @property
    def total(self):
        """Calculate the frozen invoice total in rand."""
        return sum((line.total for line in self.lines.all()), Decimal("0.00"))


class OrderLine(models.Model):
    """Store the quantity, name and unit price agreed at checkout.

    A deleted product leaves product as NULL, but the copied name and
    price remain available for the invoice. quantity must be positive.
    Totals use these saved values rather than the current product price.
    """

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="lines"
    )
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=120)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def total(self):
        """Return an exact decimal quantity-times-price subtotal."""
        return self.unit_price * self.quantity


class Review(models.Model):
    """A product review with a one-to-five rating and buyer identity.

    A unique constraint allows one review per buyer/product pair. Forms
    limit content to 3,000 characters. verified checks order evidence at
    read time; a submitted flag cannot grant verification.
    """

    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    content = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["buyer", "product"],
                name="one_review_per_buyer_product",
            )
        ]

    @property
    def verified(self):
        """Derive verification from persisted order lines."""
        return OrderLine.objects.filter(
            order__buyer=self.buyer, product=self.product
        ).exists()


class ResetToken(models.Model):
    """Record the hashed reset secret, expiry and optional use time.

    The reset service creates a 15-minute expiry and sets used_at when
    consuming the link. Keeping only the SHA-256 digest means the raw
    secret is not recoverable from this table. The service checks both
    expiry and use time before changing a password.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
