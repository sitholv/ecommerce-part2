"""Validated registration, listing, review and reset input schemas."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, SetPasswordForm
from django.contrib.auth.models import Group
from django.db import transaction

from .models import Product, Review, Store


class RegistrationForm(UserCreationForm):
    """Collect a username, unique email, role and matching passwords.

    Django's UserCreationForm handles password validation and hashing.
    Only Buyers and Vendors are offered. clean_email normalises the
    address and rejects case-insensitive duplicates for reset safety.
    The default Django widgets are labelled by the shared form template.
    """

    email = forms.EmailField()
    role = forms.ChoiceField(
        choices=[("Buyers", "Buyer"), ("Vendors", "Vendor")]
    )

    class Meta:
        model = get_user_model()
        fields = ["username", "email", "role", "password1", "password2"]

    def clean_email(self):
        """Reject duplicate reset destinations."""
        email = self.cleaned_data["email"].strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email is already registered.")
        return email

    @transaction.atomic
    def save(self, commit=True):
        """Persist the account and selected role in one transaction."""
        user = super().save(commit=commit)
        if commit:
            user.groups.add(Group.objects.get(name=self.cleaned_data["role"]))
        return user


class StoreForm(forms.ModelForm):
    """Edit a store's name and optional description.

    The field allowlist deliberately excludes vendor. The view supplies
    the owner from the authenticated session, so a hidden or forged form
    field cannot transfer a store to another account.
    """

    class Meta:
        model = Store
        fields = ["name", "description"]


class ProductForm(forms.ModelForm):
    """Edit product name, description, decimal price and stock.

    Model validators supply the field bounds. store is deliberately
    absent: the view selects an owner-checked parent store from the URL.
    Django's generated widgets and errors use the shared form template.
    """

    class Meta:
        model = Product
        fields = ["name", "description", "price", "stock"]


class ReviewForm(forms.ModelForm):
    """Collect a one-to-five rating and review text.

    buyer, product and purchase verification are not editable fields.
    The view assigns identity and the model derives verified status from
    saved order lines rather than trusting submitted data.
    """

    class Meta:
        model = Review
        fields = ["rating", "content"]


class QuantityForm(forms.Form):
    """Accept a whole quantity from 1 to 999, initially 1.

    The stock argument sets the field and widget maximum. The view
    checks accumulated quantity and checkout checks availability before
    reducing inventory, since stock may change between requests.
    """

    quantity = forms.IntegerField(min_value=1, max_value=999, initial=1)

    def __init__(self, *args, stock=999, **kwargs):
        """Bound browser hints and validation by the current stock."""
        super().__init__(*args, **kwargs)
        maximum = min(stock, 999)
        self.fields["quantity"] = forms.IntegerField(
            min_value=1, max_value=maximum, initial=1,
            widget=forms.NumberInput(attrs={"min": 1, "max": maximum}),
        )


class ResetRequestForm(forms.Form):
    """Validate a reset email without exposing accounts."""

    email = forms.EmailField()


class ResetPasswordForm(SetPasswordForm):
    """Validate two matching replacement passwords for a specific user.

    The inherited SetPasswordForm applies Django's configured password
    validators. The view passes its cleaned password to the reset
    service, which consumes the URL token and saves the password.
    """
