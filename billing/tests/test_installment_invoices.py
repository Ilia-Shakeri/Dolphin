"""Payment type on an invoice: cash or instalments (2.32.0).

An instalment invoice stores its terms as a draft, builds its schedule when it
is issued (the down payment is row 0), reschedules when the count or the down
payment changes, is paid down payment first, and is cancelled as a whole.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from billing.installments import display_status, schedule_rows, set_invoice_installments
from billing.models import Installment, InstallmentPlan, Invoice, Payment
from billing.payments import allocate_payment, register_payment
from billing.services import cancel_invoice, create_invoice, issue_invoice
from common.exceptions import BusinessConflictError, BusinessRuleError
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-938!"


class InstallmentInvoiceTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="ii.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری اقساط", phone={"raw_phone": "09129990022", "is_primary": True}
        )
        self.product = create_product(
            actor=self.manager, sku="II-1", name="کالای اقساط", current_price=Decimal("1000.00")
        )
        self.first_due = timezone.localdate() + timedelta(days=30)

    def _invoice(self, **terms):
        terms.setdefault("payment_type", Invoice.PaymentType.INSTALLMENT)
        if terms["payment_type"] == Invoice.PaymentType.INSTALLMENT:
            terms.setdefault("installment_down_payment", Decimal("600.00"))
            terms.setdefault("installment_count", 3)
            terms.setdefault("installment_first_due", self.first_due)
            terms.setdefault("installment_interval_days", 30)
        return create_invoice(
            actor=self.manager, customer=self.customer,
            items=[{"product": self.product, "quantity": 3}], **terms,
        )

    def _issued(self, **terms):
        return issue_invoice(actor=self.manager, invoice=self._invoice(**terms))

    def _rows(self, invoice):
        return list(
            InstallmentPlan.objects.get(invoice=invoice).installments.order_by("sequence")
            .values_list("sequence", "amount", "paid_amount", "status")
        )

    def _pay(self, invoice, amount):
        payment = register_payment(
            actor=self.manager, customer=self.customer, method=Payment.Method.CASH, amount=Decimal(amount)
        )
        allocate_payment(actor=self.manager, payment=payment, invoice=invoice)
        invoice.refresh_from_db()

    def test_schedule_puts_the_remainder_on_the_first_instalment(self):
        rows = schedule_rows(
            total_amount=Decimal("1000.00"), down_payment=Decimal("100.00"), installment_count=3,
            first_due=date(2026, 10, 1), interval_days=10, down_due=date(2026, 9, 1),
        )
        self.assertEqual([r[0] for r in rows], [0, 1, 2, 3])
        self.assertEqual([r[2] for r in rows], [Decimal("100.00"), Decimal("300.00"), Decimal("300.00"), Decimal("300.00")])
        self.assertEqual(rows[2][1], date(2026, 10, 11))
        odd = schedule_rows(
            total_amount=Decimal("100.00"), down_payment=Decimal("0"), installment_count=3,
            first_due=date(2026, 10, 1), interval_days=10, down_due=date(2026, 9, 1),
        )
        self.assertEqual([r[2] for r in odd], [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")])

    def test_draft_stores_terms_and_builds_no_rows_until_issue(self):
        invoice = self._invoice()
        self.assertEqual(invoice.payment_type, "installment")
        self.assertEqual(invoice.installment_down_payment, Decimal("600.00"))
        self.assertFalse(InstallmentPlan.objects.filter(invoice=invoice).exists())
        issued = issue_invoice(actor=self.manager, invoice=invoice)
        rows = self._rows(issued)
        self.assertEqual([r[0] for r in rows], [0, 1, 2, 3])
        self.assertEqual(sum(r[1] for r in rows), issued.total_amount)
        self.assertEqual(rows[0][1], Decimal("600.00"))

    def test_zero_down_payment_has_no_down_row(self):
        issued = self._issued(installment_down_payment=Decimal("0"))
        self.assertEqual([r[0] for r in self._rows(issued)], [1, 2, 3])

    def test_cash_invoice_is_unchanged_and_builds_no_plan(self):
        issued = self._issued(payment_type=Invoice.PaymentType.CASH)
        self.assertEqual(issued.payment_type, "cash")
        self.assertFalse(InstallmentPlan.objects.filter(invoice=issued).exists())

    def test_bad_terms_are_refused(self):
        with self.assertRaises(BusinessRuleError):
            self._invoice(installment_down_payment=Decimal("3000.00"))
        with self.assertRaises(BusinessRuleError):
            self._invoice(installment_count=None)
        with self.assertRaises(BusinessRuleError):
            self._invoice(installment_first_due=None)
        with self.assertRaises(BusinessRuleError):
            self._invoice(payment_type=Invoice.PaymentType.CASH, installment_count=3)

    def test_changing_count_and_down_payment_reschedules_an_issued_invoice(self):
        issued = self._issued()
        set_invoice_installments(actor=self.manager, invoice=issued, installment_count=4, down_payment=Decimal("1000"))
        rows = self._rows(issued)
        self.assertEqual([r[1] for r in rows], [Decimal("1000.00")] + [Decimal("500.00")] * 4)
        issued.refresh_from_db()
        self.assertEqual(issued.installment_count, 4)

    def test_rescheduling_keeps_money_already_paid(self):
        issued = self._issued()
        self._pay(issued, "700.00")
        set_invoice_installments(actor=self.manager, invoice=issued, installment_count=2, down_payment=Decimal("500"))
        rows = self._rows(issued)
        self.assertEqual([r[2] for r in rows], [Decimal("500.00"), Decimal("200.00"), Decimal("0.00")])
        self.assertEqual(rows[0][3], "paid")
        self.assertEqual(rows[1][3], "partially_paid")

    def test_draft_can_be_edited_before_issue(self):
        invoice = self._invoice()
        set_invoice_installments(actor=self.manager, invoice=invoice, installment_count=6)
        invoice.refresh_from_db()
        self.assertEqual(invoice.installment_count, 6)
        issued = issue_invoice(actor=self.manager, invoice=invoice)
        self.assertEqual(len(self._rows(issued)), 7)

    def test_cash_invoice_cannot_be_given_instalments(self):
        issued = self._issued(payment_type=Invoice.PaymentType.CASH)
        with self.assertRaises(BusinessConflictError):
            set_invoice_installments(actor=self.manager, invoice=issued, installment_count=3)

    def test_receipt_pays_down_payment_first_then_overflows_in_order(self):
        issued = self._issued()
        self._pay(issued, "650.00")
        rows = self._rows(issued)
        self.assertEqual([r[2] for r in rows], [Decimal("600.00"), Decimal("50.00"), Decimal("0.00"), Decimal("0.00")])
        self._pay(issued, "1000.00")
        rows = self._rows(issued)
        self.assertEqual([r[3] for r in rows], ["paid", "paid", "partially_paid", "pending"])
        self.assertEqual(rows[2][2], Decimal("250.00"))
        issued.refresh_from_db()
        self.assertEqual(issued.balance_due, Decimal("1350.00"))

    def test_cancelling_the_invoice_cancels_every_row(self):
        issued = self._issued()
        cancel_invoice(actor=self.manager, invoice=issued, reason="آزمون")
        plan = InstallmentPlan.objects.get(invoice=issued)
        self.assertEqual(plan.status, InstallmentPlan.Status.CANCELLED)
        self.assertEqual(
            set(plan.installments.values_list("status", flat=True)), {Installment.Status.CANCELLED}
        )

    def test_display_status_rules(self):
        today = date(2026, 9, 29)

        def status(due, paid="0", state="pending", invoice="issued"):
            return display_status(
                invoice_status=invoice, status=state, due_date=due, paid_amount=Decimal(paid), today=today
            )

        self.assertEqual(status(today - timedelta(days=1)), "overdue")
        self.assertEqual(status(today), "due_today")
        self.assertEqual(status(today + timedelta(days=2)), "near_due")
        self.assertEqual(status(today + timedelta(days=3)), "pending")
        self.assertEqual(status(today, paid="5", state="partially_paid"), "partially_paid")
        self.assertEqual(status(today, paid="9", state="paid"), "paid")
        self.assertEqual(status(today, state="paid", invoice="cancelled"), "cancelled")

    def test_api_lists_rows_with_display_status_and_filters_by_it(self):
        issued = self._issued()
        api = APIClient()
        api.force_authenticate(self.manager)
        listing = api.get("/api/v1/installments/").json()
        results = listing["results"] if isinstance(listing, dict) else listing
        self.assertEqual(len(results), 4)
        self.assertEqual(results[0]["customer_name"], "مشتری اقساط")
        self.assertEqual(results[0]["invoice_number"], issued.number)
        self.assertIn("display_status", results[0])
        pending = api.get("/api/v1/installments/?status=pending").json()
        pending = pending["results"] if isinstance(pending, dict) else pending
        self.assertTrue(all(row["display_status"] == "pending" for row in pending))
        self.assertEqual(api.get("/api/v1/installments/?status=bogus").status_code, 400)

    def test_api_edit_and_summary(self):
        issued = self._issued()
        api = APIClient()
        api.force_authenticate(self.manager)
        response = api.post(
            f"/api/v1/invoices/{issued.pk}/set-installments/",
            {"installment_count": 2, "down_payment": "0"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["rows"]), 2)
        summary = api.get(f"/api/v1/invoices/{issued.pk}/installments/").json()
        self.assertTrue(summary["editable"])
        patched = api.patch(
            f"/api/v1/invoices/{issued.pk}/", {"installment_count": 9}, format="json"
        )
        self.assertEqual(patched.status_code, 400)
