"""Issuing and rescheduling an instalment invoice never needs DELETE (2.40.17).

In production the application's PostgreSQL role has no DELETE on
`billing_installment` (`scripts/bootstrap-postgres.sh`: money is corrected,
never erased). The schedule used to be rebuilt by delete-and-recreate, so on
the test server every instalment invoice failed to issue with a
`ProgrammingError` («خطایی رخ داد»). The suite never saw it: tests connect as
a superuser. This test runs the same paths as a role with exactly that grant
missing.
"""

from decimal import Decimal
from unittest import skipUnless

from django.db import connection
from django.test import TestCase

from billing.installments import set_invoice_installments, visible_installments
from billing.models import InstallmentPlan
from billing.services import issue_invoice
from billing.tests import test_installment_invoices as base

ROLE = "dolphin_test_no_installment_delete"


@skipUnless(connection.vendor == "postgresql", "the grant only exists on PostgreSQL")
class WithoutDeleteGrantTests(TestCase):
    setUp = base.InstallmentInvoiceTests.setUp
    _invoice = base.InstallmentInvoiceTests._invoice

    def as_restricted_role(self):
        with connection.cursor() as cursor:
            cursor.execute(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN CREATE ROLE {ROLE} NOLOGIN; END IF; END $$;")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
            cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE}")
            cursor.execute(f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {ROLE}")
            cursor.execute(f"REVOKE DELETE ON billing_installment FROM {ROLE}")
            cursor.execute(f"SET LOCAL ROLE {ROLE}")

    def test_issue_and_reschedule_without_delete(self):
        draft = self._invoice()
        self.as_restricted_role()
        issued = issue_invoice(actor=self.manager, invoice=draft)
        plan = InstallmentPlan.objects.get(invoice=issued)
        self.assertEqual(plan.installments.count(), 4)  # down payment + 3
        set_invoice_installments(actor=self.manager, invoice=issued, installment_count=2, down_payment=Decimal("500"))
        visible = list(visible_installments(plan.installments.all()).order_by("sequence").values_list("sequence", flat=True))
        self.assertEqual(visible, [0, 1, 2])
        set_invoice_installments(actor=self.manager, invoice=issued, installment_count=4)
        visible = list(visible_installments(plan.installments.all()).order_by("sequence").values_list("sequence", flat=True))
        self.assertEqual(visible, [0, 1, 2, 3, 4])
