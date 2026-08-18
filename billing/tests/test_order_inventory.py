"""The order owns the inventory lifecycle.

Goods leave the warehouse once when an order is approved and come back once if
it is cancelled. An approved order that is edited moves only the difference. An
invoice moves nothing at all, so the same goods can never leave twice for one
sale. Every one of those is a way to lose real stock, so each has a test.
"""

from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from billing.models import Order
from billing.services import (
    create_invoice,
    create_order,
    issue_invoice,
    replace_order_items,
    transition_order,
)
from inventory.models import StockItem, StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product


PASSWORD = "Strong-pass-937!"


class OrderInventoryTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="oi.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری سفارش",
            phone={"raw_phone": "09123334444", "is_primary": True},
        )
        self.product = create_product(
            actor=self.manager, sku="OI-1", name="کالای سفارش", current_price=Decimal("100.00")
        )
        self.other_product = create_product(
            actor=self.manager, sku="OI-2", name="کالای دوم", current_price=Decimal("50.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="oiwh", name="انبار سفارش")
        self._receive(self.product, 100)
        self._receive(self.other_product, 100)

    def _receive(self, product, quantity):
        record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=quantity,
            unit_cost=Decimal("40.00"),
        )

    def _on_hand(self, product=None):
        item = StockItem.objects.filter(
            warehouse=self.warehouse, product=product or self.product
        ).first()
        return item.quantity if item else 0

    def _order(self, quantity=5, product=None):
        return create_order(
            actor=self.manager,
            customer=self.customer,
            warehouse=self.warehouse,
            items=[{"product": product or self.product, "quantity": quantity}],
        )

    # --- draft moves nothing -----------------------------------------------

    def test_a_draft_order_moves_no_stock(self):
        before = self._on_hand()
        order = self._order(quantity=5)
        self.assertEqual(order.status, Order.Status.DRAFT)
        self.assertFalse(order.stock_applied)
        self.assertEqual(self._on_hand(), before)

    # --- approval deducts exactly once -------------------------------------

    def test_approval_deducts_once(self):
        before = self._on_hand()
        order = transition_order(
            actor=self.manager, order=self._order(quantity=5), to_status=Order.Status.CONFIRMED
        )
        self.assertTrue(order.stock_applied)
        self.assertEqual(self._on_hand(), before - 5)

    def test_a_repeated_approval_never_deducts_twice(self):
        before = self._on_hand()
        order = transition_order(
            actor=self.manager, order=self._order(quantity=5), to_status=Order.Status.CONFIRMED
        )
        # The same transition asked for again — a double submit, a retry.
        from common.exceptions import BusinessConflictError

        with self.assertRaises(BusinessConflictError):
            transition_order(actor=self.manager, order=order, to_status=Order.Status.CONFIRMED)
        self.assertEqual(self._on_hand(), before - 5)

    # --- cancellation restores exactly once --------------------------------

    def test_cancelling_an_approved_order_restores_once(self):
        before = self._on_hand()
        order = transition_order(
            actor=self.manager, order=self._order(quantity=5), to_status=Order.Status.CONFIRMED
        )
        self.assertEqual(self._on_hand(), before - 5)

        cancelled = transition_order(
            actor=self.manager, order=order, to_status=Order.Status.CANCELLED
        )
        self.assertFalse(cancelled.stock_applied)
        self.assertEqual(self._on_hand(), before)

    def test_cancelling_a_draft_order_restores_nothing(self):
        before = self._on_hand()
        order = self._order(quantity=5)
        transition_order(actor=self.manager, order=order, to_status=Order.Status.CANCELLED)
        self.assertEqual(self._on_hand(), before)

    # --- editing an approved order reconciles the delta ---------------------

    def test_increasing_an_approved_order_deducts_only_the_difference(self):
        before = self._on_hand()
        order = transition_order(
            actor=self.manager, order=self._order(quantity=5), to_status=Order.Status.CONFIRMED
        )
        replace_order_items(
            actor=self.manager, order=order, items=[{"product": self.product, "quantity": 8}]
        )
        self.assertEqual(self._on_hand(), before - 8)

    def test_decreasing_an_approved_order_returns_only_the_difference(self):
        before = self._on_hand()
        order = transition_order(
            actor=self.manager, order=self._order(quantity=5), to_status=Order.Status.CONFIRMED
        )
        replace_order_items(
            actor=self.manager, order=order, items=[{"product": self.product, "quantity": 2}]
        )
        self.assertEqual(self._on_hand(), before - 2)

    def test_swapping_the_product_returns_one_and_takes_the_other(self):
        first_before = self._on_hand(self.product)
        second_before = self._on_hand(self.other_product)
        order = transition_order(
            actor=self.manager, order=self._order(quantity=5), to_status=Order.Status.CONFIRMED
        )
        replace_order_items(
            actor=self.manager, order=order, items=[{"product": self.other_product, "quantity": 3}]
        )
        self.assertEqual(self._on_hand(self.product), first_before)
        self.assertEqual(self._on_hand(self.other_product), second_before - 3)

    def test_editing_a_draft_order_moves_nothing(self):
        before = self._on_hand()
        order = self._order(quantity=5)
        replace_order_items(
            actor=self.manager, order=order, items=[{"product": self.product, "quantity": 9}]
        )
        self.assertEqual(self._on_hand(), before)

    # --- shortage never goes negative --------------------------------------

    def test_approving_more_than_the_warehouse_holds_cancels_the_order(self):
        before = self._on_hand()
        order = self._order(quantity=before + 1)
        result = transition_order(
            actor=self.manager, order=order, to_status=Order.Status.CONFIRMED
        )
        self.assertEqual(result.status, Order.Status.CANCELLED)
        self.assertIn("موجودی کافی نبود", result.notes)
        self.assertFalse(result.stock_applied)
        # Nothing moved, and nothing went negative.
        self.assertEqual(self._on_hand(), before)

    def test_editing_beyond_available_stock_cancels_and_keeps_stock_whole(self):
        before = self._on_hand()
        order = transition_order(
            actor=self.manager, order=self._order(quantity=5), to_status=Order.Status.CONFIRMED
        )
        result = replace_order_items(
            actor=self.manager,
            order=order,
            items=[{"product": self.product, "quantity": before + 50}],
        )
        self.assertEqual(result.status, Order.Status.CANCELLED)
        self.assertIn("موجودی کافی نبود", result.notes)
        # The original deduction stands; nothing extra left the warehouse.
        self.assertEqual(self._on_hand(), before - 5)

    def test_the_shortage_note_is_not_repeated(self):
        before = self._on_hand()
        order = self._order(quantity=before + 1)
        result = transition_order(
            actor=self.manager, order=order, to_status=Order.Status.CONFIRMED
        )
        self.assertEqual(result.notes.count("موجودی کافی نبود"), 1)

    # --- an invoice moves nothing ------------------------------------------

    def test_issuing_an_invoice_moves_no_stock(self):
        before = self._on_hand()
        invoice = issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.manager,
                customer=self.customer,
                items=[{"product": self.product, "quantity": 4}],
                warehouse=self.warehouse,
            ),
        )
        self.assertEqual(self._on_hand(), before)
        self.assertFalse(invoice.stock_applied)

    def test_an_order_and_its_invoice_deduct_the_goods_once_between_them(self):
        before = self._on_hand()
        transition_order(
            actor=self.manager, order=self._order(quantity=6), to_status=Order.Status.CONFIRMED
        )
        issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.manager,
                customer=self.customer,
                items=[{"product": self.product, "quantity": 6}],
                warehouse=self.warehouse,
            ),
        )
        self.assertEqual(self._on_hand(), before - 6)
