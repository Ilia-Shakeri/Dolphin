"""Instalment terms on an invoice: the schedule, its edit, and row status.

An invoice's payment type is either cash or instalments. An instalment
invoice carries its terms (down payment, count, first due date, interval) on
the invoice itself while it is a draft; issuing it builds the schedule as an
`InstallmentPlan`. The down payment is row 0 of that plan (omitted when zero)
and the remainder is split into rows 1..count, so the allocation waterfall in
`billing.payments._apply_to_installments` already pays the down payment first.
The Instalments list is read-only: rows change only through this module, an
allocation, or an invoice cancellation.
"""

import datetime
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from auditlog.services import log_activity
from billing.models import Installment, InstallmentPlan, Invoice
from billing.money import clean_money, quantize_money
from common.exceptions import BusinessConflictError, BusinessRuleError

#: Days before the due date at which an unpaid row is flagged «نزدیک سررسید».
NEAR_DUE_DAYS = 2

DISPLAY_LABELS = {
    "paid": "پرداخت شده",
    "cancelled": "لغو شده",
    "partially_paid": "پرداخت ناقص",
    "near_due": "نزدیک سررسید",
    "due_today": "سررسید امروز",
    "overdue": "سررسید رد شده",
    "pending": "در انتظار پرداخت",
}


def clean_terms(*, total_amount, down_payment, installment_count, first_due, interval_days):
    """Validate instalment terms against an invoice total; return clean values."""
    if isinstance(installment_count, bool) or not isinstance(installment_count, int):
        raise BusinessRuleError({"installment_count": "تعداد اقساط را به‌صورت عدد صحیح وارد کنید."})
    if not 1 <= installment_count <= 120:
        raise BusinessRuleError({"installment_count": "تعداد اقساط باید بین ۱ تا ۱۲۰ باشد."})
    if isinstance(interval_days, bool) or not isinstance(interval_days, int) or not 1 <= interval_days <= 365:
        raise BusinessRuleError({"installment_interval_days": "فاصلهٔ اقساط باید بین ۱ تا ۳۶۵ روز باشد."})
    if not isinstance(first_due, datetime.date):
        raise BusinessRuleError({"installment_first_due": "تاریخ نخستین قسط را وارد کنید."})
    down = clean_money(
        down_payment if down_payment is not None else 0, field="installment_down_payment", allow_zero=True
    )
    if total_amount <= 0:
        raise BusinessRuleError({"payment_type": "فاکتور بدون مبلغ قابل قسط‌بندی نیست."})
    if down >= total_amount:
        raise BusinessRuleError({"installment_down_payment": "پیش‌پرداخت باید کمتر از مبلغ فاکتور باشد."})
    if quantize_money(total_amount - down) / installment_count < Decimal("0.01"):
        raise BusinessRuleError({"installment_count": "تعداد اقساط برای این مبلغ زیاد است؛ هر قسط باید بیشتر از صفر باشد."})
    return down, installment_count, first_due, interval_days


def schedule_rows(*, total_amount, down_payment, installment_count, first_due, interval_days, down_due):
    """Rows as (sequence, due_date, amount): down payment first, then equal parts.

    The rounding remainder goes on the first instalment, so the rows always sum
    to the invoice total.
    """
    rows = []
    if down_payment > 0:
        rows.append((0, down_due, quantize_money(down_payment)))
    remainder = quantize_money(total_amount - down_payment)
    base = quantize_money(remainder / installment_count)
    first = quantize_money(remainder - base * (installment_count - 1))
    for index in range(installment_count):
        rows.append((index + 1, first_due + timedelta(days=interval_days * index), first if index == 0 else base))
    return rows


def _replace_rows(plan, *, invoice, down, count, first_due, interval_days, down_due):
    """Make the plan's rows the schedule for these terms — without deleting one.

    The application's database role has no DELETE on `billing_installment`
    (`scripts/bootstrap-postgres.sh`: money is corrected, never erased), so
    the PostgreSQL deployment refused the old delete-and-recreate with a
    `ProgrammingError` — every instalment invoice failed to issue (2.40.17).
    Each row of the schedule now updates the row of the same sequence (paid
    amount back to zero; the caller re-applies what was paid), a missing one
    is created, and a row the new schedule no longer has is cancelled. A
    cancelled row of an active plan is superseded: lists and the plan's own
    payload leave it out (`visible_installments`).
    """
    wanted = {
        sequence: (due, amount)
        for sequence, due, amount in schedule_rows(
            total_amount=invoice.total_amount, down_payment=down, installment_count=count,
            first_due=first_due, interval_days=interval_days, down_due=down_due,
        )
    }
    existing = {row.sequence: row for row in plan.installments.select_for_update()}
    for sequence, row in existing.items():
        if sequence in wanted:
            row.due_date, row.amount = wanted[sequence]
            row.paid_amount = Decimal("0.00")
            row.status = Installment.Status.PENDING
        else:
            row.paid_amount = Decimal("0.00")
            row.status = Installment.Status.CANCELLED
        row.save(update_fields=["due_date", "amount", "paid_amount", "status", "updated_at"])
    Installment.objects.bulk_create([
        Installment(plan=plan, sequence=sequence, due_date=due, amount=amount)
        for sequence, (due, amount) in sorted(wanted.items())
        if sequence not in existing
    ])


def visible_installments(queryset):
    """Rows a reader should see: everything, except rows an active plan
    superseded when its terms changed (`_replace_rows`). A cancelled plan
    keeps showing all its rows, cancelled — that is what happened to them."""
    return queryset.exclude(
        status=Installment.Status.CANCELLED, plan__status=InstallmentPlan.Status.ACTIVE
    )


def build_plan_at_issue(*, actor, invoice, issued_on):
    """Called by `issue_invoice` for an instalment invoice, inside its transaction."""
    if invoice.payment_type != Invoice.PaymentType.INSTALLMENT:
        return None
    down, count, first_due, interval = clean_terms(
        total_amount=invoice.total_amount, down_payment=invoice.installment_down_payment,
        installment_count=invoice.installment_count, first_due=invoice.installment_first_due,
        interval_days=invoice.installment_interval_days,
    )
    plan = InstallmentPlan.objects.create(
        invoice=invoice,
        total_amount=invoice.total_amount,
        principal_amount=invoice.total_amount,
        interest_amount=Decimal("0.00"),
        down_payment_amount=down,
        installment_count=count,
        interval_days=interval,
        start_date=first_due,
        created_by=actor,
    )
    _replace_rows(plan, invoice=invoice, down=down, count=count, first_due=first_due,
                  interval_days=interval, down_due=issued_on)
    return plan


@transaction.atomic
def cancel_plan_with_invoice(invoice):
    """An invoice cancellation cancels every row, paid or not."""
    plan = InstallmentPlan.objects.select_for_update().filter(invoice=invoice).first()
    if plan is None:
        return
    plan.installments.update(status=Installment.Status.CANCELLED)
    if plan.status != InstallmentPlan.Status.CANCELLED:
        plan.status = InstallmentPlan.Status.CANCELLED
        plan.save(update_fields=["status", "updated_at"])


def _is_editable_plan(plan, invoice):
    return (
        plan.status != InstallmentPlan.Status.CANCELLED
        and plan.interest_amount == 0
        and plan.extra_discount_percent == 0
        and plan.total_amount == invoice.total_amount
    )


@transaction.atomic
def set_invoice_installments(*, actor, invoice, installment_count=None, down_payment=None):
    """Change the count and/or the down payment; every amount is recomputed."""
    from billing.payments import _apply_to_installments, _lock_payment_manager
    from billing.services import _lock_document_writer

    locked_invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if locked_invoice.status == Invoice.Status.DRAFT:
        actor = _lock_document_writer(actor)
    else:
        actor = _lock_payment_manager(actor)
    if locked_invoice.payment_type != Invoice.PaymentType.INSTALLMENT:
        raise BusinessConflictError({"payment_type": "این فاکتور نقدی است."})
    if locked_invoice.status == Invoice.Status.CANCELLED:
        raise BusinessConflictError({"status": "فاکتور لغوشده قابل ویرایش نیست."})
    plan = None
    if locked_invoice.status == Invoice.Status.ISSUED:
        plan = InstallmentPlan.objects.select_for_update().filter(invoice=locked_invoice).first()
        if plan is None or not _is_editable_plan(plan, locked_invoice):
            raise BusinessConflictError({
                "invoice": "طرح اقساط این فاکتور با شرایط قدیمی ساخته شده و از این‌جا قابل ویرایش نیست."
            })
    count = locked_invoice.installment_count if installment_count is None else installment_count
    down_raw = locked_invoice.installment_down_payment if down_payment is None else down_payment
    down, count, first_due, interval = clean_terms(
        total_amount=locked_invoice.total_amount, down_payment=down_raw, installment_count=count,
        first_due=locked_invoice.installment_first_due, interval_days=locked_invoice.installment_interval_days,
    )
    locked_invoice.installment_down_payment = down
    locked_invoice.installment_count = count
    locked_invoice.save(update_fields=["installment_down_payment", "installment_count", "updated_at"])
    if plan is not None:
        down_row = plan.installments.filter(sequence=0).first()
        down_due = down_row.due_date if down_row else timezone.localdate(locked_invoice.issued_at)
        plan.down_payment_amount = down
        plan.installment_count = count
        plan.status = InstallmentPlan.Status.ACTIVE
        plan.save(update_fields=["down_payment_amount", "installment_count", "status", "updated_at"])
        _replace_rows(plan, invoice=locked_invoice, down=down, count=count, first_due=first_due,
                      interval_days=interval, down_due=down_due)
        if locked_invoice.paid_amount > 0:
            _apply_to_installments(invoice=locked_invoice, amount=locked_invoice.paid_amount)
    log_activity(
        actor=actor, operation="invoice.installments_changed", instance=locked_invoice,
        changes={"installment_count": count, "installment_down_payment": str(down)},
    )
    return locked_invoice


def display_status(*, invoice_status, status, due_date, paid_amount, today=None):
    """The status the Instalments list shows, worked out from the row itself."""
    today = today or timezone.localdate()
    if invoice_status == Invoice.Status.CANCELLED or status == Installment.Status.CANCELLED:
        return "cancelled"
    if status == Installment.Status.PAID:
        return "paid"
    if paid_amount > 0:
        return "partially_paid"
    days = (due_date - today).days
    if days < 0:
        return "overdue"
    if days == 0:
        return "due_today"
    if days <= NEAR_DUE_DAYS:
        return "near_due"
    return "pending"


def invoice_summary(invoice):
    """Terms and rows for the «اقساط» box on the invoice detail."""
    plan = InstallmentPlan.objects.filter(invoice=invoice).first()
    rows = []
    editable = invoice.status == Invoice.Status.DRAFT
    if plan is not None:
        editable = invoice.status == Invoice.Status.ISSUED and _is_editable_plan(plan, invoice)
        for row in visible_installments(plan.installments.all()).order_by("sequence"):
            key = display_status(
                invoice_status=invoice.status, status=row.status, due_date=row.due_date,
                paid_amount=row.paid_amount,
            )
            rows.append({
                "id": row.pk, "sequence": row.sequence, "is_down_payment": row.sequence == 0,
                "due_date": row.due_date, "amount": row.amount, "paid_amount": row.paid_amount,
                "balance_due": row.balance_due, "status": key, "status_display": DISPLAY_LABELS[key],
            })
    return {
        "payment_type": invoice.payment_type,
        "down_payment": invoice.installment_down_payment,
        "installment_count": invoice.installment_count,
        "first_due": invoice.installment_first_due,
        "interval_days": invoice.installment_interval_days,
        "editable": editable and invoice.payment_type == Invoice.PaymentType.INSTALLMENT,
        "rows": rows,
    }


def display_status_q(key, today=None):
    """The queryset counterpart of `display_status`, for the list filter."""
    today = today or timezone.localdate()
    cancelled = Q(status=Installment.Status.CANCELLED) | Q(plan__invoice__status=Invoice.Status.CANCELLED)
    if key == "cancelled":
        return cancelled
    live = ~cancelled
    if key == "paid":
        return live & Q(status=Installment.Status.PAID)
    if key == "partially_paid":
        return live & ~Q(status=Installment.Status.PAID) & Q(paid_amount__gt=0)
    unpaid = live & ~Q(status=Installment.Status.PAID) & Q(paid_amount__lte=0)
    if key == "overdue":
        return unpaid & Q(due_date__lt=today)
    if key == "due_today":
        return unpaid & Q(due_date=today)
    if key == "near_due":
        return unpaid & Q(due_date__gt=today, due_date__lte=today + timedelta(days=NEAR_DUE_DAYS))
    return unpaid & Q(due_date__gt=today + timedelta(days=NEAR_DUE_DAYS))
