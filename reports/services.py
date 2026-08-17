from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, Sum
from django.utils import timezone

from accounts.access import crm_identities
from accounts.models import User
from reports.selectors import REPORT_ROLES, users_for_performance_report
from sales.models import Customer, Sale
from sales.selectors import sales_documents_for


MONEY_QUANTUM = Decimal("0.01")


class InvalidReportUser(ValueError):
    pass


class InvalidReportPeriod(ValueError):
    pass


class ReportAccessDenied(PermissionError):
    pass


PERFORMANCE_METRICS = {
    "customers_created_count",
    "sales_count",
    "sales_amount",
    "average_sale_amount",
}


@dataclass(frozen=True)
class UserPerformanceRow:
    user_id: int
    username: str
    customers_created_count: int
    sales_count: int
    sales_amount: Decimal
    average_sale_amount: Decimal


@dataclass(frozen=True)
class UserPerformanceSummary:
    customers_created_count: int
    sales_count: int
    sales_amount: Decimal
    average_sale_amount: Decimal


@dataclass(frozen=True)
class UserPerformanceReport:
    period_start: str
    period_end: str
    user_id: int | None
    sales_product_id: int | None
    results: tuple[UserPerformanceRow, ...]

    @property
    def summary(self) -> UserPerformanceSummary:
        customers_created_count = sum(row.customers_created_count for row in self.results)
        sales_count = sum(row.sales_count for row in self.results)
        sales_amount = sum(
            (row.sales_amount for row in self.results),
            start=Decimal("0.00"),
        ).quantize(MONEY_QUANTUM)
        average_sale_amount = (
            (sales_amount / sales_count).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
            if sales_count
            else Decimal("0.00")
        )
        return UserPerformanceSummary(
            customers_created_count=customers_created_count,
            sales_count=sales_count,
            sales_amount=sales_amount,
            average_sale_amount=average_sale_amount,
        )


@dataclass(frozen=True)
class SalesDocumentReport:
    period_start: str
    period_end: str
    filters: dict
    total: int
    by_geography: tuple[dict, ...]
    by_postal_status: tuple[dict, ...]


def format_utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _performance_scope(*, actor, period_start, period_end, user_id=None):
    # A plain read: this report writes nothing, so it takes no row lock. It used
    # to `select_for_update` the actor's own user row, which serialised
    # concurrent report requests and blocked role changes and account edits on
    # that row for as long as the report ran.
    current_actor = crm_identities(
        User.objects.filter(
            pk=getattr(actor, "pk", None),
            is_active=True,
            role__in=REPORT_ROLES,
        )
    ).first()
    if current_actor is None:
        raise ReportAccessDenied
    if current_actor.role == User.Role.SALES_AGENT and current_actor.workstream == User.Workstream.AFTER_SALES:
        raise ReportAccessDenied
    if timezone.is_naive(period_start) or timezone.is_naive(period_end) or period_end <= period_start:
        raise InvalidReportPeriod
    period_start = period_start.astimezone(UTC)
    period_end = period_end.astimezone(UTC)
    users_queryset = users_for_performance_report(current_actor)
    if user_id is not None:
        users_queryset = users_queryset.filter(pk=user_id)
    users = list(users_queryset.values("id", "username"))
    if not users and user_id is not None:
        raise InvalidReportUser
    return period_start, period_end, users


def build_user_performance_report(
    *,
    actor,
    period_start: datetime,
    period_end: datetime,
    user_id: int | None = None,
    sales_product_id: int | None = None,
) -> UserPerformanceReport:
    period_start, period_end, users = _performance_scope(
        actor=actor,
        period_start=period_start,
        period_end=period_end,
        user_id=user_id,
    )
    user_ids = [user["id"] for user in users]
    customer_counts = {
        row["created_by_id"]: row["value"]
        for row in Customer.objects.filter(
            created_by_id__in=user_ids,
            created_at__gte=period_start,
            created_at__lt=period_end,
        )
        .values("created_by_id")
        .annotate(value=Count("id"))
    }

    sales_queryset = Sale.objects.filter(
        sold_by_id__in=user_ids,
        status=Sale.Status.CONFIRMED,
        sold_at__gte=period_start,
        sold_at__lt=period_end,
    )
    if sales_product_id is not None:
        sales_queryset = sales_queryset.filter(product_id=sales_product_id)
    sale_totals = {
        row["sold_by_id"]: row
        for row in sales_queryset.values("sold_by_id").annotate(
            sales_count=Count("id"),
            sales_amount=Sum("total_amount"),
        )
    }

    rows = []
    for user in users:
        sale_total = sale_totals.get(user["id"])
        sales_count = sale_total["sales_count"] if sale_total else 0
        sales_amount = (
            Decimal(sale_total["sales_amount"]).quantize(MONEY_QUANTUM)
            if sale_total
            else Decimal("0.00")
        )
        average_sale_amount = (
            (sales_amount / sales_count).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
            if sales_count
            else Decimal("0.00")
        )
        rows.append(
            UserPerformanceRow(
                user_id=user["id"],
                username=user["username"],
                customers_created_count=customer_counts.get(user["id"], 0),
                sales_count=sales_count,
                sales_amount=sales_amount,
                average_sale_amount=average_sale_amount,
            )
        )

    return UserPerformanceReport(
        period_start=format_utc_timestamp(period_start),
        period_end=format_utc_timestamp(period_end),
        user_id=user_id,
        sales_product_id=sales_product_id,
        results=tuple(rows),
    )


def user_performance_details(
    *, actor, period_start, period_end, metric, user_id=None, sales_product_id=None,
):
    period_start, period_end, users = _performance_scope(
        actor=actor,
        period_start=period_start,
        period_end=period_end,
        user_id=user_id,
    )
    if metric not in PERFORMANCE_METRICS:
        raise ValueError("Invalid performance metric.")
    user_ids = [user["id"] for user in users]
    if metric == "customers_created_count":
        return "customer", Customer.objects.filter(
            created_by_id__in=user_ids,
            created_at__gte=period_start,
            created_at__lt=period_end,
        ).select_related("created_by").order_by("-created_at", "-id")
    queryset = Sale.objects.filter(
        sold_by_id__in=user_ids,
        status=Sale.Status.CONFIRMED,
        sold_at__gte=period_start,
        sold_at__lt=period_end,
    ).select_related("customer", "product", "sold_by").order_by("-sold_at", "-id")
    if sales_product_id is not None:
        queryset = queryset.filter(product_id=sales_product_id)
    return "sale", queryset


def build_sales_document_report(
    *, actor, period_start: datetime, period_end: datetime,
    province: str | None = None, city: str | None = None,
    postal_status: str | None = None, is_active: bool | None = None,
) -> SalesDocumentReport:
    current_actor = crm_identities(
        User.objects.filter(
            pk=getattr(actor, "pk", None),
            is_active=True,
            role__in=REPORT_ROLES,
        )
    ).first()
    if current_actor is None:
        raise ReportAccessDenied
    if current_actor.role == User.Role.SALES_AGENT and current_actor.workstream == User.Workstream.AFTER_SALES:
        raise ReportAccessDenied
    if timezone.is_naive(period_start) or timezone.is_naive(period_end) or period_end <= period_start:
        raise InvalidReportPeriod
    period_start = period_start.astimezone(UTC)
    period_end = period_end.astimezone(UTC)
    queryset = sales_documents_for(current_actor).filter(
        registered_at__gte=period_start,
        registered_at__lt=period_end,
    )
    filters = {"province": province, "city": city, "postal_status": postal_status, "is_active": is_active}
    for field, value in (
        ("province_snapshot", province), ("city_snapshot", city), ("postal_status", postal_status),
    ):
        if value is not None:
            queryset = queryset.filter(**{field: value})
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    geography = queryset.values("province_snapshot", "city_snapshot").annotate(count=Count("id")).order_by("province_snapshot", "city_snapshot")
    statuses = queryset.values("postal_status").annotate(count=Count("id")).order_by("postal_status")
    return SalesDocumentReport(
        period_start=format_utc_timestamp(period_start), period_end=format_utc_timestamp(period_end),
        filters=filters, total=queryset.count(),
        by_geography=tuple({"province": row["province_snapshot"], "city": row["city_snapshot"], "count": row["count"]} for row in geography),
        by_postal_status=tuple(statuses),
    )
