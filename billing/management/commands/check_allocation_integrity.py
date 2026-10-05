"""Report any drift between payment allocations and the totals kept beside them.

Read-only. A receipt's `allocated_amount` must equal the sum of its active
(non-reversed) allocations, an invoice's `paid_amount` must equal the sum of the
active allocations against it, and no receipt may be allocated beyond its
amount. Since 2.40.0 also: a receipt and an invoice joined by an allocation
belong to one customer, no active allocation sits on a receipt that is not
confirmed or on a cancelled invoice, no invoice is paid beyond its total, and
an instalment plan never records more paid than its invoice. There is no
repair mode. Exit status 1 when anything disagrees, so it can run from cron or a
release checklist.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import models
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

        # 2.40.0: the relations behind those totals.
        crossed = active.exclude(payment__customer_id=models.F("invoice__customer_id")).select_related("payment", "invoice")
        for allocation in crossed:
            problems.append(
                f"allocation {allocation.pk}: receipt {allocation.payment.number} and invoice "
                f"{allocation.invoice.number} belong to different customers"
            )
        for allocation in active.exclude(payment__status=Payment.Status.CONFIRMED).select_related("payment"):
            problems.append(f"allocation {allocation.pk}: still active on receipt {allocation.payment.number} that is {allocation.payment.status}")
        for allocation in active.filter(invoice__status=Invoice.Status.CANCELLED).select_related("invoice"):
            problems.append(f"allocation {allocation.pk}: still active on cancelled invoice {allocation.invoice.number}")
        for invoice in Invoice.objects.filter(paid_amount__gt=models.F("total_amount")):
            problems.append(f"invoice {invoice.number}: paid_amount {invoice.paid_amount} exceeds total {invoice.total_amount}")
        from billing.models import InstallmentPlan

        for plan in InstallmentPlan.objects.select_related("invoice").annotate(paid=Sum("installments__paid_amount")):
            if (plan.paid or zero) > plan.invoice.paid_amount:
                problems.append(
                    f"invoice {plan.invoice.number}: instalments record {plan.paid} paid, more than the invoice's {plan.invoice.paid_amount}"
                )

        for problem in problems:
            self.stdout.write(problem)
        if problems:
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("allocations agree with receipt and invoice totals"))
