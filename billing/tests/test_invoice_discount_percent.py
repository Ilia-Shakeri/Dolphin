"""An invoice's discount as one percentage for the whole document (2.26.0).

Product-owner decision: the discount entered in «فاکتور تازه» is the
document's, not each line's. It is stored as `Invoice.discount_percent` and
`discount_amount` is derived from it on every recompute; tax is charged on
what is left after it, as before.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import Invoice
from billing.services import (
    create_invoice,
    issue_invoice,
    reissue_invoice,
    replace_invoice_items,
    update_invoice,
)
from common.exceptions import BusinessConflictError, BusinessRuleError
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-938!"


class InvoiceDiscountPercentTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="dp.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری تخفیف", phone={"raw_phone": "09129990011", "is_primary": True}
        )
        self.product = create_product(
            actor=self.manager, sku="DP-1", name="کالای تخفیف", current_price=Decimal("1000.00")
        )
        warehouse = create_warehouse(actor=self.manager, code="dpwh", name="انبار تخفیف")
        record_stock_movement(
            actor=self.manager, warehouse=warehouse, product=self.product,
            movement_type=StockMovement.MovementType.OPENING, quantity=50, unit_cost=Decimal("500.00"),
        )
        self.api = APIClient()
        self.api.force_authenticate(self.manager)

    def _invoice(self, **header):
        return create_invoice(
            actor=self.manager, customer=self.customer,
            items=[{"product": self.product, "quantity": 3}], **header,
        )

    def test_the_percentage_is_the_documents_and_lines_stay_undiscounted(self):
        invoice = self._invoice(discount_percent=Decimal("10"), tax_rate=Decimal("9"))
        self.assertEqual(invoice.discount_percent, Decimal("10.00"))
        self.assertEqual(invoice.subtotal_amount, Decimal("3000.00"))
        self.assertEqual(invoice.discount_amount, Decimal("300.00"))
        # Tax on what is left after the discount, exactly as before.
        self.assertEqual(invoice.tax_amount, Decimal("243.00"))
        self.assertEqual(invoice.total_amount, Decimal("2943.00"))
        line = invoice.items.get()
        self.assertEqual(line.discount_amount, Decimal("0.00"))
        self.assertEqual(line.line_total, Decimal("3000.00"))

    def test_an_amount_discount_still_works_and_carries_no_percentage(self):
        invoice = self._invoice(discount_amount=Decimal("150"))
        self.assertIsNone(invoice.discount_percent)
        self.assertEqual(invoice.discount_amount, Decimal("150.00"))

    def test_percentage_and_amount_together_are_refused(self):
        with self.assertRaises(BusinessRuleError):
            self._invoice(discount_percent=Decimal("5"), discount_amount=Decimal("10"))

    def test_the_percentage_is_bounded(self):
        with self.assertRaises(BusinessRuleError):
            self._invoice(discount_percent=Decimal("120"))

    def test_changing_the_lines_keeps_the_percentage(self):
        invoice = self._invoice(discount_percent=Decimal("10"))
        replace_invoice_items(
            actor=self.manager, invoice=invoice, items=[{"product": self.product, "quantity": 5}]
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.discount_percent, Decimal("10.00"))
        self.assertEqual(invoice.discount_amount, Decimal("500.00"))

    def test_a_draft_can_change_its_rates(self):
        invoice = self._invoice(discount_percent=Decimal("10"), tax_rate=Decimal("9"))
        invoice = update_invoice(
            actor=self.manager, invoice=invoice, discount_percent=Decimal("20"), tax_rate=Decimal("10")
        )
        self.assertEqual(invoice.discount_amount, Decimal("600.00"))
        self.assertEqual(invoice.tax_amount, Decimal("240.00"))
        self.assertEqual(invoice.total_amount, Decimal("2640.00"))
        # An amount instead clears the percentage: one source, never two.
        invoice = update_invoice(actor=self.manager, invoice=invoice, discount_amount=Decimal("100"))
        self.assertIsNone(invoice.discount_percent)
        self.assertEqual(invoice.discount_amount, Decimal("100.00"))

    def test_an_issued_invoice_keeps_its_rates(self):
        invoice = issue_invoice(actor=self.manager, invoice=self._invoice(discount_percent=Decimal("10")))
        with self.assertRaises(BusinessConflictError):
            update_invoice(actor=self.manager, invoice=invoice, discount_percent=Decimal("20"))

    def test_a_reissue_keeps_the_percentage(self):
        invoice = issue_invoice(actor=self.manager, invoice=self._invoice(discount_percent=Decimal("15")))
        replacement = reissue_invoice(actor=self.manager, invoice=invoice)
        self.assertEqual(replacement.discount_percent, Decimal("15.00"))
        self.assertEqual(replacement.discount_amount, invoice.discount_amount)

    def test_the_api_takes_and_returns_the_percentage(self):
        response = self.api.post("/api/v1/invoices/", {
            "customer": self.customer.pk, "discount_percent": "12.5", "tax_rate": "0",
            "items": [{"product": self.product.pk, "quantity": 2}],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Decimal(response.json()["discount_percent"]), Decimal("12.50"))
        self.assertEqual(Decimal(response.json()["discount_amount"]), Decimal("250.00"))
        invoice_id = response.json()["id"]
        response = self.api.patch(f"/api/v1/invoices/{invoice_id}/", {"discount_percent": "5", "tax_rate": "9"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Decimal(response.json()["discount_amount"]), Decimal("100.00"))
        self.assertEqual(Decimal(response.json()["total_amount"]), Decimal("2071.00"))

    def test_existing_invoices_stay_as_they_were(self):
        """Every invoice before 2.26.0 has no percentage — null, not zero."""
        invoice = self._invoice()
        Invoice.objects.filter(pk=invoice.pk).update(discount_percent=None)
        invoice = update_invoice(actor=self.manager, invoice=invoice, notes="یادداشت")
        self.assertIsNone(invoice.discount_percent)
