"""بند ۷.۱ — the profit report counts a sale when the money arrives.

The product owner was asked «مبنای حسابداری: نقدی یا تعهدی؟» and answered cash.
That single answer decides when a sale enters the report, what an unpaid invoice
contributes, and how a part-paid one is treated — so it is worth pinning all
three rather than trusting that the switch took.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from billing.models import Payment
from billing.payments import allocate_payment, register_payment
from billing.services import create_invoice, issue_invoice
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from reports.financial import BASIS_ACCRUAL, BASIS_CASH, build_profit_report
from sales.services import create_customer_with_phone, create_product


PASSWORD = "Strong-pass-937!"


class CashBasisProfitTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="cb.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.product = create_product(
            actor=self.manager, sku="CB-1", name="کالا", current_price=Decimal("100.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="cbwh", name="انبار")
        record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=1000,
            unit_cost=Decimal("40.00"),
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری مبنا",
            phone={"raw_phone": "09121260000", "is_primary": True},
        )
        self.start = datetime(2026, 1, 1, tzinfo=UTC)
        self.end = datetime(2027, 1, 1, tzinfo=UTC)

    def issued(self, *, quantity=1):
        invoice = create_invoice(
            actor=self.manager,
            customer=self.customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": quantity}],
        )
        return issue_invoice(actor=self.manager, invoice=invoice)

    def pay(self, invoice, amount, *, received_at=None):
        payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal(amount),
            **({"received_at": received_at} if received_at else {}),
        )
        return allocate_payment(
            actor=self.manager, payment=payment, invoice=invoice, amount=Decimal(amount)
        )

    def report(self, *, basis=BASIS_CASH, start=None, end=None):
        return build_profit_report(
            actor=self.manager,
            period_start=start or self.start,
            period_end=end or self.end,
            basis=basis,
        )

    # --- what the answer changes -------------------------------------------

    def test_an_unpaid_invoice_contributes_nothing(self):
        """It is a receivable, not revenue. This is the whole of بند ۷.۱."""
        self.issued()
        report = self.report()
        self.assertEqual(report.revenue, Decimal("0.00"))
        self.assertEqual(report.profit, Decimal("0.00"))
        self.assertEqual(report.results, ())

    def test_the_same_invoice_does_count_on_an_accrual_basis(self):
        """Proving the default actually changed something."""
        self.issued()
        report = self.report(basis=BASIS_ACCRUAL)
        self.assertEqual(report.revenue, Decimal("100.00"))
        self.assertEqual(report.profit, Decimal("60.00"))

    def test_a_fully_paid_invoice_contributes_all_of_itself(self):
        invoice = self.issued()
        self.pay(invoice, "100.00")
        report = self.report()
        self.assertEqual(report.revenue, Decimal("100.00"))
        self.assertEqual(report.cost, Decimal("40.00"))
        self.assertEqual(report.profit, Decimal("60.00"))

    def test_a_part_paid_invoice_contributes_its_paid_part(self):
        invoice = self.issued()
        self.pay(invoice, "25.00")
        report = self.report()
        self.assertEqual(report.revenue, Decimal("25.00"))

    def test_cost_is_recognised_in_the_same_proportion_as_revenue(self):
        """Otherwise a half-collected sale reports a loss that never happened."""
        invoice = self.issued()
        self.pay(invoice, "50.00")
        report = self.report()
        self.assertEqual(report.revenue, Decimal("50.00"))
        self.assertEqual(report.cost, Decimal("20.00"))
        self.assertEqual(report.profit, Decimal("30.00"))

    # --- the period follows the money --------------------------------------

    def test_the_period_filters_on_when_payment_arrived(self):
        """An invoice raised in one period and paid in the next belongs to the next."""
        invoice = self.issued()
        self.pay(invoice, "100.00", received_at=datetime(2026, 6, 1, tzinfo=UTC))

        inside = self.report(
            start=datetime(2026, 5, 1, tzinfo=UTC), end=datetime(2026, 7, 1, tzinfo=UTC)
        )
        self.assertEqual(inside.revenue, Decimal("100.00"))

        before = self.report(
            start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 5, 1, tzinfo=UTC)
        )
        self.assertEqual(before.revenue, Decimal("0.00"))

    def test_a_cancelled_payment_takes_its_revenue_back_out(self):
        from billing.payments import cancel_payment

        invoice = self.issued()
        allocation = self.pay(invoice, "100.00")
        self.assertEqual(self.report().revenue, Decimal("100.00"))

        cancel_payment(
            actor=self.manager, payment=allocation.payment, reason="اشتباه"
        )
        self.assertEqual(self.report().revenue, Decimal("0.00"))

    # --- guards -------------------------------------------------------------

    def test_an_unknown_basis_is_refused_rather_than_defaulted(self):
        from reports.financial import InvalidProfitPeriod

        with self.assertRaises(InvalidProfitPeriod):
            build_profit_report(
                actor=self.manager,
                period_start=self.start,
                period_end=self.end,
                basis="whatever",
            )

    def test_cash_is_the_default_without_being_asked_for(self):
        self.issued()
        self.assertEqual(
            build_profit_report(
                actor=self.manager, period_start=self.start, period_end=self.end
            ).revenue,
            Decimal("0.00"),
        )
