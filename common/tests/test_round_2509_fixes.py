"""The 2026-09-28 round of product-owner fixes (2.25.1 onward).

Script behaviour no Django test can execute is pinned by source pattern, the
same style `test_chat_drawer.py` and `test_reminders.py` already use; markup
is checked on the rendered page.
"""

from pathlib import Path

from django.test import Client, SimpleTestCase, TestCase

from accounts.models import User

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "common" / "static" / "common" / "dolphin-app.js").read_text(encoding="utf-8")
PASSWORD = "Strong-pass-274!"


def function_body(name):
    start = SCRIPT.index(f"function {name}(")
    return SCRIPT[start:SCRIPT.index("\n    }\n", start)]


class PersianDigitInputTests(SimpleTestCase):
    """A `type="number"` field refuses «۱۲۳» outright, so the digit is
    translated before the browser sees it."""

    def test_every_numeric_field_kind_is_covered(self):
        for selector in ('input[type="number"]', 'input[type="tel"]', 'input[inputmode="numeric"]',
                         'input[inputmode="decimal"]'):
            with self.subTest(selector=selector):
                self.assertIn(selector, SCRIPT)

    def test_typing_and_pasting_are_both_translated(self):
        body = function_body("setupLatinDigitInputs")
        self.assertIn('"beforeinput"', body)
        self.assertIn('"paste"', body)
        self.assertIn("event.preventDefault();", body)
        self.assertIn("latinNumberText(", body)

    def test_the_persian_decimal_separator_becomes_a_point(self):
        self.assertIn('replace(/٫/g, ".")', function_body("latinNumberText"))

    def test_it_runs_on_every_page(self):
        self.assertIn("    setupLatinDigitInputs();\n", SCRIPT)


class SearchableSelectTests(SimpleTestCase):
    """The invoice picker under «تخصیص به فاکتور»."""

    def test_matching_ignores_digit_script_and_grouping(self):
        body = function_body("setupSearchableSelect")
        self.assertIn("toLatinDigits(String(text)).toLowerCase().replace(/[،,٬\\s]/g, \"\")", body)
        # Enter picks from the same matching rule the list was drawn with.
        self.assertIn("const matches = matching(input.value);", body)

    def test_a_list_that_loaded_empty_does_not_claim_to_be_loading(self):
        body = function_body("setupSearchableSelect")
        self.assertIn("select.dataset.searchableEmpty", body)
        self.assertIn("options().length", body)

    def test_the_allocation_picker_lists_every_open_invoice(self):
        self.assertIn('select.dataset.searchableLimit = "0";', SCRIPT)
        self.assertIn("select.dataset.searchableEmpty = allocatableEmptyText;", SCRIPT)


class InvoiceWizardReviewTests(SimpleTestCase):
    def test_the_row_count_is_named_product_variety(self):
        body = SCRIPT[SCRIPT.index("async function setupInvoices()"):]
        body = body[:body.index("function renderReview()") + 1500]
        self.assertIn('["تنوع محصول", toPersianDigits(String(lines.count()))]', body)
        self.assertNotIn('["تعداد اقلام"', body)


class RenderedPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="round2509.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_the_customer_books_sit_beside_new_customer(self):
        page = self.client.get("/customers/").content.decode("utf-8")
        toolbar = page[page.index('<div class="card-toolbar gap-3">'):]
        toolbar = toolbar[:toolbar.index('id="open-create-customer"')]
        self.assertIn('data-customer-kind="individual"', toolbar)
        self.assertIn('data-customer-kind="legal"', toolbar)

    def test_the_tasks_tab_opens_on_every_status(self):
        from sales.services import create_customer_with_phone

        customer = create_customer_with_phone(
            actor=self.user, full_name="مشتری وظایف", phone={"raw_phone": "09121112233", "is_primary": True}
        )
        page = self.client.get(f"/customers/{customer.pk}/?tab=tasks").content.decode("utf-8")
        select = page[page.index('id="profile-tasks-status"'):]
        select = select[:select.index("</select>")]
        self.assertIn('<option value="" selected>همه</option>', select)


class InvoiceDocumentDiscountUiTests(TestCase):
    """2.26.0: an invoice's discount is one figure for the whole document."""

    def setUp(self):
        from decimal import Decimal

        from billing.services import create_invoice
        from sales.services import create_customer_with_phone, create_product

        self.user = User.objects.create_user(
            username="round2509.billing", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        customer = create_customer_with_phone(
            actor=self.user, full_name="مشتری سند", phone={"raw_phone": "09121112244", "is_primary": True}
        )
        product = create_product(actor=self.user, sku="RD-1", name="کالا", current_price=Decimal("1000.00"))
        self.invoice = create_invoice(
            actor=self.user, customer=customer, items=[{"product": product, "quantity": 2}],
            discount_percent=Decimal("10"),
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_the_wizard_sends_the_documents_discount_not_each_lines(self):
        body = SCRIPT[SCRIPT.index("async function setupInvoices()"):]
        body = body[:body.index("createFields: (data) => {") + 1400]
        self.assertIn("discount_percent: discountPercent,", body)
        self.assertIn("items: lines.collect(),", body)
        self.assertNotIn("discount_percent: discountPercent})", body)

    def test_the_preview_takes_the_discount_off_the_sum(self):
        body = function_body("documentTotals")
        self.assertIn("const discount = roundMoney((gross * percent) / 100);", body)

    def test_invoice_lines_carry_no_discount_column(self):
        page = self.client.get(f"/invoices/{self.invoice.pk}/").content.decode("utf-8")
        table = page[page.index('data-line-discounts="false"'):]
        self.assertNotIn("<th>تخفیف</th>", table[:table.index("</thead>")])
        self.assertNotIn('id="invoice-line-discount"', page)

    def test_the_totals_box_holds_editable_rates_and_a_save(self):
        page = self.client.get(f"/invoices/{self.invoice.pk}/").content.decode("utf-8")
        for marker in ('id="invoice-totals-form"', 'id="invoice-discount-rate"', 'name="discount_percent"',
                       'id="invoice-tax-rate-view"', 'name="tax_rate"', "ذخیره تغییرات", "نرخ تخفیف سند (٪)"):
            with self.subTest(marker=marker):
                self.assertIn(marker, page)
        # «مبلغ نهایی» drawn heavier than the parts it is made of.
        total = page[page.index('id="invoice-total"') - 200:page.index('id="invoice-total"')]
        self.assertIn("bg-light-primary", total)

    def test_quotations_and_orders_keep_their_line_discounts(self):
        include = (ROOT / "common" / "templates" / "common" / "includes" / "document_lines.inc").read_text(encoding="utf-8")
        self.assertIn('{% if doc != "invoice" %}<th>تخفیف</th>{% endif %}', include)
        self.assertIn('const lineDiscounts = body?.closest("table")?.dataset.lineDiscounts !== "false";', SCRIPT)


class CustomerRelatedRecordsTests(TestCase):
    """2.27.0: a customer's leads and calls tabs find the campaigns and calls
    that reached them through a target audience, not only the rows that name
    them directly."""

    def setUp(self):
        from django.utils import timezone

        from sales.services import (
            add_target_audience_member,
            create_customer_with_phone,
            create_lead,
            record_interaction,
        )

        self.manager = User.objects.create_user(
            username="round2509.leads", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        # A campaign with nobody's customer record on it, and an audience entry
        # that is called before its owner becomes a customer.
        self.campaign = create_lead(actor=self.manager, source="کمپین پاییز", campaign_or_batch="C-1")
        member = add_target_audience_member(
            actor=self.manager, lead=self.campaign, full_name="مخاطب", raw_phone="09125556677"
        )
        self.call = record_interaction(
            actor=self.manager, lead=self.campaign, target_member=member, phone="09125556677",
            direction="outbound", outcome="پاسخ داد", occurred_at=timezone.now(),
        )
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مخاطب", phone={"raw_phone": "09125556677", "is_primary": True}
        )
        # Someone else entirely, to prove nothing unrelated is swept in.
        self.other = create_customer_with_phone(
            actor=self.manager, full_name="دیگری", phone={"raw_phone": "09129998877", "is_primary": True}
        )
        self.client = Client()
        self.client.force_login(self.manager)

    def ids(self, url):
        return [row["id"] for row in self.client.get(url).json()["results"]]

    def test_the_leads_tab_lists_the_campaign_whose_audience_holds_them(self):
        self.assertEqual(self.ids(f"/api/v1/customers/{self.customer.pk}/leads/"), [self.campaign.pk])
        self.assertEqual(self.ids(f"/api/v1/customers/{self.other.pk}/leads/"), [])

    def test_the_calls_tab_lists_calls_made_before_they_were_a_customer(self):
        self.assertEqual(self.ids(f"/api/v1/customers/{self.customer.pk}/interactions/"), [self.call.pk])
        self.assertEqual(self.ids(f"/api/v1/customers/{self.other.pk}/interactions/"), [])

    def test_the_calls_tab_holds_only_the_call_centre_list(self):
        page = self.client.get(f"/customers/{self.customer.pk}/?tab=calls").content.decode("utf-8")
        self.assertIn('id="customer-interactions-table-body"', page)
        self.assertNotIn('data-pbx-calls="customer"', page)

    def test_the_overview_holds_the_whole_timeline_and_no_all_events_button(self):
        page = self.client.get(f"/customers/{self.customer.pk}/").content.decode("utf-8")
        box = page[page.index("data-recent-activity data-recent-activity-all"):]
        box = box[:box.index("</section>")]
        self.assertNotIn("همهٔ رویدادها", box)
        self.assertIn("scroll-y mh-500px", box)
        self.assertNotIn('data-profile-tab="activity"', page)
