"""Regression for the audit's H2 finding: the stock-item create race.

`_lock_stock_item` creates the `(warehouse, product)` row when the pair is new
and re-reads it when a concurrent transaction won the race. The insert has to
run inside its own atomic block: on PostgreSQL a failed statement aborts the
whole transaction, so catching `IntegrityError` without a savepoint leaves a
connection on which the re-read cannot run.

SQLite — what the suite runs on — does not poison the transaction, so a
functional test alone passes either way. Both tests below are therefore kept:
one proves the path behaves correctly, the other pins the savepoint that makes
it behave correctly on the database this actually ships against.
"""

import inspect
import re
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError, transaction
from django.db.models.query import QuerySet
from django.test import TestCase

from accounts.models import User
from inventory import services
from inventory.models import StockItem, StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_product


PASSWORD = "Strong-pass-937!"


class StockItemCreateRaceTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="race.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.warehouse = create_warehouse(actor=self.manager, code="racewh", name="انبار رقابت")
        self.product = create_product(
            actor=self.manager, sku="RACE-1", name="کالای رقابت", current_price=Decimal("100.00")
        )

    def test_losing_the_create_race_returns_the_winners_row(self):
        """Probe misses, insert collides, re-read finds the row the winner made.

        The winner's row is created first and the probe is made to miss it once,
        which is exactly what the loser of a real race sees: the other
        transaction had not committed when it looked, and had by the time it
        inserted.
        """
        winner = StockItem.objects.create(warehouse=self.warehouse, product=self.product)
        first_call = {"seen": False}
        real_first = QuerySet.first

        def miss_once(self):
            if not first_call["seen"]:
                first_call["seen"] = True
                return None
            return real_first(self)

        def collide(**kwargs):
            raise IntegrityError("duplicate key value violates unique constraint")

        with transaction.atomic():
            with mock.patch.object(QuerySet, "first", miss_once), mock.patch.object(
                StockItem.objects, "create", side_effect=collide
            ):
                item = services._lock_stock_item(
                    warehouse=self.warehouse, product=self.product
                )
            self.assertEqual(item.pk, winner.pk)
            # The connection is still usable: without the savepoint this query
            # raises TransactionManagementError on PostgreSQL.
            self.assertEqual(StockItem.objects.filter(pk=winner.pk).count(), 1)

    def test_the_insert_is_wrapped_in_its_own_atomic_block(self):
        """Without this savepoint the re-read raises TransactionManagementError.

        Asserted against the source because the failure it prevents only occurs
        on PostgreSQL, which the test suite does not run against.
        """
        source = inspect.getsource(services._lock_stock_item)
        self.assertRegex(
            source,
            re.compile(
                r"with transaction\.atomic\(\):\s*\n\s*StockItem\.objects\.create\(", re.MULTILINE
            ),
        )
        self.assertIn("except IntegrityError:", source)

    def test_a_new_pair_is_created_without_any_race(self):
        movement = record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=3,
            unit_cost=Decimal("50.00"),
        )
        self.assertEqual(movement.resulting_quantity, 3)
        self.assertEqual(
            StockItem.objects.filter(warehouse=self.warehouse, product=self.product).count(), 1
        )
