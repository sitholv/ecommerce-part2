"""Register the commerce application and initialize role permissions."""

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def configure_roles(sender, **kwargs):
    """Create role groups after model permissions exist."""
    from django.contrib.auth.management import create_permissions
    from django.contrib.auth.models import Group, Permission

    create_permissions(
        sender, verbosity=0, using=kwargs.get("using", "default")
    )

    buyers, _ = Group.objects.get_or_create(name="Buyers")
    vendors, _ = Group.objects.get_or_create(name="Vendors")
    permissions = Permission.objects.filter(content_type__app_label="shop")
    buyers.permissions.set(
        permissions.filter(
            codename__in=[
                "view_store",
                "view_product",
                "add_review",
                "change_review",
                "view_order",
                "view_orderline",
            ]
        )
    )
    vendors.permissions.set(
        permissions.filter(
            codename__in=[
                "add_store",
                "view_store",
                "change_store",
                "delete_store",
                "add_product",
                "view_product",
                "change_product",
                "delete_product",
                "view_review",
            ]
        )
    )


class ShopConfig(AppConfig):
    """Use explicit app initialization rather than import-time SQL."""

    name = "shop"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        """Register permission setup after migrations."""
        post_migrate.connect(
            configure_roles,
            sender=self,
            dispatch_uid="marketplace.configure_roles",
        )
