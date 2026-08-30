"""The manual-settlement and order-link endpoints, over HTTP.

The service layer is tested separately; what matters here is that the routes
enforce the same scope, refuse the same things, and publish enough for a reader
to tell a manual settlement from a real one.
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import CustomerLedgerEntry, Invoice, Payment, PaymentAllocation
from billing.services import create_invoice, create_order, issue_invoice
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product


PASSWORD = "Strong-pass-937!"


class InvoiceActionApiTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="ia.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="ia.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری API",
            phone={"raw_phone": "09129990000", "is_primary": True},
        )
        self.product = create_product(
            actor=self.manager, sku="IA-1", name="کالای API", current_price=Decimal("250.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="iawh", name="انبار API")
        record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=50,
            unit_cost=Decimal("100.00"),
        )
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.manager)

    def _issued(self, quantity=2):
        return issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.manager,
                customer=self.customer,
                items=[{"product": self.product, "quantity": quantity}],
            ),
        )

    # --- manual settlement --------------------------------------------------

    def test_the_endpoint_settles_on_an_exact_match_and_says_so(self):
        invoice = self._issued()
        response = self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/manual-paid/",
            {"amount": str(invoice.canonical_balance_due)},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["is_manually_settled"])
        self.assertEqual(Decimal(body["balance_due"]), Decimal("0.00"))
        self.assertEqual(body["settlement_status"], Invoice.SettlementStatus.PAID)
        # The canonical figure is published alongside, still telling the truth.
        self.assertEqual(Decimal(body["canonical_balance_due"]), invoice.total_amount)
        self.assertEqual(Decimal(body["paid_amount"]), Decimal("0.00"))

    def test_the_endpoint_writes_no_accounting_records(self):
        invoice = self._issued()
        before = (
            Payment.objects.count(),
            PaymentAllocation.objects.count(),
            CustomerLedgerEntry.objects.count(),
        )
        self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/manual-paid/",
            {"amount": str(invoice.canonical_balance_due)},
            format="json",
        )
        after = (
            Payment.objects.count(),
            PaymentAllocation.objects.count(),
            CustomerLedgerEntry.objects.count(),
        )
        self.assertEqual(before, after)

    def test_a_later_edit_cannot_unsettle_it_over_http(self):
        invoice = self._issued()
        self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/manual-paid/",
            {"amount": str(invoice.canonical_balance_due)},
            format="json",
        )
        response = self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/manual-paid/", {"amount": "1.00"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_manually_settled"])
        self.assertEqual(response.json()["settlement_status"], Invoice.SettlementStatus.PAID)

    def test_settlement_status_cannot_be_written_directly(self):
        invoice = self._issued()
        response = self.client_api.patch(
            f"/api/v1/invoices/{invoice.pk}/",
            {"settlement_status": Invoice.SettlementStatus.PAID},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_a_marketer_cannot_settle_an_invoice_they_do_not_own(self):
        invoice = self._issued()
        agent_client = APIClient()
        agent_client.force_authenticate(self.agent)
        response = agent_client.post(
            f"/api/v1/invoices/{invoice.pk}/manual-paid/",
            {"amount": str(invoice.canonical_balance_due)},
            format="json",
        )
        self.assertIn(response.status_code, (403, 404))

    # --- linking ------------------------------------------------------------

    def test_an_invoice_can_be_attached_to_an_order_over_http(self):
        invoice = self._issued()
        order = create_order(
            actor=self.manager,
            customer=self.customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 1}],
        )
        response = self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/link-order/", {"order": order.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["order"], order.pk)

    def test_the_link_can_be_cleared_with_null(self):
        invoice = self._issued()
        order = create_order(
            actor=self.manager,
            customer=self.customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 1}],
        )
        self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/link-order/", {"order": order.pk}, format="json"
        )
        response = self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/link-order/", {"order": None}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["order"])

    def test_the_settlement_filter_agrees_with_the_document(self):
        invoice = self._issued()
        self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/manual-paid/",
            {"amount": str(invoice.canonical_balance_due)},
            format="json",
        )
        paid = self.client_api.get("/api/v1/invoices/?settlement=paid").json()
        unpaid = self.client_api.get("/api/v1/invoices/?settlement=unpaid").json()
        self.assertIn(invoice.pk, [row["id"] for row in paid["results"]])
        self.assertNotIn(invoice.pk, [row["id"] for row in unpaid["results"]])


class InvoiceHeaderFromCreationTests(TestCase):
    """A rate typed on the «فاکتور تازه» dialog has to reach the invoice.

    It did not. The form collected `tax_rate`, the service accepted it, and the
    request in between simply never carried the field — so the tax box on the
    detail card stayed at zero and the total was the untaxed one, with nothing
    on screen to say why. The same request now carries the issue date, which is
    the document's own date rather than the moment it was keyed in.
    """

    def setUp(self):
        self.manager = User.objects.create_user(
            username="hdr.manager", password="Strong-pass-937!", role=User.Role.SALES_MANAGER
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری سربرگ",
            phone={"raw_phone": "09121250000", "is_primary": True},
        )
        self.product = create_product(
            actor=self.manager, sku="HDR-1", name="کالا", current_price=Decimal("1000.00")
        )

    def test_a_tax_rate_sent_on_creation_reaches_the_totals(self):
        response = self.client.post(
            "/api/v1/invoices/",
            {
                "customer": self.customer.pk,
                "tax_rate": "9.00",
                "items": [{"product": self.product.pk, "quantity": 2}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data["tax_rate"]), Decimal("9.00"))
        self.assertGreater(Decimal(response.data["tax_amount"]), Decimal("0"))
        self.assertEqual(
            Decimal(response.data["total_amount"]),
            Decimal(response.data["subtotal_amount"])
            - Decimal(response.data["discount_amount"])
            + Decimal(response.data["tax_amount"]),
        )

    def test_a_percentage_discount_rides_on_the_lines(self):
        """The discount is a percentage and each line already has one, so no new
        header concept was invented for it."""
        response = self.client.post(
            "/api/v1/invoices/",
            {
                "customer": self.customer.pk,
                "items": [{"product": self.product.pk, "quantity": 2, "discount_percent": "10.00"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data["total_amount"]), Decimal("1800.00"))

    def test_the_document_date_is_the_operators_and_survives_issuing(self):
        """«تاریخ صدور» has its own field, and that is the whole point of it.

        `issued_at` could not carry this: a check constraint,
        `invoice_draft_has_no_issue_time`, says a draft must not have one,
        because issuing is what sets it. A stated document date is a different
        fact — it exists while the invoice is still a draft, and a paper invoice
        carries the date it was written rather than the moment it was keyed in.
        """
        response = self.client.post(
            "/api/v1/invoices/",
            {
                "customer": self.customer.pk,
                "document_date": "2026-05-20",
                "items": [{"product": self.product.pk, "quantity": 1}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        invoice = Invoice.objects.get(pk=response.data["id"])
        self.assertEqual(str(invoice.document_date), "2026-05-20")
        # And the invariant it was built around is untouched.
        self.assertIsNone(invoice.issued_at)

        issue_invoice(actor=self.manager, invoice=invoice)
        invoice.refresh_from_db()
        self.assertEqual(str(invoice.document_date), "2026-05-20")
        self.assertIsNotNone(invoice.issued_at)

    def test_an_unstated_document_date_is_filled_in_by_issuing(self):
        """So the column reading it is never blank for an issued document."""
        invoice = create_invoice(
            actor=self.manager,
            customer=self.customer,
            items=[{"product": self.product, "quantity": 1}],
        )
        self.assertIsNone(invoice.document_date)
        issue_invoice(actor=self.manager, invoice=invoice)
        invoice.refresh_from_db()
        self.assertIsNotNone(invoice.document_date)
        self.assertEqual(invoice.document_date, timezone.localdate(invoice.issued_at))

    def test_the_document_date_can_be_corrected_while_the_invoice_is_a_draft(self):
        invoice = create_invoice(
            actor=self.manager,
            customer=self.customer,
            items=[{"product": self.product, "quantity": 1}],
        )
        response = self.client.patch(
            f"/api/v1/invoices/{invoice.pk}/", {"document_date": "2026-03-01"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        invoice.refresh_from_db()
        self.assertEqual(str(invoice.document_date), "2026-03-01")

    def test_a_draft_still_refuses_an_issue_date(self):
        """The invariant that `document_date` exists because of.

        `invoice_draft_has_no_issue_time` says a draft's `issued_at` must be
        NULL, because issuing is the thing that sets it. That is why the
        operator's stated «تاریخ صدور» could not simply be written here: every
        save would have failed the constraint, and it surfaced as a number
        conflict rather than as anything resembling the real cause.

        The product owner chose the separate field over relaxing this, so the
        invariant stays and is pinned here — `issued_at` remains the system's
        own record of issuing, and nothing outside `issue_invoice` may set it.
        """
        response = self.client.post(
            "/api/v1/invoices/",
            {
                "customer": self.customer.pk,
                "issued_at": "2026-05-20T08:30:00Z",
                "items": [{"product": self.product.pk, "quantity": 1}],
            },
            format="json",
        )
        # Refused rather than accepted and dropped, which is the better of the
        # two: a caller that sends a date is told it did not take effect.
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("issued_at", response.data)

        # And the date still arrives the only way it can — by issuing.
        # The service takes model instances; the pk form above is the API's.
        invoice = create_invoice(
            actor=self.manager,
            customer=self.customer,
            items=[{"product": self.product, "quantity": 1}],
        )
        self.assertIsNone(invoice.issued_at)
        issue_invoice(actor=self.manager, invoice=invoice)
        invoice.refresh_from_db()
        self.assertIsNotNone(invoice.issued_at)
