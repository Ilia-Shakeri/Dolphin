"""بند ۶.۳ — a marketer sees the balance of their own customers, and no others.

The product owner was asked whether a marketer should see their customers'
balances and answered yes. Before this, the ledger was elevated-roles only and
a marketer got an empty queryset.

What is pinned here is that the answer was implemented as **permission plus
object scope**, not by widening the company-wide capability: a marketer holds
`ledger.own`, never `ledger.company`, and the selector confines them to the
customers `customers_for` already gives them.
"""

from decimal import Decimal

from django.test import TestCase

from accounts.access import capabilities_for, has_any_capability
from accounts.models import User
from billing.selectors import ledger_entries_for
from billing.services import create_invoice, issue_invoice
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product


PASSWORD = "Strong-pass-937!"


class MarketerLedgerScopeTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="ls.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.marketer = User.objects.create_user(
            username="ls.marketer", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.other_marketer = User.objects.create_user(
            username="ls.other", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.product = create_product(
            actor=self.manager, sku="LS-1", name="کالا", current_price=Decimal("100.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="lswh", name="انبار")
        record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=500,
            unit_cost=Decimal("40.00"),
        )
        self.mine = self.customer_of(self.marketer, "09121250001", "مشتری من")
        self.theirs = self.customer_of(self.other_marketer, "09121250002", "مشتری دیگری")
        self.invoice_for(self.mine)
        self.invoice_for(self.theirs)

    def customer_of(self, owner, phone, name):
        return create_customer_with_phone(
            actor=owner,
            full_name=name,
            phone={"raw_phone": phone, "is_primary": True},
        )

    def invoice_for(self, customer):
        invoice = create_invoice(
            actor=self.manager,
            customer=customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 1}],
        )
        return issue_invoice(actor=self.manager, invoice=invoice)

    # --- permission --------------------------------------------------------

    def test_a_marketer_may_read_a_ledger_at_all(self):
        self.assertTrue(has_any_capability(self.marketer, "ledger.own"))

    def test_a_marketer_never_holds_the_company_wide_capability(self):
        """Which is the whole reason `ledger.own` is a separate name."""
        self.assertNotIn("ledger.company", capabilities_for(self.marketer))

    def test_a_manager_still_holds_the_company_wide_capability(self):
        self.assertIn("ledger.company", capabilities_for(self.manager))

    # --- object scope ------------------------------------------------------

    def test_a_marketer_sees_their_own_customers_movements(self):
        customers = set(
            ledger_entries_for(self.marketer).values_list("customer_id", flat=True)
        )
        self.assertIn(self.mine.pk, customers)

    def test_a_marketer_never_sees_another_marketers_customer(self):
        customers = set(
            ledger_entries_for(self.marketer).values_list("customer_id", flat=True)
        )
        self.assertNotIn(self.theirs.pk, customers)

    def test_a_manager_sees_both(self):
        customers = set(
            ledger_entries_for(self.manager).values_list("customer_id", flat=True)
        )
        self.assertIn(self.mine.pk, customers)
        self.assertIn(self.theirs.pk, customers)

    def test_an_after_sales_agent_still_sees_nothing(self):
        """The ledger was never theirs and بند ۶.۳ did not widen it to them."""
        after_sales = User.objects.create_user(
            username="ls.after",
            password=PASSWORD,
            role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )
        self.assertFalse(ledger_entries_for(after_sales).exists())
