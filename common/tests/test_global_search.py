"""The header search box: `common.search`, its API, and the header control.

What is worth proving, in the same shape the reminder bell's tests take:

* **it finds the things people actually look up** — a customer by name or by
  a partly-typed phone, an invoice by number, a product by SKU — and it does
  so whether the digits typed are Persian or Latin, because the panel prints
  them in Persian and people copy what they see;
* **object scope is not reimplemented** — a marketer searching a company-wide
  name gets only their own rows, and that comes from each module's existing
  selector, not from a rule written twice here;
* **the feature gate** — `global_search` off means no control in the header
  and a 404 from the API, and a deployment missing a *source* feature keeps
  the sources it does have;
* **the caps hold** — a group lists at most `GROUP_LIMIT` rows while `count`
  still reports the truth, and a one-character query does no work at all.
"""

import pathlib
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from accounts.models import User
from aftersales.services import create_after_sales_request
from billing.services import create_invoice
from common import search
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import (
    assign_lead,
    create_customer_with_phone,
    create_lead,
    create_product,
)

PASSWORD = "Strong-pass-661!"


def profile_without(*features):
    return DeploymentProfile(
        profile_id="client-1",
        features=frozenset(ALL_FEATURES) - frozenset(features),
        source="signed-manifest",
    )


class SearchFixtures(TestCase):
    phone_counter = 0

    def setUp(self):
        self.manager = User.objects.create_user(
            username="find.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="find.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.after_sales_agent = User.objects.create_user(
            username="find.aftersales", password=PASSWORD, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )

    def a_customer(self, name, *, actor=None, phone=None, **extra):
        SearchFixtures.phone_counter += 1
        number = phone or f"0913000{SearchFixtures.phone_counter:04d}"
        return create_customer_with_phone(
            actor=actor or self.manager,
            full_name=name,
            phone={"raw_phone": number, "is_primary": True},
            **extra,
        )

    def kinds(self, data):
        return [group["kind"] for group in data["groups"]]

    def group(self, data, kind):
        return next(group for group in data["groups"] if group["kind"] == kind)


class FindingThingsTests(SearchFixtures):
    def test_a_customer_is_found_by_part_of_their_name(self):
        self.a_customer("رضا محمدی‌فر")
        data = search.search(self.manager, "محمدی")
        self.assertIn("customers", self.kinds(data))
        self.assertEqual(self.group(data, "customers")["items"][0]["title"], "رضا محمدی‌فر")

    def test_a_customer_is_found_by_a_partly_typed_phone_number(self):
        self.a_customer("سارا احمدی", phone="09121234567")
        data = search.search(self.manager, "1234567")
        self.assertIn("customers", self.kinds(data))

    def test_the_same_phone_is_found_when_typed_in_persian_digits(self):
        """The panel prints Persian digits, so people copy Persian digits."""
        self.a_customer("لیلا رضایی", phone="09127654321")
        data = search.search(self.manager, "۷۶۵۴۳۲۱")
        self.assertIn("customers", self.kinds(data))

    def test_a_phone_typed_with_its_leading_zero_still_matches(self):
        """Stored as `+98…`, so the typed `0912…` can only match by its tail."""
        self.a_customer("مهدی کاظمی", phone="09129998877")
        self.assertIn("customers", self.kinds(search.search(self.manager, "09129998877")))

    def test_the_international_forms_of_the_same_number_all_match(self):
        """`+98…` is what is stored; `0912…`, `98912…` and `0098912…` are
        what people type."""
        self.a_customer("نگار موسوی", phone="09121112233")
        for typed in ("09121112233", "989121112233", "00989121112233", "9121112233"):
            with self.subTest(typed=typed):
                self.assertIn("customers", self.kinds(search.search(self.manager, typed)))

    def test_too_few_digits_do_not_match_every_phone_in_the_book(self):
        """`09` would otherwise match every stored number."""
        self.a_customer("کاربر ارقام", phone="09121119999")
        data = search.search(self.manager, "09")
        self.assertNotIn("customers", self.kinds(data))

    def test_a_product_is_found_by_sku(self):
        create_product(actor=self.manager, sku="PMP-4410", name="پمپ صنعتی", current_price=Decimal("100.00"))
        self.assertIn("products", self.kinds(search.search(self.manager, "PMP-4410")))

    def test_a_lead_is_found_by_its_campaign(self):
        lead = create_lead(
            actor=self.manager, customer=self.a_customer("مشتری کمپین"), source="نمایشگاه پاییز",
        )
        data = search.search(self.manager, "نمایشگاه")
        self.assertIn("leads", self.kinds(data))
        self.assertEqual(self.group(data, "leads")["items"][0]["url"], f"/leads/{lead.pk}/")

    def test_an_invoice_is_found_by_its_number(self):
        invoice = self._an_invoice()
        data = search.search(self.manager, invoice.number)
        self.assertIn("invoices", self.kinds(data))
        self.assertEqual(self.group(data, "invoices")["items"][0]["url"], f"/invoices/{invoice.pk}/")

    def test_an_invoice_number_typed_in_persian_digits_is_found_too(self):
        from common.jalali import to_persian_digits

        invoice = self._an_invoice()
        data = search.search(self.manager, to_persian_digits(invoice.number))
        self.assertIn("invoices", self.kinds(data))

    def test_an_after_sales_case_is_found_by_its_subject(self):
        create_after_sales_request(
            actor=self.manager,
            customer=self.a_customer("مشتری خدمات"),
            subject="تعویض برد اصلی",
            description="شرح",
            status="باز",
            assigned_to=self.after_sales_agent,
        )
        self.assertIn("after_sales", self.kinds(search.search(self.manager, "برد اصلی")))

    def test_one_query_reaches_several_modules_at_once(self):
        """The whole point: one box, not one box per page."""
        customer = self.a_customer("آریا صنعت")
        create_lead(actor=self.manager, customer=customer, source="آریا صنعت")
        create_product(actor=self.manager, sku="ARIA-1", name="قطعهٔ آریا صنعت", current_price=Decimal("50.00"))
        kinds = self.kinds(search.search(self.manager, "آریا صنعت"))
        self.assertIn("customers", kinds)
        self.assertIn("leads", kinds)
        self.assertIn("products", kinds)

    def test_nothing_matching_returns_no_groups_and_a_zero_count(self):
        self.a_customer("کسی")
        data = search.search(self.manager, "چنین‌چیزی‌وجودندارد")
        self.assertEqual(data["groups"], [])
        self.assertEqual(data["count"], 0)

    def _an_invoice(self):
        customer = self.a_customer("مشتری فاکتور")
        product = create_product(
            actor=self.manager, sku="INV-1", name="کالای فاکتور", current_price=Decimal("250000.00"),
        )
        warehouse = create_warehouse(actor=self.manager, code="findwh", name="انبار جست‌وجو")
        record_stock_movement(
            actor=self.manager, warehouse=warehouse, product=product,
            movement_type=StockMovement.MovementType.OPENING, quantity=5, unit_cost=Decimal("100000.00"),
        )
        return create_invoice(
            actor=self.manager, customer=customer,
            items=[{"product": product, "quantity": 1}], warehouse=warehouse,
        )


class ShortQueryTests(SearchFixtures):
    def test_a_one_character_query_does_no_work(self):
        self.a_customer("الف")
        data = search.search(self.manager, "ا")
        self.assertEqual(data["groups"], [])
        self.assertEqual(data["count"], 0)

    def test_an_empty_query_is_not_an_error(self):
        """The box is typed into one letter at a time; the first is not a fault."""
        for query in ("", "   ", None):
            with self.subTest(query=query):
                self.assertEqual(search.search(self.manager, query)["count"], 0)

    def test_surrounding_spaces_are_ignored(self):
        self.a_customer("پویا نیکو")
        self.assertIn("customers", self.kinds(search.search(self.manager, "  نیکو  ")))


class ScopeTests(SearchFixtures):
    def test_a_marketer_finds_only_their_own_leads(self):
        mine = create_lead(
            actor=self.manager, customer=self.a_customer("مشتری من"), source="کمپین مشترک",
        )
        assign_lead(actor=self.manager, lead=mine, to_user=self.agent)
        create_lead(
            actor=self.manager, customer=self.a_customer("مشتری دیگری"), source="کمپین مشترک",
        )
        data = search.search(self.agent, "کمپین مشترک")
        group = self.group(data, "leads")
        self.assertEqual(group["count"], 1)
        self.assertEqual(group["items"][0]["url"], f"/leads/{mine.pk}/")
        # The manager, whose scope is wider, finds both — so the assertion
        # above is about scope, not about the rows failing to exist.
        self.assertEqual(self.group(search.search(self.manager, "کمپین مشترک"), "leads")["count"], 2)

    def test_a_marketer_is_told_nothing_about_company_money(self):
        customer = self.a_customer("مشتری پولی")
        from billing.models import Payment
        from billing.payments import register_payment

        register_payment(
            actor=self.manager, customer=customer, method=Payment.Method.CASH,
            amount=Decimal("500000.00"),
        )
        self.assertNotIn("payments", self.kinds(search.search(self.agent, "مشتری پولی")))
        self.assertIn("payments", self.kinds(search.search(self.manager, "مشتری پولی")))

    def test_an_after_sales_agent_gets_no_customers_or_leads(self):
        customer = self.a_customer("مشتری فروش")
        create_lead(actor=self.manager, customer=customer, source="کمپین فروش")
        kinds = self.kinds(search.search(self.after_sales_agent, "فروش"))
        self.assertNotIn("customers", kinds)
        self.assertNotIn("leads", kinds)


class FeatureGateTests(SearchFixtures):
    def test_the_api_is_404_when_the_feature_is_off(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        with override_active_profile(profile_without("global_search")):
            self.assertEqual(client.get("/api/v1/search/?q=رضا").status_code, 404)

    def test_the_control_is_absent_from_the_header_when_the_feature_is_off(self):
        self.client.force_login(self.manager)
        with override_active_profile(profile_without("global_search")):
            page = self.client.get("/").content.decode("utf-8")
        self.assertNotIn('id="global-search-toggle"', page)

    def test_the_control_is_in_the_header_by_default(self):
        self.client.force_login(self.manager)
        page = self.client.get("/").content.decode("utf-8")
        self.assertIn('id="global-search-toggle"', page)
        self.assertIn("جست‌وجوی سراسری", page)

    def test_a_deployment_without_invoices_still_searches_its_customers(self):
        self.a_customer("مشتری بدون فاکتور")
        with override_active_profile(profile_without("invoices", "payments")):
            kinds = self.kinds(search.search(self.manager, "بدون فاکتور"))
        self.assertIn("customers", kinds)
        self.assertNotIn("invoices", kinds)
        self.assertNotIn("payments", kinds)

    def test_global_search_is_on_by_default_like_the_bell(self):
        from common.deployment.registry import DEFAULT_FEATURES, DEFAULT_OFF_FEATURES

        self.assertIn("global_search", DEFAULT_FEATURES)
        self.assertNotIn("global_search", DEFAULT_OFF_FEATURES)


class GroupCapTests(SearchFixtures):
    def test_a_group_lists_a_page_but_reports_the_true_count(self):
        for index in range(search.GROUP_LIMIT + 4):
            self.a_customer(f"شرکت آزمون {index}")
        group = self.group(search.search(self.manager, "شرکت آزمون"), "customers")
        self.assertEqual(group["count"], search.GROUP_LIMIT + 4)
        self.assertEqual(len(group["items"]), search.GROUP_LIMIT)

    def test_every_group_names_the_page_that_holds_the_rest(self):
        self.a_customer("مشتری فهرست")
        group = self.group(search.search(self.manager, "مشتری فهرست"), "customers")
        self.assertEqual(group["list_url"], "/customers/")


class ApiTests(SearchFixtures):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.manager)

    def test_the_endpoint_returns_the_grouped_result(self):
        self.a_customer("مینا سلطانی")
        response = self.api.get("/api/v1/search/?q=سلطانی")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["query"], "سلطانی")
        self.assertEqual(response.data["groups"][0]["kind"], "customers")

    def test_a_missing_query_parameter_is_not_an_error(self):
        response = self.api.get("/api/v1/search/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

    def test_the_result_may_not_be_cached(self):
        self.assertEqual(self.api.get("/api/v1/search/?q=رضا")["Cache-Control"], "private, no-store")

    def test_an_anonymous_caller_is_refused(self):
        self.assertIn(APIClient().get("/api/v1/search/?q=رضا").status_code, (401, 403))

    def test_typing_quickly_is_not_rate_limited(self):
        """Same lesson as the reminder bell: a per-keystroke endpoint must not
        spend the shared `sensitive` budget, or somebody's unrelated write
        answers 429 for no visible reason."""
        from common.search_views import GlobalSearchView
        from common.throttles import SensitiveRateThrottle

        self.assertFalse(
            [t for t in GlobalSearchView().get_throttles() if isinstance(t, SensitiveRateThrottle)]
        )
        for _ in range(40):
            self.assertEqual(self.api.get("/api/v1/search/?q=رضا").status_code, 200)


class PanelMarkupTests(SimpleTestCase):
    """The two topbar panels share their row markup rather than duplicating it."""

    script = (
        pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin-app.js"
    ).read_text(encoding="utf-8")
    css = (
        pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin.css"
    ).read_text(encoding="utf-8")

    def test_both_panels_build_the_same_row_class(self):
        self.assertEqual(self.script.count('"topbar-list-item"'), 2)

    def test_the_shared_row_is_styled_once(self):
        self.assertEqual(self.css.count(".topbar-list-item {"), 1)

    def test_the_search_panel_debounces_rather_than_asking_per_keystroke(self):
        self.assertIn("SEARCH_DEBOUNCE_MS", self.script)

    def test_the_search_panel_discards_a_stale_answer(self):
        """Type fast and a slow reply for the shorter query can arrive last."""
        self.assertIn("if (mine !== sequence) return;", self.script)


class NarrowScreenPanelTests(SimpleTestCase):
    """Both topbar panels stop following their own button on a phone.

    Anchored to its button, each panel starts wherever that icon sits in the
    header and runs its fixed 300px from there. At 375px that put the search
    panel's far edge 38px off-screen and left the bell only just fitting, so
    a narrower phone would have clipped that one too. Found in the live
    browser at 375px — no Python test could have seen it — and fixed by
    pinning both to the viewport below the `sm` breakpoint.
    """

    css = (
        pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin.css"
    ).read_text(encoding="utf-8")

    def rule(self):
        block = self.css.split("@media (max-width: 575.98px) {")[1]
        return block.split("}")[0]

    def test_both_panels_are_pinned_on_a_narrow_screen(self):
        rule = self.rule()
        self.assertIn("#global-search-menu", rule)
        self.assertIn("#reminder-bell-menu", rule)

    def test_the_pinned_panel_leaves_the_button_behind(self):
        self.assertIn("position: fixed", self.rule())

    def test_the_top_comes_from_the_themes_own_header_height(self):
        """A number guessed here would drift the moment the theme's header did."""
        self.assertIn("--bs-app-header-height", self.rule())

    def test_only_one_inline_edge_is_pinned(self):
        """Both, with the theme's `w-300px !important` still in force, is
        over-constrained — and which edge the browser then drops is not a
        thing to build a layout on."""
        rule = self.rule()
        self.assertIn("inset-inline-start", rule)
        self.assertIn("inset-inline-end: auto", rule)
