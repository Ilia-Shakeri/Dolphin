"""Inventory rules that would be expensive to discover in production."""

from decimal import Decimal

from django.test import TestCase, override_settings

from accounts.models import User
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from inventory.models import StockItem, StockMovement, Warehouse
from inventory.services import (
    create_warehouse,
    deactivate_warehouse,
    record_stock_movement,
    transfer_stock,
    update_warehouse,
)
from sales.services import create_product


class StockFixtureMixin:
    def build(self):
        self.manager = User.objects.create_user(
            username="stock.manager", password="Strong-pass-937!", role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="stock.agent", password="Strong-pass-937!", role=User.Role.SALES_AGENT
        )
        self.warehouse = create_warehouse(actor=self.manager, code="main", name="انبار مرکزی")
        self.product = create_product(
            actor=self.manager, sku="P-1", name="کالا", current_price=Decimal("500.00")
        )

    def receive(self, quantity, cost, movement_type=StockMovement.MovementType.PURCHASE, **extra):
        return record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=movement_type,
            quantity=quantity,
            unit_cost=Decimal(cost),
            **extra,
        )

    def issue(self, quantity, **extra):
        return record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.ADJUSTMENT_OUT,
            quantity=quantity,
            **extra,
        )

    def level(self):
        return StockItem.objects.get(warehouse=self.warehouse, product=self.product)


class MovingAverageCostTests(StockFixtureMixin, TestCase):
    def setUp(self):
        self.build()

    def test_average_is_weighted_by_quantity_not_by_receipt_count(self):
        self.receive(90, "10.00")
        self.receive(10, "110.00")
        # A naive mean would be 60.00; the weighted average is 20.00.
        self.assertEqual(self.level().average_cost, Decimal("20.00"))

    def test_issuing_consumes_the_average_and_never_moves_it(self):
        self.receive(10, "40.00")
        self.issue(4)
        item = self.level()
        self.assertEqual(item.quantity, 6)
        self.assertEqual(item.average_cost, Decimal("40.00"))

    def test_a_return_without_a_cost_re_enters_at_the_average_in_force(self):
        self.receive(10, "40.00")
        movement = record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.RETURN_IN,
            quantity=2,
        )
        self.assertEqual(movement.unit_cost, Decimal("40.00"))
        self.assertEqual(self.level().average_cost, Decimal("40.00"))

    def test_every_movement_snapshots_the_level_it_produced(self):
        self.receive(10, "10.00")
        self.receive(10, "30.00")
        second = StockMovement.objects.order_by("-id").first()
        self.assertEqual(second.resulting_quantity, 20)
        self.assertEqual(second.resulting_average_cost, Decimal("20.00"))
        # The snapshot survives later movements: history is not recomputed.
        self.issue(5)
        second.refresh_from_db()
        self.assertEqual(second.resulting_quantity, 20)


class NegativeStockTests(StockFixtureMixin, TestCase):
    def setUp(self):
        self.build()

    def test_an_issue_beyond_the_level_is_refused_by_default(self):
        self.receive(3, "10.00")
        with self.assertRaises(BusinessConflictError):
            self.issue(4)
        self.assertEqual(self.level().quantity, 3)
        # The refused issue left no movement behind.
        self.assertEqual(StockMovement.objects.filter(movement_type="adjustment_out").count(), 0)

    @override_settings(INVENTORY_ALLOW_NEGATIVE_STOCK=True)
    def test_a_deployment_may_opt_into_negative_stock_explicitly(self):
        self.receive(3, "10.00")
        self.issue(4)
        self.assertEqual(self.level().quantity, -1)


class MovementGuardTests(StockFixtureMixin, TestCase):
    def setUp(self):
        self.build()

    def test_an_incoming_movement_without_a_cost_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            record_stock_movement(
                actor=self.manager,
                warehouse=self.warehouse,
                product=self.product,
                movement_type=StockMovement.MovementType.PURCHASE,
                quantity=1,
            )

    def test_an_outgoing_movement_may_not_carry_a_cost(self):
        self.receive(5, "10.00")
        with self.assertRaises(BusinessRuleError):
            self.issue(1, unit_cost=Decimal("5.00"))

    def test_a_repeated_idempotency_key_returns_the_original_movement(self):
        first = self.receive(5, "10.00", idempotency_key="receipt-1")
        second = self.receive(5, "10.00", idempotency_key="receipt-1")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(self.level().quantity, 5)

    def test_an_agent_cannot_move_stock(self):
        with self.assertRaises(BusinessPermissionDenied):
            record_stock_movement(
                actor=self.agent,
                warehouse=self.warehouse,
                product=self.product,
                movement_type=StockMovement.MovementType.PURCHASE,
                quantity=1,
                unit_cost=Decimal("1.00"),
            )

    def test_an_inactive_warehouse_accepts_nothing(self):
        deactivate_warehouse(actor=self.manager, warehouse=self.warehouse)
        with self.assertRaises(BusinessConflictError):
            self.receive(1, "10.00")


class WarehouseTests(StockFixtureMixin, TestCase):
    def setUp(self):
        self.build()

    def test_only_one_warehouse_is_default_at_a_time(self):
        second = create_warehouse(actor=self.manager, code="second", name="انبار دوم", is_default=True)
        update_warehouse(actor=self.manager, warehouse=self.warehouse, is_default=True)
        second.refresh_from_db()
        self.assertFalse(second.is_default)
        self.assertEqual(Warehouse.objects.filter(is_default=True).count(), 1)

    def test_a_warehouse_holding_stock_cannot_be_deactivated(self):
        self.receive(1, "10.00")
        with self.assertRaises(BusinessConflictError):
            deactivate_warehouse(actor=self.manager, warehouse=self.warehouse)

    def test_transfer_moves_quantity_and_leaves_total_value_unchanged(self):
        destination = create_warehouse(actor=self.manager, code="branch", name="انبار شعبه")
        self.receive(10, "25.00")
        transfer_stock(
            actor=self.manager,
            from_warehouse=self.warehouse,
            to_warehouse=destination,
            product=self.product,
            quantity=4,
        )
        source = self.level()
        target = StockItem.objects.get(warehouse=destination, product=self.product)
        self.assertEqual(source.quantity, 6)
        self.assertEqual(target.quantity, 4)
        self.assertEqual(target.average_cost, Decimal("25.00"))
        self.assertEqual(source.stock_value + target.stock_value, Decimal("250.00"))

    def test_a_transfer_to_the_same_warehouse_is_refused(self):
        self.receive(5, "10.00")
        with self.assertRaises(BusinessRuleError):
            transfer_stock(
                actor=self.manager,
                from_warehouse=self.warehouse,
                to_warehouse=self.warehouse,
                product=self.product,
                quantity=1,
            )

    def test_an_insufficient_transfer_leaves_neither_leg_behind(self):
        destination = create_warehouse(actor=self.manager, code="branch", name="انبار شعبه")
        self.receive(2, "10.00")
        with self.assertRaises(BusinessConflictError):
            transfer_stock(
                actor=self.manager,
                from_warehouse=self.warehouse,
                to_warehouse=destination,
                product=self.product,
                quantity=5,
            )
        self.assertEqual(self.level().quantity, 2)
        self.assertFalse(StockItem.objects.filter(warehouse=destination).exclude(quantity=0).exists())
        self.assertEqual(StockMovement.objects.filter(reference_kind="transfer").count(), 0)
