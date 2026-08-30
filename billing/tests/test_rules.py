"""Billing rules: arithmetic, status graph, money bounds, and the ledger."""

from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.core.cache import cache
from django.test import TestCase, override_settings

from accounts.models import User
from billing.ledger import current_balance
from billing.models import (
    Cheque,
    CustomerLedgerEntry,
    Installment,
    Invoice,
    Order,
    Payment,
    PaymentAllocation,
    Quotation,
)
from billing.numbering import next_document_number
from billing.payments import (
    allocate_payment,
    cancel_payment,
    create_installment_plan,
    register_payment,
    release_allocation,
    transition_cheque,
)
from billing.services import (
    cancel_invoice,
    convert_quotation_to_order,
    create_invoice,
    create_quotation,
    issue_invoice,
    replace_invoice_items,
    transition_quotation,
    update_invoice,
)
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from inventory.models import StockItem, StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product


class BillingFixtureMixin:
    def build(self):
        self.manager = User.objects.create_user(
            username="bill.manager", password="Strong-pass-937!", role=User.Role.SALES_MANAGER
        )
        self.platform_admin = User.objects.create_user(
            username="rules.status_admin", password="Strong-pass-937!", role=User.Role.PLATFORM_ADMIN
        )
        self.agent = User.objects.create_user(
            username="bill.agent", password="Strong-pass-937!", role=User.Role.SALES_AGENT
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری",
            phone={"raw_phone": "09121230000", "is_primary": True},
        )
        self.product = create_product(
            actor=self.manager, sku="B-1", name="کالا", current_price=Decimal("100.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="wh", name="انبار")
        record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=100,
            unit_cost=Decimal("60.00"),
        )

    def draft_invoice(self, quantity=5, **extra):
        return create_invoice(
            actor=self.manager,
            customer=self.customer,
            items=[{"product": self.product, "quantity": quantity}],
            **extra,
        )


class DocumentArithmeticTests(BillingFixtureMixin, TestCase):
    def setUp(self):
        self.build()

    def test_percentage_and_absolute_line_discounts_cannot_be_given_together(self):
        with self.assertRaises(BusinessRuleError):
            create_quotation(
                actor=self.manager,
                customer=self.customer,
                items=[{
                    "product": self.product,
                    "quantity": 2,
                    "discount_percent": Decimal("10"),
                    "discount_amount": Decimal("5"),
                }],
            )

    def test_header_totals_equal_the_sum_of_the_stored_lines(self):
        quotation = create_quotation(
            actor=self.manager,
            customer=self.customer,
            items=[
                {"product": self.product, "quantity": 3},
                {"product": self.product, "quantity": 2, "discount_percent": Decimal("50")},
            ],
            discount_amount=Decimal("50.00"),
            tax_rate=Decimal("10"),
        )
        lines = sum(item.line_total for item in quotation.items.all())
        self.assertEqual(quotation.subtotal_amount, lines)
        self.assertEqual(quotation.subtotal_amount, Decimal("400.00"))
        self.assertEqual(quotation.tax_amount, Decimal("35.00"))
        self.assertEqual(
            quotation.total_amount,
            quotation.subtotal_amount - quotation.discount_amount + quotation.tax_amount,
        )

    def test_a_header_discount_larger_than_the_subtotal_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            create_quotation(
                actor=self.manager,
                customer=self.customer,
                items=[{"product": self.product, "quantity": 1}],
                discount_amount=Decimal("500.00"),
            )

    def test_tax_is_off_unless_the_deployment_configures_it(self):
        quotation = create_quotation(
            actor=self.manager,
            customer=self.customer,
            items=[{"product": self.product, "quantity": 1}],
        )
        self.assertEqual(quotation.tax_rate, Decimal("0.00"))
        self.assertEqual(quotation.tax_amount, Decimal("0.00"))

    @override_settings(BILLING_DEFAULT_TAX_RATE="9.00")
    def test_the_configured_default_tax_rate_is_applied_to_a_new_document(self):
        quotation = create_quotation(
            actor=self.manager,
            customer=self.customer,
            items=[{"product": self.product, "quantity": 1}],
        )
        self.assertEqual(quotation.tax_rate, Decimal("9.00"))
        self.assertEqual(quotation.tax_amount, Decimal("9.00"))

    def test_a_document_needs_at_least_one_line(self):
        with self.assertRaises(BusinessRuleError):
            create_quotation(actor=self.manager, customer=self.customer, items=[])

    def test_line_price_is_snapshotted_and_a_later_catalogue_change_does_not_move_it(self):
        from sales.services import update_product

        quotation = create_quotation(
            actor=self.manager,
            customer=self.customer,
            items=[{"product": self.product, "quantity": 2}],
        )
        update_product(actor=self.manager, product=self.product, current_price=Decimal("999.00"))
        quotation.refresh_from_db()
        self.assertEqual(quotation.items.first().unit_price, Decimal("100.00"))
        self.assertEqual(quotation.total_amount, Decimal("200.00"))


class DocumentStatusTests(BillingFixtureMixin, TestCase):
    def setUp(self):
        self.build()

    def test_an_unlisted_status_jump_is_refused(self):
        quotation = create_quotation(
            actor=self.manager,
            customer=self.customer,
            items=[{"product": self.product, "quantity": 1}],
        )
        with self.assertRaises(BusinessConflictError):
            transition_quotation(
                actor=self.manager, quotation=quotation, to_status=Quotation.Status.ACCEPTED
            )

    def test_an_issued_invoices_lines_stay_frozen(self):
        """The lines and everything they add up to are a snapshot the customer
        has already been given; nothing here may move once issued."""
        invoice = self.draft_invoice()
        issue_invoice(actor=self.manager, invoice=invoice)
        invoice.refresh_from_db()
        with self.assertRaises(BusinessConflictError):
            replace_invoice_items(
                actor=self.manager,
                invoice=invoice,
                items=[{"product": self.product, "quantity": 1}],
            )

    def test_an_issued_invoice_may_only_have_its_note_corrected(self):
        """The one narrow exception, added when the product owner asked for a
        way to fix a note without cancelling and reissuing the whole document.

        Everything with accounting or legal weight — discount, tax, the stated
        document date, the official/unofficial type — stays refused exactly as
        it was before this exception existed.
        """
        invoice = self.draft_invoice()
        issue_invoice(actor=self.manager, invoice=invoice)
        invoice.refresh_from_db()

        updated = update_invoice(actor=self.manager, invoice=invoice, notes="پس از صدور")
        self.assertEqual(updated.notes, "پس از صدور")

        for changes in (
            {"discount_amount": Decimal("10.00")},
            {"tax_rate": Decimal("9.00")},
            {"document_date": date(2026, 1, 1)},
            {"invoice_type": Invoice.InvoiceType.OFFICIAL},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(BusinessConflictError):
                    update_invoice(actor=self.manager, invoice=invoice, **changes)

    def test_converting_an_unaccepted_quotation_is_refused(self):
        quotation = create_quotation(
            actor=self.manager,
            customer=self.customer,
            items=[{"product": self.product, "quantity": 1}],
        )
        with self.assertRaises(BusinessConflictError):
            convert_quotation_to_order(actor=self.manager, quotation=quotation)

    def test_a_quotation_yields_at_most_one_live_order(self):
        quotation = create_quotation(
            actor=self.manager,
            customer=self.customer,
            items=[{"product": self.product, "quantity": 1}],
        )
        transition_quotation(actor=self.manager, quotation=quotation, to_status=Quotation.Status.SENT)
        quotation.refresh_from_db()
        transition_quotation(actor=self.manager, quotation=quotation, to_status=Quotation.Status.ACCEPTED)
        quotation.refresh_from_db()
        convert_quotation_to_order(actor=self.manager, quotation=quotation)
        with self.assertRaises(BusinessConflictError):
            convert_quotation_to_order(actor=self.manager, quotation=quotation)

    def test_an_agent_may_draft_a_document_and_may_not_issue_one(self):
        # The agent drafts for a customer of their own: object scope and role
        # permission are separate controls, and this test is about the second.
        own_customer = create_customer_with_phone(
            actor=self.agent,
            full_name="مشتری بازاریاب",
            phone={"raw_phone": "09121230001", "is_primary": True},
        )
        invoice = create_invoice(
            actor=self.agent,
            customer=own_customer,
            items=[{"product": self.product, "quantity": 1}],
        )
        self.assertEqual(invoice.created_by, self.agent)
        with self.assertRaises(BusinessPermissionDenied):
            issue_invoice(actor=self.agent, invoice=invoice)

    def test_an_agent_cannot_draft_against_another_users_customer(self):
        with self.assertRaises(BusinessPermissionDenied):
            create_invoice(
                actor=self.agent,
                customer=self.customer,
                items=[{"product": self.product, "quantity": 1}],
            )


class InvoiceIssueTests(BillingFixtureMixin, TestCase):
    """Issuing an invoice, including the optional stock effect.

    That effect is **off** for Client-1, where the order owns the inventory
    lifecycle and an invoice moves nothing. The capability is kept for a
    deployment that invoices straight out of stock with no order step, so the
    tests that exercise it turn it on explicitly rather than relying on a
    default that no longer holds.
    """

    def setUp(self):
        self.build()

    @override_settings(BILLING_INVOICE_AFFECTS_STOCK=True)
    def test_issuing_deducts_stock_snapshots_cost_and_posts_the_ledger_together(self):
        invoice = self.draft_invoice(quantity=5, warehouse=self.warehouse)
        issue_invoice(actor=self.manager, invoice=invoice)
        invoice.refresh_from_db()
        item = StockItem.objects.get(warehouse=self.warehouse, product=self.product)
        self.assertEqual(item.quantity, 95)
        self.assertEqual(invoice.items.first().unit_cost_snapshot, Decimal("60.00"))
        self.assertEqual(current_balance(self.customer), invoice.total_amount)
        self.assertTrue(invoice.stock_applied)

    @override_settings(BILLING_INVOICE_AFFECTS_STOCK=True)
    def test_a_stock_shortfall_aborts_the_whole_issue(self):
        invoice = self.draft_invoice(quantity=500, warehouse=self.warehouse)
        with self.assertRaises(BusinessConflictError):
            issue_invoice(actor=self.manager, invoice=invoice)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        self.assertEqual(StockItem.objects.get(warehouse=self.warehouse, product=self.product).quantity, 100)
        self.assertEqual(current_balance(self.customer), Decimal("0.00"))

    def test_an_invoice_without_a_warehouse_takes_no_stock_and_records_no_cost(self):
        invoice = self.draft_invoice(quantity=5)
        issue_invoice(actor=self.manager, invoice=invoice)
        invoice.refresh_from_db()
        self.assertEqual(StockItem.objects.get(warehouse=self.warehouse, product=self.product).quantity, 100)
        self.assertIsNone(invoice.items.first().unit_cost_snapshot)
        self.assertFalse(invoice.stock_applied)

    @override_settings(BILLING_INVOICE_AFFECTS_STOCK=False)
    def test_a_deployment_may_switch_the_stock_effect_off(self):
        invoice = self.draft_invoice(quantity=5, warehouse=self.warehouse)
        issue_invoice(actor=self.manager, invoice=invoice)
        self.assertEqual(StockItem.objects.get(warehouse=self.warehouse, product=self.product).quantity, 100)

    def test_cancelling_returns_the_stock_and_reverses_the_ledger(self):
        invoice = self.draft_invoice(quantity=5, warehouse=self.warehouse)
        issue_invoice(actor=self.manager, invoice=invoice)
        invoice.refresh_from_db()
        cancel_invoice(actor=self.manager, invoice=invoice, reason="اصلاح")
        self.assertEqual(StockItem.objects.get(warehouse=self.warehouse, product=self.product).quantity, 100)
        self.assertEqual(current_balance(self.customer), Decimal("0.00"))
        # Both ledger entries survive: a reversal is another row, never a delete.
        self.assertEqual(CustomerLedgerEntry.objects.filter(customer=self.customer).count(), 2)

    def test_an_invoice_with_money_on_it_cannot_be_cancelled_underneath_the_payment(self):
        invoice = self.draft_invoice(quantity=5, warehouse=self.warehouse)
        issue_invoice(actor=self.manager, invoice=invoice)
        invoice.refresh_from_db()
        payment = register_payment(
            actor=self.manager, customer=self.customer, method=Payment.Method.CASH, amount=Decimal("100.00")
        )
        allocate_payment(actor=self.manager, payment=payment, invoice=invoice)
        invoice.refresh_from_db()
        with self.assertRaises(BusinessConflictError):
            cancel_invoice(actor=self.manager, invoice=invoice)


class PaymentTests(BillingFixtureMixin, TestCase):
    def setUp(self):
        self.build()
        self.invoice = self.draft_invoice(quantity=5, warehouse=self.warehouse)
        self.invoice = issue_invoice(actor=self.manager, invoice=self.invoice)

    def pay(self, amount, **extra):
        return register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal(amount),
            **extra,
        )

    def test_a_repeated_idempotency_key_returns_the_original_payment(self):
        first = self.pay("100.00", idempotency_key="till-1")
        second = self.pay("100.00", idempotency_key="till-1")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(current_balance(self.customer), self.invoice.total_amount - Decimal("100.00"))

    def test_allocation_never_exceeds_the_invoice(self):
        """Allocating more than the invoice owes is still refused.

        The surplus half of this test is gone with بند ۳.۴: a receipt larger
        than the debt can no longer be registered at all, so there is no
        overpayment left to sit on account. The invoice-side limit still
        matters, because a receipt can legitimately cover several invoices and
        must not pour all of itself into the first one.
        """
        payment = self.pay(str(self.invoice.total_amount))
        with self.assertRaises(BusinessRuleError):
            allocate_payment(
                actor=self.manager,
                payment=payment,
                invoice=self.invoice,
                amount=self.invoice.total_amount + Decimal("1.00"),
            )
        allocate_payment(actor=self.manager, payment=payment, invoice=self.invoice)
        self.invoice.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, self.invoice.total_amount)
        self.assertEqual(payment.unallocated_amount, Decimal("0.00"))

    def test_a_receipt_larger_than_the_debt_is_refused(self):
        """بند ۳.۴ — «اضافه پرداخت نداریم این آپشنو حذف کن»."""
        with self.assertRaises(BusinessRuleError) as caught:
            self.pay(str(self.invoice.total_amount + Decimal("0.01")))
        self.assertIn("amount", caught.exception.detail)

    def test_money_on_account_is_not_an_overpayment(self):
        """A customer with no issued invoice has no debt to exceed.

        بند ۳.۱ allows a receipt to sit unallocated and be assigned later, which
        is exactly a deposit taken before invoicing. Refusing that would have
        broken the ordinary case while chasing بند ۳.۴.
        """
        from sales.services import create_customer_with_phone

        fresh = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری بی‌فاکتور",
            phone={"raw_phone": "09121119999", "is_primary": True},
        )
        payment = register_payment(
            actor=self.manager,
            customer=fresh,
            method=Payment.Method.CASH,
            amount=Decimal("5000.00"),
        )
        self.assertEqual(payment.unallocated_amount, Decimal("5000.00"))

    def test_an_unallocated_payment_still_credits_the_customer_account(self):
        self.pay("50.00")
        self.assertEqual(current_balance(self.customer), self.invoice.total_amount - Decimal("50.00"))

    def test_releasing_an_allocation_restores_both_sides_and_deletes_nothing(self):
        payment = self.pay("200.00")
        allocation = allocate_payment(actor=self.manager, payment=payment, invoice=self.invoice)
        release_allocation(actor=self.manager, allocation=allocation, reason="اصلاح")
        self.invoice.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("0.00"))
        self.assertEqual(payment.allocated_amount, Decimal("0.00"))
        self.assertEqual(PaymentAllocation.objects.count(), 1)
        self.assertTrue(PaymentAllocation.objects.get().is_reversed)

    def test_cancelling_a_payment_releases_its_allocations_and_reverses_the_credit(self):
        payment = self.pay("200.00")
        allocate_payment(actor=self.manager, payment=payment, invoice=self.invoice)
        cancel_payment(actor=self.manager, payment=payment, reason="برگشت")
        self.invoice.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CANCELLED)
        self.assertEqual(self.invoice.paid_amount, Decimal("0.00"))
        self.assertEqual(current_balance(self.customer), self.invoice.total_amount)

    def test_an_agent_cannot_register_or_cancel_a_payment(self):
        with self.assertRaises(BusinessPermissionDenied):
            register_payment(
                actor=self.agent,
                customer=self.customer,
                method=Payment.Method.CASH,
                amount=Decimal("10.00"),
            )

    def test_a_draft_invoice_cannot_receive_a_payment(self):
        draft = self.draft_invoice(quantity=1)
        payment = self.pay("10.00")
        with self.assertRaises(BusinessConflictError):
            allocate_payment(actor=self.manager, payment=payment, invoice=draft)


class ChequeTests(BillingFixtureMixin, TestCase):
    def setUp(self):
        self.build()

    def register_cheque(self, amount="300.00"):
        return register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CHEQUE,
            amount=Decimal(amount),
            cheque={
                "bank_name": "بانک ملت",
                "serial_number": "554433",
                "due_date": date(2026, 12, 1),
            },
        )

    def test_receiving_a_cheque_credits_the_customer_before_it_clears(self):
        """The product owner's rule since 1.3.0, and a reversal of the old one.

        Their staff treat handing over a cheque as settling the account. Waiting
        for clearance left balances showing debts both sides considered paid,
        and the reconciliation calls that followed were the actual complaint.
        """
        payment = self.register_cheque()
        self.assertEqual(payment.status, Payment.Status.CONFIRMED)
        self.assertEqual(current_balance(self.customer), Decimal("-300.00"))

    def test_a_new_cheque_is_pending_and_not_yet_registered(self):
        """The two axes start independent, and both start at their zero."""
        cheque = Cheque.objects.get(payment=self.register_cheque())
        self.assertEqual(cheque.status, Cheque.Status.PENDING)
        self.assertFalse(cheque.is_registered)

    def test_clearing_a_cheque_does_not_credit_the_customer_twice(self):
        """The credit was already taken at registration; clearing confirms it."""
        payment = self.register_cheque()
        cheque = Cheque.objects.get(payment=payment)
        transition_cheque(actor=self.manager, cheque=cheque, to_status=Cheque.Status.CLEARED)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CONFIRMED)
        self.assertEqual(current_balance(self.customer), Decimal("-300.00"))
        self.assertEqual(
            CustomerLedgerEntry.objects.filter(customer=self.customer).count(), 1
        )

    def test_a_bounced_cheque_takes_its_credit_back(self):
        """Answer 4.3: on a bounce, the amount returns to what is owed.

        The credit is reversed rather than deleted, so the ledger keeps both
        movements and the bounce stays auditable instead of looking like a
        cheque that was never received.
        """
        payment = self.register_cheque()
        cheque = Cheque.objects.get(payment=payment)
        self.assertEqual(current_balance(self.customer), Decimal("-300.00"))
        transition_cheque(actor=self.manager, cheque=cheque, to_status=Cheque.Status.BOUNCED)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CANCELLED)
        self.assertEqual(current_balance(self.customer), Decimal("0.00"))
        self.assertEqual(
            CustomerLedgerEntry.objects.filter(customer=self.customer).count(), 2
        )

    def test_an_unlisted_cheque_transition_is_refused(self):
        """CLEARED is terminal — a cleared cheque cannot later bounce."""
        cheque = Cheque.objects.get(payment=self.register_cheque())
        transition_cheque(actor=self.manager, cheque=cheque, to_status=Cheque.Status.CLEARED)
        cheque.refresh_from_db()
        with self.assertRaises(BusinessConflictError):
            transition_cheque(actor=self.manager, cheque=cheque, to_status=Cheque.Status.BOUNCED)

    @override_settings(BILLING_CHEQUE_CREDITS_ON="cleared")
    def test_a_deployment_may_wait_for_clearance_before_crediting(self):
        """The opposite accounting choice is still reachable by configuration."""
        payment = self.register_cheque()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(current_balance(self.customer), Decimal("0.00"))
        cheque = Cheque.objects.get(payment=payment)
        transition_cheque(actor=self.manager, cheque=cheque, to_status=Cheque.Status.CLEARED)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CONFIRMED)
        self.assertEqual(current_balance(self.customer), Decimal("-300.00"))


class InstallmentTests(BillingFixtureMixin, TestCase):
    def setUp(self):
        self.build()
        self.invoice = issue_invoice(
            actor=self.manager, invoice=self.draft_invoice(quantity=3, warehouse=self.warehouse)
        )

    def test_a_plan_sums_exactly_to_the_invoice(self):
        plan = create_installment_plan(
            actor=self.manager, invoice=self.invoice, installment_count=7, start_date=date(2026, 9, 1)
        )
        amounts = list(plan.installments.order_by("sequence").values_list("amount", flat=True))
        self.assertEqual(sum(amounts), self.invoice.total_amount)
        self.assertEqual(len(amounts), 7)

    def test_a_payment_fills_installments_from_the_earliest_due_date(self):
        plan = create_installment_plan(
            actor=self.manager, invoice=self.invoice, installment_count=3, start_date=date(2026, 9, 1)
        )
        first_due = plan.installments.order_by("sequence").first()
        payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=first_due.amount,
        )
        allocate_payment(actor=self.manager, payment=payment, invoice=self.invoice, amount=first_due.amount)
        first_due.refresh_from_db()
        self.assertEqual(first_due.status, Installment.Status.PAID)
        self.assertEqual(
            plan.installments.filter(status=Installment.Status.PENDING).count(), 2
        )

    def test_releasing_the_allocation_unwinds_the_plan_exactly(self):
        plan = create_installment_plan(
            actor=self.manager, invoice=self.invoice, installment_count=3, start_date=date(2026, 9, 1)
        )
        payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal("120.00"),
        )
        allocation = allocate_payment(actor=self.manager, payment=payment, invoice=self.invoice)
        release_allocation(actor=self.manager, allocation=allocation)
        self.assertEqual(
            list(plan.installments.order_by("sequence").values_list("paid_amount", flat=True)),
            [Decimal("0.00")] * 3,
        )

    def test_only_one_plan_per_invoice(self):
        create_installment_plan(
            actor=self.manager, invoice=self.invoice, installment_count=2, start_date=date(2026, 9, 1)
        )
        with self.assertRaises(BusinessConflictError):
            create_installment_plan(
                actor=self.manager, invoice=self.invoice, installment_count=2, start_date=date(2026, 9, 1)
            )

    def test_a_draft_invoice_cannot_be_split(self):
        with self.assertRaises(BusinessConflictError):
            create_installment_plan(
                actor=self.manager,
                invoice=self.draft_invoice(quantity=1),
                installment_count=2,
                start_date=date(2026, 9, 1),
            )


class NumberingTests(BillingFixtureMixin, TestCase):
    def setUp(self):
        self.build()

    def test_numbers_advance_and_do_not_repeat(self):
        numbers = {next_document_number("invoice") for _ in range(20)}
        self.assertEqual(len(numbers), 20)
        self.assertTrue(all(value.startswith("INV-") for value in numbers))

    def test_an_unknown_document_kind_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            next_document_number("receipt")

    @override_settings(BILLING_NUMBER_FORMATS={"invoice": "FIXED"})
    def test_a_format_without_the_counter_is_refused_rather_than_colliding(self):
        with self.assertRaises(BusinessRuleError):
            next_document_number("invoice")

    @override_settings(BILLING_NUMBER_FORMATS={"invoice": "FA-{sequence:04d}"})
    def test_the_configured_format_is_honoured(self):
        self.assertEqual(next_document_number("invoice"), "FA-0001")

    def test_the_database_refuses_a_duplicate_number_independently(self):
        invoice = self.draft_invoice(quantity=1)
        duplicate = self.draft_invoice(quantity=1)
        duplicate.number = invoice.number
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                duplicate.save(update_fields=["number"])


class LedgerTests(BillingFixtureMixin, TestCase):
    def setUp(self):
        self.build()

    def test_the_balance_chain_matches_the_sum_of_every_entry(self):
        invoice = issue_invoice(
            actor=self.manager, invoice=self.draft_invoice(quantity=2, warehouse=self.warehouse)
        )
        register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal("50.00"),
        )
        entries = CustomerLedgerEntry.objects.filter(customer=self.customer)
        computed = sum(entry.debit - entry.credit for entry in entries)
        self.assertEqual(current_balance(self.customer), computed)
        self.assertEqual(current_balance(self.customer), invoice.total_amount - Decimal("50.00"))

    def test_every_entry_carries_exactly_one_side(self):
        issue_invoice(actor=self.manager, invoice=self.draft_invoice(quantity=1))
        for entry in CustomerLedgerEntry.objects.all():
            self.assertNotEqual(entry.debit > 0, entry.credit > 0)


class DocumentLineScopeTests(BillingFixtureMixin, TestCase):
    """The nested line serializer must really scope its product field.

    Regression: the nested serializer is constructed before DRF binds it to a
    parent, so its own `__init__` sees an empty context. That left the product
    queryset empty and the API refused every line — fail-closed, but it made the
    whole document API unusable, and the fix must not overshoot into accepting
    a product the caller may not use.
    """

    def setUp(self):
        # Throttle buckets are keyed by user id, and a rolled-back test hands
        # the next one the same ids — so a class that makes many requests can
        # inherit the previous class's spend and get 429 where it expected 201.
        # Every other request-heavy class in this suite clears it the same way.
        cache.clear()
        self.build()

    def test_the_api_accepts_a_line_for_a_product_in_scope(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            "/api/v1/quotations/",
            data={"customer": self.customer.pk, "items": [{"product": self.product.pk, "quantity": 2}]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["line_items"][0]["product"], self.product.pk)

    def test_the_api_refuses_a_line_for_an_inactive_product(self):
        from sales.services import deactivate_product

        # Activation is a Platform Admin action; this test is about the line
        # rule, so it uses the role that holds the action.
        deactivate_product(actor=self.platform_admin, product=self.product)
        self.client.force_login(self.manager)
        response = self.client.post(
            "/api/v1/quotations/",
            data={"customer": self.customer.pk, "items": [{"product": self.product.pk, "quantity": 1}]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("product", response.json()["items"][0])

    def test_the_items_action_scopes_its_lines_too(self):
        self.client.force_login(self.manager)
        quotation = self.client.post(
            "/api/v1/quotations/",
            data={"customer": self.customer.pk, "items": [{"product": self.product.pk, "quantity": 1}]},
            content_type="application/json",
        ).json()
        response = self.client.post(
            f"/api/v1/quotations/{quotation['id']}/items/",
            data={"items": [{"product": self.product.pk, "quantity": 5}]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["line_items"][0]["quantity"], 5)
        self.assertEqual(response.json()["total_amount"], "500.00")
