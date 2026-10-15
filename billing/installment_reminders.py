"""Instalment reminder SMS (2.40.51, feature `installment_reminders`).

Owner decision 2026-10-14 (Q15): reminders before the due date, on it, and
after it, each with an editable text. The rules are this company's
(`billing.installment_settings`); this module only decides which rows are due
for which reminder today and sends them.

* **before** — once, while the row falls due within `remind_days_before` days;
* **due** — on the due date;
* **overdue** — once, from `remind_days_after` days after the due date, for a
  week (a reminder a cron run missed is still sent the next day, and turning
  the feature on does not message every customer about years-old rows).

Only a live row with something left to pay is reminded: an issued invoice, an
active plan, a row neither paid nor cancelled. Each send is claimed first by a
unique `InstallmentReminder` row (installment, kind, due date), so two runs at
once cannot send the same reminder twice, and a rescheduled row is reminded
again for its new date. Nothing is sent before `remind_send_hour`, or after
21:00, Tehran time.

Run from cron through `manage.py send_installment_reminders` (runbook).
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from billing.installment_settings import REMINDERS, get_settings
from billing.models import Installment, InstallmentPlan, InstallmentReminder, Invoice
from common.deployment.profile import feature_enabled
from common.jalali import format_date, to_persian_digits

logger = logging.getLogger("dolphin.billing.installment_reminders")

#: Most reminders one run sends: each is a provider round trip.
DISPATCH_BATCH = 50
#: How long after `remind_days_after` an overdue reminder may still go.
OVERDUE_WINDOW_DAYS = 7
LAST_SEND_HOUR = 21


def _amount_text(value):
    whole = int(Decimal(value).to_integral_value())
    return to_persian_digits(f"{whole:,}".replace(",", "٬")) + " ریال"


def _open_interest(row):
    """The row's own interest still open (2.40.52): the instalment the customer
    pays is its principal and its interest together."""
    from billing.models import InstallmentCharge

    total = Decimal("0")
    for charge in row.charges.filter(kind=InstallmentCharge.Kind.INTEREST, status=InstallmentCharge.Status.OPEN):
        total += charge.open_amount
    return total


def render(template, row):
    """The template with the row's own facts; every token has a value."""
    invoice = row.plan.invoice
    label = "پیش‌پرداخت" if row.sequence == 0 else f"قسط {to_persian_digits(str(row.sequence))}"
    values = {
        "{نام}": (invoice.customer.full_name or "").strip() or "مشتری",
        "{مبلغ}": _amount_text(row.amount - row.paid_amount + _open_interest(row)),
        "{تاریخ}": format_date(row.due_date),
        "{فاکتور}": to_persian_digits(invoice.number),
        "{قسط}": label,
    }
    text = template
    for token, value in values.items():
        text = text.replace(token, value)
    return " ".join(text.split())


def _live_unpaid():
    return Installment.objects.filter(
        plan__status=InstallmentPlan.Status.ACTIVE,
        plan__invoice__status=Invoice.Status.ISSUED,
        status__in=[Installment.Status.PENDING, Installment.Status.PARTIALLY_PAID],
        paid_amount__lt=F("amount"),
    )


def due_reminders(*, today, settings_row):
    """`[(installment, kind)]` owed a reminder today, earliest due first."""
    found = []
    if settings_row.remind_days_before > 0:
        rows = _live_unpaid().filter(
            due_date__gt=today, due_date__lte=today + timedelta(days=settings_row.remind_days_before)
        )
        found += [(row, InstallmentReminder.Kind.BEFORE) for row in rows]
    if settings_row.remind_on_due:
        found += [(row, InstallmentReminder.Kind.DUE) for row in _live_unpaid().filter(due_date=today)]
    if settings_row.remind_days_after > 0:
        latest = today - timedelta(days=settings_row.remind_days_after)
        rows = _live_unpaid().filter(due_date__lte=latest, due_date__gt=latest - timedelta(days=OVERDUE_WINDOW_DAYS))
        found += [(row, InstallmentReminder.Kind.OVERDUE) for row in rows]
    sent = set(
        InstallmentReminder.objects.filter(installment__in=[row for row, _ in found]).values_list(
            "installment_id", "kind", "due_date"
        )
    )
    found = [(row, kind) for row, kind in found if (row.pk, kind, row.due_date) not in sent]
    return sorted(found, key=lambda item: (item[0].due_date, item[0].pk, item[1]))


def _error_text(error):
    detail = getattr(error, "detail", "")
    if isinstance(detail, dict):
        parts = []
        for value in detail.values():
            parts.extend(value if isinstance(value, list) else [value])
        return "؛ ".join(str(part) for part in parts)
    return str(detail)


def _claim(row, kind):
    try:
        with transaction.atomic():
            return InstallmentReminder.objects.create(installment=row, kind=kind, due_date=row.due_date)
    except IntegrityError:
        return None


def dispatch_installment_reminders(*, now=None, limit=DISPATCH_BATCH):
    """Send what is due now. Returns `(sent, failed, skipped)`."""
    from communications import sms
    from communications.services import send_system_sms
    from common.exceptions import BusinessRuleError

    if not feature_enabled(REMINDERS) or not sms.provider_is_available():
        return (0, 0, 0)
    now = timezone.localtime(now or timezone.now())
    settings_row = get_settings()
    if not settings_row.remind_send_hour <= now.hour < LAST_SEND_HOUR:
        return (0, 0, 0)
    templates = {
        InstallmentReminder.Kind.BEFORE: settings_row.template_before,
        InstallmentReminder.Kind.DUE: settings_row.template_due,
        InstallmentReminder.Kind.OVERDUE: settings_row.template_overdue,
    }
    sent = failed = skipped = 0
    candidates = due_reminders(today=now.date(), settings_row=settings_row)
    rows = {row.pk: row for row in Installment.objects.select_related("plan__invoice__customer").filter(
        pk__in=[row.pk for row, _ in candidates]
    )}
    for row, kind in candidates:
        if sent + failed + skipped >= limit:
            break
        claim = _claim(row, kind)
        if claim is None:
            continue
        row = rows[row.pk]
        try:
            message = send_system_sms(body=render(templates[kind], row), customer=row.plan.invoice.customer)
        except BusinessRuleError as error:
            # No active phone, or the provider went away: nothing was sent and
            # nothing will be until the cause is fixed — recorded, not retried.
            InstallmentReminder.objects.filter(pk=claim.pk).update(
                status=InstallmentReminder.Status.SKIPPED, detail=_error_text(error)[:255]
            )
            skipped += 1
            continue
        except Exception:  # noqa: BLE001 — one bad send must not stop the batch
            logger.exception("installment reminder %s could not be sent", claim.pk)
            InstallmentReminder.objects.filter(pk=claim.pk).update(
                status=InstallmentReminder.Status.FAILED, detail="ارسال ناموفق بود."
            )
            failed += 1
            continue
        ok = message.status == "sent"
        InstallmentReminder.objects.filter(pk=claim.pk).update(
            status=InstallmentReminder.Status.SENT if ok else InstallmentReminder.Status.FAILED,
            detail=message.status_detail[:255], message_id=message.pk,
        )
        if ok:
            sent += 1
        else:
            failed += 1
    return (sent, failed, skipped)


def reminders_for_rows(installment_ids):
    """`{installment_id: [{kind, kind_display, due_date, status, status_display, at}]}`
    for the invoice page's instalment box."""
    found = {}
    for item in InstallmentReminder.objects.filter(installment_id__in=installment_ids).order_by("created_at", "id"):
        found.setdefault(item.installment_id, []).append({
            "kind": item.kind, "kind_display": item.get_kind_display(), "due_date": item.due_date,
            "status": item.status, "status_display": item.get_status_display(), "at": item.created_at,
        })
    return found
