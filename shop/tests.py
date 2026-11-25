"""Purchase, transaction and security regression tests."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.utils import timezone

from .models import Order, Product, ResetToken, Review, Store
from .services import (
    checkout,
    create_reset_token,
    email_invoice,
    reset_password,
)


class CommerceServiceTests(TestCase):
    """Test purchases without real customer email."""

    def setUp(self):
        """Create two roles and one stocked product."""
        self.buyer = get_user_model().objects.create_user(
            "buyer", "buyer@example.test", "Strong-test-password-41"
        )
        self.buyer.groups.add(Group.objects.get(name="Buyers"))
        self.vendor = get_user_model().objects.create_user("vendor")
        self.vendor.groups.add(Group.objects.get(name="Vendors"))
        store = Store.objects.create(vendor=self.vendor, name="Bay Sports")
        self.product = Product.objects.create(
            store=store,
            name="Ball",
            description="Training football",
            price=Decimal("119.95"),
            stock=4,
        )

    def test_success_persists_frozen_invoice(self):
        """Preserve invoices after listing edits."""
        order = checkout(self.buyer, {str(self.product.pk): 2}, uuid4())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 2)
        self.assertEqual(order.total, Decimal("239.90"))
        self.product.price = Decimal("199.00")
        self.product.save()
        # Invoices must use the checkout snapshot, not today's price.
        self.assertEqual(order.total, Decimal("239.90"))

    def test_duplicate_checkout_is_idempotent(self):
        """Make repeated checkout idempotent."""
        key = uuid4()
        cart = {str(self.product.pk): 1}
        first = checkout(self.buyer, cart, key)
        self.assertEqual(checkout(self.buyer, cart, key).pk, first.pk)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)

    def test_invalid_cart_rolls_back_every_line(self):
        """Roll back checkout for missing listings."""
        with self.assertRaises(ValidationError):
            checkout(
                self.buyer, {str(self.product.pk): 1, "99999": 1}, uuid4()
            )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(Order.objects.count(), 0)

    def test_insufficient_stock_and_invalid_quantity(self):
        """Reject invalid and overstock quantities."""
        for quantity in (5, 0, -1, True, "2", 1000):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValidationError):
                    checkout(
                        self.buyer, {str(self.product.pk): quantity}, uuid4()
                    )
        self.assertFalse(Order.objects.exists())

    def test_vendor_cannot_checkout(self):
        """Reject vendors at the service boundary."""
        with self.assertRaises(ValidationError):
            checkout(self.vendor, {str(self.product.pk): 1}, uuid4())

    def test_verification_requires_purchase(self):
        """Require purchase evidence for verification."""
        review = Review.objects.create(
            buyer=self.buyer, product=self.product, rating=4, content="Useful"
        )
        self.assertFalse(review.verified)
        checkout(self.buyer, {str(self.product.pk): 1}, uuid4())
        self.assertTrue(review.verified)

    @patch("shop.services.send_mail")
    def test_invoice_is_sent_once(self, mail):
        """Do not resend delivered invoices."""
        order = checkout(self.buyer, {str(self.product.pk): 1}, uuid4())
        email_invoice(order)
        email_invoice(order)
        # Check retry behaviour without depending on a real mail server.
        mail.assert_called_once()
        self.assertIn("119.95", mail.call_args.args[1])

    def test_token_digest_and_single_use(self):
        """Hash reset secrets and reject reuse."""
        secret = create_reset_token(self.buyer)
        self.assertNotEqual(ResetToken.objects.get().digest, secret)
        reset_password(secret, "Another-strong-password-73")
        self.buyer.refresh_from_db()
        self.assertTrue(
            self.buyer.check_password("Another-strong-password-73")
        )
        with self.assertRaises(ValidationError):
            reset_password(secret, "Another-strong-password-74")

    def test_expired_reset_does_not_change_password(self):
        """Reject expired reset links."""
        secret = create_reset_token(self.buyer)
        ResetToken.objects.update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        with self.assertRaises(ValidationError):
            reset_password(secret, "Another-strong-password-73")
        self.buyer.refresh_from_db()
        self.assertTrue(self.buyer.check_password("Strong-test-password-41"))


class CommerceViewTests(TestCase):
    """Test browser URLs, sessions and ownership."""

    setUp = CommerceServiceTests.setUp

    def test_public_catalogue_and_detail(self):
        """Let visitors browse but not change listings."""
        self.assertContains(self.client.get("/"), "Ball")
        self.assertContains(
            self.client.get(f"/products/{self.product.pk}/"), "119.95"
        )
        self.assertEqual(self.client.post("/stores/new/", {}).status_code, 302)

    def test_buyer_cannot_create_store(self):
        """Reject buyer listing changes."""
        self.client.force_login(self.buyer)
        self.assertEqual(
            self.client.post("/stores/new/", {"name": "No"}).status_code, 403
        )

    def test_vendor_cannot_edit_another_vendor_store(self):
        """Reject other vendors' guessed IDs."""
        other = get_user_model().objects.create_user("other-vendor")
        other.groups.add(Group.objects.get(name="Vendors"))
        self.client.force_login(other)
        url = f"/stores/{self.product.store_id}/edit/"
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.post(url, {"name": "Stolen"}).status_code, 404
        )

    def test_vendor_can_create_and_edit_store(self):
        """Ignore forged vendor fields."""
        self.client.force_login(self.vendor)
        response = self.client.post(
            "/stores/new/",
            {
                "name": "New store",
                "description": "Local stock",
                "vendor": self.buyer.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Store.objects.get(name="New store").vendor, self.vendor
        )

    def test_session_cart_checkout_and_new_order(self):
        """Allow separate purchases in one session."""
        self.client.force_login(self.buyer)
        for _ in range(2):
            self.client.post(f"/cart/add/{self.product.pk}/", {"quantity": 1})
            self.client.get("/cart/")
            key = self.client.session["checkout_key"]
            with patch("shop.views.email_invoice"):
                response = self.client.post(
                    "/checkout/", {"checkout_key": key}
                )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.client.session["cart"], {})
        self.assertEqual(Order.objects.count(), 2)

    def test_invoice_is_private(self):
        """Keep other buyers' invoices private."""
        order = checkout(self.buyer, {str(self.product.pk): 1}, uuid4())
        other = get_user_model().objects.create_user("other-buyer")
        other.groups.add(Group.objects.get(name="Buyers"))
        self.client.force_login(other)
        self.assertEqual(
            self.client.get(f"/invoices/{order.pk}/").status_code, 404
        )

    def test_get_delete_only_confirms(self):
        """Require POST for deletion."""
        self.client.force_login(self.vendor)
        self.client.get(f"/products/{self.product.pk}/delete/")
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_csrf_and_html_escaping(self):
        """Enforce CSRF and escape stored scripts."""
        # Enable CSRF checks: Django's default test client skips them.
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.vendor)
        self.assertEqual(
            client.post("/stores/new/", {"name": "No"}).status_code, 403
        )
        # A saved script payload must render as text, not execute.
        self.product.description = "<script>alert(1)</script>"
        self.product.save()
        response = self.client.get(f"/products/{self.product.pk}/")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_checkout_rejects_unbound_key(self):
        """Bind checkout keys to their session."""
        self.client.force_login(self.buyer)
        response = self.client.post(
            "/checkout/", {"checkout_key": str(uuid4())}
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Order.objects.exists())

    def test_review_verification_cannot_be_forged(self):
        """Ignore forged review verification."""
        self.client.force_login(self.buyer)
        response = self.client.post(
            f"/products/{self.product.pk}/review/",
            {
                "rating": 5,
                "content": "Good",
                "verified": True,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Review.objects.get().verified)
