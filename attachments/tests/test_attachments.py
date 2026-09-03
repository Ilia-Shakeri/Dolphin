"""Attachments: the model constraints, the service (upload/delete), the
object-scope selector, and the API surface.

Every uploaded byte string below carries a real magic-byte header — proving
`_sniff_content_type` reads what a file actually is, never the client's
claimed `Content-Type` or filename, is the one thing worth a real check
rather than a mock.
"""

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from aftersales.services import create_after_sales_request
from attachments.models import Attachment
from attachments.selectors import attachments_for
from attachments.services import (
    delete_attachment,
    max_attachment_bytes,
    upload_attachment,
)
from auditlog.models import ActivityLog
from billing.services import create_invoice
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import (
    create_customer_with_phone,
    create_lead,
    create_product,
    register_sales_document,
)


PASSWORD = "Strong-pass-983!"

REAL_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
REAL_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
REAL_WEBP = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBP" + b"\x00" * 16
REAL_PDF = b"%PDF-1.4\n" + b"\x00" * 32
FAKE_JPEG_ACTUALLY_TEXT = b"this is not a jpeg, just text pretending to be one"


class AttachmentFixtures(TestCase):
    """Shared setup: one of each of the five parent record types."""

    def setUp(self):
        self.manager = User.objects.create_user(username="att.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="att.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.other_agent = User.objects.create_user(username="att.other.agent", password=PASSWORD, role=User.Role.SALES_AGENT)

        self.customer = create_customer_with_phone(
            actor=self.agent, full_name="مشتری پیوست", phone={"raw_phone": "09121110000", "is_primary": True},
        )
        self.lead = create_lead(actor=self.agent, customer=self.customer, source="تماس")

        product = create_product(actor=self.manager, sku="ATT-1", name="کالای پیوست", current_price=Decimal("100.00"))
        warehouse = create_warehouse(actor=self.manager, code="attwh", name="انبار پیوست")
        record_stock_movement(
            actor=self.manager, warehouse=warehouse, product=product,
            movement_type=StockMovement.MovementType.OPENING, quantity=10, unit_cost=Decimal("50.00"),
        )
        self.invoice = create_invoice(actor=self.agent, customer=self.customer, items=[{"product": product, "quantity": 1}])

        self.sales_document = register_sales_document(
            actor=self.manager, customer=self.customer, document_number="SD-ATT-1", postal_status="آماده ارسال",
        )
        self.after_sales_request = create_after_sales_request(
            actor=self.manager, customer=self.customer, subject="خرابی دستگاه", description="توضیح", status="باز",
        )


class UploadServiceTests(AttachmentFixtures):
    def test_a_real_jpeg_uploads_against_a_customer_and_is_sniffed_correctly(self):
        attachment = upload_attachment(
            actor=self.agent, field_name="customer", parent_id=self.customer.pk,
            original_filename="receipt.jpg", content=REAL_JPEG,
        )
        self.assertEqual(attachment.content_type, "image/jpeg")
        self.assertEqual(attachment.customer, self.customer)
        self.assertEqual(attachment.size_bytes, len(REAL_JPEG))
        self.assertEqual(bytes(attachment.content), REAL_JPEG)
        self.assertTrue(ActivityLog.objects.filter(operation="attachment.uploaded", object_id=str(attachment.pk)).exists())

    def test_upload_succeeds_against_each_of_the_five_parent_types(self):
        cases = [
            ("customer", self.customer.pk, REAL_PNG, "image/png"),
            ("lead", self.lead.pk, REAL_WEBP, "image/webp"),
            ("invoice", self.invoice.pk, REAL_PDF, "application/pdf"),
            ("sales_document", self.sales_document.pk, REAL_JPEG, "image/jpeg"),
            ("after_sales_request", self.after_sales_request.pk, REAL_PNG, "image/png"),
        ]
        for field_name, parent_id, content, expected_type in cases:
            with self.subTest(field_name=field_name):
                attachment = upload_attachment(
                    actor=self.manager, field_name=field_name, parent_id=parent_id,
                    original_filename="file", content=content,
                )
                self.assertEqual(getattr(attachment, f"{field_name}_id"), parent_id)
                self.assertEqual(attachment.content_type, expected_type)

    def test_content_that_does_not_match_any_allowed_signature_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            upload_attachment(
                actor=self.agent, field_name="customer", parent_id=self.customer.pk,
                original_filename="receipt.jpg", content=FAKE_JPEG_ACTUALLY_TEXT,
            )
        self.assertEqual(Attachment.objects.count(), 0)

    def test_a_file_over_the_size_limit_is_refused(self):
        oversized = REAL_JPEG + b"\x00" * max_attachment_bytes()
        with self.assertRaises(BusinessRuleError):
            upload_attachment(
                actor=self.agent, field_name="customer", parent_id=self.customer.pk,
                original_filename="big.jpg", content=oversized,
            )

    def test_an_empty_file_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            upload_attachment(
                actor=self.agent, field_name="customer", parent_id=self.customer.pk,
                original_filename="empty.jpg", content=b"",
            )

    def test_a_path_separator_in_the_filename_is_stripped(self):
        attachment = upload_attachment(
            actor=self.agent, field_name="customer", parent_id=self.customer.pk,
            original_filename="../../etc/passwd.jpg", content=REAL_JPEG,
        )
        self.assertNotIn("/", attachment.original_filename)
        self.assertNotIn("\\", attachment.original_filename)

    def test_an_agent_may_upload_to_their_own_customer_lead_and_invoice(self):
        for field_name, parent_id in (
            ("customer", self.customer.pk), ("lead", self.lead.pk), ("invoice", self.invoice.pk),
        ):
            with self.subTest(field_name=field_name):
                upload_attachment(
                    actor=self.agent, field_name=field_name, parent_id=parent_id,
                    original_filename="f.pdf", content=REAL_PDF,
                )

    def test_an_agent_may_not_upload_to_a_sales_document_or_after_sales_request(self):
        """Those two are register_sales_document/after_sales.manage-gated writes — elevated only, matching the parent."""
        for field_name, parent_id in (
            ("sales_document", self.sales_document.pk), ("after_sales_request", self.after_sales_request.pk),
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaises(BusinessPermissionDenied):
                    upload_attachment(
                        actor=self.agent, field_name=field_name, parent_id=parent_id,
                        original_filename="f.pdf", content=REAL_PDF,
                    )

    def test_a_lead_outside_the_actors_scope_is_refused(self):
        other_lead = create_lead(
            actor=self.other_agent,
            customer=create_customer_with_phone(
                actor=self.other_agent, full_name="مشتری دیگر", phone={"raw_phone": "09121110099"},
            ),
            source="تماس",
        )
        with self.assertRaises(BusinessRuleError):
            upload_attachment(
                actor=self.agent, field_name="lead", parent_id=other_lead.pk,
                original_filename="f.pdf", content=REAL_PDF,
            )

    def test_an_unknown_parent_id_is_refused_the_same_as_out_of_scope(self):
        with self.assertRaises(BusinessRuleError):
            upload_attachment(
                actor=self.manager, field_name="customer", parent_id=999999,
                original_filename="f.pdf", content=REAL_PDF,
            )


class DeleteServiceTests(AttachmentFixtures):
    def setUp(self):
        super().setUp()
        self.attachment = upload_attachment(
            actor=self.agent, field_name="customer", parent_id=self.customer.pk,
            original_filename="receipt.jpg", content=REAL_JPEG,
        )

    def test_the_uploader_agent_may_not_delete_their_own_upload(self):
        with self.assertRaises(BusinessPermissionDenied):
            delete_attachment(actor=self.agent, attachment=self.attachment)
        self.assertTrue(Attachment.objects.filter(pk=self.attachment.pk).exists())

    def test_a_manager_may_delete_and_it_is_logged(self):
        delete_attachment(actor=self.manager, attachment=self.attachment)
        self.assertFalse(Attachment.objects.filter(pk=self.attachment.pk).exists())
        self.assertTrue(ActivityLog.objects.filter(operation="attachment.deleted").exists())


class ModelConstraintTests(AttachmentFixtures):
    def test_zero_parents_is_refused_at_the_database_level(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Attachment.objects.create(
                    original_filename="f.jpg", content_type="image/jpeg", size_bytes=len(REAL_JPEG),
                    content=REAL_JPEG, uploaded_by=self.manager,
                )

    def test_two_parents_at_once_is_refused_at_the_database_level(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Attachment.objects.create(
                    customer=self.customer, lead=self.lead,
                    original_filename="f.jpg", content_type="image/jpeg", size_bytes=len(REAL_JPEG),
                    content=REAL_JPEG, uploaded_by=self.manager,
                )

    def test_a_disallowed_content_type_is_refused_at_the_database_level(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Attachment.objects.create(
                    customer=self.customer, original_filename="f.exe", content_type="application/x-executable",
                    size_bytes=10, content=b"x" * 10, uploaded_by=self.manager,
                )


class SelectorScopeTests(AttachmentFixtures):
    def setUp(self):
        super().setUp()
        self.attachment = upload_attachment(
            actor=self.agent, field_name="customer", parent_id=self.customer.pk,
            original_filename="receipt.jpg", content=REAL_JPEG,
        )

    def test_the_owning_agent_sees_it(self):
        queryset = attachments_for(self.agent, field_name="customer", parent_id=self.customer.pk)
        self.assertIn(self.attachment, queryset)

    def test_a_manager_sees_it_too(self):
        queryset = attachments_for(self.manager, field_name="customer", parent_id=self.customer.pk)
        self.assertIn(self.attachment, queryset)

    def test_an_unrelated_agent_sees_nothing_for_a_customer_outside_their_scope(self):
        queryset = attachments_for(self.other_agent, field_name="customer", parent_id=self.customer.pk)
        self.assertEqual(list(queryset), [])


class AttachmentAPITests(AttachmentFixtures):
    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def test_upload_download_and_list_round_trip_over_http(self):
        client = self.client_for(self.agent)
        upload = client.post(
            "/api/v1/attachments/",
            {"customer": self.customer.pk, "file": SimpleUploadedFile("receipt.jpg", REAL_JPEG, content_type="image/jpeg")},
            format="multipart",
        )
        self.assertEqual(upload.status_code, 200)
        attachment_id = upload.data["id"]
        self.assertEqual(upload.data["content_type"], "image/jpeg")
        self.assertNotIn("content", upload.data)

        listing = client.get("/api/v1/attachments/", {"customer": self.customer.pk})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data), 1)

        download = client.get(f"/api/v1/attachments/{attachment_id}/download/")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, REAL_JPEG)
        self.assertEqual(download["Content-Type"], "image/jpeg")
        self.assertIn("receipt.jpg", download["Content-Disposition"])

    def test_a_disallowed_file_type_is_refused_with_400(self):
        client = self.client_for(self.agent)
        response = client.post(
            "/api/v1/attachments/",
            {"customer": self.customer.pk, "file": SimpleUploadedFile("note.txt", FAKE_JPEG_ACTUALLY_TEXT, content_type="text/plain")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_naming_two_parents_at_once_is_a_400(self):
        client = self.client_for(self.agent)
        response = client.post(
            "/api/v1/attachments/",
            {
                "customer": self.customer.pk, "lead": self.lead.pk,
                "file": SimpleUploadedFile("f.jpg", REAL_JPEG, content_type="image/jpeg"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_an_out_of_scope_customer_is_refused_before_any_row_is_written(self):
        other_customer = create_customer_with_phone(
            actor=self.other_agent, full_name="مشتری خارج از دسترس", phone={"raw_phone": "09121110088"},
        )
        client = self.client_for(self.agent)
        response = client.post(
            "/api/v1/attachments/",
            {"customer": other_customer.pk, "file": SimpleUploadedFile("f.jpg", REAL_JPEG, content_type="image/jpeg")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Attachment.objects.count(), 0)

    def test_download_and_delete_are_404_outside_the_callers_scope(self):
        attachment = upload_attachment(
            actor=self.manager, field_name="customer", parent_id=self.customer.pk,
            original_filename="f.jpg", content=REAL_JPEG,
        )
        client = self.client_for(self.other_agent)
        self.assertEqual(client.get(f"/api/v1/attachments/{attachment.pk}/download/").status_code, 404)
        self.assertEqual(client.post(f"/api/v1/attachments/{attachment.pk}/delete/").status_code, 404)

    def test_an_agent_gets_403_deleting_even_within_scope(self):
        attachment = upload_attachment(
            actor=self.agent, field_name="customer", parent_id=self.customer.pk,
            original_filename="f.jpg", content=REAL_JPEG,
        )
        client = self.client_for(self.agent)
        response = client.post(f"/api/v1/attachments/{attachment.pk}/delete/")
        self.assertEqual(response.status_code, 403)

    def test_a_manager_can_delete_over_http(self):
        attachment = upload_attachment(
            actor=self.agent, field_name="customer", parent_id=self.customer.pk,
            original_filename="f.jpg", content=REAL_JPEG,
        )
        client = self.client_for(self.manager)
        response = client.post(f"/api/v1/attachments/{attachment.pk}/delete/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Attachment.objects.filter(pk=attachment.pk).exists())
