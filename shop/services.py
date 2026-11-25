"""Atomic checkout and secure password reset operations."""

from datetime import timedelta
from hashlib import sha256
import secrets

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Order, OrderLine, Product, ResetToken


@transaction.atomic
def checkout(buyer, cart, checkout_key):
    """Persist checkout atomically or reject the cart.

    Args:
        buyer: Authenticated buyer with an email address.
        cart: Session mapping of product IDs to quantities.
        checkout_key: UUID preventing repeated purchases.

    Returns:
        The existing or new Order. Clear the cart after success
        and send its invoice after commit.
    """
    if not (
        buyer.groups.filter(name="Buyers").exists()
        and buyer.has_perm("shop.view_order")
    ):
        raise ValidationError("Only buyers can check out.")
    if not buyer.email:
        raise ValidationError("Add an email address before checkout.")
    existing = Order.objects.filter(checkout_key=checkout_key).first()
    if existing:
        if existing.buyer_id != buyer.pk:
            raise ValidationError("This checkout belongs to another account.")
        return existing
    if not isinstance(cart, dict) or not cart:
        raise ValidationError("Your cart is empty.")
    order = Order.objects.create(buyer=buyer, checkout_key=checkout_key)
    for product_id, quantity in sorted(cart.items()):
        if type(quantity) is not int or not 1 <= quantity <= 999:
            raise ValidationError("Quantities must be between 1 and 999.")
        try:
            product = Product.objects.select_for_update().get(pk=product_id)
        except (Product.DoesNotExist, ValueError, TypeError) as error:
            raise ValidationError(
                "A cart product is no longer available."
            ) from error
        # Keep the stock guard as well as the MariaDB row lock.
        changed = Product.objects.filter(
            pk=product.pk, stock__gte=quantity
        ).update(stock=F("stock") - quantity)
        if not changed:
            raise ValidationError(f"Not enough stock for {product.name}.")
        OrderLine.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            quantity=quantity,
            unit_price=product.price,
        )
    return order


def email_invoice(order):
    """Send an invoice and record successful delivery.

    Raises the mail backend's exception on failure. An order remains
    valid and visible even when email delivery is temporarily
    unavailable.
    """
    if order.email_sent:
        return
    lines = [f"Invoice {order.pk}", "All prices in ZAR."]
    for line in order.lines.all():
        lines.append(
            f"{line.product_name}: {line.quantity} x "
            f"R{line.unit_price:.2f} = R{line.total:.2f}"
        )
    lines.append(f"Total: R{order.total:.2f}")
    send_mail(
        f"Invoice {order.pk}",
        "\n".join(lines),
        settings.DEFAULT_FROM_EMAIL,
        [order.buyer.email],
    )
    order.email_sent = True
    order.save(update_fields=["email_sent"])


def create_reset_token(user):
    """Return a reset secret and store only its digest."""
    secret = secrets.token_urlsafe(32)
    ResetToken.objects.create(
        user=user,
        digest=sha256(secret.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    return secret


@transaction.atomic
def reset_password(secret, password):
    """Consume a valid reset token and return its account.

    Lock the token while changing the password so concurrent requests
    cannot both reuse it. Django's validators apply to the new password.
    """
    try:
        token = (
            ResetToken.objects.select_for_update()
            .select_related("user")
            .get(
                digest=sha256(secret.encode()).hexdigest(),
                used_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
        )
    except ResetToken.DoesNotExist as error:
        raise ValidationError(
            "The reset link is invalid or expired."
        ) from error
    validate_password(password, token.user)
    token.user.set_password(password)
    token.user.save(update_fields=["password"])
    token.used_at = timezone.now()
    token.save(update_fields=["used_at"])
    # A successful reset invalidates the account's other reset links.
    ResetToken.objects.filter(user=token.user, used_at__isnull=True).update(
        used_at=timezone.now()
    )
    return token.user
