"""بند ۳ — one receipt divided between several invoices.

The product owner's answers to بند ۳ were: one invoice may be settled by several
receipts and one receipt may cover several invoices; do not separate them, but
give the operator the choice of which invoice a receipt goes to, and a place to
say how it is divided. Partial payment stays allowed. Overpayment does not
exist and its option is removed.

`allocate_payment` already applied one receipt to one invoice. What is pinned
here is the batch on top of it — that it is all-or-nothing, that it relaxes none
of the single-allocation rules, and that both sides of each invoice move.
"""

from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from billing.models import Invoice, Payment
from billing.payments import allocate_payment_across, register_payment
from billing.services import create_invoice, issue_invoice
from common.exceptions import BusinessConflictError, BusinessRuleError
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product


PASSWORD = "Strong-pass-937!"


class PaymentSplitTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="split.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.product = create_product(
            actor=self.manager, sku="SP-1", name="کالا", current_price=Decimal("100.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="spwh", name="انبار")
        record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=1000,
            unit_cost=Decimal("40.00"),
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری تقسیم",
            phone={"raw_phone": "09121230000", "is_primary": True},
        )
        self.other = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری دیگر",
            phone={"raw_phone": "09121230001", "is_primary": True},
        )

    def issued_invoice(self, *, quantity, customer=None):
        invoice = create_invoice(
            actor=self.manager,
            customer=customer or self.customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": quantity}],
        )
        return issue_invoice(actor=self.manager, invoice=invoice)

    def receipt(self, amount):
        return register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal(amount),
        )

    # --- the split itself --------------------------------------------------

    def test_one_receipt_settles_several_invoices(self):
        first = self.issued_invoice(quantity=1)
        second = self.issued_invoice(quantity=2)
        payment = self.receipt("300.00")

        allocations = allocate_payment_across(
            actor=self.manager,
            payment=payment,
            splits=[
                {"invoice": first, "amount": Decimal("100.00")},
                {"invoice": second, "amount": Decimal("200.00")},
            ],
        )

        self.assertEqual(len(allocations), 2)
        first.refresh_from_db()
        second.refresh_from_db()
        payment.refresh_from_db()
        # Each invoice's paid_amount rose and its balance fell, which is what
        # the product owner asked for in بند ۳.۲.
        self.assertEqual(first.paid_amount, Decimal("100.00"))
        self.assertEqual(first.balance_due, Decimal("0.00"))
        self.assertEqual(second.paid_amount, Decimal("200.00"))
        self.assertEqual(second.balance_due, Decimal("0.00"))
        self.assertEqual(payment.unallocated_amount, Decimal("0.00"))

    def test_a_split_may_be_partial_on_each_side(self):
        """بند ۳.۳ — partial payment stays allowed inside a split."""
        first = self.issued_invoice(quantity=2)
        second = self.issued_invoice(quantity=2)
        payment = self.receipt("150.00")

        allocate_payment_across(
            actor=self.manager,
            payment=payment,
            splits=[
                {"invoice": first, "amount": Decimal("120.00")},
                {"invoice": second, "amount": Decimal("30.00")},
            ],
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.balance_due, Decimal("80.00"))
        self.assertEqual(second.balance_due, Decimal("170.00"))
        self.assertEqual(first.settlement_status, Invoice.SettlementStatus.PARTIALLY_PAID)

    def test_an_omitted_amount_takes_what_the_invoice_still_owes(self):
        first = self.issued_invoice(quantity=1)
        second = self.issued_invoice(quantity=1)
        payment = self.receipt("200.00")

        allocate_payment_across(
            actor=self.manager,
            payment=payment,
            splits=[{"invoice": first}, {"invoice": second}],
        )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.balance_due, Decimal("0.00"))
        self.assertEqual(second.balance_due, Decimal("0.00"))

    # --- all of it or none of it -------------------------------------------

    def test_a_failing_row_undoes_the_rows_before_it(self):
        """The operator chose one split; they must not be left with half of it."""
        first = self.issued_invoice(quantity=1)
        second = self.issued_invoice(quantity=1)
        payment = self.receipt("200.00")

        with self.assertRaises(BusinessRuleError):
            allocate_payment_across(
                actor=self.manager,
                payment=payment,
                splits=[
                    {"invoice": first, "amount": Decimal("100.00")},
                    # More than this invoice owes: the whole batch must roll back.
                    {"invoice": second, "amount": Decimal("500.00")},
                ],
            )

        first.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(first.paid_amount, Decimal("0.00"))
        self.assertEqual(payment.allocated_amount, Decimal("0.00"))

    def test_the_same_invoice_twice_is_refused_as_such(self):
        """Rather than surfacing as a confusing conflict from the unique index."""
        invoice = self.issued_invoice(quantity=2)
        payment = self.receipt("200.00")
        with self.assertRaises(BusinessRuleError):
            allocate_payment_across(
                actor=self.manager,
                payment=payment,
                splits=[
                    {"invoice": invoice, "amount": Decimal("50.00")},
                    {"invoice": invoice, "amount": Decimal("50.00")},
                ],
            )

    def test_an_empty_split_is_refused(self):
        payment = self.receipt("100.00")
        with self.assertRaises(BusinessRuleError):
            allocate_payment_across(actor=self.manager, payment=payment, splits=[])

    # --- nothing is relaxed for being part of a batch ----------------------

    def test_a_split_cannot_exceed_what_the_receipt_holds(self):
        first = self.issued_invoice(quantity=2)
        second = self.issued_invoice(quantity=2)
        payment = self.receipt("100.00")
        with self.assertRaises(BusinessRuleError):
            allocate_payment_across(
                actor=self.manager,
                payment=payment,
                splits=[
                    {"invoice": first, "amount": Decimal("60.00")},
                    {"invoice": second, "amount": Decimal("60.00")},
                ],
            )
        payment.refresh_from_db()
        self.assertEqual(payment.allocated_amount, Decimal("0.00"))

    def test_a_split_cannot_reach_another_customers_invoice(self):
        mine = self.issued_invoice(quantity=1)
        theirs = self.issued_invoice(quantity=1, customer=self.other)
        payment = self.receipt("100.00")
        with self.assertRaises(BusinessRuleError):
            allocate_payment_across(
                actor=self.manager,
                payment=payment,
                splits=[{"invoice": mine}, {"invoice": theirs}],
            )

    def test_a_split_cannot_reach_a_draft_invoice(self):
        issued = self.issued_invoice(quantity=1)
        draft = create_invoice(
            actor=self.manager,
            customer=self.customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 1}],
        )
        payment = self.receipt("100.00")
        with self.assertRaises(BusinessConflictError):
            allocate_payment_across(
                actor=self.manager,
                payment=payment,
                splits=[{"invoice": issued}, {"invoice": draft}],
            )

    def test_a_disbursement_can_never_be_split_onto_invoices(self):
        """Money leaving the company must not reduce a customer's debt."""
        self.issued_invoice(quantity=1)
        disbursement = register_payment(
            actor=self.manager,
            customer=self.customer,
            direction=Payment.Direction.DISBURSEMENT,
            method=Payment.Method.CASH,
            amount=Decimal("50.00"),
            payee="گیرنده",
        )
        invoice = self.issued_invoice(quantity=1)
        with self.assertRaises(BusinessRuleError):
            allocate_payment_across(
                actor=self.manager, payment=disbursement, splits=[{"invoice": invoice}]
            )
