"""Test cart recovery, permissions, query counts and email."""

from contextlib import redirect_stdout
from io import StringIO
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.mail import get_connection
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .context_processors import account_roles
from .forms import QuantityForm
from .models import Product, Review, Store
from .services import checkout, email_invoice


class FeedbackTests(TestCase):
    """Protect corrected edge cases with real database records."""

    def setUp(self):
        """Build two roles and a stocked product."""
        users = get_user_model().objects
        self.buyer = users.create_user("cartbuyer", email="buyer@example.test")
        self.buyer.groups.add(Group.objects.get(name="Buyers"))
        self.vendor = users.create_user("storevendor")
        self.vendor.groups.add(Group.objects.get(name="Vendors"))
        self.store = Store.objects.create(vendor=self.vendor, name="Bay Store")
        self.product = Product.objects.create(
            store=self.store, name="Ball", description="Training ball",
            price="100.00", stock=4,
        )

    def test_deleted_cart_line_is_pruned_and_checkout_recovers(self):
        """Prune deleted listings before checkout."""
        deleted = Product.objects.create(
            store=self.store, name="Gone", description="Gone",
            price="10.00", stock=2,
        )
        dead_id = str(deleted.pk)
        deleted.delete()
        self.client.force_login(self.buyer)
        session = self.client.session
        session["cart"] = {dead_id: 1, str(self.product.pk): 1}
        session.save()
        self.assertEqual(self.client.get(reverse("cart")).status_code, 200)
        self.assertEqual(
            self.client.session["cart"], {str(self.product.pk): 1}
        )
        with override_settings(MAILERS={
            "default": {
                "BACKEND": "django.core.mail.backends.locmem.EmailBackend"
            }
        }):
            result = self.client.post(reverse("checkout"), {
                "checkout_key": self.client.session["checkout_key"]
            })
        self.assertEqual(result.status_code, 302)
        self.assertEqual(self.buyer.order_set.count(), 1)

    def test_vendor_group_without_permission_cannot_create(self):
        """A role name alone is not an authorization grant."""
        group = Group.objects.get(name="Vendors")
        group.permissions.remove(Permission.objects.get(
            content_type__app_label="shop", codename="add_store"
        ))
        self.client.force_login(self.vendor)
        response = self.client.post(
            reverse("store_create"), {"name": "Denied"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Store.objects.filter(name="Denied").exists())

    def test_invoice_and_store_lists_are_owner_scoped(self):
        """Keep history and management lists private."""
        order = checkout(self.buyer, {str(self.product.pk): 1}, uuid4())
        other = get_user_model().objects.create_user("otherbuyer")
        other.groups.add(Group.objects.get(name="Buyers"))
        self.client.force_login(other)
        self.assertNotContains(self.client.get(reverse("invoices")),
                               f"Invoice {order.pk}")
        self.client.force_login(self.vendor)
        self.assertContains(self.client.get(reverse("my_stores")), "Bay Store")

    def test_review_query_count_does_not_grow_with_reviews(self):
        """Keep query counts constant as reviews increase."""
        self.client.force_login(self.buyer)
        url = reverse("product", args=[self.product.pk])
        with CaptureQueriesContext(connection) as baseline:
            self.client.get(url)
        for number in range(5):
            user = get_user_model().objects.create_user(f"reviewer{number}")
            Review.objects.create(
                buyer=user, product=self.product, rating=4, content="Useful"
            )
        with CaptureQueriesContext(connection) as populated:
            response = self.client.get(url)
        self.assertContains(response, "Unverified review", count=5)
        self.assertEqual(len(baseline), len(populated))

    def test_roles_are_loaded_once_per_request(self):
        """Reuse roles within the same request."""
        request = RequestFactory().get("/")
        request.user = self.buyer
        with self.assertNumQueries(1):
            self.assertTrue(account_roles(request)["is_buyer"])
            self.assertTrue(account_roles(request)["is_buyer"])

    def test_stock_bounds_and_sold_out_control(self):
        """Validate stock in the form and expose browser limits."""
        self.assertFalse(QuantityForm({"quantity": 5}, stock=4).is_valid())
        self.client.force_login(self.buyer)
        response = self.client.get(reverse("product", args=[self.product.pk]))
        self.assertContains(response, 'max="4"')
        self.product.stock = 0
        self.product.save()
        response = self.client.get(reverse("product", args=[self.product.pk]))
        self.assertContains(response, "disabled")

    def test_console_backend_and_configured_reset_sender(self):
        """Prove console email runs with the configured sender."""
        with override_settings(
            MAILERS={"default": {
                "BACKEND": "django.core.mail.backends.console.EmailBackend"
            }},
            DEFAULT_FROM_EMAIL="configured@example.test",
        ):
            self.assertEqual(
                get_connection().__class__.__module__,
                "django.core.mail.backends.console",
            )
            output = StringIO()
            with redirect_stdout(output):
                order = checkout(
                    self.buyer, {str(self.product.pk): 1}, uuid4()
                )
                email_invoice(order)
                self.client.post(reverse("reset_request"), {
                    "email": self.buyer.email
                })
            self.assertIn(settings.DEFAULT_FROM_EMAIL, output.getvalue())
            self.assertIn("Password reset", output.getvalue())
            self.assertIn("Invoice", output.getvalue())
