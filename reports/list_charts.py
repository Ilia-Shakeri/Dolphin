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
from datetime import timedelta
from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from aftersales.selectors import after_sales_requests_for
from billing.models import Invoice, Payment
from billing.selectors import invoices_for, orders_for, payments_for
from inventory.selectors import stock_items_for, stock_movements_for
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


def totals_for(result):
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
    money = any(str(row.get("display", "")).endswith("ریال") for row in result)
    return {
        "total_display": _money(total) if money else _persian_digits(int(total)),
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


def _amounts(rows, labels=None):
    """The same, for money rather than counts."""
    named = []
    for key, total in rows:
        label = (labels or {}).get(key) or (str(key).strip() if key else "") or UNLABELLED
        named.append((label, Decimal(total or 0)))
    named.sort(key=lambda item: (-item[1], item[0]))

    head, tail = named[:TOP_N], named[TOP_N:]
    result = [
        {"label": label, "value": float(total), "display": _money(total)}
        for label, total in head
    ]
    if tail:
        remainder = sum(total for _, total in tail)
        result.append({
            "label": "سایر",
            "value": float(remainder),
            "display": _money(remainder),
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


# --- builders ---------------------------------------------------------------


def invoices_by_settlement(actor):
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
    for invoice in invoices_for(actor).only(
        "status", "paid_amount", "total_amount", "manual_settled_at"
    ):
        key = invoice.settlement_status
        counts[key] = counts.get(key, 0) + 1
    return _counted(counts.items(), {k: persian.get(k, labels.get(k)) for k in counts})


def orders_by_status(actor):
    from billing.models import Order

    labels = {
        "draft": "پیش‌نویس",
        "confirmed": "تأییدشده",
        "fulfilled": "تحویل‌شده",
        "cancelled": "لغوشده",
    }
    return _counted(_grouped_count(orders_for(actor), "status"), labels)


def payments_by_method(actor):
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
        payments_for(actor)
        .filter(direction=Payment.Direction.RECEIPT)
        .exclude(status=Payment.Status.CANCELLED)
    )
    return _amounts(_grouped_sum(scoped, "method", "amount"), labels)


def payments_by_direction(actor):
    """Money in against money out, from the same table."""
    labels = {
        Payment.Direction.RECEIPT: "دریافتی",
        Payment.Direction.DISBURSEMENT: "پرداختی",
    }
    scoped = payments_for(actor).exclude(status=Payment.Status.CANCELLED)
    return _amounts(_grouped_sum(scoped, "direction", "amount"), labels)


def products_by_category(actor):
    return _counted(_grouped_count(products_for(actor), "category__name"))


def categories_by_active_products(actor):
    """Active products per category, counted through the product scope.

    `filter=` on the aggregate rather than on the queryset, so a category with
    no active product still appears — at zero — instead of vanishing from its
    own page.
    """
    rows = (
        product_categories_for(actor)
        .values("name")
        .annotate(total=Count("products", filter=Q(products__is_active=True)))
        .order_by()
    )
    return _counted([(row["name"], row["total"]) for row in rows])


def leads_by_status(actor):
    labels = {
        Lead.Status.PENDING: "در انتظار",
        Lead.Status.COMPLETED: "تکمیل‌شده",
        Lead.Status.CANCELLED: "لغوشده",
    }
    return _counted(_grouped_count(leads_for(actor), "status"), labels)


def after_sales_by_status(actor):
    # Free text rather than a fixed vocabulary, so whatever operators recorded
    # is what is charted.
    return _counted(_grouped_count(after_sales_requests_for(actor), "status"))


def documents_by_postal_status(actor):
    return _counted(_grouped_count(sales_documents_for(actor), "postal_status"))


def stock_value_by_warehouse(actor):
    """Stock value is `quantity * average_cost`; there is no such column."""
    rows = (
        stock_items_for(actor)
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
    return _amounts([(row["warehouse__name"], row["total"]) for row in rows])


def sales_by_agent(actor):
    """Confirmed sales only — a cancelled sale is not an agent's result."""
    scoped = sales_for(actor).filter(status=Sale.Status.CONFIRMED)
    rows = (
        scoped.values("sold_by__username")
        .annotate(total=Coalesce(Sum("total_amount"), Decimal("0.00")))
        .order_by()
    )
    return _amounts([(row["sold_by__username"], row["total"]) for row in rows])


def interactions_by_outcome(actor):
    return _counted(_grouped_count(interactions_for(actor), "outcome"))


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
LIST_TRENDS = {
    "invoices": (invoices_for, "created_at", "روند صدور فاکتور در دوازده هفتهٔ اخیر"),
    "orders": (orders_for, "created_at", "روند ثبت سفارش در دوازده هفتهٔ اخیر"),
    "payments": (payments_for, "received_at", "روند ثبت پرداخت در دوازده هفتهٔ اخیر"),
    "payments-direction": (payments_for, "received_at", "روند ثبت پرداخت در دوازده هفتهٔ اخیر"),
    "products": (products_for, "created_at", "روند افزودن محصول در دوازده هفتهٔ اخیر"),
    "product-categories": (product_categories_for, "created_at",
                           "روند افزودن دسته‌بندی در دوازده هفتهٔ اخیر"),
    "leads": (leads_for, "created_at", "روند ثبت سرنخ در دوازده هفتهٔ اخیر"),
    "after-sales": (after_sales_requests_for, "created_at",
                    "روند ثبت درخواست در دوازده هفتهٔ اخیر"),
    "sales-documents": (sales_documents_for, "registered_at",
                        "روند ثبت مرسوله در دوازده هفتهٔ اخیر"),
    "inventory": (stock_movements_for, "occurred_at", "روند گردش انبار در دوازده هفتهٔ اخیر"),
    "sales": (sales_for, "sold_at", "روند ثبت نتیجهٔ کمپین در دوازده هفتهٔ اخیر"),
    "interactions": (interactions_for, "occurred_at", "روند تماس‌ها در دوازده هفتهٔ اخیر"),
}


def _jalali_day(value):
    from common.jalali import format_date

    return format_date(value)


def trend_for(key, actor, *, now=None):
    """Weekly record counts for the last `TREND_WEEKS` weeks, oldest first.

    Bucketed in Python over one ordered range scan rather than with a database
    date-truncation function, for the reason `common/dashboard.py` already
    records for its own trend: this codebase runs on PostgreSQL in production
    and SQLite in development, and the two disagree about where a week starts.

    Returns `None` for a key with no trend declared, so a chart that has one
    and a chart that does not both render correctly rather than the caller
    having to know which is which.
    """
    entry = LIST_TRENDS.get(key)
    if entry is None:
        return None
    selector, field, title = entry

    local_now = timezone.localtime(now or timezone.now())
    start_of_today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    first_bucket_start = start_of_today - timedelta(
        weeks=TREND_WEEKS - 1, days=local_now.weekday()
    )

    buckets = [0] * TREND_WEEKS
    values = selector(actor).filter(**{f"{field}__gte": first_bucket_start}).values_list(
        field, flat=True
    )
    for moment in values:
        if moment is None:
            continue
        index = (timezone.localtime(moment) - first_bucket_start).days // 7
        if 0 <= index < TREND_WEEKS:
            buckets[index] += 1

    points = [
        {
            "label": _jalali_day(first_bucket_start + timedelta(weeks=index)),
            "value": count,
            "display": _persian_digits(count),
        }
        for index, count in enumerate(buckets)
    ]
    total = sum(buckets)
    return {
        "title": title,
        "points": points,
        "summary": f"مجموع این بازه: {_persian_digits(total)} مورد",
    }
