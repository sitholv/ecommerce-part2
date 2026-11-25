"""HTML request handlers with role, ownership and HTTP-method checks."""

from decimal import Decimal
from functools import wraps
from hashlib import sha256
import logging
from uuid import uuid4

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import (
    require_http_methods,
    require_POST,
    require_safe,
)

from .forms import (
    ProductForm,
    QuantityForm,
    RegistrationForm,
    ResetPasswordForm,
    ResetRequestForm,
    ReviewForm,
    StoreForm,
)
from .models import Order, OrderLine, Product, ResetToken, Review, Store
from .services import (
    checkout,
    create_reset_token,
    email_invoice,
    reset_password,
)

logger = logging.getLogger(__name__)


@require_safe
def reddit_feed(request):
    """Render posts or a clear unavailable state on GET or HEAD."""
    from functions.reddit import fetch_posts, RedditUnavailable

    try:
        posts = fetch_posts()
    except RedditUnavailable as error:
        return render(request, "shop/reddit_feed.html", {
            "posts": [], "error": str(error),
        }, status=503)
    return render(request, "shop/reddit_feed.html", {"posts": posts})


def role_required(group, permission="shop.view_product"):
    """Require a named group before running a browser view.

    Both group membership and the named model permission are required.
    Anonymous requests go to login; missing authority returns HTTP 403. The
    wrapped view retains its original name and documentation.
    """

    def decorator(view):
        """Wrap view with the login and group checks for this role."""

        @login_required
        @wraps(view)
        def guarded(request, *args, **kwargs):
            """Reject a valid login with the wrong account role."""
            if not request.user.groups.filter(name=group).exists():
                raise PermissionDenied
            if not request.user.has_perm(permission):
                raise PermissionDenied("Your account lacks this permission.")
            return view(request, *args, **kwargs)

        return guarded

    return decorator


@require_safe
def catalogue(request):
    """Show the public catalogue on GET or HEAD.

    Return shop/catalogue.html with a products queryset ordered by name.
    Joining stores here avoids a separate lookup for each product card.
    """
    return render(
        request,
        "shop/catalogue.html",
        {
            "products": Product.objects.select_related("store").order_by(
                "name"
            ),
        },
    )


@require_http_methods(["GET", "POST"])
def register(request):
    """Display registration or create a buyer/vendor account.

    GET renders shop/form.html with form and title. Invalid POST data
    returns the same form with errors. A valid POST creates the account,
    logs it in and redirects to catalogue.
    """
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("catalogue")
    return render(
        request, "shop/form.html", {"form": form, "title": "Register"}
    )


@require_safe
def stores(request):
    """List public stores on GET or HEAD.

    Render shop/stores.html with stores ordered by name. Include vendor
    records in the query so each card can show its owner efficiently.
    """
    return render(
        request,
        "shop/stores.html",
        {
            "stores": Store.objects.select_related("vendor").order_by("name"),
        },
    )


@require_safe
def store_detail(request, pk):
    """Show the store identified by the URL's pk on GET or HEAD.

    Return shop/store.html with store, products and an owner flag. A
    missing store raises Http404. The flag controls visible actions;
    write views still check ownership independently.
    """
    store = get_object_or_404(Store, pk=pk)
    return render(
        request,
        "shop/store.html",
        {
            "store": store,
            "products": store.products.all(),
            "owner": request.user.is_authenticated
            and store.vendor_id == request.user.pk,
        },
    )


@role_required("Vendors", "shop.view_store")
@require_safe
def my_stores(request):
    """Render the vendor's own stores on GET or HEAD."""
    return render(request, "shop/stores.html", {
        "stores": Store.objects.filter(vendor=request.user),
        "title": "My stores",
    })


@role_required("Buyers", "shop.view_order")
@require_safe
def invoices(request):
    """Render only the buyer's own invoice history."""
    orders = Order.objects.filter(buyer=request.user).prefetch_related(
        "lines"
    ).order_by("-created_at", "-pk")
    return render(request, "shop/invoices.html", {"orders": orders})


@role_required("Vendors")
@require_http_methods(["GET", "POST"])
def store_edit(request, pk=None):
    """Show or save the current vendor's store.

    GET renders shop/form.html with form and title. On POST, validate
    the submitted fields and redirect to store detail after saving. pk
    is an existing store ID, or None for creation. Another vendor's ID
    returns HTTP 404; the owner always comes from the login session.
    """
    action = "change" if pk else "add"
    if not request.user.has_perm(f"shop.{action}_store"):
        raise PermissionDenied
    store = (
        get_object_or_404(Store, pk=pk, vendor=request.user) if pk else None
    )
    form = StoreForm(
        request.POST if request.method == "POST" else None, instance=store
    )
    if request.method == "POST" and form.is_valid():
        store = form.save(commit=False)
        store.vendor = request.user
        store.save()
        return redirect("store", pk=store.pk)
    return render(
        request, "shop/form.html", {"form": form, "title": "Store details"}
    )


@role_required("Vendors")
@require_http_methods(["GET", "POST"])
def product_edit(request, store_pk, pk=None):
    """Show or save a product within the vendor's own store.

    store_pk identifies the parent store; optional pk selects a product
    for editing. GET and invalid POST render form and title through
    shop/form.html. A valid POST redirects to product detail. Missing
    records or records outside the vendor's store return HTTP 404.
    """
    action = "change" if pk else "add"
    if not request.user.has_perm(f"shop.{action}_product"):
        raise PermissionDenied
    store = get_object_or_404(Store, pk=store_pk, vendor=request.user)
    product = get_object_or_404(Product, pk=pk, store=store) if pk else None
    form = ProductForm(
        request.POST if request.method == "POST" else None, instance=product
    )
    if request.method == "POST" and form.is_valid():
        product = form.save(commit=False)
        product.store = store
        product.save()
        return redirect("product", pk=product.pk)
    return render(
        request, "shop/form.html", {"form": form, "title": "Product details"}
    )


@role_required("Vendors")
@require_http_methods(["GET", "POST"])
def delete_listing(request, kind, pk):
    """Confirm or remove a store/product belonging to the vendor.

    kind is supplied by the URL configuration; pk selects the listing.
    GET renders shop/confirm.html with listing. POST removes it and
    redirects to stores. Ownership is checked before either response.
    Deleting listings must not remove the buyer's frozen invoice lines.
    """
    if not request.user.has_perm(f"shop.delete_{kind}"):
        raise PermissionDenied
    if kind == "store":
        listing = get_object_or_404(Store, pk=pk, vendor=request.user)
    else:
        listing = get_object_or_404(Product, pk=pk, store__vendor=request.user)
    if request.method == "POST":
        listing.delete()
        messages.success(
            request, "Listing removed. Past invoices are unchanged."
        )
        return redirect("stores")
    return render(request, "shop/confirm.html", {"listing": listing})


@require_safe
def product_detail(request, pk):
    """Show a public product and its reviews on GET or HEAD.

    pk selects the product or returns HTTP 404. shop/product.html gets
    product, reviews, quantity_form, review_form and an owner flag.
    Displayed controls do not replace the write views' role checks.
    """
    product = get_object_or_404(Product.objects.select_related("store"), pk=pk)
    return render(
        request,
        "shop/product.html",
        {
            "product": product,
            "reviews": product.reviews.select_related("buyer").annotate(
                purchase_verified=Exists(OrderLine.objects.filter(
                    order__buyer_id=OuterRef("buyer_id"),
                    product_id=OuterRef("product_id"),
                ))
            ),
            "quantity_form": QuantityForm(stock=product.stock),
            "review_form": ReviewForm(),
            "owner": request.user.is_authenticated
            and product.store.vendor_id == request.user.pk,
        },
    )


@role_required("Buyers", "shop.add_review")
@require_POST
def review(request, pk):
    """Create or update the logged-in buyer's review using POST.

    pk identifies the product. ReviewForm accepts rating and content,
    never buyer identity or a verified flag. Set a success/error message
    and redirect to product detail. A missing product returns HTTP 404.
    """
    product = get_object_or_404(Product, pk=pk)
    existing = Review.objects.filter(
        buyer=request.user, product=product
    ).first()
    if existing and not request.user.has_perm("shop.change_review"):
        raise PermissionDenied
    form = ReviewForm(request.POST, instance=existing)
    if form.is_valid():
        opinion = form.save(commit=False)
        opinion.buyer, opinion.product = request.user, product
        opinion.save()
        messages.success(request, "Review saved.")
    else:
        messages.error(
            request,
            "Enter a rating from 1 to 5 and a review of at most "
            "3,000 characters.",
        )
    return redirect("product", pk=pk)


@role_required("Buyers")
@require_POST
def cart_add(request, pk):
    """Add a product quantity to the buyer's session cart using POST.

    pk identifies the product and quantity comes from the form. Reject
    invalid or unavailable quantities without changing stock. Set a
    message and redirect to product detail; checkout rechecks stock.
    """
    product = get_object_or_404(Product, pk=pk)
    form = QuantityForm(request.POST, stock=product.stock)
    cart = request.session.get("cart", {})
    if form.is_valid():
        if not cart:
            request.session.pop("checkout_key", None)
        quantity = cart.get(str(pk), 0) + form.cleaned_data["quantity"]
        if quantity <= min(product.stock, 999):
            cart[str(pk)] = quantity
            request.session["cart"] = cart
            messages.success(request, "Added to cart.")
        else:
            messages.error(request, "That quantity is not available.")
    else:
        messages.error(request, "Enter a whole quantity between 1 and 999.")
    return redirect("product", pk=pk)


@role_required("Buyers")
@require_POST
def cart_remove(request, pk):
    """Remove product pk from the buyer's cart using POST.

    Only the session dictionary changes. Redirect to cart detail even
    when that line is already absent; the product itself is untouched.
    """
    cart = request.session.get("cart", {})
    cart.pop(str(pk), None)
    request.session["cart"] = cart
    return redirect("cart")


@role_required("Buyers")
@require_safe
def cart_detail(request):
    """Display the buyer's cart on GET or HEAD.

    Render shop/cart.html with rows, total, checkout_key and missing.
    Each row holds product, quantity and a current-price subtotal.
    missing counts deleted listings; checkout_key binds a purchase to
    this session and supports safe repeated submissions.
    """
    cart = request.session.get("cart", {})
    products = list(
        Product.objects.filter(pk__in=cart).select_related("store")
    )
    valid_ids = {str(product.pk) for product in products}
    missing = len(cart) - len(valid_ids)
    if missing:
        # Reassign the dictionary so session changes are persisted.
        cart = {key: value for key, value in cart.items() if key in valid_ids}
        request.session["cart"] = cart
        messages.info(
            request, "Unavailable products were removed from your cart."
        )
    rows = [
        {
            "product": p,
            "quantity": cart[str(p.pk)],
            "total": p.price * cart[str(p.pk)],
        }
        for p in products
    ]
    if "checkout_key" not in request.session:
        request.session["checkout_key"] = str(uuid4())
    return render(
        request,
        "shop/cart.html",
        {
            "rows": rows,
            "total": sum((row["total"] for row in rows), Decimal("0.00")),
            "checkout_key": request.session["checkout_key"],
            "missing": missing,
        },
    )


@role_required("Buyers")
@require_POST
def checkout_view(request):
    """Place the buyer's order using a session-bound POST.

    Reject a missing or mismatched checkout_key with HTTP 403. Cart
    validation errors redirect to cart without clearing it. Successful
    checkout clears the cart and redirects to invoice with its order ID.
    A mail failure leaves the saved order valid and reports delivery as
    pending, so an email outage does not repeat the purchase.
    """
    key = request.POST.get("checkout_key")
    if not key or key != request.session.get("checkout_key"):
        raise PermissionDenied("Reload the cart before checking out.")
    try:
        order = checkout(request.user, request.session.get("cart", {}), key)
    except ValidationError as error:
        messages.error(request, "; ".join(error.messages))
        return redirect("cart")
    request.session["cart"] = {}
    # Retain the key for retries until the buyer starts a new cart.
    try:
        email_invoice(order)
    except Exception:
        logger.exception("Invoice delivery failed for order %s", order.pk)
        messages.warning(
            request, "Order saved; invoice email is awaiting delivery."
        )
    return redirect("invoice", pk=order.pk)


@role_required("Buyers", "shop.view_order")
@require_safe
def invoice(request, pk):
    """Show the buyer's invoice on GET or HEAD.

    pk selects an order owned by the logged-in buyer. Return
    shop/invoice.html with order; missing and other buyers' orders both
    return HTTP 404 so changing the URL cannot reveal private purchases.
    """
    order = get_object_or_404(Order, pk=pk, buyer=request.user)
    return render(request, "shop/invoice.html", {"order": order})


@require_http_methods(["GET", "POST"])
def reset_request(request):
    """Display the reset form or request a password-reset email.

    GET and invalid POST render shop/form.html with form and title. A
    valid POST creates a short-lived token for an active matching
    account, attempts delivery, then redirects to login. Known, unknown
    and delivery-failure cases share the same public message so the
    endpoint does not disclose which email addresses have accounts.
    """
    form = ResetRequestForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = (
            get_user_model()
            .objects.filter(
                email__iexact=form.cleaned_data["email"], is_active=True
            )
            .first()
        )
        if user:
            secret = create_reset_token(user)
            url = request.build_absolute_uri(reverse("reset", args=[secret]))
            try:
                send_mail(
                    "Password reset",
                    f"Use this link within 15 minutes: {url}",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                )
            except Exception:
                logger.exception("Password reset delivery failed")
        messages.info(
            request, "If the account exists, a reset link has been sent."
        )
        return redirect("login")
    return render(
        request, "shop/form.html", {"form": form, "title": "Reset password"}
    )


@require_http_methods(["GET", "POST"])
def reset_confirm(request, secret):
    """Show or consume the reset secret supplied in the URL.

    GET renders form and title through shop/form.html. An invalid,
    expired or used secret renders shop/message.html with HTTP 400. POST
    validates matching passwords and consumes the token in the reset
    service. Success redirects to login; a validation/race error returns
    the form with errors rather than changing the password.
    """
    token = (
        ResetToken.objects.filter(
            digest=sha256(secret.encode()).hexdigest(),
            used_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .select_related("user")
        .first()
    )
    if not token:
        return render(
            request,
            "shop/message.html",
            {
                "title": "Reset link unavailable",
                "body": "This link is invalid, expired or already used.",
            },
            status=400,
        )
    form = ResetPasswordForm(
        token.user, request.POST if request.method == "POST" else None
    )
    if request.method == "POST" and form.is_valid():
        try:
            reset_password(secret, form.cleaned_data["new_password1"])
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Password changed. Please log in.")
            return redirect("login")
    return render(
        request, "shop/form.html", {"form": form, "title": "Choose a password"}
    )
