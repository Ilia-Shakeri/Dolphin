"""The official / unofficial distinction on an invoice.

What this pins is narrow on purpose. `OPEN_BUSINESS_DECISIONS.md` D.3 to D.7 —
which tax applies, whether price is tax-inclusive, whether tax comes before or
after discount, how rounding works, and how official invoices are numbered — are
all still open. None of them is answered here, and these tests assert that they
are not: an official invoice and an unofficial one with the same lines must
still produce the same figures, because nothing about the type may change a
number until the product owner has decided how.

What the type does do is require the identities a tax document names, and refuse
the issue when they are absent.
"""

from decimal import Decimal

from django.test import TestCase, override_settings

from accounts.models import User
from billing.models import Invoice
from billing.services import (
    cancel_invoice,
    create_invoice,
    issue_invoice,
    official_invoice_identity_errors,
)
from common.exceptions import BusinessRuleError
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.models import Customer
from sales.services import create_customer_with_phone, create_product


PASSWORD = "Strong-pass-937!"
SELLER = {
    "SELLER_LEGAL_NAME": "فروشگاه نمونه",
    "SELLER_NATIONAL_ID": "10101010101",
    "SELLER_ECONOMIC_CODE": "411111111111",
    "SELLER_REGISTRATION_NUMBER": "۱۲۳۴۵",
    "SELLER_ADDRESS": "تهران، خیابان نمونه، پلاک ۱",
    "SELLER_POSTAL_CODE": "1234567890",
    "SELLER_CITY": "تهران",
    "SELLER_PHONE": "021-88888888",
}


class OfficialInvoiceTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="oi.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.product = create_product(
            actor=self.manager, sku="OI-1", name="کالا", current_price=Decimal("1000.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="oiwh", name="انبار")
        record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=500,
            unit_cost=Decimal("400.00"),
        )
        self.phone_counter = 0

    def make_customer(self, *, kind, national_id="", economic_code=""):
        self.phone_counter += 1
        return create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری آزمون",
            kind=kind,
            national_id=national_id,
            economic_code=economic_code,
            phone={"raw_phone": f"0912111{self.phone_counter:04d}", "is_primary": True},
        )

    def make_invoice(self, customer, *, invoice_type=Invoice.InvoiceType.UNOFFICIAL, quantity=1):
        invoice = create_invoice(
            actor=self.manager,
            customer=customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": quantity}],
        )
        if invoice_type != invoice.invoice_type:
            invoice.invoice_type = invoice_type
            invoice.save(update_fields=["invoice_type"])
        return invoice

    # --- the default -------------------------------------------------------

    def test_an_invoice_is_unofficial_unless_it_is_made_official(self):
        """Every invoice that predates the field was unofficial, so is every new one."""
        invoice = self.make_invoice(self.make_customer(kind=Customer.Kind.INDIVIDUAL))
        self.assertEqual(invoice.invoice_type, Invoice.InvoiceType.UNOFFICIAL)

    def test_an_unofficial_invoice_issues_with_no_identity_at_all(self):
        customer = self.make_customer(kind=Customer.Kind.INDIVIDUAL)
        issued = issue_invoice(actor=self.manager, invoice=self.make_invoice(customer))
        self.assertEqual(issued.status, Invoice.Status.ISSUED)

    # --- what official requires -------------------------------------------

    @override_settings(**SELLER)
    def test_an_official_invoice_needs_the_buyer_national_id(self):
        customer = self.make_customer(kind=Customer.Kind.INDIVIDUAL)
        invoice = self.make_invoice(customer, invoice_type=Invoice.InvoiceType.OFFICIAL)
        with self.assertRaises(BusinessRuleError) as caught:
            issue_invoice(actor=self.manager, invoice=invoice)
        self.assertIn("customer_national_id", caught.exception.detail)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)

    @override_settings(**SELLER)
    def test_a_legal_buyer_also_needs_an_economic_code(self):
        customer = self.make_customer(kind=Customer.Kind.LEGAL, national_id="10101010101")
        invoice = self.make_invoice(customer, invoice_type=Invoice.InvoiceType.OFFICIAL)
        with self.assertRaises(BusinessRuleError) as caught:
            issue_invoice(actor=self.manager, invoice=invoice)
        self.assertIn("customer_economic_code", caught.exception.detail)

    @override_settings(**SELLER)
    def test_an_individual_buyer_does_not_need_an_economic_code(self):
        """A natural person has no economic code; requiring one would be wrong."""
        customer = self.make_customer(kind=Customer.Kind.INDIVIDUAL, national_id="0012345678")
        issued = issue_invoice(
            actor=self.manager,
            invoice=self.make_invoice(customer, invoice_type=Invoice.InvoiceType.OFFICIAL),
        )
        self.assertEqual(issued.status, Invoice.Status.ISSUED)

    @override_settings(**SELLER)
    def test_a_complete_legal_buyer_issues(self):
        customer = self.make_customer(
            kind=Customer.Kind.LEGAL, national_id="10101010101", economic_code="411111111111"
        )
        issued = issue_invoice(
            actor=self.manager,
            invoice=self.make_invoice(customer, invoice_type=Invoice.InvoiceType.OFFICIAL),
        )
        self.assertEqual(issued.status, Invoice.Status.ISSUED)

    # --- the seller side ---------------------------------------------------

    @override_settings(SELLER_LEGAL_NAME="", SELLER_NATIONAL_ID="", SELLER_ECONOMIC_CODE="")
    def test_a_deployment_with_no_seller_identity_cannot_issue_an_official_invoice(self):
        """Better to refuse than to print a tax document with a blank seller."""
        customer = self.make_customer(kind=Customer.Kind.INDIVIDUAL, national_id="0012345678")
        invoice = self.make_invoice(customer, invoice_type=Invoice.InvoiceType.OFFICIAL)
        with self.assertRaises(BusinessRuleError) as caught:
            issue_invoice(actor=self.manager, invoice=invoice)
        for field in ("seller_legal_name", "seller_national_id", "seller_economic_code"):
            self.assertIn(field, caught.exception.detail)

    @override_settings(SELLER_LEGAL_NAME="", SELLER_NATIONAL_ID="", SELLER_ECONOMIC_CODE="")
    def test_that_same_deployment_still_issues_unofficial_invoices(self):
        """Seller identity gates official invoices only, not the whole module."""
        customer = self.make_customer(kind=Customer.Kind.INDIVIDUAL)
        issued = issue_invoice(actor=self.manager, invoice=self.make_invoice(customer))
        self.assertEqual(issued.status, Invoice.Status.ISSUED)

    # --- what the type must NOT change ------------------------------------

    @override_settings(**SELLER)
    def test_the_type_changes_no_figure_on_the_document(self):
        """D.3 to D.6 are open. Until they are answered, nothing may differ.

        If a later change makes an official invoice compute tax, round, or total
        differently, this test fails — and it should, because that is a decision
        the product owner has not yet made.
        """
        individual = self.make_customer(kind=Customer.Kind.INDIVIDUAL, national_id="0012345678")
        official = issue_invoice(
            actor=self.manager,
            invoice=self.make_invoice(individual, invoice_type=Invoice.InvoiceType.OFFICIAL, quantity=3),
        )
        other = self.make_customer(kind=Customer.Kind.INDIVIDUAL)
        unofficial = issue_invoice(
            actor=self.manager, invoice=self.make_invoice(other, quantity=3)
        )
        for field in ("subtotal_amount", "discount_amount", "tax_rate", "tax_amount", "total_amount"):
            with self.subTest(field=field):
                self.assertEqual(getattr(official, field), getattr(unofficial, field))

    # --- the official series (D.7, settled: separate and gapless) ----------

    @override_settings(**SELLER)
    def test_a_draft_holds_no_official_number(self):
        """A number is spent only when the document becomes a tax document.

        Allocating at creation would put holes in the series: a draft that is
        abandoned, or created official and switched back, would have consumed a
        number no tax document ever carries.
        """
        individual = self.make_customer(kind=Customer.Kind.INDIVIDUAL, national_id="0012345678")
        draft = self.make_invoice(individual, invoice_type=Invoice.InvoiceType.OFFICIAL)
        self.assertEqual(draft.official_number, "")

    @override_settings(**SELLER)
    def test_issuing_takes_a_number_from_a_separate_series(self):
        individual = self.make_customer(kind=Customer.Kind.INDIVIDUAL, national_id="0012345678")
        issued = issue_invoice(
            actor=self.manager,
            invoice=self.make_invoice(individual, invoice_type=Invoice.InvoiceType.OFFICIAL),
        )
        self.assertTrue(issued.official_number)
        # Its own series, not the one every document draws from.
        self.assertNotEqual(issued.official_number, issued.number)
        self.assertTrue(issued.official_number.startswith("OINV-"))
        self.assertTrue(issued.number.startswith("INV-"))

    @override_settings(**SELLER)
    def test_an_unofficial_invoice_never_takes_an_official_number(self):
        issued = issue_invoice(
            actor=self.manager,
            invoice=self.make_invoice(self.make_customer(kind=Customer.Kind.INDIVIDUAL)),
        )
        self.assertEqual(issued.official_number, "")

    @override_settings(**SELLER)
    def test_the_official_series_has_no_gaps(self):
        """Consecutive, even with unofficial invoices issued between them."""
        numbers = []
        for index in range(3):
            buyer = self.make_customer(kind=Customer.Kind.INDIVIDUAL, national_id=f"001234567{index}")
            issued = issue_invoice(
                actor=self.manager,
                invoice=self.make_invoice(buyer, invoice_type=Invoice.InvoiceType.OFFICIAL),
            )
            numbers.append(int(issued.official_number.split("-")[1]))
            # An unofficial invoice between each pair must not disturb the series.
            issue_invoice(
                actor=self.manager,
                invoice=self.make_invoice(self.make_customer(kind=Customer.Kind.INDIVIDUAL)),
            )
        self.assertEqual(numbers, list(range(numbers[0], numbers[0] + 3)))

    @override_settings(**SELLER)
    def test_cancelling_does_not_release_the_number(self):
        """Gapless means a cancelled invoice keeps its number, and it is not reused."""
        buyer = self.make_customer(kind=Customer.Kind.INDIVIDUAL, national_id="0012345678")
        issued = issue_invoice(
            actor=self.manager,
            invoice=self.make_invoice(buyer, invoice_type=Invoice.InvoiceType.OFFICIAL),
        )
        taken = issued.official_number
        cancel_invoice(actor=self.manager, invoice=issued, reason="آزمون")
        issued.refresh_from_db()
        self.assertEqual(issued.official_number, taken)

        other = self.make_customer(kind=Customer.Kind.INDIVIDUAL, national_id="0012345679")
        following = issue_invoice(
            actor=self.manager,
            invoice=self.make_invoice(other, invoice_type=Invoice.InvoiceType.OFFICIAL),
        )
        self.assertNotEqual(following.official_number, taken)
        self.assertEqual(
            int(following.official_number.split("-")[1]),
            int(taken.split("-")[1]) + 1,
        )

    # --- the create path ---------------------------------------------------

    def test_the_type_can_be_chosen_when_the_invoice_is_created(self):
        """The create dialog sends it, so the service has to accept it.

        It did not at first: `invoice_type` was not in INVOICE_HEADER_FIELDS and
        every invoice created from the panel was refused as setting an unknown
        field. The browser test caught it, which is the only reason it did not
        ship.
        """
        invoice = create_invoice(
            actor=self.manager,
            customer=self.make_customer(kind=Customer.Kind.INDIVIDUAL),
            warehouse=self.warehouse,
            invoice_type=Invoice.InvoiceType.OFFICIAL,
            items=[{"product": self.product, "quantity": 1}],
        )
        self.assertEqual(invoice.invoice_type, Invoice.InvoiceType.OFFICIAL)

    def test_an_invented_type_is_refused_at_create(self):
        with self.assertRaises(BusinessRuleError) as caught:
            create_invoice(
                actor=self.manager,
                customer=self.make_customer(kind=Customer.Kind.INDIVIDUAL),
                warehouse=self.warehouse,
                invoice_type="proforma",
                items=[{"product": self.product, "quantity": 1}],
            )
        self.assertIn("invoice_type", caught.exception.detail)

    # --- the helper the UI mirrors ----------------------------------------

    @override_settings(**SELLER)
    def test_the_helper_reports_every_missing_field_at_once(self):
        """One round trip should tell the operator everything that is wrong."""
        customer = self.make_customer(kind=Customer.Kind.LEGAL)
        invoice = self.make_invoice(customer, invoice_type=Invoice.InvoiceType.OFFICIAL)
        errors = official_invoice_identity_errors(invoice)
        self.assertEqual(
            set(errors), {"customer_national_id", "customer_economic_code"}
        )

class IdentitySnapshotTests(OfficialInvoiceTests):
    """بند ۲ — an issued invoice stops reading the customer file.

    An issued invoice is evidence of a transaction that already happened. While
    it read the buyer live, correcting a typo in a customer record silently
    rewrote every tax document ever issued to them.
    """

    def complete_buyer(self):
        customer = self.make_customer(
            kind=Customer.Kind.LEGAL,
            national_id="10101010101",
            economic_code="411111111111",
        )
        customer.address = "اصفهان، خیابان اول، پلاک ۹"
        customer.postal_code = "9876543210"
        customer.city = "اصفهان"
        customer.save(update_fields=["address", "postal_code", "city"])
        return customer

    @override_settings(**SELLER)
    def test_issuing_copies_both_parties_onto_the_invoice(self):
        customer = self.complete_buyer()
        issued = issue_invoice(
            actor=self.manager,
            invoice=self.make_invoice(customer, invoice_type=Invoice.InvoiceType.OFFICIAL),
        )
        self.assertEqual(issued.buyer_name, customer.full_name)
        self.assertEqual(issued.buyer_national_id, "10101010101")
        self.assertEqual(issued.buyer_economic_code, "411111111111")
        self.assertEqual(issued.buyer_address, "اصفهان، خیابان اول، پلاک ۹")
        self.assertEqual(issued.buyer_postal_code, "9876543210")
        self.assertEqual(issued.buyer_city, "اصفهان")
        # The address came from the customer file, so it must be the same string.
        self.assertEqual(issued.buyer_address, customer.address)
        # And the primary phone, which is what the customer screen shows.
        self.assertTrue(issued.buyer_phone)

        self.assertEqual(issued.seller_name, "فروشگاه نمونه")
        self.assertEqual(issued.seller_national_id, "10101010101")
        self.assertEqual(issued.seller_economic_code, "411111111111")
        self.assertEqual(issued.seller_address, "تهران، خیابان نمونه، پلاک ۱")
        self.assertEqual(issued.seller_postal_code, "1234567890")
        self.assertEqual(issued.seller_city, "تهران")
        self.assertEqual(issued.seller_phone, "021-88888888")

    @override_settings(**SELLER)
    def test_correcting_the_customer_afterwards_does_not_touch_the_document(self):
        """The whole reason بند ۲ exists."""
        customer = self.complete_buyer()
        issued = issue_invoice(
            actor=self.manager,
            invoice=self.make_invoice(customer, invoice_type=Invoice.InvoiceType.OFFICIAL),
        )
        customer.full_name = "نام تازه"
        customer.economic_code = "999999999999"
        customer.address = "نشانی تازه"
        customer.save(update_fields=["full_name", "economic_code", "address"])

        issued.refresh_from_db()
        self.assertEqual(issued.buyer_name, "مشتری آزمون")
        self.assertEqual(issued.buyer_economic_code, "411111111111")
        self.assertEqual(issued.buyer_address, "اصفهان، خیابان اول، پلاک ۹")

    @override_settings(**SELLER)
    def test_a_draft_carries_no_snapshot_at_all(self):
        """Blank means "not yet a document", and the print falls back to live."""
        invoice = self.make_invoice(
            self.complete_buyer(), invoice_type=Invoice.InvoiceType.OFFICIAL
        )
        self.assertEqual(invoice.buyer_name, "")
        self.assertEqual(invoice.buyer_address, "")
        self.assertEqual(invoice.seller_name, "")

    @override_settings(**SELLER)
    def test_an_unofficial_invoice_is_snapshotted_too(self):
        """It is printed and handed over as well; its copy must not drift either."""
        customer = self.complete_buyer()
        issued = issue_invoice(actor=self.manager, invoice=self.make_invoice(customer))
        self.assertEqual(issued.buyer_name, customer.full_name)
        self.assertEqual(issued.buyer_address, customer.address)

    @override_settings(**SELLER)
    def test_no_write_path_exposes_the_snapshot(self):
        """The rule is that these are never typed — only selected from the file.

        Enforced by there being no input for them: if a snapshot column ever
        appears in the invoice serializer or in the header fields the update
        path accepts, an operator could type an address onto a tax document and
        the customer record would no longer be the single source of it.
        """
        from billing.serializers import InvoiceSerializer
        from billing.services import INVOICE_HEADER_FIELDS, PARTY_SNAPSHOT_FIELDS

        writable = {
            name
            for name, field in InvoiceSerializer().get_fields().items()
            if not field.read_only
        }
        for column in PARTY_SNAPSHOT_FIELDS:
            self.assertNotIn(column, writable, column)
            self.assertNotIn(column, INVOICE_HEADER_FIELDS, column)
