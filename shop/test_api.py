"""API ownership and external-feed boundary regression tests."""

from io import StringIO
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
import requests

from functions.reddit import fetch_posts, RedditUnavailable
from .models import Product, Review, Store


class MarketplaceAPITests(TestCase):
    """Exercise endpoints with real tokens and records."""

    def setUp(self):
        """Create buyer/vendor accounts and tokens."""
        user = get_user_model()
        self.vendor = user.objects.create_user("api-vendor")
        self.other = user.objects.create_user("api-other")
        self.buyer = user.objects.create_user("api-buyer")
        for vendor in (self.vendor, self.other):
            vendor.groups.add(Group.objects.get(name="Vendors"))
        self.buyer.groups.add(Group.objects.get(name="Buyers"))
        self.store = Store.objects.create(vendor=self.vendor, name="Bay store")
        self.product = Product.objects.create(
            store=self.store,
            name="Ball",
            description="Training ball",
            price="100.00",
            stock=5,
        )
        self.client = APIClient()

    def authenticate(self, user):
        """Authenticate with a real token."""
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_anonymous_denied(self):
        """Reject anonymous catalogue requests."""
        response = self.client.get(f"/api/vendors/{self.vendor.pk}/stores/")
        self.assertEqual(response.status_code, 401)

    def test_members_read_filtered_lists(self):
        """Return the requested vendor/store listings."""
        Store.objects.create(vendor=self.other, name="Different")
        for user in (self.buyer, self.vendor):
            self.authenticate(user)
            response = self.client.get(
                f"/api/vendors/{self.vendor.pk}/stores/"
            )
            self.assertEqual(
                [row["id"] for row in response.json()], [self.store.pk]
            )
            response = self.client.get(
                f"/api/stores/{self.store.pk}/products/"
            )
            self.assertEqual(response.json()[0]["name"], "Ball")

    def test_vendor_store_owner_not_client_selected(self):
        """Ignore forged listing ownership."""
        self.authenticate(self.vendor)
        response = self.client.post(
            "/api/stores/",
            {
                "name": "New",
                "vendor": self.other.pk,
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["vendor"], self.vendor.pk)

    def test_buyer_cannot_create(self):
        """Reject listing creation by buyers."""
        self.authenticate(self.buyer)
        self.assertEqual(
            self.client.post(
                "/api/stores/",
                {
                    "name": "Wrong role",
                },
            ).status_code,
            403,
        )

    def test_product_owner_check_and_validation(self):
        """Reject cross-vendor writes and invalid prices."""
        url = f"/api/stores/{self.store.pk}/products/"
        data = {
            "name": "Boots",
            "description": "Football boots",
            "price": "20.00",
            "stock": 2,
        }
        self.authenticate(self.other)
        self.assertEqual(self.client.post(url, data).status_code, 404)
        self.authenticate(self.vendor)
        self.assertEqual(self.client.post(url, data).status_code, 201)
        data["price"] = "-1.00"
        self.assertEqual(self.client.post(url, data).status_code, 400)

    def test_reviews_vendor_only_and_owner_scoped(self):
        """Restrict review reads to product owners."""
        Review.objects.create(
            buyer=self.buyer, product=self.product, rating=4, content="Useful"
        )
        url = f"/api/products/{self.product.pk}/reviews/"
        self.authenticate(self.buyer)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.authenticate(self.vendor)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()[0]["verified"], False)


class RedditFeedTests(SimpleTestCase):
    """Test external responses without network access."""

    @patch("functions.reddit.requests.get")
    def test_real_response_shape(self, get):
        """Parse titles, authors and links with a User-Agent."""
        get.return_value = Mock()
        get.return_value.json.return_value = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Python release",
                            "author": "reader",
                            "url": "https://www.python.org/",
                        }
                    },
                ]
            }
        }
        self.assertEqual(fetch_posts()[0]["author"], "reader")
        self.assertEqual(
            get.call_args.args[0], "https://www.reddit.com/r/python/.json"
        )
        self.assertIn("User-Agent", get.call_args.kwargs["headers"])
        self.assertEqual(
            get.call_args.kwargs["headers"]["User-Agent"],
            "DjangoEcommerceApp/1.0",
        )
        self.assertNotIn("auth", get.call_args.kwargs)
        self.assertNotIn("params", get.call_args.kwargs)
        self.assertEqual(get.call_args.kwargs["timeout"], (3.05, 10))

    @patch("functions.reddit.requests.get")
    def test_failure_is_visible_not_fake_posts(self, get):
        """Explain timeouts without fabricated posts."""
        get.side_effect = requests.Timeout("Timed out")
        response = self.client.get("/reddit/")
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "Reddit is unavailable", status_code=503)

    @patch("functions.reddit.requests.get")
    def test_malformed_payload(self, get):
        """Handle malformed JSON safely."""
        get.return_value.json.return_value = {"unexpected": []}
        with self.assertRaises(RedditUnavailable):
            fetch_posts()

    @patch("functions.reddit.requests.get")
    def test_executable_link_omitted(self, get):
        """HTML escaping alone cannot make a javascript URI safe."""
        get.return_value.json.return_value = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Unsafe",
                            "author": "reader",
                            "url": "javascript:alert(1)",
                        }
                    },
                ]
            }
        }
        self.assertEqual(fetch_posts(), [])

    @patch("functions.reddit.requests.get")
    def test_forbidden_reports_actual_access_status(self, get):
        """Distinguish access denial from an empty successful feed."""
        response = Mock(status_code=403)
        get.return_value.raise_for_status.side_effect = requests.HTTPError(
            response=response
        )
        with self.assertRaises(RedditUnavailable) as caught:
            fetch_posts()
        self.assertEqual(caught.exception.status_code, 403)
        self.assertIn("HTTP 403", str(caught.exception))
        page = self.client.get("/reddit/")
        self.assertContains(page, "HTTP 403", status_code=503)

    @patch("functions.reddit.requests.get")
    def test_rate_limit_does_not_trigger_repeated_requests(self, get):
        """Do not retry around a rate-limit response."""
        get.return_value.raise_for_status.side_effect = requests.HTTPError(
            response=Mock(status_code=429)
        )
        with self.assertRaises(RedditUnavailable) as caught:
            fetch_posts()
        self.assertEqual(caught.exception.status_code, 429)
        self.assertIn("rate limit", str(caught.exception))
        get.assert_called_once()


class RedditDiagnosticTests(SimpleTestCase):
    """Check diagnostic reporting with isolated mock results."""

    @patch("shop.management.commands.check_reddit.fetch_posts")
    def test_command_prints_received_posts(self, fetch):
        """Report all three display fields after a successful fetch."""
        fetch.return_value = [
            {
                "title": "Python release",
                "author": "reader",
                "url": "https://www.reddit.com/r/python/comments/test/",
            }
        ]
        output = StringIO()
        call_command("check_reddit", stdout=output)
        self.assertIn("Received 1 live", output.getvalue())
        self.assertIn("Python release", output.getvalue())
        self.assertIn("reader", output.getvalue())

    @patch("shop.management.commands.check_reddit.fetch_posts")
    def test_command_fails_when_access_is_denied(self, fetch):
        """An access refusal must fail the check."""
        fetch.side_effect = RedditUnavailable("HTTP 403", status_code=403)
        with self.assertRaisesMessage(CommandError, "HTTP 403"):
            call_command("check_reddit")

    @patch(
        "shop.management.commands.check_reddit.fetch_posts", return_value=[]
    )
    def test_empty_response_does_not_verify_post_display(self, fetch):
        """An empty result cannot verify live post display."""
        with self.assertRaisesMessage(CommandError, "no usable posts"):
            call_command("check_reddit")
