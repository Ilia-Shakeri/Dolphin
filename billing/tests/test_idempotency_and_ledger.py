"""Regressions for the audit's H1, H3 and H5 findings.

Each test here failed against the code as shipped, and each describes money
going missing or crossing a boundary rather than a style preference.
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from billing.ledger import current_balance
from billing.models import CustomerLedgerEntry, Payment
from billing.payments import record_opening_balance, register_payment
from billing.services import create_invoice, issue_invoice
from common.exceptions import BusinessConflictError
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product


PASSWORD = "Strong-pass-937!"


class PaymentIdempotencyTests(TestCase):
    """H1: matching a client key alone leaked one payment and swallowed another."""

    def setUp(self):
        self.manager = User.objects.create_user(
            username="idem.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.first = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری اول",
            phone={"raw_phone": "09120000001", "is_primary": True},
        )
        self.second = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری دوم",
            phone={"raw_phone": "09120000002", "is_primary": True},
        )

    def _pay(self, customer, amount, key, method=Payment.Method.CASH):
        return register_payment(
            actor=self.manager,
            customer=customer,
            method=method,
            amount=Decimal(amount),
            idempotency_key=key,
        )

    def test_a_true_retry_returns_the_original_payment(self):
        first = self._pay(self.first, "100.00", "retry-1")
        again = self._pay(self.first, "100.00", "retry-1")
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(Payment.objects.filter(customer=self.first).count(), 1)

    def test_the_same_key_for_a_different_amount_is_refused_not_swallowed(self):
        self._pay(self.first, "100.00", "collide-1")
        # Registering a second, genuine payment under a colliding key used to
        # return the first one and record nothing: money taken, no row, 201.
        with self.assertRaises(BusinessConflictError):
            self._pay(self.first, "250.00", "collide-1")

    def test_the_same_key_for_a_different_method_is_refused(self):
        self._pay(self.first, "100.00", "collide-2")
        with self.assertRaises(BusinessConflictError):
            self._pay(self.first, "100.00", "collide-2", method=Payment.Method.CARD)

    def test_another_customers_key_never_returns_their_payment(self):
        theirs = self._pay(self.first, "100.00", "shared-key")
        with self.assertRaises(BusinessConflictError) as caught:
            self._pay(self.second, "100.00", "shared-key")
        # Refused, and nothing about the other customer's payment is disclosed.
        message = str(caught.exception.detail)
        self.assertNotIn(theirs.number, message)
        self.assertNotIn(str(theirs.pk), message)
        self.assertEqual(Payment.objects.filter(customer=self.second).count(), 0)

    def test_an_empty_key_never_matches_anything(self):
        first = self._pay(self.first, "100.00", "")
        second = self._pay(self.first, "100.00", "")
        self.assertNotEqual(first.pk, second.pk)


class LedgerBalanceTests(TestCase):
    """H3: the balance came from the newest `occurred_at`, not from every entry."""

    def setUp(self):
        self.manager = User.objects.create_user(
            username="ledger.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری دفتر",
            phone={"raw_phone": "09120000003", "is_primary": True},
        )
        self.product = create_product(
            actor=self.manager, sku="LED-1", name="کالای دفتر", current_price=Decimal("1000.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="ledwh", name="انبار دفتر")
        record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=100,
            unit_cost=Decimal("400.00"),
        )

    def _issue(self, quantity=1):
        return issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.manager,
                customer=self.customer,
                items=[{"product": self.product, "quantity": quantity}],
                warehouse=self.warehouse,
            ),
        )

    def test_a_back_dated_payment_still_reduces_the_balance(self):
        invoice = self._issue()
        self.assertEqual(current_balance(self.customer), invoice.total_amount)

        register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal("400.00"),
            # Received yesterday, entered today — the ordinary case that used to
            # leave the customer still owing the whole invoice.
            received_at=timezone.now() - timedelta(days=1),
        )
        self.assertEqual(
            current_balance(self.customer), invoice.total_amount - Decimal("400.00")
        )

    def test_a_back_dated_opening_balance_is_counted(self):
        invoice = self._issue()
        record_opening_balance(
            actor=self.manager,
            customer=self.customer,
            amount=Decimal("250.00"),
            occurred_at=timezone.now() - timedelta(days=365),
        )
        self.assertEqual(
            current_balance(self.customer), invoice.total_amount + Decimal("250.00")
        )

    def test_the_balance_equals_every_debit_less_every_credit(self):
        self._issue(quantity=2)
        register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal("500.00"),
            received_at=timezone.now() - timedelta(hours=3),
        )
        record_opening_balance(
            actor=self.manager,
            customer=self.customer,
            amount=Decimal("75.00"),
            occurred_at=timezone.now() - timedelta(days=30),
        )
        entries = CustomerLedgerEntry.objects.filter(customer=self.customer)
        expected = sum(
            (entry.debit - entry.credit for entry in entries), start=Decimal("0.00")
        )
        self.assertEqual(current_balance(self.customer), expected)

    def test_the_ledger_stays_append_only(self):
        self._issue()
        before = list(
            CustomerLedgerEntry.objects.filter(customer=self.customer).values_list("pk", "balance_after")
        )
        register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal("100.00"),
            received_at=timezone.now() - timedelta(days=2),
        )
        # Posting a back-dated entry appends; it never rewrites an existing row.
        after = dict(
            CustomerLedgerEntry.objects.filter(customer=self.customer).values_list("pk", "balance_after")
        )
        for pk, balance in before:
            self.assertEqual(after[pk], balance)


class StockMovementIdempotencyTests(TestCase):
    """H5: a client key matched globally and returned an unrelated movement."""

    def setUp(self):
        self.manager = User.objects.create_user(
            username="stock.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.product = create_product(
            actor=self.manager, sku="MOV-1", name="کالای حرکت", current_price=Decimal("100.00")
        )
        self.other_product = create_product(
            actor=self.manager, sku="MOV-2", name="کالای دیگر", current_price=Decimal("100.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="movwh", name="انبار حرکت")
        self.other_warehouse = create_warehouse(
            actor=self.manager, code="movwh2", name="انبار دوم"
        )

    def _movement(self, *, warehouse=None, product=None, quantity=5, key="move-1"):
        return record_stock_movement(
            actor=self.manager,
            warehouse=warehouse or self.warehouse,
            product=product or self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=quantity,
            unit_cost=Decimal("40.00"),
            idempotency_key=key,
        )

    def test_a_true_retry_applies_the_movement_once(self):
        first = self._movement()
        again = self._movement()
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(StockMovement.objects.filter(product=self.product).count(), 1)

    def test_the_same_key_for_a_different_quantity_is_refused(self):
        self._movement(quantity=5)
        with self.assertRaises(BusinessConflictError):
            self._movement(quantity=9)

    def test_a_key_belonging_to_another_product_is_refused_not_returned(self):
        theirs = self._movement(product=self.product, key="cross-key")
        with self.assertRaises(BusinessConflictError):
            self._movement(product=self.other_product, key="cross-key")
        # The unrelated movement is neither returned nor duplicated.
        self.assertEqual(StockMovement.objects.filter(idempotency_key="cross-key").count(), 1)
        self.assertEqual(StockMovement.objects.get(idempotency_key="cross-key").pk, theirs.pk)

    def test_a_key_belonging_to_another_warehouse_is_refused(self):
        self._movement(warehouse=self.warehouse, key="cross-warehouse")
        with self.assertRaises(BusinessConflictError):
            self._movement(warehouse=self.other_warehouse, key="cross-warehouse")
