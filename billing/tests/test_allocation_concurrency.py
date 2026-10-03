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
