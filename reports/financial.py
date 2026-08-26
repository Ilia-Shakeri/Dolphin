"""Receivables, profit, and inventory valuation reports.

Every figure here is read from stored rows — issued invoice totals, recorded
allocations, and the unit cost snapshotted when the invoice was issued. Nothing
is modelled, estimated, or accrued. Where a number cannot be sourced the report
says so rather than substituting zero:

* an invoice line issued without a warehouse has no cost snapshot, so its
  invoice is reported as **unmeasured** and kept out of the profit totals;
* an invoice with no `due_at` is treated as due on issue, which is what
  `BILLING_INVOICE_DUE_DAYS = 0` already means elsewhere.

Aging buckets are the conventional 1–30 / 31–60 / 61–90 / 90+ days past due,
plus a separate not-yet-due column. They are a presentation grouping and carry
no accounting or legal meaning.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.access import crm_identities, has_any_capability
from accounts.models import User
from billing.models import Invoice, InvoiceItem, Payment, PaymentAllocation
from billing.money import quantize_money
from billing.selectors import invoices_for
from inventory.selectors import stock_items_for
from reports.services import ReportAccessDenied, format_utc_timestamp


AGING_BUCKETS = ("not_due", "days_1_30", "days_31_60", "days_61_90", "days_over_90")
ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ReceivablesRow:
    customer_id: int
    customer_name: str
    invoice_count: int
    total_outstanding: Decimal
    not_due: Decimal
    days_1_30: Decimal
    days_31_60: Decimal
    days_61_90: Decimal
    days_over_90: Decimal


@dataclass(frozen=True)
class ReceivablesReport:
    as_of: str
    total_outstanding: Decimal
    buckets: dict
    results: tuple


@dataclass(frozen=True)
class ProfitRow:
    invoice_id: int
    number: str
    customer_id: int
    customer_name: str
    issued_at: str
    revenue: Decimal
    cost: Decimal
    profit: Decimal
    margin_percent: Decimal


@dataclass(frozen=True)
class ProfitReport:
    period_start: str
    period_end: str
    revenue: Decimal
    cost: Decimal
    profit: Decimal
    margin_percent: Decimal
    measured_invoice_count: int
    unmeasured_invoice_count: int
    results: tuple


@dataclass(frozen=True)
class ValuationRow:
    warehouse_id: int
    warehouse_name: str
    product_id: int
    product_sku: str
    product_name: str
    quantity: int
    average_cost: Decimal
    stock_value: Decimal


@dataclass(frozen=True)
class ValuationReport:
    as_of: str
    total_quantity: int
    total_value: Decimal
    results: tuple


def _financial_reader(actor):
    """Money reports are company-wide, so only a company-scoped role may read them.

    A Sales Agent holds `reports.own`, which covers their own activity metrics
    and deliberately does not reach receivables, profit, or stock valuation.
    """
    current = crm_identities(User.objects.filter(pk=getattr(actor, "pk", None), is_active=True)).first()
    if current is None or not has_any_capability(current, "reports.company"):
        raise ReportAccessDenied
    return current


def _bucket_for(due_at, as_of):
    if due_at is None or due_at >= as_of:
        return "not_due"
    days = (as_of - due_at).days
    if days <= 30:
        return "days_1_30"
    if days <= 60:
        return "days_31_60"
    if days <= 90:
        return "days_61_90"
    return "days_over_90"


def build_receivables_report(*, actor, customer_id=None, as_of=None):
    actor = _financial_reader(actor)
    as_of = as_of or timezone.now()
    queryset = (
        invoices_for(actor)
        .filter(status=Invoice.Status.ISSUED)
        .filter(paid_amount__lt=F("total_amount"))
        .select_related("customer")
        .order_by("customer__full_name", "due_at", "id")
    )
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)

    per_customer = {}
    buckets = {name: ZERO for name in AGING_BUCKETS}
    total = ZERO
    for invoice in queryset.iterator(chunk_size=500):
        outstanding = invoice.total_amount - invoice.paid_amount
        if outstanding <= 0:
            continue
        # An invoice with no explicit term is due when it was issued, matching
        # BILLING_INVOICE_DUE_DAYS = 0.
        due_at = invoice.due_at or invoice.issued_at
        bucket = _bucket_for(due_at, as_of)
        row = per_customer.setdefault(
            invoice.customer_id,
            {
                "customer_id": invoice.customer_id,
                "customer_name": invoice.customer.full_name,
                "invoice_count": 0,
                "total_outstanding": ZERO,
                **{name: ZERO for name in AGING_BUCKETS},
            },
        )
        row["invoice_count"] += 1
        row["total_outstanding"] += outstanding
        row[bucket] += outstanding
        buckets[bucket] += outstanding
        total += outstanding

    results = tuple(
        ReceivablesRow(**row)
        for row in sorted(per_customer.values(), key=lambda item: -item["total_outstanding"])
    )
    return ReceivablesReport(
        as_of=format_utc_timestamp(as_of.astimezone(UTC)),
        total_outstanding=total,
        buckets=buckets,
        results=results,
    )


#: The two ways of deciding when a sale counts.
BASIS_CASH = "cash"
BASIS_ACCRUAL = "accrual"
PROFIT_BASES = (BASIS_CASH, BASIS_ACCRUAL)


def _collected_by_invoice(*, invoices, period_start, period_end):
    """How much was actually **collected** against each invoice in the period.

    Cash basis asks when the money arrived, so the period is applied to the
    payment's `received_at` and not to the invoice's `issued_at`. An invoice
    raised in March and paid in April belongs to April, and an invoice raised in
    April and never paid belongs to no period at all until it is.

    Only confirmed receipts count. A cancelled payment has had its allocations
    released, so it contributes nothing here without needing to be filtered out
    a second time.

    One grouped query, so the report stays flat in query count as the period
    widens.
    """
    rows = (
        PaymentAllocation.objects.filter(
            invoice__in=invoices,
            payment__status=Payment.Status.CONFIRMED,
            payment__direction=Payment.Direction.RECEIPT,
            payment__received_at__gte=period_start,
            payment__received_at__lt=period_end,
        )
        .values("invoice_id")
        .annotate(
            collected=Coalesce(
                Sum("amount", output_field=DecimalField(max_digits=38, decimal_places=2)),
                Value(ZERO, output_field=DecimalField(max_digits=38, decimal_places=2)),
            )
        )
    )
    return {row["invoice_id"]: row["collected"] for row in rows}


def build_profit_report(
    *, actor, period_start: datetime, period_end: datetime, customer_id=None, basis=BASIS_CASH
):
    """Revenue, cost and profit for a period.

    **The default is a cash basis** (بند ۷.۱). The product owner was asked
    "نقدی یا تعهدی؟" and answered cash: a sale counts when the money arrives,
    not when the document is raised.

    That decides three things at once, which is why it was worth asking:

    * The period filters on when payment was **received**, not when the invoice
      was issued.
    * An issued but unpaid invoice contributes **nothing**. It is a receivable,
      and the receivables report is where it appears.
    * A part-paid invoice contributes **its paid part**, with cost recognised in
      the same proportion — otherwise a half-collected sale would show its full
      cost against half its revenue and report a loss that has not happened.

    `basis="accrual"` keeps the former behaviour. It is not what the product
    owner chose and nothing in the panel selects it; it exists so that the
    difference the answer makes is visible and testable rather than asserted.
    """
    actor = _financial_reader(actor)
    if timezone.is_naive(period_start) or timezone.is_naive(period_end) or period_end <= period_start:
        raise InvalidProfitPeriod
    if basis not in PROFIT_BASES:
        raise InvalidProfitPeriod
    period_start = period_start.astimezone(UTC)
    period_end = period_end.astimezone(UTC)

    queryset = (
        invoices_for(actor)
        .filter(status=Invoice.Status.ISSUED)
        .select_related("customer")
        .order_by("-issued_at", "-id")
    )
    if basis == BASIS_ACCRUAL:
        queryset = queryset.filter(
            issued_at__gte=period_start, issued_at__lt=period_end
        )
    else:
        # بند ۷.۶ — a cancelled invoice drops out here without a second rule:
        # cancelling releases its allocations, so nothing was collected against
        # it. A discount is already gone too, because what was collected is
        # measured against the discounted total.
        collected = _collected_by_invoice(
            invoices=queryset, period_start=period_start, period_end=period_end
        )
        queryset = queryset.filter(pk__in=collected)
    if customer_id is not None:
        queryset = queryset.filter(customer_id=customer_id)

    # One grouped query for costs rather than one per invoice: the report must
    # stay flat in query count as the period widens.
    cost_by_invoice = {
        row["invoice_id"]: row["cost"]
        for row in InvoiceItem.objects.filter(invoice__in=queryset)
        .values("invoice_id")
        .annotate(
            cost=Coalesce(
                Sum(F("unit_cost_snapshot") * F("quantity"), output_field=DecimalField(max_digits=38, decimal_places=2)),
                Value(ZERO, output_field=DecimalField(max_digits=38, decimal_places=2)),
            )
        )
    }
    unmeasured_ids = set(
        InvoiceItem.objects.filter(invoice__in=queryset, unit_cost_snapshot__isnull=True)
        .values_list("invoice_id", flat=True)
        .distinct()
    )

    rows = []
    revenue_total = ZERO
    cost_total = ZERO
    unmeasured = 0
    for invoice in queryset.iterator(chunk_size=500):
        if invoice.pk in unmeasured_ids:
            unmeasured += 1
            continue
        # Revenue excludes tax on both bases: tax collected is not the
        # company's money, and including it would inflate every margin.
        taxable = invoice.subtotal_amount - invoice.discount_amount
        cost = cost_by_invoice.get(invoice.pk, ZERO)
        if basis == BASIS_CASH:
            # The collected share of the document, applied to revenue and cost
            # alike. Measured against `total_amount` because that is what the
            # customer actually pays.
            received = collected.get(invoice.pk, ZERO)
            share = (
                Decimal(received) / invoice.total_amount
                if invoice.total_amount > 0
                else ZERO
            )
            revenue = quantize_money(taxable * share)
            cost = quantize_money(cost * share)
        else:
            revenue = taxable
        profit = revenue - cost
        rows.append(
            ProfitRow(
                invoice_id=invoice.pk,
                number=invoice.number,
                customer_id=invoice.customer_id,
                customer_name=invoice.customer.full_name,
                issued_at=format_utc_timestamp(invoice.issued_at.astimezone(UTC)),
                revenue=revenue,
                cost=cost,
                profit=profit,
                margin_percent=_margin(profit, revenue),
            )
        )
        revenue_total += revenue
        cost_total += cost

    profit_total = revenue_total - cost_total
    return ProfitReport(
        period_start=format_utc_timestamp(period_start),
        period_end=format_utc_timestamp(period_end),
        revenue=revenue_total,
        cost=cost_total,
        profit=profit_total,
        margin_percent=_margin(profit_total, revenue_total),
        measured_invoice_count=len(rows),
        unmeasured_invoice_count=unmeasured,
        results=tuple(rows),
    )


def _margin(profit, revenue):
    """Margin as a percentage of revenue, or zero when there is no revenue.

    Revenue of zero has no defined margin; reporting zero is the honest choice
    here because the profit is also zero in that case by construction.
    """
    if revenue <= 0:
        return ZERO
    return (profit / revenue * Decimal("100")).quantize(Decimal("0.01"))


def build_inventory_valuation_report(*, actor, warehouse_id=None):
    """Stock on hand valued at its moving average cost.

    Tax is irrelevant here and no revaluation policy is applied: the value is
    exactly what the movement ledger says the stock cost.
    """
    actor = _financial_reader(actor)
    queryset = (
        stock_items_for(actor)
        .exclude(quantity=0)
        .select_related("warehouse", "product")
        .order_by("warehouse__name", "product__name", "id")
    )
    if warehouse_id is not None:
        queryset = queryset.filter(warehouse_id=warehouse_id)

    rows = []
    total_quantity = 0
    total_value = ZERO
    for item in queryset.iterator(chunk_size=500):
        value = (item.average_cost * item.quantity).quantize(Decimal("0.01"))
        rows.append(
            ValuationRow(
                warehouse_id=item.warehouse_id,
                warehouse_name=item.warehouse.name,
                product_id=item.product_id,
                product_sku=item.product.sku,
                product_name=item.product.name,
                quantity=item.quantity,
                average_cost=item.average_cost,
                stock_value=value,
            )
        )
        total_quantity += item.quantity
        total_value += value

    return ValuationReport(
        as_of=format_utc_timestamp(timezone.now().astimezone(UTC)),
        total_quantity=total_quantity,
        total_value=total_value,
        results=tuple(rows),
    )


class InvalidProfitPeriod(Exception):
    """Raised when the requested profit period is naive or inverted."""
