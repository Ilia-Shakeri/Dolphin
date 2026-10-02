"""Report any drift between payment allocations and the totals kept beside them.

Read-only. A receipt's `allocated_amount` must equal the sum of its active
(non-reversed) allocations, an invoice's `paid_amount` must equal the sum of the
active allocations against it, and no receipt may be allocated beyond its
amount. Exit status 1 when anything disagrees, so it can run from cron or a
release checklist.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from billing.models import Invoice, Payment, PaymentAllocation


class Command(BaseCommand):
    help = "Check that payment allocations agree with receipt and invoice totals (read-only)."

    def handle(self, *args, **options):
        zero = Decimal("0.00")
        active = PaymentAllocation.objects.filter(is_reversed=False)
        problems = []

        by_payment = {row["payment"]: row["total"] for row in active.values("payment").annotate(total=Sum("amount"))}
        for payment in Payment.objects.filter(direction=Payment.Direction.RECEIPT):
            expected = by_payment.get(payment.pk, zero)
            if payment.allocated_amount != expected:
                problems.append(f"receipt {payment.number}: allocated_amount {payment.allocated_amount} but allocations sum to {expected}")
            if payment.allocated_amount > payment.amount:
                problems.append(f"receipt {payment.number}: allocated {payment.allocated_amount} exceeds amount {payment.amount}")

        by_invoice = {row["invoice"]: row["total"] for row in active.values("invoice").annotate(total=Sum("amount"))}
        for invoice in Invoice.objects.exclude(status=Invoice.Status.DRAFT):
            expected = by_invoice.get(invoice.pk, zero)
            if invoice.paid_amount != expected:
                problems.append(f"invoice {invoice.number}: paid_amount {invoice.paid_amount} but allocations sum to {expected}")

        for problem in problems:
            self.stdout.write(problem)
        if problems:
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("allocations agree with receipt and invoice totals"))
