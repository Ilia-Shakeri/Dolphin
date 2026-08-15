from decimal import Decimal
from threading import Barrier, Lock, Thread
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase
from django.utils import timezone

from accounts.models import User
from accounts.services import change_user_role, update_crm_user
from auditlog.models import ActivityLog
from sales.models import (
    Customer,
    CustomerPhone,
    Interaction,
    Lead,
    LeadAssignmentHistory,
    Product,
    Sale,
)
from sales.services import (
    cancel_sale,
    create_customer_phone,
    mark_sale,
    reassign_lead,
    update_product,
)


POSTGRES_ONLY = skipUnless(
    connection.vendor == "postgresql",
    "PostgreSQL concurrency proof runs in the isolated PostgreSQL harness.",
)


@POSTGRES_ONLY
class PostgresConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def _run_race(self, *calls):
        start = Barrier(len(calls))
        result_lock = Lock()
        results = []

        def run(call):
            close_old_connections()
            try:
                start.wait(timeout=10)
                call()
            except BaseException as exc:  # Test captures the exact competing outcome.
                result = ("error", type(exc).__name__)
            else:
                result = ("ok", None)
            finally:
                close_old_connections()
            with result_lock:
                results.append(result)

        threads = [Thread(target=run, args=(call,), daemon=True) for call in calls]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads), "Database race did not finish.")
        self.assertEqual(len(results), len(calls))
        return results

    def _user(self, username, role):
        return User.objects.create_user(
            username=username,
            password="Long-Safe-Pass-741!",
            role=role,
        )

    def _assigned_lead(self, *, agent, manager, suffix="race"):
        customer = Customer.objects.create(
            full_name=f"Customer {suffix}",
            created_by=agent,
        )
        lead = Lead.objects.create(
            customer=customer,
            created_by=agent,
            assigned_to=agent,
            assigned_by=manager,
            assigned_at=timezone.now(),
        )
        return customer, lead

    def test_last_platform_admin_guard_is_serialized(self):
        first = self._user("race-admin-one", User.Role.PLATFORM_ADMIN)
        second = self._user("race-admin-two", User.Role.PLATFORM_ADMIN)

        results = self._run_race(
            lambda: change_user_role(
                actor=User.objects.get(pk=first.pk),
                target=User.objects.get(pk=second.pk),
                role=User.Role.SALES_MANAGER,
            ),
            lambda: update_crm_user(
                actor=User.objects.get(pk=second.pk),
                target=User.objects.get(pk=first.pk),
                is_active=False,
            ),
        )

        self.assertEqual(sum(result[0] == "ok" for result in results), 1)
        self.assertEqual(
            User.objects.filter(role=User.Role.PLATFORM_ADMIN, is_active=True).count(),
            1,
        )
        self.assertEqual(
            ActivityLog.objects.filter(
                operation__in=["user.role_changed", "user.updated"],
            ).count(),
            1,
        )

    def test_global_active_phone_identity_wins_once(self):
        first = self._user("race-phone-one", User.Role.SALES_MANAGER)
        second = self._user("race-phone-two", User.Role.SALES_MANAGER)
        first_customer = Customer.objects.create(full_name="First", created_by=first)
        second_customer = Customer.objects.create(full_name="Second", created_by=second)

        results = self._run_race(
            lambda: create_customer_phone(
                actor=User.objects.get(pk=first.pk),
                customer=Customer.objects.get(pk=first_customer.pk),
                raw_phone="09121234567",
            ),
            lambda: create_customer_phone(
                actor=User.objects.get(pk=second.pk),
                customer=Customer.objects.get(pk=second_customer.pk),
                raw_phone="+98 912 123 4567",
            ),
        )

        self.assertEqual(sum(result[0] == "ok" for result in results), 1)
        self.assertEqual(
            CustomerPhone.objects.filter(
                normalized_phone="+989121234567",
                is_active=True,
            ).count(),
            1,
        )

    def test_sale_price_snapshot_is_linear_with_product_update(self):
        manager = self._user("race-price-manager", User.Role.SALES_MANAGER)
        other_manager = self._user("race-price-other", User.Role.SALES_MANAGER)
        agent = self._user("race-price-agent", User.Role.SALES_AGENT)
        customer, lead = self._assigned_lead(agent=agent, manager=manager, suffix="price")
        product = Product.objects.create(
            sku="RACE-PRICE",
            name="Race Price",
            current_price=Decimal("10.00"),
            created_by=manager,
            updated_by=manager,
        )

        results = self._run_race(
            lambda: update_product(
                actor=User.objects.get(pk=other_manager.pk),
                product=Product.objects.get(pk=product.pk),
                current_price=Decimal("25.00"),
            ),
            lambda: mark_sale(
                actor=User.objects.get(pk=agent.pk),
                lead=Lead.objects.get(pk=lead.pk),
                product=Product.objects.get(pk=product.pk),
                quantity=2,
                sold_at=timezone.now(),
            ),
        )

        self.assertEqual([result[0] for result in results].count("ok"), 2)
        product.refresh_from_db()
        sale = Sale.objects.get(customer=customer)
        self.assertEqual(product.current_price, Decimal("25.00"))
        self.assertIn(sale.unit_price_snapshot, {Decimal("10.00"), Decimal("25.00")})
        self.assertEqual(sale.total_amount, sale.unit_price_snapshot * sale.quantity)

    def test_cancel_race_has_one_transition_and_one_audit_row(self):
        first = self._user("race-cancel-one", User.Role.SALES_MANAGER)
        second = self._user("race-cancel-two", User.Role.SALES_MANAGER)
        agent = self._user("race-cancel-agent", User.Role.SALES_AGENT)
        customer, lead = self._assigned_lead(agent=agent, manager=first, suffix="cancel")
        sale = Sale.objects.create(
            lead=lead,
            customer=customer,
            sold_by=agent,
            total_amount=Decimal("10.00"),
            sold_at=timezone.now(),
        )

        results = self._run_race(
            lambda: cancel_sale(
                actor=User.objects.get(pk=first.pk),
                sale=Sale.objects.get(pk=sale.pk),
            ),
            lambda: cancel_sale(
                actor=User.objects.get(pk=second.pk),
                sale=Sale.objects.get(pk=sale.pk),
            ),
        )

        sale.refresh_from_db()
        self.assertEqual(sum(result[0] == "ok" for result in results), 1)
        self.assertEqual(sale.status, Sale.Status.CANCELLED)
        self.assertEqual(
            ActivityLog.objects.filter(
                operation="sale.cancelled",
                object_id=str(sale.pk),
            ).count(),
            1,
        )

    def test_reassignment_and_sale_use_one_lead_order(self):
        manager = self._user("race-lead-manager", User.Role.SALES_MANAGER)
        first_agent = self._user("race-lead-first", User.Role.SALES_AGENT)
        second_agent = self._user("race-lead-second", User.Role.SALES_AGENT)
        customer, lead = self._assigned_lead(
            agent=first_agent,
            manager=manager,
            suffix="lead",
        )

        results = self._run_race(
            lambda: reassign_lead(
                actor=User.objects.get(pk=manager.pk),
                lead=Lead.objects.get(pk=lead.pk),
                to_user=User.objects.get(pk=second_agent.pk),
                reason="race proof",
            ),
            lambda: mark_sale(
                actor=User.objects.get(pk=first_agent.pk),
                lead=Lead.objects.get(pk=lead.pk),
                total_amount=Decimal("10.00"),
                sold_at=timezone.now(),
            ),
        )

        lead.refresh_from_db()
        self.assertEqual(lead.assigned_to, second_agent)
        self.assertEqual(LeadAssignmentHistory.objects.filter(lead=lead).count(), 1)
        self.assertEqual(Sale.objects.filter(lead=lead).count(), sum(result[0] == "ok" for result in results) - 1)
        if Sale.objects.filter(lead=lead).exists():
            self.assertEqual(Sale.objects.get(lead=lead).sold_by, first_agent)


@POSTGRES_ONLY
class PostgresMigrationUpgradeTests(TransactionTestCase):
    def test_sales_upgrade_from_0004_keeps_valid_business_rows(self):
        manager = User.objects.create_user(
            username="upgrade-manager",
            password="Long-Safe-Pass-741!",
            role=User.Role.SALES_MANAGER,
        )
        agent = User.objects.create_user(
            username="upgrade-agent",
            password="Long-Safe-Pass-741!",
            role=User.Role.SALES_AGENT,
        )
        customer = Customer.objects.create(full_name="Upgrade", created_by=agent)
        CustomerPhone.objects.create(
            customer=customer,
            raw_phone="09121234567",
            normalized_phone="+989121234567",
            is_primary=True,
        )
        product = Product.objects.create(
            sku="UPGRADE-PRODUCT",
            name="Upgrade Product",
            current_price=Decimal("10.00"),
            created_by=manager,
            updated_by=manager,
        )
        lead = Lead.objects.create(
            customer=customer,
            created_by=agent,
            assigned_to=agent,
            assigned_by=manager,
            assigned_at=timezone.now(),
        )
        interaction = Interaction.objects.create(
            lead=lead,
            customer=customer,
            agent=agent,
            phone="09121234567",
            direction=Interaction.Direction.OUTBOUND,
            outcome="answered",
            occurred_at=timezone.now(),
        )
        sale = Sale.objects.create(
            lead=lead,
            customer=customer,
            sold_by=agent,
            product=product,
            quantity=2,
            unit_price_snapshot=Decimal("10.00"),
            total_amount=Decimal("20.00"),
            sold_at=timezone.now(),
        )

        old_target = [("sales", "0004_lead_lead_assignment_fields_consistent")]
        new_target = [("sales", "0010_interaction_contract")]
        try:
            MigrationExecutor(connection).migrate(old_target)
            old_executor = MigrationExecutor(connection)
            old_apps = old_executor.loader.project_state(old_target).apps
            OldInteraction = old_apps.get_model("sales", "Interaction")
            old_row = OldInteraction.objects.get(pk=interaction.pk)
            self.assertEqual(old_row.direction, "outbound")
            self.assertEqual(old_row.outcome, "answered")
            OldSale = old_apps.get_model("sales", "Sale")
            old_sale = OldSale.objects.get(pk=sale.pk)
            self.assertEqual(old_sale.unit_price_snapshot, Decimal("10.00"))
            self.assertEqual(old_sale.total_amount, Decimal("20.00"))

            old_executor.migrate(new_target)
        finally:
            # This is a TransactionTestCase, so schema changes are not rolled
            # back: the database must be returned to the newest migration state,
            # not merely to new_target. Leaving it at 0010 would strip every
            # later sales column from each test that runs afterwards.
            #
            # Every app is restored, not just sales: unapplying sales back to
            # 0004 also unapplies the migrations that depend on it, which drops
            # the aftersales and communications tables.
            restore_executor = MigrationExecutor(connection)
            restore_executor.migrate(restore_executor.loader.graph.leaf_nodes())

        self.assertTrue(
            MigrationRecorder(connection).migration_qs.filter(
                app="sales",
                name="0010_interaction_contract",
            ).exists()
        )
        interaction.refresh_from_db()
        self.assertEqual(interaction.direction, Interaction.Direction.OUTBOUND)
        self.assertEqual(interaction.outcome, "answered")
        sale.refresh_from_db()
        self.assertEqual(sale.total_amount, sale.unit_price_snapshot * sale.quantity)
