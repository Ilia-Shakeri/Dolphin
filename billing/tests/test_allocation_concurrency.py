"""Two receipts touching the same two invoices in opposite order must not deadlock (2.39.5).

Needs a real database with row locks, so it runs on PostgreSQL only.
"""

import threading
from decimal import Decimal

from django.db import connection, connections
from django.test import TransactionTestCase, skipUnlessDBFeature

from accounts.models import User
from billing.models import Payment
from billing.payments import allocate_payment_across, register_payment
from billing.services import create_invoice, issue_invoice
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-937!"


@skipUnlessDBFeature("has_select_for_update")
class AllocationLockOrderTests(TransactionTestCase):
    def test_opposite_orders_complete_without_a_deadlock(self):
        if connection.vendor != "postgresql":
            self.skipTest("row-lock ordering needs PostgreSQL")
        manager = User.objects.create_user(username="lock.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        product = create_product(actor=manager, sku="LK-1", name="کالا", current_price=Decimal("100.00"))
        customer = create_customer_with_phone(actor=manager, full_name="مشتری", phone={"raw_phone": "09121110077"})
        invoices = [
            issue_invoice(
                actor=manager,
                invoice=create_invoice(
                    actor=manager, customer=customer,
                    items=[{"product": product, "quantity": 5, "unit_price": product.current_price}],
                ),
            )
            for _ in range(2)
        ]
        receipts = [
            register_payment(actor=manager, customer=customer, method=Payment.Method.CASH, amount=Decimal("500.00"))
            for _ in range(2)
        ]
        errors = []
        barrier = threading.Barrier(2)

        def run(receipt, order):
            try:
                barrier.wait()
                allocate_payment_across(
                    actor=manager, payment=receipt,
                    splits=[{"invoice": invoice, "amount": Decimal("100.00")} for invoice in order],
                )
            except Exception as exc:  # noqa: BLE001 - collected and asserted below
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=run, args=(receipts[0], invoices)),
            threading.Thread(target=run, args=(receipts[1], list(reversed(invoices)))),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(errors, [])
        for invoice in invoices:
            invoice.refresh_from_db()
            self.assertEqual(invoice.paid_amount, Decimal("200.00"))


@skipUnlessDBFeature("has_select_for_update")
class ReleaseAndCancelLockOrderTests(TransactionTestCase):
    """2.40.0: release, cancel and correction share one lock order
    (payment → allocations by id → invoices by id)."""

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("row-lock ordering needs PostgreSQL")
        self.manager = User.objects.create_user(username="lock2.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        product = create_product(actor=self.manager, sku="LK-2", name="کالا", current_price=Decimal("100.00"))
        self.customer = create_customer_with_phone(actor=self.manager, full_name="مشتری", phone={"raw_phone": "09121110078"})
        self.invoices = [
            issue_invoice(actor=self.manager, invoice=create_invoice(
                actor=self.manager, customer=self.customer,
                items=[{"product": product, "quantity": 5, "unit_price": product.current_price}],
            ))
            for _ in range(2)
        ]

    def run_together(self, *calls):
        errors = []
        barrier = threading.Barrier(len(calls))

        def wrap(call):
            try:
                barrier.wait()
                call()
            except Exception as exc:  # noqa: BLE001 - collected and asserted below
                errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=wrap, args=(call,)) for call in calls]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        return errors

    def receipt(self):
        receipt = register_payment(actor=self.manager, customer=self.customer, method=Payment.Method.CASH, amount=Decimal("200.00"))
        allocate_payment_across(actor=self.manager, payment=receipt, splits=[
            {"invoice": self.invoices[0], "amount": Decimal("100.00")},
            {"invoice": self.invoices[1], "amount": Decimal("100.00")},
        ])
        return receipt

    def test_a_release_racing_a_cancel_of_the_same_receipt_never_deadlocks(self):
        from billing.payments import cancel_payment, release_allocation
        from common.exceptions import BusinessConflictError

        receipt = self.receipt()
        allocation = receipt.allocations.order_by("id").last()
        errors = self.run_together(
            lambda: release_allocation(actor=self.manager, allocation=allocation, reason="race"),
            lambda: cancel_payment(actor=self.manager, payment=receipt, reason="race"),
        )
        self.assertTrue(all(isinstance(error, BusinessConflictError) for error in errors), errors)
        for invoice in self.invoices:
            invoice.refresh_from_db()
            self.assertEqual(invoice.paid_amount, Decimal("0.00"))

    def test_two_cancels_sharing_invoices_never_deadlock(self):
        from billing.payments import cancel_payment

        first, second = self.receipt(), self.receipt()
        errors = self.run_together(
            lambda: cancel_payment(actor=self.manager, payment=first, reason="race"),
            lambda: cancel_payment(actor=self.manager, payment=second, reason="race"),
        )
        self.assertEqual(errors, [])
        for invoice in self.invoices:
            invoice.refresh_from_db()
            self.assertEqual(invoice.paid_amount, Decimal("0.00"))
