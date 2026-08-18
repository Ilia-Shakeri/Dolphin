"""Invoice first, order second — and the link between them is optional.

Client-1 raises the invoice before the order exists, so an invoice must stand on
its own, an order may gather several invoices, and the two can be joined after
both already exist. The link is a real foreign key, not a document number
compared as text.
"""

from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from billing.models import Invoice, Order
from billing.services import (
    create_invoice,
    create_order,
    issue_invoice,
    link_invoice_to_order,
)
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product


PASSWORD = "Strong-pass-937!"


class InvoiceOrderLinkTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="iol.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری پیوند",
            phone={"raw_phone": "09125556666", "is_primary": True},
        )
        self.product = create_product(
            actor=self.manager, sku="IOL-1", name="کالای پیوند", current_price=Decimal("100.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="iolwh", name="انبار پیوند")
        record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=100,
            unit_cost=Decimal("40.00"),
        )

    def _invoice(self, quantity=1):
        return create_invoice(
            actor=self.manager,
            customer=self.customer,
            items=[{"product": self.product, "quantity": quantity}],
        )

    def _order(self, quantity=1):
        return create_order(
            actor=self.manager,
            customer=self.customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": quantity}],
        )

    # --- an invoice stands on its own --------------------------------------

    def test_an_invoice_needs_no_order(self):
        invoice = self._invoice()
        self.assertIsNone(invoice.order_id)
        issued = issue_invoice(actor=self.manager, invoice=invoice)
        self.assertIsNone(issued.order_id)
        self.assertEqual(issued.status, Invoice.Status.ISSUED)

    # --- linking after the fact --------------------------------------------

    def test_an_existing_invoice_can_be_attached_to_an_order_later(self):
        invoice = issue_invoice(actor=self.manager, invoice=self._invoice())
        order = self._order()
        self.assertIsNone(invoice.order_id)

        linked = link_invoice_to_order(actor=self.manager, invoice=invoice, order=order)
        self.assertEqual(linked.order_id, order.pk)
        # Neither document had to be recreated.
        self.assertEqual(linked.pk, invoice.pk)
        self.assertEqual(linked.number, invoice.number)

    def test_the_link_can_be_removed_again(self):
        invoice = self._invoice()
        order = self._order()
        link_invoice_to_order(actor=self.manager, invoice=invoice, order=order)
        detached = link_invoice_to_order(actor=self.manager, invoice=invoice, order=None)
        self.assertIsNone(detached.order_id)

    def test_one_order_gathers_several_invoices(self):
        order = self._order()
        first = link_invoice_to_order(actor=self.manager, invoice=self._invoice(), order=order)
        second = link_invoice_to_order(actor=self.manager, invoice=self._invoice(2), order=order)
        third = link_invoice_to_order(actor=self.manager, invoice=self._invoice(3), order=order)

        numbers = set(order.invoices.values_list("number", flat=True))
        self.assertEqual(numbers, {first.number, second.number, third.number})
        self.assertEqual(order.invoices.count(), 3)

    def test_the_link_is_a_relation_not_a_number_match(self):
        invoice = self._invoice()
        order = self._order()
        link_invoice_to_order(actor=self.manager, invoice=invoice, order=order)
        invoice.refresh_from_db()
        # A real foreign key: following it returns the order object itself.
        self.assertEqual(invoice.order, order)
        self.assertNotEqual(invoice.number, order.number)

    def test_an_order_for_another_customer_is_refused(self):
        other = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری دیگر",
            phone={"raw_phone": "09127778888", "is_primary": True},
        )
        foreign_order = create_order(
            actor=self.manager,
            customer=other,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 1}],
        )
        with self.assertRaises(BusinessRuleError):
            link_invoice_to_order(
                actor=self.manager, invoice=self._invoice(), order=foreign_order
            )

    # --- scope --------------------------------------------------------------

    def test_a_marketer_cannot_link_documents_they_do_not_own(self):
        invoice = self._invoice()
        order = self._order()
        agent = User.objects.create_user(
            username="iol.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        with self.assertRaises(BusinessPermissionDenied):
            link_invoice_to_order(actor=agent, invoice=invoice, order=order)

    def test_existing_invoices_without_a_link_stay_valid(self):
        """Nothing about the older shape becomes invalid."""
        invoice = issue_invoice(actor=self.manager, invoice=self._invoice())
        self.assertIsNone(invoice.order_id)
        invoice.refresh_from_db()
        self.assertIsNone(invoice.order_id)
        self.assertEqual(Invoice.objects.filter(order__isnull=True).count(), 1)
