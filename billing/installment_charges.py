"""Interest and late fees on instalments (2.40.52, owner decision 2026-10-14, Q15).

Two manifest features, both off by default, set per company in Settings →
اقساط (`billing.installment_settings`):

* `installment_interest` — «سود ساده یا کاهنده، با نرخ پیش‌فرض قابل تنظیم».
  Worked out once, when an instalment invoice is issued, at the invoice's own
  annual rate or the company's default:
  - **simple (ساده)** — interest on the whole principal for the whole term:
    `principal × rate% × months / 1200`, spread evenly over the rows, the
    remainder on the first;
  - **reducing (کاهنده)** — each row's interest is the period's rate on the
    principal still owed before that row (the rows keep their equal
    principal), so later instalments are smaller. Its total is the
    `principal × rate% × (n + 1) / 2400` the older plan API
    (`billing.money.installment_plan_amounts`) charges for monthly rows.
  One interval is `interval_days` of a 360-day year (a month is 30 days), so a
  monthly row carries a twelfth of the annual rate.
* `installment_late_fees` — once a row is more than `late_fee_grace_days`
  past due and still unpaid, one fee: a percent of what is left on the row
  (its principal and open interest) or a fixed amount, at most `late_fee_cap`.
  Posted by `manage.py post_installment_late_fees` from cron, never for a row
  due before the day a fee was first configured (`late_fee_since`).

The owner's defaults, confirmed 2026-10-14: **a charge is a debit of its own in
the customer ledger, never added to the invoice or to the instalment, and every
amount is whole rials.** A charge is settled from a receipt
(`settle_charges`), a late fee may be waived with a reason (a credit), and
cancelling the invoice cancels what is still open (a credit). Rescheduling a
plan moves the interest still open to the new rows; it adds none.
"""

from datetime import timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from auditlog.services import log_activity
from billing.ledger import append_ledger_entry
from billing.models import (
    ChargeSettlement,
    CustomerLedgerEntry,
    Installment,
    InstallmentCharge,
    InstallmentPlan,
    InstallmentSettings,
    Invoice,
    Payment,
)
from billing.money import clean_money, quantize_money
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessConflictError, BusinessRuleError

INTEREST = "installment_interest"
LATE_FEES = "installment_late_fees"
WHOLE = Decimal("1")
ZERO = Decimal("0.00")
#: Most rows one late-fee run charges.
LATE_FEE_BATCH = 500
RELEASE_REASON_MAX_LENGTH = 500


def whole_rials(value):
    return Decimal(value).quantize(WHOLE, rounding=ROUND_HALF_UP)


def interest_shares(*, method, annual_rate, principals, interval_days):
    """Interest per row, whole rials, for rows with these principals in order."""
    count = len(principals)
    rate = Decimal(annual_rate or 0)
    if not count or rate <= 0:
        return [ZERO] * count
    period = Decimal(interval_days)
    if method == InstallmentSettings.InterestMethod.REDUCING:
        per_period = rate / Decimal(100) * period / Decimal(360)
        outstanding = sum(principals, ZERO)
        shares = []
        for principal in principals:
            shares.append(whole_rials(outstanding * per_period))
            outstanding -= principal
        return shares
    months = period / Decimal(30) * count
    total = whole_rials(sum(principals, ZERO) * rate * months / Decimal(1200))
    base = (total / count).quantize(WHOLE, rounding=ROUND_DOWN)
    return [total - base * (count - 1)] + [base] * (count - 1)


def effective_rate(invoice, settings_row):
    if invoice.installment_profit_rate is not None:
        return invoice.installment_profit_rate
    return settings_row.interest_default_rate


def interest_preview(invoice, rows):
    """`{"method", "rate", "rows": {sequence: interest}, "total"}` for rows
    given as `(sequence, principal)` — the draft's box shows what issuing
    will charge. `None` without the feature."""
    if not feature_enabled(INTEREST) or invoice.payment_type != Invoice.PaymentType.INSTALLMENT:
        return None
    from billing.installment_settings import get_settings

    settings_row = get_settings()
    rate = effective_rate(invoice, settings_row)
    payable = [(sequence, principal) for sequence, principal in rows if sequence >= 1]
    shares = interest_shares(
        method=settings_row.interest_method, annual_rate=rate, principals=[principal for _, principal in payable],
        interval_days=invoice.installment_interval_days or 30,
    )
    return {
        "method": settings_row.interest_method,
        "method_display": settings_row.get_interest_method_display(),
        "rate": rate,
        "default_rate": settings_row.interest_default_rate,
        "rows": {sequence: share for (sequence, _), share in zip(payable, shares)},
        "total": sum(shares, ZERO),
    }


def charge_interest_at_issue(*, actor, invoice, occurred_at):
    """Called by `issue_invoice` inside its transaction, after the invoice's own
    ledger debit: one interest charge per instalment row, and one ledger debit
    for their total."""
    if not feature_enabled(INTEREST) or invoice.payment_type != Invoice.PaymentType.INSTALLMENT:
        return []
    plan = InstallmentPlan.objects.filter(invoice=invoice).first()
    if plan is None:
        return []
    from billing.installment_settings import get_settings

    settings_row = get_settings()
    rate = effective_rate(invoice, settings_row)
    if rate <= 0:
        return []
    rows = list(
        plan.installments.exclude(status=Installment.Status.CANCELLED).filter(sequence__gte=1).order_by("sequence")
    )
    shares = interest_shares(
        method=settings_row.interest_method, annual_rate=rate, principals=[row.amount for row in rows],
        interval_days=plan.interval_days,
    )
    pairs = [(row, share) for row, share in zip(rows, shares) if share > 0]
    if not pairs:
        return []
    total = sum((share for _, share in pairs), ZERO)
    entry = append_ledger_entry(
        actor=actor, customer=invoice.customer, entry_type=CustomerLedgerEntry.EntryType.INSTALLMENT_INTEREST,
        debit=total, occurred_at=occurred_at, reference_kind=CustomerLedgerEntry.ReferenceKind.INVOICE,
        reference_id=invoice.pk, reference_number=invoice.number,
        notes=f"سود اقساط، روش {settings_row.get_interest_method_display()}، نرخ سالانهٔ {rate} درصد",
    )
    charges = InstallmentCharge.objects.bulk_create([
        InstallmentCharge(
            plan=plan, installment=row, kind=InstallmentCharge.Kind.INTEREST, amount=share, due_date=row.due_date,
            ledger_entry_id=entry.pk,
        )
        for row, share in pairs
    ])
    plan.annual_profit_rate = rate
    plan.save(update_fields=["annual_profit_rate", "updated_at"])
    log_activity(
        actor=actor, operation="installment_plan.interest_charged", instance=plan,
        changes={"invoice": invoice.pk, "amount": str(total), "installment_count": len(pairs)},
    )
    return charges


def move_open_interest(*, closed_rows, new_rows):
    """A reschedule (`billing.installments.reschedule_plan`) closed `closed_rows`;
    the interest still open on them moves, unchanged in total, to `new_rows`
    (whole rials, the remainder on the first). Nothing is posted: the debt is
    the same debt."""
    charges = list(
        InstallmentCharge.objects.select_for_update()
        .filter(installment__in=closed_rows, kind=InstallmentCharge.Kind.INTEREST, status=InstallmentCharge.Status.OPEN)
        .order_by("id")
    )
    moved = sum((charge.open_amount for charge in charges), ZERO)
    if moved <= 0 or not new_rows:
        return ZERO
    for charge in charges:
        charge.released_amount = quantize_money(charge.released_amount + charge.open_amount)
        charge.status = InstallmentCharge.Status.MOVED
        charge.save(update_fields=["released_amount", "status", "updated_at"])
    count = len(new_rows)
    base = (moved / count).quantize(WHOLE, rounding=ROUND_DOWN)
    shares = [moved - base * (count - 1)] + [base] * (count - 1)
    InstallmentCharge.objects.bulk_create([
        InstallmentCharge(
            plan=row.plan, installment=row, kind=InstallmentCharge.Kind.INTEREST, amount=share, due_date=row.due_date,
            ledger_entry_id=charges[0].ledger_entry_id,
        )
        for row, share in zip(new_rows, shares)
        if share > 0
    ])
    return moved


def _restatus(charge):
    if charge.open_amount > 0:
        charge.status = InstallmentCharge.Status.OPEN
    elif charge.released_amount == 0:
        charge.status = InstallmentCharge.Status.PAID


def late_fee_for(row, settings_row, open_interest=ZERO):
    """The fee one overdue row draws under these rules, whole rials."""
    if settings_row.late_fee_value <= 0:
        return ZERO
    if settings_row.late_fee_mode == InstallmentSettings.LateFeeMode.FIXED:
        fee = whole_rials(settings_row.late_fee_value)
    else:
        owed = row.amount - row.paid_amount + open_interest
        fee = whole_rials(owed * settings_row.late_fee_value / Decimal(100))
    if settings_row.late_fee_cap > 0:
        fee = min(fee, whole_rials(settings_row.late_fee_cap))
    return max(fee, ZERO)


def post_late_fees(*, today=None, limit=LATE_FEE_BATCH):
    """Charge every row now past its grace that has no fee yet. Returns how many."""
    if not feature_enabled(LATE_FEES):
        return 0
    from billing.installment_settings import get_settings

    settings_row = get_settings()
    if settings_row.late_fee_value <= 0 or settings_row.late_fee_since is None:
        return 0
    today = today or timezone.localdate()
    cutoff = today - timedelta(days=settings_row.late_fee_grace_days)
    candidates = list(
        Installment.objects.filter(
            plan__status=InstallmentPlan.Status.ACTIVE,
            plan__invoice__status=Invoice.Status.ISSUED,
            status__in=[Installment.Status.PENDING, Installment.Status.PARTIALLY_PAID],
            paid_amount__lt=F("amount"),
            due_date__lt=cutoff,
            due_date__gte=settings_row.late_fee_since,
        )
        .exclude(charges__kind=InstallmentCharge.Kind.LATE_FEE)
        .order_by("due_date", "id")
        .values_list("pk", flat=True)[:limit]
    )
    charged = 0
    for pk in candidates:
        with transaction.atomic():
            row = Installment.objects.select_for_update().select_related("plan__invoice__customer").get(pk=pk)
            if row.paid_amount >= row.amount or row.charges.filter(kind=InstallmentCharge.Kind.LATE_FEE).exists():
                continue
            interest = row.charges.filter(
                kind=InstallmentCharge.Kind.INTEREST, status=InstallmentCharge.Status.OPEN
            ).aggregate(open=Sum(F("amount") - F("paid_amount") - F("released_amount")))["open"] or ZERO
            fee = late_fee_for(row, settings_row, interest)
            if fee <= 0:
                continue
            invoice = row.plan.invoice
            label = "پیش‌پرداخت" if row.sequence == 0 else f"قسط {row.sequence}"
            entry = append_ledger_entry(
                actor=None, customer=invoice.customer, entry_type=CustomerLedgerEntry.EntryType.LATE_FEE, debit=fee,
                occurred_at=timezone.now(), reference_kind=CustomerLedgerEntry.ReferenceKind.INVOICE,
                reference_id=invoice.pk, reference_number=invoice.number, notes=f"جریمهٔ دیرکرد {label}",
            )
            charge = InstallmentCharge.objects.create(
                plan=row.plan, installment=row, kind=InstallmentCharge.Kind.LATE_FEE, amount=fee, due_date=today,
                ledger_entry_id=entry.pk,
            )
            log_activity(
                actor=None, operation="installment_charge.late_fee_charged", instance=charge,
                changes={"invoice": invoice.pk, "amount": str(fee)},
            )
            charged += 1
    return charged


def _lock_manager(actor):
    from billing.payments import _lock_payment_manager

    return _lock_payment_manager(actor)


@transaction.atomic
def waive_charge(*, actor, charge, reason=""):
    """Forgive what is left of a late fee: a credit for that much, and the
    reason on the charge. Interest is not waived here — it is the price of the
    sale on credit, not a penalty."""
    actor = _lock_manager(actor)
    locked = InstallmentCharge.objects.select_for_update().select_related("plan__invoice__customer").get(pk=charge.pk)
    if locked.kind != InstallmentCharge.Kind.LATE_FEE:
        raise BusinessConflictError({"charge": "فقط جریمهٔ دیرکرد بخشیدنی است."})
    if locked.status != InstallmentCharge.Status.OPEN or locked.open_amount <= 0:
        raise BusinessConflictError({"charge": "از این جریمه چیزی باقی نمانده است."})
    reason = " ".join(str(reason or "").split())
    if not reason:
        raise BusinessRuleError({"reason": "دلیل بخشیدن جریمه را بنویسید."})
    if len(reason) > RELEASE_REASON_MAX_LENGTH:
        raise BusinessRuleError({"reason": f"دلیل نباید بیش از {RELEASE_REASON_MAX_LENGTH} نویسه باشد."})
    amount = locked.open_amount
    locked.released_amount = quantize_money(locked.released_amount + amount)
    locked.status = InstallmentCharge.Status.WAIVED
    locked.released_by = actor
    locked.release_reason = reason
    locked.save(update_fields=["released_amount", "status", "released_by", "release_reason", "updated_at"])
    invoice = locked.plan.invoice
    append_ledger_entry(
        actor=actor, customer=invoice.customer, entry_type=CustomerLedgerEntry.EntryType.CHARGE_WAIVED, credit=amount,
        occurred_at=timezone.now(), reference_kind=CustomerLedgerEntry.ReferenceKind.INVOICE,
        reference_id=invoice.pk, reference_number=invoice.number, notes="بخشودگی جریمهٔ دیرکرد",
    )
    log_activity(
        actor=actor, operation="installment_charge.waived", instance=locked,
        changes={"invoice": invoice.pk, "amount": str(amount), "reason_provided": True},
    )
    return locked


def cancel_charges_with_invoice(*, actor, invoice, occurred_at):
    """Called by `cancel_invoice` before the invoice is closed. Refused while a
    receipt still settles one of its charges — the same rule as the invoice's
    own allocations; otherwise what is open is cancelled, with one credit."""
    charges = list(InstallmentCharge.objects.select_for_update().filter(plan__invoice=invoice).order_by("id"))
    if any(charge.paid_amount > 0 for charge in charges):
        raise BusinessConflictError({
            "paid_amount": "پیش از لغو این فاکتور، تسویه‌های سود و جریمهٔ اقساط آن را آزاد کنید."
        })
    total = ZERO
    for charge in charges:
        if charge.status != InstallmentCharge.Status.OPEN:
            continue
        total += charge.open_amount
        charge.released_amount = quantize_money(charge.released_amount + charge.open_amount)
        charge.status = InstallmentCharge.Status.CANCELLED
        charge.save(update_fields=["released_amount", "status", "updated_at"])
    if total > 0:
        append_ledger_entry(
            actor=actor, customer=invoice.customer, entry_type=CustomerLedgerEntry.EntryType.CHARGE_CANCELLED,
            credit=total, occurred_at=occurred_at, reference_kind=CustomerLedgerEntry.ReferenceKind.INVOICE,
            reference_id=invoice.pk, reference_number=invoice.number, notes="لغو سود و جریمهٔ اقساط با ابطال فاکتور",
        )
    return total


def open_charges_total(customer):
    """What a customer still owes in charges (for `customer_outstanding`)."""
    total = InstallmentCharge.objects.filter(
        plan__invoice__customer=customer, status=InstallmentCharge.Status.OPEN
    ).aggregate(open=Sum(F("amount") - F("paid_amount") - F("released_amount")))["open"]
    return quantize_money(total or ZERO)


@transaction.atomic
def settle_charges(*, actor, payment, items=None):
    """Apply part of a confirmed receipt to charges of the same customer.

    `items` is `[{"charge": InstallmentCharge, "amount": Decimal|None}]`; an
    absent amount takes as much as both sides allow. With no `items`, every
    open charge of the customer is settled, earliest due first, for as long as
    the receipt has money left. All of it or none of it.
    """
    actor = _lock_manager(actor)
    locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if locked_payment.direction != Payment.Direction.RECEIPT or locked_payment.customer_id is None:
        raise BusinessRuleError({"payment": "فقط دریافتِ دارای مشتری را می‌توان برای سود و جریمه به کار برد."})
    if locked_payment.status != Payment.Status.CONFIRMED:
        raise BusinessConflictError({"payment": "فقط پرداخت تأییدشده قابل تخصیص است."})
    automatic = items is None
    if automatic:
        ids = list(
            InstallmentCharge.objects.filter(
                plan__invoice__customer_id=locked_payment.customer_id, status=InstallmentCharge.Status.OPEN
            ).order_by("due_date", "id").values_list("pk", flat=True)
        )
        items = [{"charge_id": pk, "amount": None} for pk in ids]
    else:
        items = [{"charge_id": item["charge"].pk, "amount": item.get("amount")} for item in items]
    if not items:
        raise BusinessConflictError({"charges": "این مشتری سود یا جریمهٔ بازی ندارد."})
    locked = {
        charge.pk: charge
        for charge in InstallmentCharge.objects.select_for_update().select_related("plan__invoice")
        .filter(pk__in={item["charge_id"] for item in items}).order_by("pk")
    }
    made = []
    for item in items:
        charge = locked[item["charge_id"]]
        if charge.plan.invoice.customer_id != locked_payment.customer_id:
            raise BusinessRuleError({"charges": "سود یا جریمه و دریافت باید متعلق به یک مشتری باشند."})
        available = locked_payment.unallocated_amount
        if charge.status != InstallmentCharge.Status.OPEN or charge.open_amount <= 0:
            if automatic:
                continue
            raise BusinessConflictError({"charges": "از این سود یا جریمه چیزی باقی نمانده است."})
        if available <= 0:
            if automatic and made:
                break
            raise BusinessConflictError({"payment": "این پرداخت به‌طور کامل تخصیص یافته است."})
        if item["amount"] is None:
            amount = min(available, charge.open_amount)
        else:
            amount = clean_money(item["amount"], field="amount", allow_zero=False)
            if amount > available:
                raise BusinessRuleError({"amount": "مبلغ از بخش تخصیص‌نیافته این پرداخت بیشتر است."})
            if amount > charge.open_amount:
                raise BusinessRuleError({"amount": "مبلغ از ماندهٔ این سود یا جریمه بیشتر است."})
        settlement = ChargeSettlement.objects.create(
            payment=locked_payment, charge=charge, amount=amount, created_by=actor
        )
        locked_payment.allocated_amount = quantize_money(locked_payment.allocated_amount + amount)
        charge.paid_amount = quantize_money(charge.paid_amount + amount)
        _restatus(charge)
        charge.save(update_fields=["paid_amount", "status", "updated_at"])
        made.append(settlement)
        log_activity(
            actor=actor, operation="installment_charge.settled", instance=settlement,
            changes={"payment": locked_payment.pk, "invoice": charge.plan.invoice_id, "allocated_amount": str(amount)},
        )
    if not made:
        raise BusinessConflictError({"charges": "این مشتری سود یا جریمهٔ بازی ندارد."})
    locked_payment.save(update_fields=["allocated_amount", "updated_at"])
    return made


@transaction.atomic
def release_settlement(*, actor, settlement, reason=""):
    """Take a settlement back: the receipt has that money again and the charge
    is owed again. A flag and a reason, never a deleted row."""
    actor = _lock_manager(actor)
    locked = ChargeSettlement.objects.select_for_update().get(pk=settlement.pk)
    if locked.is_reversed:
        raise BusinessConflictError({"settlement": "این تسویه پیش‌تر آزاد شده است."})
    payment = Payment.objects.select_for_update().get(pk=locked.payment_id)
    charge = InstallmentCharge.objects.select_for_update().get(pk=locked.charge_id)
    payment.allocated_amount = quantize_money(payment.allocated_amount - locked.amount)
    payment.save(update_fields=["allocated_amount", "updated_at"])
    charge.paid_amount = quantize_money(charge.paid_amount - locked.amount)
    _restatus(charge)
    charge.save(update_fields=["paid_amount", "status", "updated_at"])
    locked.is_reversed = True
    locked.release_reason = " ".join(str(reason or "").split())[:RELEASE_REASON_MAX_LENGTH]
    locked.save(update_fields=["is_reversed", "release_reason", "updated_at"])
    log_activity(
        actor=actor, operation="installment_charge.settlement_released", instance=locked,
        changes={"payment": payment.pk, "allocated_amount": str(locked.amount), "reason_provided": bool(reason)},
    )
    return locked


def serialize_charge(charge, *, row_label=None):
    if row_label is None:
        row_label = "پیش‌پرداخت" if charge.installment.sequence == 0 else f"قسط {charge.installment.sequence}"
    return {
        "id": charge.pk, "kind": charge.kind, "kind_display": charge.get_kind_display(),
        "installment_sequence": charge.installment.sequence, "installment_label": row_label,
        "due_date": charge.due_date, "amount": charge.amount, "paid_amount": charge.paid_amount,
        "released_amount": charge.released_amount, "open_amount": charge.open_amount,
        "status": charge.status, "status_display": charge.get_status_display(),
        "release_reason": charge.release_reason,
    }


def plan_charges(plan):
    return [
        serialize_charge(charge)
        for charge in plan.charges.select_related("installment").order_by("due_date", "kind", "id")
    ]


def customer_open_charges(customer_id):
    """The receipt page's list: every open charge of this customer."""
    charges = (
        InstallmentCharge.objects.filter(plan__invoice__customer_id=customer_id, status=InstallmentCharge.Status.OPEN)
        .select_related("installment", "plan__invoice").order_by("due_date", "id")
    )
    return [{**serialize_charge(charge), "invoice": charge.plan.invoice_id, "invoice_number": charge.plan.invoice.number}
            for charge in charges]


def payment_settlements(payment):
    return [
        {
            "id": item.pk, "charge": item.charge_id, "kind_display": item.charge.get_kind_display(),
            "invoice_number": item.charge.plan.invoice.number,
            "installment_label": "پیش‌پرداخت" if item.charge.installment.sequence == 0 else f"قسط {item.charge.installment.sequence}",
            "amount": item.amount, "is_reversed": item.is_reversed, "created_at": item.created_at,
        }
        for item in payment.charge_settlements.select_related("charge__plan__invoice", "charge__installment").order_by("-created_at", "-id")
    ]
