"""A cancelled invoice cannot be changed or deleted by anyone, by any path.

The rule lives on the model and its querysets, so it holds for the API, the
services, the shell and Django admin alike — and for the platform administrator,
who may otherwise correct or delete almost anything.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import Invoice, InvoiceItem
from billing.services import cancel_invoice, create_invoice, issue_invoice
from common.exceptions import BusinessConflictError
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-937!"


class CancelledInvoiceImmutableTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="imm.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.admin = User.objects.create_user(
            username="imm.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN
        )
        self.product = create_product(
            actor=self.manager, sku="IMM-1", name="کالا", current_price=Decimal("1000.00")
        )
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری", phone={"raw_phone": "09121110002"}
        )

    def draft(self):
        return create_invoice(
            actor=self.manager, customer=self.customer,
            items=[{"product": self.product, "quantity": 1, "unit_price": self.product.current_price}],
        )

    def cancelled(self):
        invoice = self.draft()
        issue_invoice(actor=self.manager, invoice=invoice)
        cancel_invoice(actor=self.manager, invoice=invoice, reason="آزمون")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CANCELLED)
        return invoice

    def test_the_cancellation_flow_itself_still_works(self):
        self.cancelled()

    def test_saving_a_cancelled_invoice_is_refused(self):
        invoice = self.cancelled()
        invoice.notes = "تغییر"
        with self.assertRaises(BusinessConflictError):
            invoice.save()
        invoice.refresh_from_db()
        self.assertNotEqual(invoice.notes, "تغییر")

    def test_a_queryset_update_cannot_reach_a_cancelled_invoice(self):
        invoice = self.cancelled()
        with self.assertRaises(BusinessConflictError):
            Invoice.objects.filter(pk=invoice.pk).update(notes="تغییر")
        with self.assertRaises(BusinessConflictError):
            Invoice.objects.all().update(notes="تغییر")

    def test_a_cancelled_invoice_cannot_be_deleted_even_in_bulk(self):
        invoice = self.cancelled()
        with self.assertRaises(BusinessConflictError):
            invoice.delete()
        with self.assertRaises(BusinessConflictError):
            Invoice.objects.filter(pk=invoice.pk).delete()
        self.assertTrue(Invoice.objects.filter(pk=invoice.pk).exists())

    def test_its_lines_cannot_be_changed_added_or_removed(self):
        invoice = self.cancelled()
        item = invoice.items.first()
        item.description = "تغییر"
        with self.assertRaises(BusinessConflictError):
            item.save()
        with self.assertRaises(BusinessConflictError):
            item.delete()
        with self.assertRaises(BusinessConflictError):
            InvoiceItem.objects.filter(invoice=invoice).update(description="تغییر")
        with self.assertRaises(BusinessConflictError):
            InvoiceItem.objects.filter(invoice=invoice).delete()
        with self.assertRaises(BusinessConflictError):
            InvoiceItem.objects.bulk_create([
                InvoiceItem(
                    invoice=invoice, product=self.product, line_number=9, quantity=1,
                    unit_price=Decimal("1.00"), line_total=Decimal("1.00"),
                )
            ])
        self.assertEqual(invoice.items.count(), 1)

    def test_the_platform_administrator_cannot_edit_or_delete_it_over_http(self):
        invoice = self.cancelled()
        client = APIClient()
        client.force_authenticate(self.admin)
        patched = client.patch(f"/api/v1/invoices/{invoice.pk}/", {"notes": "تغییر"}, format="json")
        deleted = client.delete(f"/api/v1/invoices/{invoice.pk}/")
        bulk = client.post("/api/v1/invoices/bulk-delete/", {"ids": [invoice.pk]}, format="json")
        for response in (patched, deleted, bulk):
            self.assertGreaterEqual(response.status_code, 400)
        invoice.refresh_from_db()
        self.assertNotEqual(invoice.notes, "تغییر")
        self.assertTrue(Invoice.objects.filter(pk=invoice.pk).exists())

    def test_an_issued_invoice_is_never_deleted_but_a_draft_can_be(self):
        issued = self.draft()
        issue_invoice(actor=self.manager, invoice=issued)
        with self.assertRaises(BusinessConflictError):
            issued.delete()
        with self.assertRaises(BusinessConflictError):
            Invoice.objects.filter(pk=issued.pk).delete()
        self.assertTrue(Invoice.objects.filter(pk=issued.pk).exists())

        draft = self.draft()
        draft.items.all().delete()
        draft.delete()
        self.assertFalse(Invoice.objects.filter(pk=draft.pk).exists())
