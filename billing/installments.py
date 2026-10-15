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
from decimal import ROUND_DOWN, Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from auditlog.services import log_activity
from billing.models import Installment, InstallmentPlan, InstallmentReschedule, Invoice
from billing.money import clean_money, quantize_money
from common.deployment.profile import feature_enabled
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
    # A rescheduled plan is no longer the invoice's terms split evenly, so
    # editing those terms would throw the agreed schedule away (2.40.51); a
    # plan with charges keeps the rows they were worked out on (2.40.52).
    return (
        plan.status != InstallmentPlan.Status.CANCELLED
        and plan.interest_amount == 0
        and plan.extra_discount_percent == 0
        and plan.total_amount == invoice.total_amount
        and not plan.reschedules.exists()
        and not plan.charges.exists()
    )


_UNSET = object()


def _clean_profit_rate(value):
    """An invoice's own annual interest rate (2.40.52): `None` takes the
    company's default; otherwise 0–100 with two decimals."""
    if value is None:
        return None
    try:
        rate = Decimal(str(value))
    except (ArithmeticError, ValueError):
        raise BusinessRuleError({"profit_rate": "نرخ سود را به‌صورت عدد وارد کنید."}) from None
    if not rate.is_finite() or rate < 0 or rate > 100:
        raise BusinessRuleError({"profit_rate": "نرخ سالانهٔ سود باید بین ۰ تا ۱۰۰ درصد باشد."})
    return rate.quantize(Decimal("0.01"))


@transaction.atomic
def set_invoice_installments(*, actor, invoice, installment_count=None, down_payment=None, profit_rate=_UNSET):
    """Change the count and/or the down payment; every amount is recomputed.
    A draft may also take its own annual interest rate (2.40.52, feature
    `installment_interest`); an issued invoice's interest was fixed at issue."""
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
    fields = ["installment_down_payment", "installment_count", "updated_at"]
    if profit_rate is not _UNSET:
        if not feature_enabled("installment_interest"):
            raise BusinessConflictError({"profit_rate": "سود اقساط در این استقرار فعال نیست."})
        if locked_invoice.status != Invoice.Status.DRAFT:
            raise BusinessConflictError({"profit_rate": "سود فاکتور صادرشده هنگام صدور تعیین شده و تغییر نمی‌کند."})
        locked_invoice.installment_profit_rate = _clean_profit_rate(profit_rate)
        fields.append("installment_profit_rate")
    locked_invoice.save(update_fields=fields)
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


RESCHEDULE_FEATURE = "installment_reschedule"
RESCHEDULE_REASON_MAX_LENGTH = 500


def _row_state(row):
    return {
        "sequence": row.sequence, "due_date": row.due_date.isoformat(), "amount": str(row.amount),
        "paid_amount": str(row.paid_amount), "status": row.status,
    }


def _open_amount(rows):
    return quantize_money(sum((row.amount - row.paid_amount for row in rows), Decimal("0.00")))


def reschedule_preview_rows(*, remaining, installment_count, first_due, interval_days, first_sequence):
    """The new rows: the unpaid amount in equal parts of whole rials, the
    remainder on the first (owner decision 2026-10-14: amounts the advanced
    instalment features make are whole rials)."""
    base = (remaining / installment_count).quantize(Decimal("1"), rounding=ROUND_DOWN)
    first = quantize_money(remaining - base * (installment_count - 1))
    return [
        (first_sequence + index, first_due + timedelta(days=interval_days * index), first if index == 0 else base)
        for index in range(installment_count)
    ]


def _clean_reschedule_terms(*, remaining, installment_count, first_due, interval_days, reason, today):
    if isinstance(installment_count, bool) or not isinstance(installment_count, int) or not 1 <= installment_count <= 120:
        raise BusinessRuleError({"installment_count": "تعداد اقساط باید بین ۱ تا ۱۲۰ باشد."})
    if isinstance(interval_days, bool) or not isinstance(interval_days, int) or not 1 <= interval_days <= 365:
        raise BusinessRuleError({"interval_days": "فاصلهٔ اقساط باید بین ۱ تا ۳۶۵ روز باشد."})
    if not isinstance(first_due, datetime.date):
        raise BusinessRuleError({"first_due": "تاریخ نخستین قسط را وارد کنید."})
    if first_due < today:
        raise BusinessRuleError({"first_due": "نخستین قسط برنامهٔ تازه نمی‌تواند پیش از امروز باشد."})
    if remaining / installment_count < 1:
        raise BusinessRuleError({"installment_count": "تعداد اقساط برای این مبلغ زیاد است؛ هر قسط باید دست‌کم یک ریال باشد."})
    reason = " ".join(str(reason or "").split())
    if not reason:
        raise BusinessRuleError({"reason": "دلیل تغییر برنامه را بنویسید."})
    if len(reason) > RESCHEDULE_REASON_MAX_LENGTH:
        raise BusinessRuleError({"reason": f"دلیل نباید بیش از {RESCHEDULE_REASON_MAX_LENGTH} نویسه باشد."})
    return reason


@transaction.atomic
def reschedule_plan(*, actor, invoice, installment_count, first_due, interval_days, reason="", preview=False):
    """Change or extend what is left of an active plan (2.40.51, feature
    `installment_reschedule`, owner decision 2026-10-14).

    «قسط‌های پرداخت‌شده دست نمی‌خورند، هیچ ردیفی حذف نمی‌شود و تاریخچه کامل
    می‌ماند»: a paid row is left exactly as it is; a part-paid row keeps what
    was paid and is closed at that amount; an unpaid row is closed (`cancelled`,
    which lists already leave out for an active plan). What was still owed is
    spread over `installment_count` new rows from `first_due`, `interval_days`
    apart, numbered after every existing row — so the plan still sums to the
    invoice total and the allocation waterfall, which fills rows by sequence,
    needs nothing re-applied. Both sides are kept in an `InstallmentReschedule`.

    With `preview=True` nothing is written and the new rows come back.
    """
    from billing.payments import _lock_payment_manager

    if not feature_enabled(RESCHEDULE_FEATURE):
        raise BusinessConflictError({"invoice": "تغییر برنامهٔ اقساط در این استقرار فعال نیست."})
    actor = _lock_payment_manager(actor)
    locked_invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if locked_invoice.status != Invoice.Status.ISSUED:
        raise BusinessConflictError({"invoice": "فقط برنامهٔ اقساط فاکتور صادرشده قابل تغییر است."})
    plan = InstallmentPlan.objects.select_for_update().filter(invoice=locked_invoice).first()
    if plan is None or plan.status != InstallmentPlan.Status.ACTIVE:
        raise BusinessConflictError({"invoice": "این فاکتور برنامهٔ اقساط فعالی ندارد."})
    live = list(plan.installments.select_for_update().exclude(status=Installment.Status.CANCELLED).order_by("sequence"))
    open_rows = [row for row in live if row.paid_amount < row.amount]
    remaining = _open_amount(open_rows)
    if remaining <= 0:
        raise BusinessConflictError({"invoice": "همهٔ اقساط این برنامه پرداخت شده است."})
    reason = _clean_reschedule_terms(
        remaining=remaining, installment_count=installment_count, first_due=first_due,
        interval_days=interval_days, reason=reason if not preview else (reason or "پیش‌نمایش"),
        today=timezone.localdate(),
    )
    first_sequence = max(row.sequence for row in plan.installments.all()) + 1
    new_rows = reschedule_preview_rows(
        remaining=remaining, installment_count=installment_count, first_due=first_due,
        interval_days=interval_days, first_sequence=first_sequence,
    )
    if preview:
        return {"remaining_amount": remaining, "rows": new_rows}

    before = [_row_state(row) for row in live]
    for row in open_rows:
        if row.paid_amount > 0:
            row.amount = row.paid_amount
            row.status = Installment.Status.PAID
        else:
            row.status = Installment.Status.CANCELLED
        row.save(update_fields=["amount", "status", "updated_at"])
    Installment.objects.bulk_create([
        Installment(plan=plan, sequence=sequence, due_date=due, amount=amount) for sequence, due, amount in new_rows
    ])
    # Interest still open on the closed rows moves to the new ones; no new
    # interest is charged for the change (2.40.52).
    from billing.installment_charges import move_open_interest

    created = list(plan.installments.filter(sequence__gte=first_sequence).order_by("sequence"))
    move_open_interest(closed_rows=open_rows, new_rows=created)
    after = [
        _row_state(row)
        for row in plan.installments.exclude(status=Installment.Status.CANCELLED).order_by("sequence")
    ]
    InstallmentReschedule.objects.create(
        plan=plan, actor=actor, reason=reason, remaining_amount=remaining, installment_count=installment_count,
        first_due=first_due, interval_days=interval_days, before=before, after=after,
    )
    log_activity(
        actor=actor, operation="installment_plan.rescheduled", instance=plan,
        changes={
            "invoice": locked_invoice.pk, "installment_count": installment_count, "amount": str(remaining),
            "reason_provided": True, "fields": ["first_due", "interval_days"],
        },
    )
    return {"remaining_amount": remaining, "rows": new_rows}


def reschedule_history(plan):
    return [
        {
            "id": item.pk, "at": item.created_at, "actor_display": item.actor.get_full_name() or item.actor.username,
            "reason": item.reason, "remaining_amount": item.remaining_amount,
            "installment_count": item.installment_count, "first_due": item.first_due,
            "interval_days": item.interval_days,
        }
        for item in plan.reschedules.select_related("actor").order_by("-created_at", "-id")
    ]


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
    reschedulable = False
    history = []
    from billing.installment_charges import INTEREST, LATE_FEES, interest_preview, plan_charges

    charges = []
    if plan is not None and (feature_enabled(INTEREST) or feature_enabled(LATE_FEES) or plan.charges.exists()):
        charges = plan_charges(plan)
    preview = None
    if (
        plan is None
        and invoice.status == Invoice.Status.DRAFT
        and invoice.payment_type == Invoice.PaymentType.INSTALLMENT
        and invoice.installment_count
        and invoice.total_amount > 0
        and invoice.installment_down_payment < invoice.total_amount
    ):
        draft_rows = schedule_rows(
            total_amount=invoice.total_amount, down_payment=invoice.installment_down_payment,
            installment_count=invoice.installment_count,
            first_due=invoice.installment_first_due or timezone.localdate(),
            interval_days=invoice.installment_interval_days or 30, down_due=timezone.localdate(),
        )
        preview = interest_preview(invoice, [(sequence, amount) for sequence, _, amount in draft_rows])
    reminders = {}
    if plan is not None and feature_enabled("installment_reminders"):
        from billing.installment_reminders import reminders_for_rows

        reminders = reminders_for_rows(plan.installments.values_list("pk", flat=True))
    if plan is not None:
        editable = invoice.status == Invoice.Status.ISSUED and _is_editable_plan(plan, invoice)
        reschedulable = (
            feature_enabled(RESCHEDULE_FEATURE)
            and invoice.status == Invoice.Status.ISSUED
            and plan.status == InstallmentPlan.Status.ACTIVE
        )
        if feature_enabled(RESCHEDULE_FEATURE):
            history = reschedule_history(plan)
        for row in visible_installments(plan.installments.all()).order_by("sequence"):
            key = display_status(
                invoice_status=invoice.status, status=row.status, due_date=row.due_date,
                paid_amount=row.paid_amount,
            )
            rows.append({
                "id": row.pk, "sequence": row.sequence, "is_down_payment": row.sequence == 0,
                "due_date": row.due_date, "amount": row.amount, "paid_amount": row.paid_amount,
                "balance_due": row.balance_due, "status": key, "status_display": DISPLAY_LABELS[key],
                # The reminder SMS sent for this row (2.40.51), oldest first.
                "reminders": reminders.get(row.pk, []),
            })
    return {
        "payment_type": invoice.payment_type,
        "down_payment": invoice.installment_down_payment,
        "installment_count": invoice.installment_count,
        "first_due": invoice.installment_first_due,
        "interval_days": invoice.installment_interval_days,
        "editable": editable and invoice.payment_type == Invoice.PaymentType.INSTALLMENT,
        "rows": rows,
        # 2.40.51: whether the remaining schedule may be changed or extended
        # (the feature, an issued invoice, an active plan; the payments-manager
        # check is the service's), and every earlier change.
        "reschedulable": reschedulable and any(row["balance_due"] > 0 for row in rows),
        "interval_days_current": plan.interval_days if plan is not None else None,
        "reschedules": history,
        # 2.40.52: interest and late fees, each its own debit; and for a draft,
        # the interest issuing it will charge (`None` without the feature).
        "charges": charges,
        "can_set_profit_rate": feature_enabled(INTEREST) and invoice.status == Invoice.Status.DRAFT,
        "profit_rate": invoice.installment_profit_rate,
        "interest_preview": preview,
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
