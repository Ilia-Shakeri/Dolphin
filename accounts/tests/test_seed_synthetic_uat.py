import os
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.management.commands.seed_synthetic_uat import (
    GUARDED_MODELS,
    database_identity_is_allowed,
)
from accounts.models import User
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


TEST_PASSWORD = "Uat-Only-Safe-Pass-963!"


class SeedSyntheticUatTests(TestCase):
    def assert_guarded_tables_empty(self):
        for model in GUARDED_MODELS:
            self.assertFalse(model.objects.exists(), model._meta.label)

    def run_seed(self, *, confirm=True, password=TEST_PASSWORD):
        stdout = StringIO()
        stderr = StringIO()
        environment = {
            "KARIZ_ALLOW_UAT_SEED": "1",
            "KARIZ_UAT_PASSWORD": password,
        }
        with patch.dict(os.environ, environment, clear=True):
            call_command(
                "seed_synthetic_uat",
                confirm_synthetic_data=confirm,
                stdout=stdout,
                stderr=stderr,
            )
        return stdout.getvalue(), stderr.getvalue()

    def test_requires_environment_gate_before_any_write(self):
        with patch.dict(
            os.environ,
            {"KARIZ_ALLOW_UAT_SEED": "0", "KARIZ_UAT_PASSWORD": TEST_PASSWORD},
            clear=True,
        ):
            with self.assertRaisesMessage(CommandError, "environment gate"):
                call_command("seed_synthetic_uat", confirm_synthetic_data=True)
        self.assert_guarded_tables_empty()

    def test_requires_explicit_confirmation_before_any_write(self):
        with self.assertRaisesMessage(CommandError, "confirmation flag"):
            self.run_seed(confirm=False)
        self.assert_guarded_tables_empty()

    def test_database_identity_guard_is_narrow(self):
        allowed = (
            ("sqlite", ":memory:", True),
            ("sqlite", "file:memorydb_default?mode=memory&cache=shared", True),
            ("postgresql", "uat_kariz_team_1", False),
        )
        denied = (
            ("sqlite", ":memory:", False),
            ("sqlite", "kariz.sqlite3", True),
            ("postgresql", "kariz", False),
            ("postgresql", "uat_kariz_", False),
            ("postgresql", "uat_kariz_BAD", False),
            ("postgresql", "uat_kariz_bad-name", False),
            ("mysql", "uat_kariz_team_1", False),
        )
        for vendor, name, test_settings in allowed:
            with self.subTest(vendor=vendor, name=name):
                self.assertTrue(
                    database_identity_is_allowed(
                        vendor,
                        name,
                        django_test_settings=test_settings,
                    )
                )
        for vendor, name, test_settings in denied:
            with self.subTest(vendor=vendor, name=name):
                self.assertFalse(
                    database_identity_is_allowed(
                        vendor,
                        name,
                        django_test_settings=test_settings,
                    )
                )

    def test_refuses_bad_database_before_password_or_write(self):
        with patch(
            "accounts.management.commands.seed_synthetic_uat.Command._database_is_allowed",
            return_value=False,
        ):
            with patch.dict(
                os.environ,
                {"KARIZ_ALLOW_UAT_SEED": "1"},
                clear=True,
            ):
                with self.assertRaisesMessage(CommandError, "not an allowed"):
                    call_command(
                        "seed_synthetic_uat",
                        confirm_synthetic_data=True,
                    )
        self.assert_guarded_tables_empty()

    def test_refuses_nonempty_guarded_table_before_password(self):
        ActivityLog.objects.create(
            actor=None,
            operation="test.guard",
            object_type="test.fixture",
            object_id="1",
            safe_changes={},
        )
        with patch.dict(
            os.environ,
            {"KARIZ_ALLOW_UAT_SEED": "1"},
            clear=True,
        ):
            with self.assertRaisesMessage(CommandError, "empty guarded tables"):
                call_command(
                    "seed_synthetic_uat",
                    confirm_synthetic_data=True,
                )
        self.assertEqual(ActivityLog.objects.count(), 1)
        self.assertFalse(User.objects.exists())

    def test_requires_validated_password_before_any_write(self):
        with patch.dict(
            os.environ,
            {"KARIZ_ALLOW_UAT_SEED": "1"},
            clear=True,
        ):
            with self.assertRaisesMessage(CommandError, "KARIZ_UAT_PASSWORD"):
                call_command(
                    "seed_synthetic_uat",
                    confirm_synthetic_data=True,
                )
        self.assert_guarded_tables_empty()

        with self.assertRaisesMessage(CommandError, "configured validation") as caught:
            self.run_seed(password="12345678")
        self.assertNotIn("12345678", str(caught.exception))
        self.assert_guarded_tables_empty()

    def test_creates_exact_synthetic_graph_without_secret_output(self):
        stdout, stderr = self.run_seed()

        expected_roles = {
            "uat_sales_agent": User.Role.SALES_AGENT,
            "uat_sales_manager": User.Role.SALES_MANAGER,
            "uat_company_it": User.Role.COMPANY_IT,
            "uat_platform_admin": User.Role.PLATFORM_ADMIN,
        }
        users = {user.username: user for user in User.objects.order_by("username")}
        self.assertEqual(
            {username: user.role for username, user in users.items()},
            expected_roles,
        )
        for user in users.values():
            self.assertTrue(user.is_active)
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)
            self.assertTrue(user.check_password(TEST_PASSWORD))
            self.assertNotEqual(user.password, TEST_PASSWORD)

        agent = users["uat_sales_agent"]
        manager = users["uat_sales_manager"]
        customer = Customer.objects.get()
        phone = CustomerPhone.objects.get()
        product = Product.objects.get()
        lead = Lead.objects.get()
        assignment = LeadAssignmentHistory.objects.get()
        interaction = Interaction.objects.get()
        sale = Sale.objects.get()

        self.assertEqual(customer.created_by, agent)
        self.assertIn("ساختگی", customer.full_name)
        self.assertEqual(phone.customer, customer)
        self.assertEqual(phone.normalized_phone, "+989000000000")
        self.assertTrue(phone.is_primary)
        self.assertEqual(product.created_by, manager)
        self.assertEqual(product.current_price, Decimal("125000.00"))
        self.assertEqual(lead.customer, customer)
        self.assertEqual(lead.interested_product, product)
        self.assertEqual(lead.created_by, agent)
        self.assertEqual(lead.assigned_to, agent)
        self.assertEqual(lead.assigned_by, manager)
        self.assertEqual(assignment.lead, lead)
        self.assertIsNone(assignment.from_user)
        self.assertEqual(assignment.to_user, agent)
        self.assertEqual(assignment.changed_by, manager)
        self.assertEqual(interaction.lead, lead)
        self.assertEqual(interaction.customer, customer)
        self.assertEqual(interaction.agent, agent)
        self.assertEqual(sale.lead, lead)
        self.assertEqual(sale.customer, customer)
        self.assertEqual(sale.sold_by, agent)
        self.assertEqual(sale.product, product)
        self.assertEqual(sale.quantity, 2)
        self.assertEqual(sale.unit_price_snapshot, Decimal("125000.00"))
        self.assertEqual(sale.total_amount, Decimal("250000.00"))
        self.assertEqual(sale.status, Sale.Status.CONFIRMED)

        serialized_audit = str(
            list(ActivityLog.objects.values("operation", "safe_changes"))
        )
        self.assertNotIn(TEST_PASSWORD, stdout)
        self.assertNotIn(TEST_PASSWORD, stderr)
        self.assertNotIn(TEST_PASSWORD, serialized_audit)
        self.assertEqual(
            ActivityLog.objects.filter(operation="user.uat_seeded").count(),
            4,
        )
        self.assertTrue(ActivityLog.objects.filter(operation="product.created").exists())
        self.assertTrue(ActivityLog.objects.filter(operation="lead.reassigned").exists())
        self.assertTrue(ActivityLog.objects.filter(operation="sale.created").exists())

    def test_rerun_refuses_without_changing_rows(self):
        self.run_seed()
        counts = {model: model.objects.count() for model in GUARDED_MODELS}
        with self.assertRaisesMessage(CommandError, "empty guarded tables"):
            self.run_seed()
        self.assertEqual(
            {model: model.objects.count() for model in GUARDED_MODELS},
            counts,
        )

    def test_failure_rolls_back_whole_graph(self):
        with patch(
            "accounts.management.commands.seed_synthetic_uat.mark_sale",
            side_effect=RuntimeError("sale fixture failed"),
        ):
            with self.assertRaises(RuntimeError):
                self.run_seed()
        self.assert_guarded_tables_empty()
        self.assertFalse(CustomerPhone.objects.exists())
        self.assertFalse(LeadAssignmentHistory.objects.exists())
