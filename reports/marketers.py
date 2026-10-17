"""Marketers side by side, ranked (2.40.34).

Product owner, 2026-10-07: «باید صفحه‌ای برای تحلیل کلی بازاریاب‌ها و رنکینگ
آن‌ها بر اساس فروش و آپشن‌های دیگر وجود داشته باشد».

One row per marketer (a Sales Agent of the sales workstream) for a window:
what they sold (issued invoices they made — the same definition the dashboard
uses since 2.39.27), what of it was collected, the customers they added, the
calls they logged, the leads they were given and closed. Ranked by whichever
of those the reader chooses, with the rank each held over the window of the
same length just before, so a climb or a fall shows. Company-wide figures:
`reports.company` only.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, Q, Sum

from accounts.access import crm_identities, has_any_capability
from accounts.models import User
from billing.models import Invoice

from reports.services import MONEY_QUANTUM, InvalidReportPeriod, ReportAccessDenied, format_utc_timestamp
from sales.conversion import definitions, figure, rate
from sales.models import Customer, Interaction

#: What a ranking can be by, with the Persian name the page shows.
RANKINGS = {
    "sales_amount": "مبلغ فروش",
    "sales_count": "تعداد فاکتور",
    "collected_amount": "وصول‌شده",
    "average_amount": "میانگین فاکتور",
    "customers_count": "مشتری تازه",
    "calls_count": "تماس",
    "successful_calls": "تماس موفق",
    "qualified_calls": "تماس واجد شرایط",
    "conversion_rate": "نرخ تبدیل سرنخ به فروش",
    "resolution_rate": "نرخ تعیین تکلیف",
}


@dataclass(frozen=True)
class MarketerRow:
    user_id: int
    name: str
    rank: int
    previous_rank: int | None
    sales_count: int
    sales_amount: Decimal
    collected_amount: Decimal
    average_amount: Decimal
    customers_count: int
    calls_count: int
    #: Calls where someone was really reached, and calls a real need was
    #: confirmed on (2.40.58, BIZ-003) — counted apart from the calls and
    #: from the sales, never added into either.
    successful_calls: int
    qualified_calls: int
    #: The unified rates (2.40.59, BIZ-004; `sales.conversion`): lead-to-sale
    #: over the qualified leads given to them in the window (`conversion_rate`,
    #: with its numerator and denominator), resolution over their leads closed
    #: in the window, and repeat purchases apart.
    qualified_leads: int
    won_leads: int
    conversion_rate: Decimal | None
    closed_leads: int
    closed_won: int
    resolution_rate: Decimal | None
    repeat_purchases: int
    share: Decimal


def marketers_queryset():
    """Every active marketer (Sales Agent of the sales workstream), the people
    the ranking and the monthly targets are about."""
    return crm_identities(
        User.objects.filter(is_active=True, role=User.Role.SALES_AGENT).exclude(workstream=User.Workstream.AFTER_SALES)
    ).order_by("id")


def _figures(user_ids, start, end):
    invoices = {
        row["created_by_id"]: row
        for row in Invoice.objects.filter(
            created_by_id__in=user_ids, status=Invoice.Status.ISSUED, issued_at__gte=start, issued_at__lt=end,
        ).values("created_by_id").annotate(count=Count("id"), amount=Sum("total_amount"), paid=Sum("paid_amount"))
    }
    customers = dict(
        Customer.objects.filter(created_by_id__in=user_ids, created_at__gte=start, created_at__lt=end)
        .values_list("created_by_id").annotate(n=Count("id"))
    )
    from sales.call_outcomes import SUCCESSFUL

    calls = {
        row["agent_id"]: row
        for row in Interaction.objects.filter(agent_id__in=user_ids, occurred_at__gte=start, occurred_at__lt=end)
        .values("agent_id")
        .annotate(
            n=Count("id"),
            successful=Count("id", filter=Q(result_standard__in=SUCCESSFUL)),
            qualified=Count("id", filter=Q(qualified=True)),
        )
    }
    from sales.conversion import per_owner

    return invoices, customers, calls, per_owner(user_ids, start, end)


def _money(value):
    return Decimal(value or 0).quantize(MONEY_QUANTUM)


def _metric_rows(users, start, end):
    ids = [user.pk for user in users]
    invoices, customers, calls, leads = _figures(ids, start, end)
    rows = {}
    for user in users:
        sold = invoices.get(user.pk, {})
        count = sold.get("count", 0)
        amount = _money(sold.get("amount"))
        handed = leads[user.pk]
        called = calls.get(user.pk, {})
        rows[user.pk] = {
            "sales_count": count,
            "sales_amount": amount,
            "collected_amount": _money(sold.get("paid")),
            "average_amount": (amount / count).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP) if count else Decimal("0.00"),
            "customers_count": customers.get(user.pk, 0),
            "calls_count": called.get("n", 0),
            "successful_calls": called.get("successful", 0),
            "qualified_calls": called.get("qualified", 0),
            "qualified_leads": handed["qualified"],
            "won_leads": handed["won"],
            "conversion_rate": rate(handed["won"], handed["qualified"]),
            "closed_leads": handed["closed"],
            "closed_won": handed["closed_won"],
            "resolution_rate": rate(handed["closed_won"], handed["closed"]),
            "repeat_purchases": handed["repeat"],
        }
    return rows


def _ranks(rows, ordering):
    """Competition ranking (1, 2, 2, 4): equal figures share a place."""
    value = lambda pk: rows[pk][ordering] if rows[pk][ordering] is not None else Decimal("-1")
    ordered = sorted(rows, key=lambda pk: (-value(pk), pk))
    ranks, previous_value, previous_rank = {}, None, 0
    for position, pk in enumerate(ordered, start=1):
        if value(pk) != previous_value:
            previous_rank, previous_value = position, value(pk)
        ranks[pk] = previous_rank
    return ordered, ranks


def build_marketer_ranking(*, actor, period_start, period_end, ordering="sales_amount"):
    if not has_any_capability(actor, "reports.company"):
        raise ReportAccessDenied
    if ordering not in RANKINGS:
        ordering = "sales_amount"
    if period_end <= period_start:
        raise InvalidReportPeriod
    users = list(marketers_queryset())
    current = _metric_rows(users, period_start, period_end)
    length = period_end - period_start
    before = _metric_rows(users, period_start - length, period_start)
    ordered, ranks = _ranks(current, ordering)
    _, previous_ranks = _ranks(before, ordering)
    total_amount = sum((row["sales_amount"] for row in current.values()), start=Decimal("0.00"))
    names = {user.pk: user.get_full_name() or user.username for user in users}
    results = []
    for pk in ordered:
        row = current[pk]
        had_anything = any(before[pk][key] for key in ("sales_count", "customers_count", "calls_count", "qualified_leads", "closed_leads"))
        results.append(MarketerRow(
            user_id=pk,
            name=names[pk],
            rank=ranks[pk],
            previous_rank=previous_ranks[pk] if had_anything else None,
            share=(row["sales_amount"] * 100 / total_amount).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if total_amount else Decimal("0.0"),
            **row,
        ))
    return {
        "period_start": format_utc_timestamp(period_start),
        "period_end": format_utc_timestamp(period_end),
        "ordering": ordering,
        "orderings": [{"value": key, "label": label} for key, label in RANKINGS.items()],
        "totals": {
            "marketers": len(users),
            "sales_count": sum(row["sales_count"] for row in current.values()),
            "sales_amount": total_amount,
            "collected_amount": sum((row["collected_amount"] for row in current.values()), start=Decimal("0.00")),
            "customers_count": sum(row["customers_count"] for row in current.values()),
            "calls_count": sum(row["calls_count"] for row in current.values()),
            "successful_calls": sum(row["successful_calls"] for row in current.values()),
            "qualified_calls": sum(row["qualified_calls"] for row in current.values()),
            "lead_to_sale": figure(
                "lead_to_sale", sum(row["won_leads"] for row in current.values()),
                sum(row["qualified_leads"] for row in current.values()),
            ),
            "resolution": figure(
                "resolution", sum(row["closed_won"] for row in current.values()),
                sum(row["closed_leads"] for row in current.values()),
            ),
            "repeat_purchases": sum(row["repeat_purchases"] for row in current.values()),
        },
        "definitions": definitions(),
        "results": results,
    }


def default_window(now):
    """This month so far would rank nobody on its first day; the last thirty
    days always has a story."""
    return now - timedelta(days=30), now
