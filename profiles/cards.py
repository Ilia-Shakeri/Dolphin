"""The profile header's stat cards #4–#7 (2.20.0).

Each card is a provider: who may see it (`visible`), and what it says for a
period (`compute`). **A card the reader may not see is not built at all** —
the page renders no shell for it and the API computes no value for it, so its
number never reaches the browser.

Definitions are the approved ones from the plan (decisions D2–D5):

| Card | User | Customer |
|---|---|---|
| #4 | درآمد — confirmed sales they made (D2) | بدهکاری — ledger balance, else issued-invoice outstanding (D3) |
| #5 | مشتریان فعال — customers behind their open leads | مجموع خرید — issued invoices, else confirmed sales (D4) |
| #6 | نرخ تبدیل — completed ÷ decided leads (D5) | آخرین تعامل — the newest timeline event |
| #7 | امتیاز | امتیاز |

Money is read through the viewer's own selectors (`invoices_for`,
`ledger_entries_for`, …), so a card never totals rows its reader could not
open one by one.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from accounts.access import capabilities_for
from common.deployment.profile import feature_enabled
from common.formatting import money, persian_digits
from common.jalali import from_jalali, to_jalali
from common.preferences import effective_preferences

# --- Periods -------------------------------------------------------------------

PERIODS = (
    ("this_month", "این ماه"),
    ("last_month", "ماه گذشته"),
    ("last_90_days", "۹۰ روز اخیر"),
    ("this_year", "امسال"),
)
DEFAULT_PERIOD = "this_month"


def _local_midnight(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def _month_start(year, month):
    return _local_midnight(from_jalali(year, month, 1))


def _next_month(year, month):
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _previous_month(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


@dataclass(frozen=True)
class Period:
    key: str
    label: str
    start: datetime
    end: datetime
    previous_start: datetime
    previous_end: datetime


def period_for(key, *, now=None):
    """A Jalali-calendar window and the equal window before it."""
    now = timezone.localtime(now or timezone.now())
    labels = dict(PERIODS)
    if key not in labels:
        key = DEFAULT_PERIOD
    year, month, _ = to_jalali(now.date())
    if key == "this_month":
        start = _month_start(year, month)
        end = _month_start(*_next_month(year, month))
        previous_start = _month_start(*_previous_month(year, month))
        previous_end = start
    elif key == "last_month":
        end = _month_start(year, month)
        start = _month_start(*_previous_month(year, month))
        previous_end = start
        previous_start = _month_start(*_previous_month(*_previous_month(year, month)))
    elif key == "last_90_days":
        end = now
        start = now - timedelta(days=90)
        previous_end = start
        previous_start = start - timedelta(days=90)
    else:  # this_year
        start = _month_start(year, 1)
        end = _month_start(year + 1, 1)
        previous_start = _month_start(year - 1, 1)
        previous_end = start
    return Period(key, labels[key], start, end, previous_start, previous_end)


# --- Card values ---------------------------------------------------------------


def _value(display, *, raw=None, tooltip="", accent="", trend=None, extra=None):
    return {"value": display, "raw": raw, "missing": False, "tooltip": tooltip, "accent": accent, "trend": trend, **(extra or {})}


def _missing(reason):
    """«—» with the reason as its tooltip — never an empty tile."""
    return {"value": "—", "raw": None, "missing": True, "tooltip": reason, "accent": "", "trend": None}


def _trend(current, previous):
    """Direction and size of the change against the equal window before."""
    if previous in (None, 0) or current is None:
        return None
    change = (Decimal(str(current)) - Decimal(str(previous))) / Decimal(str(previous)) * 100
    direction = "up" if change > 0 else ("down" if change < 0 else "flat")
    return {
        "direction": direction,
        "display": f"{persian_digits(abs(round(change)))}٪",
        "tooltip": "نسبت به بازهٔ هم‌اندازهٔ قبل",
    }


def _raw_money(value):
    """Two decimal places whatever the database returned — SQLite's `Sum`
    drops them, PostgreSQL's keeps them, and the API must not differ."""
    return str(Decimal(value).quantize(Decimal("0.01")))


def _unit(viewer):
    return effective_preferences(viewer)["currency_unit"]


def _relative(moment, *, now=None):
    now = now or timezone.now()
    seconds = max(0, (now - moment).total_seconds())
    if seconds < 3600:
        return "کمتر از یک ساعت پیش"
    if seconds < 86400:
        return f"{persian_digits(int(seconds // 3600))} ساعت پیش"
    days = int(seconds // 86400)
    if days < 30:
        return f"{persian_digits(days)} روز پیش"
    if days < 365:
        return f"{persian_digits(days // 30)} ماه پیش"
    return f"{persian_digits(days // 365)} سال پیش"


# --- User cards -----------------------------------------------------------------


def _reads_performance(viewer, person):
    from profiles.registry import adapter_for

    return adapter_for("user").reads_performance(viewer, person)


def _user_income(viewer, person, period):
    from sales.models import Sale
    from sales.selectors import sales_for

    def total(start, end):
        return (
            sales_for(viewer)
            .filter(sold_by=person, status=Sale.Status.CONFIRMED, sold_at__gte=start, sold_at__lt=end)
            .aggregate(total=Sum("total_amount"))["total"]
            or Decimal("0")
        )

    current = total(period.start, period.end)
    previous = total(period.previous_start, period.previous_end)
    return _value(
        money(current, _unit(viewer)),
        raw=_raw_money(current),
        tooltip="مجموع فروش‌های تأییدشده‌ای که این کاربر در این بازه ثبت کرده است — نه کمیسیون و نه حقوق.",
        trend=_trend(current, previous),
    )


def _user_active_customers(viewer, person, period):
    from sales.models import Lead
    from sales.selectors import leads_for

    count = (
        leads_for(viewer)
        .filter(assigned_to=person, status=Lead.Status.PENDING, customer__isnull=False)
        .values("customer_id").distinct().count()
    )
    return _value(
        persian_digits(count),
        raw=count,
        tooltip="مشتریانی که سرنخِ در انتظار تکمیلِ آن‌ها همین حالا به این کاربر واگذار است — مستقل از بازه.",
    )


def _conversion(viewer, person, start, end):
    from sales.models import Lead
    from sales.selectors import leads_for

    row = (
        leads_for(viewer)
        .filter(
            assigned_to=person,
            status__in=[Lead.Status.COMPLETED, Lead.Status.CANCELLED],
            closed_at__gte=start,
            closed_at__lt=end,
        )
        .aggregate(decided=Count("id"), completed=Count("id", filter=Q(status=Lead.Status.COMPLETED)))
    )
    return row["completed"], row["decided"]


def _user_conversion(viewer, person, period):
    completed, decided = _conversion(viewer, person, period.start, period.end)
    if not decided:
        return _missing("در این بازه هیچ سرنخی از این کاربر به نتیجه (تکمیل یا کنسل) نرسیده است.")
    rate = completed / decided * 100
    previous_completed, previous_decided = _conversion(viewer, person, period.previous_start, period.previous_end)
    previous_rate = previous_completed / previous_decided * 100 if previous_decided else None
    return _value(
        f"{persian_digits(round(rate))}٪",
        raw=round(rate, 1),
        tooltip=(
            f"{persian_digits(completed)} تکمیل از {persian_digits(decided)} سرنخ تصمیم‌گرفته‌شده در این بازه — "
            "همان تعریفِ گیج نرخ تبدیل داشبورد."
        ),
        trend=_trend(round(rate, 1), round(previous_rate, 1) if previous_rate is not None else None),
    )


# --- Customer cards --------------------------------------------------------------

MONEY_CAPABILITIES = {"ledger.company", "ledger.own", "invoices.company", "payments.company"}


def _customer_money_visible(viewer, person):
    if not capabilities_for(viewer) & MONEY_CAPABILITIES:
        return False
    return feature_enabled("customer_ledger") or feature_enabled("invoices")


def _customer_debt(viewer, person, period):
    from billing.models import Installment, Invoice
    from billing.selectors import installments_for, invoices_for, ledger_entries_for

    unit = _unit(viewer)
    now = timezone.now()
    capabilities = capabilities_for(viewer)
    invoices = invoices_for(viewer).filter(customer=person, status=Invoice.Status.ISSUED)
    overdue_invoices = [
        invoice for invoice in invoices.filter(Q(due_at__lt=now) | Q(due_at__isnull=True, issued_at__lt=now))
        if invoice.balance_due > 0
    ]
    overdue_instalments = 0
    if feature_enabled("payments"):
        overdue_instalments = installments_for(viewer).filter(
            plan__invoice__customer=person,
            due_date__lt=timezone.localdate(now),
            status__in=[Installment.Status.PENDING, Installment.Status.PARTIALLY_PAID],
        ).count()
    overdue_count = len(overdue_invoices) + overdue_instalments

    if feature_enabled("customer_ledger") and capabilities & {"ledger.company", "ledger.own"}:
        totals = ledger_entries_for(viewer).filter(customer=person).aggregate(debit=Sum("debit"), credit=Sum("credit"))
        balance = (totals["debit"] or Decimal("0")) - (totals["credit"] or Decimal("0"))
        basis = "مانده دفتر حساب مشتری (شامل مانده اول دوره)."
    elif feature_enabled("invoices"):
        balance = sum((invoice.balance_due for invoice in invoices), Decimal("0"))
        basis = "مجموع ماندهٔ فاکتورهای صادرشده."
    else:
        return _missing("نه دفتر حساب مشتری و نه فاکتور در این استقرار فعال است.")
    tooltip = basis
    if overdue_count:
        tooltip += f" {persian_digits(overdue_count)} سررسید معوق دارد."
    elif balance > 0:
        tooltip += " سررسید معوقی ندارد."
    if balance < 0:
        display = f"{money(-balance, unit)} بستانکار"
    else:
        display = money(balance, unit)
    return _value(
        display,
        raw=_raw_money(balance),
        tooltip=tooltip,
        accent="danger" if overdue_count else "",
        extra={"overdue_count": overdue_count},
    )


def _customer_purchases(viewer, person, period):
    unit = _unit(viewer)
    if feature_enabled("invoices"):
        from billing.models import Invoice
        from billing.selectors import invoices_for

        def total(start, end):
            return (
                invoices_for(viewer)
                .filter(customer=person, status=Invoice.Status.ISSUED, issued_at__gte=start, issued_at__lt=end)
                .aggregate(total=Sum("total_amount"))["total"]
                or Decimal("0")
            )

        basis = "مجموع فاکتورهای صادرشدهٔ این مشتری در این بازه (فاکتورهای لغوشده حساب نمی‌شوند)."
    elif feature_enabled("sales"):
        from sales.models import Sale
        from sales.selectors import sales_for

        def total(start, end):
            return (
                sales_for(viewer)
                .filter(customer=person, status=Sale.Status.CONFIRMED, sold_at__gte=start, sold_at__lt=end)
                .aggregate(total=Sum("total_amount"))["total"]
                or Decimal("0")
            )

        basis = "مجموع فروش‌های تأییدشدهٔ این مشتری در این بازه."
    else:
        return _missing("خرید در این استقرار ثبت نمی‌شود.")
    current = total(period.start, period.end)
    previous = total(period.previous_start, period.previous_end)
    return _value(money(current, unit), raw=_raw_money(current), tooltip=basis, trend=_trend(current, previous))


def _customer_purchases_visible(viewer, person):
    capabilities = capabilities_for(viewer)
    if feature_enabled("invoices"):
        return bool(capabilities & {"invoices.scoped", "invoices.company"})
    if feature_enabled("sales"):
        return bool(capabilities & {"sales.own", "sales.company"})
    return False


def _customer_last_interaction(viewer, person, period):
    from profiles.registry import adapter_for

    events = adapter_for("customer").timeline(viewer, person)["events"]
    dated = [event for event in events if event.get("at")]
    if not dated:
        return _missing("هنوز هیچ رویدادی برای این مشتری ثبت نشده است.")
    event = dated[0]
    moment = datetime.fromisoformat(event["at"])
    return _value(
        _relative(moment),
        raw=event["at"],
        tooltip=f"{event['label']}: {event['title']}",
        extra={"url": event.get("url", "")},
    )


# --- Score -----------------------------------------------------------------------


def _score(person_type):
    def compute(viewer, person, period):
        from scoring.services import LEVEL_LABELS, current_score

        snapshot = current_score(person_type, person)
        if snapshot is None:
            return _missing("داده‌ای برای امتیازدهی نیست: هیچ‌کدام از عامل‌های امتیاز برای این شخص قابل سنجش نیست.")
        label, accent = LEVEL_LABELS.get(snapshot.level, ("", ""))
        return _value(
            persian_digits(snapshot.score),
            raw=snapshot.score,
            tooltip=f"{label} — برای دیدن دلیل هر امتیاز روی کارت بزنید.",
            accent=accent,
            extra={"level": snapshot.level, "level_label": label, "computed_at": snapshot.computed_at.isoformat()},
        )

    return compute


def _score_visible(person_type):
    def visible(viewer, person):
        if person_type == "user":
            return _reads_performance(viewer, person)
        return True

    return visible


# --- Registry --------------------------------------------------------------------


@dataclass(frozen=True)
class StatCard:
    key: str
    person_type: str
    slot: int
    label: str
    icon: str
    icon_paths: int
    features: tuple
    visible: object
    compute: object
    #: Opens the score breakdown instead of just showing a figure.
    explains: bool = False

    @property
    def paths(self):
        return range(1, self.icon_paths + 1)


CARDS = (
    StatCard("income", "user", 4, "درآمد", "di-dollar", 3, ("sales",), _reads_performance, _user_income),
    StatCard("active_customers", "user", 5, "مشتریان فعال", "di-profile-user", 4, ("leads",), _reads_performance, _user_active_customers),
    StatCard("conversion", "user", 6, "نرخ تبدیل", "di-chart-simple", 4, ("leads",), _reads_performance, _user_conversion),
    StatCard("score", "user", 7, "امتیاز", "di-medal-star", 4, ("person_scoring",), _score_visible("user"), _score("user"), True),
    StatCard("debt", "customer", 4, "بدهکاری", "di-wallet", 4, (), _customer_money_visible, _customer_debt),
    StatCard("purchases", "customer", 5, "مجموع خرید", "di-basket", 4, (), _customer_purchases_visible, _customer_purchases),
    StatCard("last_interaction", "customer", 6, "آخرین تعامل", "di-time", 2, (), lambda viewer, person: True, _customer_last_interaction),
    StatCard("score", "customer", 7, "امتیاز", "di-medal-star", 4, ("person_scoring",), _score_visible("customer"), _score("customer"), True),
)


def cards_for(viewer, person_type, person):
    """The cards `viewer` may see on this person's profile, in slot order."""
    return [
        card
        for card in CARDS
        if card.person_type == person_type
        and all(feature_enabled(feature) for feature in card.features)
        and card.visible(viewer, person)
    ]


def card_values(viewer, person_type, person, period):
    values = []
    for card in cards_for(viewer, person_type, person):
        payload = card.compute(viewer, person, period)
        values.append({"key": card.key, "label": card.label, "slot": card.slot, **payload})
    return values
