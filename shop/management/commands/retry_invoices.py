"""Retry invoices without recorded delivery."""

from django.core.management.base import BaseCommand, CommandError

from shop.models import Order
from shop.services import email_invoice


class Command(BaseCommand):
    """Retry invoice delivery after a mail outage."""

    help = "Retry invoice emails that are still awaiting delivery."

    def handle(self, *args, **options):
        """Report failures without changing purchase records."""
        failures = 0
        for order in Order.objects.filter(email_sent=False).select_related(
            "buyer"
        ):
            try:
                email_invoice(order)
                self.stdout.write(
                    f"Invoice {order.pk}: sent to configured backend"
                )
            except Exception as error:
                failures += 1
                self.stderr.write(f"Invoice {order.pk}: {error}")
        if failures:
            raise CommandError(
                f"{failures} invoice deliveries remain pending."
            )
