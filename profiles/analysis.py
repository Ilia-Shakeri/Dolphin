"""The customer profile's «آنالیز» tab (2.33.0): five figures and a monthly line each.

Every figure reads through the owning module's own selector, so a viewer sees
only what their scope allows; a figure the viewer may not read is reported as
missing (with the reason) rather than shown as zero. Months are Jalali.
"""

from collections import defaultdict
from datetime import datetime, time
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from accounts.access import capabilities_for
from common.deployment.profile import feature_enabled
from common.formatting import money, persian_digits
from common.jalali import JALALI_MONTHS, format_date, from_jalali, to_jalali
from common.preferences import effective_preferences

#: Months drawn on the chart: the twelve ending with the current one for money
#: already moved, and three back through eight ahead for what is still due.
PAST_MONTHS = 12
DUE_MONTHS_BACK = 3
DUE_MONTHS_AHEAD = 8
ZERO = Decimal("0.00")


def _month_key(day):
    year, month, _ = to_jalali(day)
    return year, month


def _shift(key, delta):
    year, month = key
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _month_start(key):
    return from_jalali(key[0], key[1], 1)


def _month_start_moment(key):
    return timezone.make_aware(datetime.combine(_month_start(key), time.min))


def _label(key):
    return f"{JALALI_MONTHS[key[1] - 1]} {persian_digits(key[0])}"


def _local_day(moment):
    return timezone.localtime(moment).date()


def _quantized(value):
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _missing(reason):
    return {"missing": True, "raw": None, "display": "—", "tooltip": reason}


def _present(raw, display, tooltip=""):
    return {"missing": False, "raw": raw, "display": display, "tooltip": tooltip}


def _series(label, kind, keys, values, unit):
    points = []
    for key, value in zip(keys, values):
        display = money(value, unit) if kind == "money" else persian_digits(int(value))
        points.append({"label": _label(key), "value": float(value), "display": display})
    return {"label": label, "kind": kind, "points": points}


def _monthly(rows, keys):
    """Sum `(moment_or_day, amount)` pairs into the given Jalali months."""
    buckets = defaultdict(lambda: ZERO)
    for moment, amount in rows:
        day = moment if not hasattr(moment, "hour") else _local_day(moment)
        buckets[_month_key(day)] += amount
    return buckets


def customer_analysis(viewer, customer):
    from billing.models import Installment, Invoice, Payment
    from billing.selectors import installments_for, invoices_for, payments_for
    from profiles.cards import _customer_debt, _customer_money_visible, _customer_purchases_visible

    unit = effective_preferences(viewer)["currency_unit"]
    capabilities = capabilities_for(viewer)
    today = timezone.localdate()
    now_key = _month_key(today)
    past_keys = [_shift(now_key, delta) for delta in range(-(PAST_MONTHS - 1), 1)]
    due_keys = [_shift(now_key, delta) for delta in range(-DUE_MONTHS_BACK, DUE_MONTHS_AHEAD + 1)]

    kpis = {}
    series = {}

    sees_purchases = feature_enabled("invoices") and _customer_purchases_visible(viewer, customer)
    sees_payments = feature_enabled("payments") and "payments.company" in capabilities

    purchases = (
        invoices_for(viewer).filter(customer=customer, status=Invoice.Status.ISSUED) if sees_purchases else None
    )
    receipts = (
        payments_for(viewer).filter(
            customer=customer, direction=Payment.Direction.RECEIPT, status=Payment.Status.CONFIRMED
        )
        if sees_payments
        else None
    )

    if purchases is not None:
        total = _quantized(purchases.aggregate(total=Sum("total_amount"))["total"])
        kpis["total_purchase"] = _present(
            str(total), money(total, unit), "مجموع فاکتورهای صادرشده؛ فاکتور لغوشده حساب نمی‌شود."
        )
        buckets = _monthly(
            purchases.filter(issued_at__gte=_month_start_moment(past_keys[0])).values_list("issued_at", "total_amount"),
            past_keys,
        )
        series["total_purchase"] = _series("مجموع خرید", "money", past_keys, [buckets[k] for k in past_keys], unit)
    else:
        kpis["total_purchase"] = _missing("فاکتورهای این مشتری برای شما قابل نمایش نیست.")

    if receipts is not None:
        total = _quantized(receipts.aggregate(total=Sum("amount"))["total"])
        kpis["total_received"] = _present(str(total), money(total, unit), "مجموع دریافتی‌های تأییدشدهٔ این مشتری.")
        buckets = _monthly(
            receipts.filter(received_at__gte=_month_start_moment(past_keys[0])).values_list("received_at", "amount"),
            past_keys,
        )
        series["total_received"] = _series(
            "مجموع دریافت‌شده", "money", past_keys, [buckets[k] for k in past_keys], unit
        )
    else:
        kpis["total_received"] = _missing("دریافتی‌های این مشتری برای شما قابل نمایش نیست.")

    debt = _customer_debt(viewer, customer, None) if _customer_money_visible(viewer, customer) else None
    if debt and not debt["missing"]:
        kpis["debt_balance"] = _present(debt["raw"], debt["value"], debt["tooltip"])
        if purchases is not None and receipts is not None:
            invoiced = _monthly(purchases.values_list("issued_at", "total_amount"), past_keys)
            received = _monthly(receipts.values_list("received_at", "amount"), past_keys)
            running = sum((v for k, v in invoiced.items() if k < past_keys[0]), ZERO) - sum(
                (v for k, v in received.items() if k < past_keys[0]), ZERO
            )
            values = []
            for key in past_keys:
                running += invoiced[key] - received[key]
                values.append(running)
            series["debt_balance"] = _series("مانده بدهی در پایان ماه", "money", past_keys, values, unit)
    else:
        kpis["debt_balance"] = _missing((debt or {}).get("tooltip") or "مانده این مشتری برای شما قابل نمایش نیست.")

    if sees_payments:
        rows = installments_for(viewer).filter(
            plan__invoice__customer=customer,
            plan__invoice__status=Invoice.Status.ISSUED,
            status__in=[Installment.Status.PENDING, Installment.Status.PARTIALLY_PAID],
        )
        open_count = rows.count()
        kpis["open_installments"] = _present(
            open_count,
            persian_digits(open_count),
            "ردیف‌های پیش‌پرداخت و اقساطِ فاکتورهای صادرشده که هنوز کامل پرداخت نشده‌اند.",
        )
        earliest = rows.order_by("due_date").values_list("due_date", flat=True).first()
        if earliest:
            overdue = earliest < today
            kpis["next_due"] = _present(
                earliest.isoformat(),
                format_date(earliest),
                "قدیمی‌ترین سررسیدِ پرداخت‌نشده؛ گذشته است." if overdue else "نزدیک‌ترین سررسیدِ پرداخت‌نشده.",
            )
            kpis["next_due"]["overdue"] = overdue
        else:
            kpis["next_due"] = _present(None, "—", "سررسید بازی ندارد.")
        counts = defaultdict(int)
        owed = defaultdict(lambda: ZERO)
        for due_date, amount, paid in rows.filter(due_date__gte=_month_start(due_keys[0])).values_list(
            "due_date", "amount", "paid_amount"
        ):
            key = _month_key(due_date)
            counts[key] += 1
            owed[key] += amount - paid
        series["open_installments"] = _series(
            "اقساط باز در هر ماه سررسید", "count", due_keys, [counts[k] for k in due_keys], unit
        )
        series["next_due"] = _series(
            "مبلغ مانده در هر ماه سررسید", "money", due_keys, [owed[k] for k in due_keys], unit
        )
    else:
        reason = "اقساط این مشتری برای شما قابل نمایش نیست."
        kpis["open_installments"] = _missing(reason)
        kpis["next_due"] = _missing(reason)

    return {"kpis": kpis, "series": series}
