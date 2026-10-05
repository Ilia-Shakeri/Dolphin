"""Link an older order to the invoice it was converted into (2.40.0).

Before 2.37.0 an order was converted into an invoice and the link lived on the
invoice (`Invoice.order`). A supply request is an order carrying `invoice`.
This command copies the old link onto the order (`Order.invoice`) so the
«one active request per invoice» rule and the double-deduction guards see it.

Idempotent and expand-only: an order that already names an invoice is left
alone, as is an invoice that already has an active request. `--dry-run` (the
default) reports without writing; `--apply` writes.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from billing.models import Invoice, Order


class Command(BaseCommand):
    help = "Copy legacy Invoice.order links onto Order.invoice (dry run unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="write the links (default: report only)")

    def handle(self, *args, apply=False, **options):
        linked = skipped = 0
        candidates = Invoice.objects.filter(order__isnull=False).select_related("order").order_by("pk")
        with transaction.atomic():
            for invoice in candidates:
                order = invoice.order
                if order.invoice_id is not None:
                    skipped += 1
                    continue
                if Order.objects.filter(invoice=invoice).exclude(status=Order.Status.CANCELLED).exists():
                    skipped += 1
                    self.stdout.write(f"skip {order.number}: invoice {invoice.number} already has an active request")
                    continue
                if order.status == Order.Status.CANCELLED:
                    skipped += 1
                    continue
                linked += 1
                self.stdout.write(f"{'link' if apply else 'would link'} {order.number} -> {invoice.number}")
                if apply:
                    Order.objects.filter(pk=order.pk, invoice__isnull=True).update(invoice=invoice)
        self.stdout.write(f"{'linked' if apply else 'to link'}: {linked}, skipped: {skipped}")
