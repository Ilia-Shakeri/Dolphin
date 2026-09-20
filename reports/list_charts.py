"""One chart per list page, declared in a table rather than written eleven times.

Every entry names three things explicitly, because they are three separate
controls and merging them is how a chart ends up showing more than its viewer
may list:

* ``feature``      — the deployment module it belongs to;
* ``capabilities`` — any one of which the role must hold;
* ``builder``      — which starts from that module's own selector, never from
                     a model manager.

A builder returns ``[{"label", "value", "display"}]`` already formatted, in the
order it wants drawn. The panel passes them straight to ``renderBarChart``.

Two of these deviate from what was first asked for, and both deviations are
forced by the data model rather than chosen:

* **invoices** were to be grouped by settlement status. That is a Python
  property over ``is_manually_settled``, ``status``, ``paid_amount`` and
  ``total_amount`` — not a column — so it is counted by reading the property,
  not by rebuilding the rule in SQL where the two could drift apart.
* **stock value** is likewise not a column. It is ``quantity * average_cost``,
  summed per warehouse in the query.
"""

from common import formatting
from collections import namedtuple
from datetime import timedelta
from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from aftersales.selectors import after_sales_requests_for
from billing.models import Invoice, Order, Payment
from billing.selectors import invoices_for, orders_for, payments_for
from inventory.selectors import stock_items_for, stock_movements_for
from reports.ranges import (
    bucket_index,
    bucket_label_value,
    granularity_for,
    local_bucket_starts,
)
from sales.models import Interaction, Lead, Sale
from sales.selectors import (
    interactions_for,
    leads_for,
    product_categories_for,
    products_for,
    sales_documents_for,
    sales_for,
)


#: How many bars before a chart stops being readable. The tail is grouped rather
#: than dropped, so the total a reader adds up still matches the list above it.
TOP_N = 12
#: What an empty grouping key is called. Left blank it would draw a nameless bar.
UNLABELLED = "نامشخص"


#: Both moved to `common/formatting.py` when the dashboard needed the same
#: two formatters (1.8.6); read from there so the product has one grouped-rial
#: rule on the Python side rather than one per consumer. The local names stay
#: so nothing in this module's own body changed.
_persian_digits = formatting.persian_digits
_money = formatting.money

#: The two currency words a formatted amount can end in. `totals_for` reads
#: the unit back off `display` rather than being told it, so it has to know
#: both since 2.8.0 — a toman chart whose total fell through to the count
#: branch would print a bare integer under grouped amounts.
_CURRENCY_SUFFIXES = (formatting.CURRENCY_LABEL, formatting.TOMAN_LABEL)


def unit_for(actor):
    """This reader's own currency unit.

    Resolved here rather than threaded through all twelve builders: the unit
    is a property of the actor each builder already receives, and only the
    four builders that sum money ever need it.
    """
    from common.preferences import effective_preferences

    return effective_preferences(actor)["currency_unit"]


def totals_for(result, unit="rial"):
    """The whole the slices add up to, formatted the way the slices are.

    The donut prints this in its middle, and only the server knows whether a
    series counts documents or sums rial — the browser sees `value` as a bare
    number either way, and formatting it there produced an ungrouped
    `793125000` under a chart whose own labels read «۵۳۶٬۸۲۵٬۰۰۰ ریال».

    Which of the two it is, is read back off `display` rather than threaded
    through all twelve builders as a flag. `_money` and `_persian_digits` are
    the only things that ever write that field, and `_money` always ends in the
    currency word — so the question is already answered in the data.
    """
    if not result:
        return {"total_display": "", "total_label": ""}
    total = sum(Decimal(str(row["value"])) for row in result)
    money = any(
        str(row.get("display", "")).endswith(_CURRENCY_SUFFIXES) for row in result
    )
    return {
        "total_display": _money(total, unit) if money else _persian_digits(int(total)),
        "total_label": "مجموع" if money else "مجموع تعداد",
    }


def _counted(rows, labels=None):
    """`[(key, count)]` into chart rows, largest first, with a grouped tail."""
    named = []
    for key, count in rows:
        label = (labels or {}).get(key) or (str(key).strip() if key else "") or UNLABELLED
        named.append((label, count))
    named.sort(key=lambda item: (-item[1], item[0]))

    head, tail = named[:TOP_N], named[TOP_N:]
    result = [
        {"label": label, "value": count, "display": _persian_digits(count)}
        for label, count in head
    ]
    if tail:
        remainder = sum(count for _, count in tail)
        result.append({
            "label": "سایر",
            "value": remainder,
            "display": _persian_digits(remainder),
        })
    return result


def _amounts(rows, labels=None, unit="rial"):
    """The same, for money rather than counts."""
    named = []
    for key, total in rows:
        label = (labels or {}).get(key) or (str(key).strip() if key else "") or UNLABELLED
        named.append((label, Decimal(total or 0)))
    named.sort(key=lambda item: (-item[1], item[0]))

    head, tail = named[:TOP_N], named[TOP_N:]
    result = [
        {"label": label, "value": float(total), "display": _money(total, unit)}
        for label, total in head
    ]
    if tail:
        remainder = sum(total for _, total in tail)
        result.append({
            "label": "سایر",
            "value": float(remainder),
            "display": _money(remainder, unit),
        })
    return result


def _grouped_count(queryset, field):
    return [
        (row[field], row["total"])
        for row in queryset.values(field).annotate(total=Count("id")).order_by()
    ]


def _grouped_sum(queryset, field, amount_field):
    return [
        (row[field], row["total"])
        for row in queryset.values(field)
        .annotate(total=Coalesce(Sum(amount_field), Decimal("0.00")))
        .order_by()
    ]


def _narrowed(selector, actor, narrow):
    """That module's scoped queryset, with the reader's own filters applied.

    Every builder starts here rather than calling its selector directly, so a
    filter can only ever make a chart show *less* — it is applied after the
    scope, never instead of it, and a key with no declared filters passes
    `None` and gets exactly the queryset it always had.
    """
    queryset = selector(actor)
    return narrow(queryset) if narrow else queryset


# --- builders ---------------------------------------------------------------


def invoices_by_settlement(actor, narrow=None):
    """Counted by reading the property, not by rebuilding it in SQL.

    `Invoice.settlement_status` folds in the manual-settlement override, which
    is a display decision with no accounting effect. Re-expressing that as a
    CASE would put the same rule in two places, and the day they disagreed the
    chart would quietly contradict the invoice it came from.
    """
    labels = dict(Invoice.SettlementStatus.choices)
    persian = {
        Invoice.SettlementStatus.UNPAID: "تسویه‌نشده",
        Invoice.SettlementStatus.PARTIALLY_PAID: "تسویه جزئی",
        Invoice.SettlementStatus.PAID: "تسویه‌شده",
    }
    counts = {}
    for invoice in _narrowed(invoices_for, actor, narrow).only(
        "status", "paid_amount", "total_amount", "manual_settled_at"
    ):
        key = invoice.settlement_status
        counts[key] = counts.get(key, 0) + 1
    return _counted(counts.items(), {k: persian.get(k, labels.get(k)) for k in counts})


def orders_by_status(actor, narrow=None):
    labels = {
        "draft": "پیش‌نویس",
        "confirmed": "تأییدشده",
        "fulfilled": "تحویل‌شده",
        "cancelled": "لغوشده",
    }
    return _counted(_grouped_count(_narrowed(orders_for, actor, narrow), "status"), labels)


def payments_by_method(actor, narrow=None):
    labels = {
        Payment.Method.CASH: "نقدی",
        Payment.Method.BANK_TRANSFER: "حواله بانکی",
        Payment.Method.CHEQUE: "چک",
        Payment.Method.CARD: "کارت",
    }
    # Receipts only. Once disbursements share this table, summing without the
    # direction filter would add money paid out to money taken in and report the
    # total as income — a wrong number that looks entirely plausible.
    #
    # Cancelled receipts are excluded too: a chart of money received should not
    # count money that was given back.
    scoped = (
        _narrowed(payments_for, actor, narrow)
        .filter(direction=Payment.Direction.RECEIPT)
        .exclude(status=Payment.Status.CANCELLED)
    )
    return _amounts(_grouped_sum(scoped, "method", "amount"), labels, unit_for(actor))


def payments_by_direction(actor, narrow=None):
    """Money in against money out, from the same table."""
    labels = {
        Payment.Direction.RECEIPT: "دریافتی",
        Payment.Direction.DISBURSEMENT: "پرداختی",
    }
    scoped = _narrowed(payments_for, actor, narrow).exclude(status=Payment.Status.CANCELLED)
    return _amounts(_grouped_sum(scoped, "direction", "amount"), labels, unit_for(actor))


def products_by_category(actor, narrow=None):
    return _counted(_grouped_count(_narrowed(products_for, actor, narrow), "category__name"))


def categories_by_active_products(actor, narrow=None):
    """Active products per category, counted through the product scope.

    `filter=` on the aggregate rather than on the queryset, so a category with
    no active product still appears — at zero — instead of vanishing from its
    own page.
    """
    rows = (
        _narrowed(product_categories_for, actor, narrow)
        .values("name")
        .annotate(total=Count("products", filter=Q(products__is_active=True)))
        .order_by()
    )
    return _counted([(row["name"], row["total"]) for row in rows])


def leads_by_status(actor, narrow=None):
    labels = {
        Lead.Status.PENDING: "در انتظار",
        Lead.Status.COMPLETED: "تکمیل‌شده",
        Lead.Status.CANCELLED: "لغوشده",
    }
    return _counted(_grouped_count(_narrowed(leads_for, actor, narrow), "status"), labels)


def after_sales_by_status(actor, narrow=None):
    # Free text rather than a fixed vocabulary, so whatever operators recorded
    # is what is charted.
    return _counted(_grouped_count(_narrowed(after_sales_requests_for, actor, narrow), "status"))


def documents_by_postal_status(actor, narrow=None):
    """Grouped by the state's own Persian label since 3.0.0.

    `postal_status` holds a vocabulary key on a row written since then and
    whatever an operator typed on an older one. Labelling through
    `postal.label_for` folds «ارسال به پست» and `handed_to_post` into one
    slice — they are the same state — while a genuinely free-text value
    still appears under exactly the words that were recorded.
    """
    from sales import postal

    rows = _grouped_count(_narrowed(sales_documents_for, actor, narrow), "postal_status")
    folded = {}
    for value, count in rows:
        folded[postal.label_for(value)] = folded.get(postal.label_for(value), 0) + count
    return _counted(folded.items())


def stock_value_by_warehouse(actor, narrow=None):
    """Stock value is `quantity * average_cost`; there is no such column."""
    rows = (
        _narrowed(stock_items_for, actor, narrow)
        .values("warehouse__name")
        .annotate(
            total=Coalesce(
                Sum(
                    F("quantity") * F("average_cost"),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                ),
                Decimal("0.00"),
            )
        )
        .order_by()
    )
    return _amounts([(row["warehouse__name"], row["total"]) for row in rows], unit=unit_for(actor))


def sales_by_agent(actor, narrow=None):
    """Confirmed sales only — a cancelled sale is not an agent's result."""
    scoped = _narrowed(sales_for, actor, narrow).filter(status=Sale.Status.CONFIRMED)
    rows = (
        scoped.values("sold_by__username")
        .annotate(total=Coalesce(Sum("total_amount"), Decimal("0.00")))
        .order_by()
    )
    return _amounts([(row["sold_by__username"], row["total"]) for row in rows], unit=unit_for(actor))


def interactions_by_outcome(actor, narrow=None):
    return _counted(_grouped_count(_narrowed(interactions_for, actor, narrow), "outcome"))


# --- the registry -----------------------------------------------------------

#: key -> (feature, capabilities, builder, title)
LIST_CHARTS = {
    "invoices": ("invoices", ("invoices.scoped", "invoices.company"),
                 invoices_by_settlement, "تعداد فاکتور به تفکیک وضعیت تسویه"),
    "orders": ("orders", ("orders.scoped", "orders.company"),
               orders_by_status, "تعداد سفارش به تفکیک وضعیت"),
    "payments": ("payments", ("payments.company",),
                 payments_by_method, "مبلغ دریافتی به تفکیک روش"),
    "payments-direction": ("payments", ("payments.company",),
                           payments_by_direction, "مبلغ به تفکیک جهت (دریافتی/پرداختی)"),
    "products": ("products", ("products.read", "products.manage"),
                 products_by_category, "تعداد محصول به تفکیک دسته‌بندی"),
    "product-categories": ("products", ("products.read", "products.manage"),
                           categories_by_active_products, "محصول فعال در هر دسته‌بندی"),
    "leads": ("leads", ("leads.scoped", "leads.company"),
              leads_by_status, "تعداد سرنخ به تفکیک وضعیت"),
    "after-sales": ("after_sales", ("after_sales.assigned", "after_sales.company", "after_sales.manage"),
                    after_sales_by_status, "تعداد درخواست به تفکیک وضعیت"),
    "sales-documents": ("sales_documents", ("sales_documents.company", "sales_documents.manage"),
                        documents_by_postal_status, "تعداد مرسوله به تفکیک وضعیت پستی"),
    "inventory": ("inventory", ("inventory.read", "inventory.manage"),
                  stock_value_by_warehouse, "ارزش موجودی به تفکیک انبار"),
    "sales": ("sales", ("sales.own", "sales.company"),
              sales_by_agent, "مبلغ فروش تأییدشده به تفکیک بازاریاب"),
    # Gated by `leads`, matching InteractionViewSet: there is no separate
    # interactions feature, and inventing one here would let a chart appear on
    # a deployment that has no such page.
    "interactions": ("leads", ("interactions.scoped", "interactions.company"),
                     interactions_by_outcome, "تعداد تماس به تفکیک نتیجه"),
}


# --- the optional filters ---------------------------------------------------

#: One declared filter on one chart.
#:
#: `param`     the query-string name the panel sends;
#: `label`     what the selector is called to a screen reader;
#: `all_label` the "no narrowing" option's own text — written out rather than
#:             composed, because «همهٔ» plus a singular noun is wrong Persian
#:             for half of these and pluralising in code is guesswork;
#: `lookup`    the ORM keyword it becomes, applied to the *already scoped*
#:             queryset — so a filter can only ever narrow what a chart shows;
#: `options`   a callable taking that scoped queryset and returning the values
#:             the panel may offer, `[{"value", "label"}]`.
ChartFilter = namedtuple("ChartFilter", "param label all_label lookup options")


def _choice_options(choices, labels=None):
    """A model's own `TextChoices`, in the order the model declares them."""

    def build(_queryset):
        return [
            {"value": value, "label": (labels or {}).get(value) or str(label)}
            for value, label in choices
        ]

    return build


def _related_options(field, label_field):
    """The distinct related rows that actually occur in this reader's scope.

    Derived from the scoped queryset rather than from the related model's own
    table, which is the whole reason this is safe without a second permission
    rule: a marketer offered the list of marketers whose leads they can already
    see is being offered nothing new.
    """

    def build(queryset):
        rows = (
            queryset.exclude(**{f"{field}__isnull": True})
            .values(field, label_field)
            .distinct()
            .order_by(label_field)
        )
        return [
            {"value": str(row[field]), "label": row[label_field] or UNLABELLED}
            for row in rows
        ]

    return build


def _text_options(field):
    """The distinct non-empty free-text values occurring in this reader's scope."""

    def build(queryset):
        rows = (
            queryset.exclude(**{field: ""})
            .exclude(**{f"{field}__isnull": True})
            .values_list(field, flat=True)
            .distinct()
            .order_by(field)
        )
        return [{"value": value, "label": value} for value in rows]

    return build


#: key -> the filters that key offers, in the order they are drawn.
#:
#: Product-owner request 2026-09-20: «فیلترهای معنادار اضافه شود (بر اساس
#: بازاریاب، وضعیت، منبع سرنخ)». Declared rather than written per chart for the
#: same reason `LIST_CHARTS` is: adding one to another key is a line in this
#: table, and there is exactly one place to read to know what a chart can be
#: narrowed by.
#:
#: Only columns a record really has appear here. A chart is not given a filter
#: because the filter sounds useful — an order has no marketer of its own, and
#: inventing one by joining through its lead would be a business rule this
#: table has no authority to invent.
CHART_FILTERS = {
    "leads": (
        ChartFilter("assigned_to", "بازاریاب", "همهٔ بازاریاب‌ها", "assigned_to_id",
                    _related_options("assigned_to_id", "assigned_to__username")),
        ChartFilter("status", "وضعیت", "همهٔ وضعیت‌ها", "status",
                    _choice_options(Lead.Status.choices, {
                        Lead.Status.PENDING: "در انتظار",
                        Lead.Status.COMPLETED: "تکمیل‌شده",
                        Lead.Status.CANCELLED: "لغوشده",
                    })),
        ChartFilter("source", "منبع سرنخ", "همهٔ منبع‌ها", "source",
                    _text_options("source")),
    ),
    "sales": (
        ChartFilter("sold_by", "بازاریاب", "همهٔ بازاریاب‌ها", "sold_by_id",
                    _related_options("sold_by_id", "sold_by__username")),
    ),
    "orders": (
        ChartFilter("status", "وضعیت", "همهٔ وضعیت‌ها", "status",
                    _choice_options(Order.Status.choices, {
                        "draft": "پیش‌نویس",
                        "confirmed": "تأییدشده",
                        "fulfilled": "تحویل‌شده",
                        "cancelled": "لغوشده",
                    })),
    ),
    "interactions": (
        ChartFilter("agent", "بازاریاب", "همهٔ بازاریاب‌ها", "agent_id",
                    _related_options("agent_id", "agent__username")),
        ChartFilter("outcome", "نتیجه", "همهٔ نتیجه‌ها", "outcome",
                    _text_options("outcome")),
    ),
    # Free text until 3.0.0, so the options are whatever this deployment's
    # rows actually hold rather than the vocabulary — which keeps a filter
    # honest on a database that predates it.
    "sales-documents": (
        ChartFilter("postal_status", "وضعیت پستی", "همهٔ وضعیت‌ها", "postal_status",
                    _text_options("postal_status")),
    ),
}


class UnknownChartFilter(ValueError):
    """A filter value the chart never offered."""


class InvalidChartPeriod(ValueError):
    """The requested window cannot be charted."""


def _filter_base(key, actor):
    """The scoped queryset a key's filter options are read from.

    Its *trend* selector, not its chart builder's: the two are the same for
    every key that declares a filter, and the trend selector is the one that
    is already a plain callable taking an actor.
    """
    entry = LIST_TRENDS.get(key)
    return entry[0](actor) if entry else None


def filters_for(key, actor):
    """What the panel may offer above this chart, with each option's own label.

    Empty for a key with nothing declared, and an individual filter with no
    options — a deployment where no lead has a source yet — is dropped rather
    than drawn as an empty selector.
    """
    declared = CHART_FILTERS.get(key)
    if not declared:
        return []
    base = _filter_base(key, actor)
    if base is None:
        return []
    offered = []
    for entry in declared:
        options = entry.options(base)
        if options:
            offered.append({
                "param": entry.param,
                "label": entry.label,
                "all_label": entry.all_label,
                "options": options,
            })
    return offered


#: The query parameters that are not filters. Named here so `filter_params`
#: has one place to subtract them from, rather than the view re-listing the
#: window serializer's own field names.
WINDOW_PARAMS = frozenset({"period_start", "period_end"})


def filter_params(key, params):
    """`params` split into this key's declared filters, or a refusal.

    The window serializer refuses an unknown query parameter
    (`RejectServerFieldsMixin`), which is right and is why the filters cannot
    simply be passed to it: which ones exist depends on the key. This keeps
    the same strictness for the other half — anything that is neither a
    window bound nor a filter this chart declares is refused by name rather
    than quietly dropped.
    """
    declared = {entry.param for entry in CHART_FILTERS.get(key, ())}
    unknown = sorted(set(params) - WINDOW_PARAMS - declared)
    if unknown:
        raise UnknownChartFilter(unknown[0])
    return {name: value for name, value in params.items() if name in declared}


def narrowing(key, actor, params):
    """A callable applying `params` to any queryset, or `None` for no filters.

    Every value is checked against the options this reader was actually
    offered. A value that was never offered is refused rather than ignored:
    silently dropping it would answer a different question than the one the
    URL asks, and silently accepting it would let the query string reach a
    column the table above never declared.
    """
    declared = {entry.param: entry for entry in CHART_FILTERS.get(key, ())}
    if not declared:
        return None
    wanted = {name: value for name, value in params.items() if name in declared and value}
    if not wanted:
        return None

    offered = {entry["param"]: {option["value"] for option in entry["options"]}
               for entry in filters_for(key, actor)}
    lookups = {}
    for name, value in wanted.items():
        if value not in offered.get(name, ()):  # includes a param with no options at all
            raise UnknownChartFilter(name)
        lookups[declared[name].lookup] = value

    def narrow(queryset):
        return queryset.filter(**lookups)

    return narrow


# --- the companion trend ----------------------------------------------------

#: How many weekly buckets the trend beside each list chart covers. The same
#: window the dashboard's own sales trend uses (`common/dashboard.py`,
#: `TREND_WEEKS`) — one convention for "recent direction" across the product,
#: not a second number invented here.
TREND_WEEKS = 12

#: key -> (selector, the dated column, title).
#:
#: Product-owner request 2026-09-19: every list page that draws a composition
#: chart ("what is this total made of") should draw a direction chart beside
#: it ("which way is it going"), because a ring alone never answers the second
#: question. The pair is deliberate — one is a breakdown, the other is time.
#:
#: The column named for each key is that record's own real business date, not
#: `created_at` reflexively: a payment is dated when it was received, a
#: campaign result when it was sold, a parcel when it was registered, an
#: interaction when it happened. Where a model genuinely has no business date
#: of its own (orders, invoices, leads, products, categories, after-sales
#: requests), `created_at` *is* the date it was entered and is named as such.
#:
#: Inventory is the one entry that does not share its chart's own selector:
#: `stock_items_for` rows are per product-and-warehouse balances whose
#: `created_at` says when a balance row first appeared, which is not a fact
#: anybody wants plotted. The movements behind those balances are, so the
#: trend reads `stock_movements_for` — still an inventory selector, still the
#: same feature and capabilities gate, so it can never show more than the
#: chart beside it.
#: The title is the *subject* only — «روند ثبت سرنخ» — and the window is
#: appended by `_ranged_title` from the range actually drawn. They used to read
#: «… در دوازده هفتهٔ اخیر» with the twelve weeks written into the string, which
#: became a lie the moment 2.11.0 let a reader ask for thirty days (product
#: owner, 2026-09-20: «عنوان/نام هر چارت با داده‌اش تطبیق داده شود»).
LIST_TRENDS = {
    "invoices": (invoices_for, "created_at", "روند صدور فاکتور"),
    "orders": (orders_for, "created_at", "روند ثبت سفارش"),
    "payments": (payments_for, "received_at", "روند ثبت پرداخت"),
    "payments-direction": (payments_for, "received_at", "روند ثبت پرداخت"),
    "products": (products_for, "created_at", "روند افزودن محصول"),
    "product-categories": (product_categories_for, "created_at", "روند افزودن دسته‌بندی"),
    "leads": (leads_for, "created_at", "روند ثبت سرنخ"),
    "after-sales": (after_sales_requests_for, "created_at", "روند ثبت درخواست"),
    "sales-documents": (sales_documents_for, "registered_at", "روند ثبت مرسوله"),
    "inventory": (stock_movements_for, "occurred_at", "روند گردش انبار"),
    "sales": (sales_for, "sold_at", "روند ثبت نتیجهٔ کمپین"),
    "interactions": (interactions_for, "occurred_at", "روند تماس‌ها"),
}


#: What each preset window is called in a chart title. The panel sends the
#: window itself, not its name, so this is the one place the two are tied
#: together — a title that said «۳۰ روز» for a window the reader had widened
#: is precisely the mismatch 2.11.0 set out to fix.
RANGE_TITLES = {
    1: "در ۲۴ ساعت گذشته",
    7: "در هفتهٔ گذشته",
    30: "در ۳۰ روز گذشته",
    90: "در سه ماه گذشته",
    365: "در یک سال گذشته",
}


def _ranged_title(subject, period_start, period_end, *, now):
    """`subject` plus the window it was actually drawn over.

    A window that ends now and matches a preset is named — the reader picked
    that name and should read it back. Anything else is spelled out as two
    Jalali dates, which is the only honest description of a custom range.
    """
    days = round((period_end - period_start).total_seconds() / 86400)
    recent = abs((now - period_end).total_seconds()) < 3600
    if recent and days in RANGE_TITLES:
        return f"{subject} {RANGE_TITLES[days]}"
    return (
        f"{subject} از {bucket_label_value(timezone.localdate(period_start))}"
        f" تا {bucket_label_value(timezone.localdate(period_end))}"
    )


def trend_for(key, actor, *, now=None, period_start=None, period_end=None, narrow=None):
    """Record counts per bucket across the window, oldest first.

    Bucketed in Python over one ordered range scan rather than with a database
    date-truncation function, for the reason `common/dashboard.py` already
    records for its own trend: this codebase runs on PostgreSQL in production
    and SQLite in development, and the two disagree about where a week starts.
    The arithmetic itself lives in `reports.ranges` so that this module and the
    two growth reports bucket a window the same way.

    The window defaults to the twelve weeks this chart has always shown, so a
    caller that asks for nothing gets exactly what it used to get. How wide a
    bucket is follows from the window rather than being chosen beside it, which
    is why thirty days draws thirty points and a year draws twelve.

    Returns `None` for a key with no trend declared, so a chart that has one
    and a chart that does not both render correctly rather than the caller
    having to know which is which.
    """
    entry = LIST_TRENDS.get(key)
    if entry is None:
        return None
    selector, field, subject = entry

    local_now = timezone.localtime(now or timezone.now())
    if period_end is None:
        period_end = local_now
    if period_start is None:
        start_of_today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_start = start_of_today - timedelta(
            weeks=TREND_WEEKS - 1, days=local_now.weekday()
        )
    if period_start >= period_end:
        raise InvalidChartPeriod("تاریخ شروع بازه باید پیش از پایان آن باشد.")

    granularity = granularity_for(period_start, period_end)
    starts = local_bucket_starts(granularity, period_start, period_end)
    if not starts:
        return None

    counts = [0] * len(starts)
    queryset = _narrowed(selector, actor, narrow)
    values = queryset.filter(
        **{f"{field}__gte": starts[0], f"{field}__lt": period_end}
    ).values_list(field, flat=True)
    for moment in values:
        if moment is None:
            continue
        index = bucket_index(granularity, starts, moment)
        if index is not None:
            counts[index] += 1

    points = [
        {
            "label": bucket_label_value(
                start if granularity == "hour" else start.date()
            ),
            "value": count,
            "display": _persian_digits(count),
        }
        for start, count in zip(starts, counts)
    ]
    total = sum(counts)
    return {
        "title": _ranged_title(subject, period_start, period_end, now=local_now),
        "granularity": granularity,
        "points": points,
        "summary": f"مجموع این بازه: {_persian_digits(total)} مورد",
    }
