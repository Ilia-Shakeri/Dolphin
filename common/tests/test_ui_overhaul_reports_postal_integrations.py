"""Batch D of the 2026-09-20 UI pass: report wizards, postal states, integrations.

**Item 9 — the two reports, rebuilt.** «گزارش اسناد فروش و پست» and «گزارش
پیامک ورودی» each had a filter panel that asked everything at once and then
showed whatever it had built. Both are four-step wizards now — window,
narrowing, what to show, result — driven by one `setupReportWizard`, because
two reports of the same shape written twice become two different wizards.
Both gained an XLSX export that goes through the report view itself, so a
workbook cannot disagree with the page it was downloaded from.

One defect found by measuring rather than reading: the vendor's KTStepper
marks the current step with `KTUtil.index(element)`, which is an element's
position among *its parent's* children and not among the stepper's own
elements. With the four contents sitting beside the nav row and the button
row, every content's index came out one too high — the nav said step 4 while
the page showed step 3, so the built report was invisible. The four contents
live in their own container now, which is exactly what the creation wizards
already had in their `<form>`.

**Item 10 — the postal states.** `postal_status` was free text. It is now the
four states the product owner named, in the order a parcel travels them,
declared once in `sales/postal.py` with the icon and label each carries, and
drawn as a stepper with the current stop lit. Free text still reads: a row
written before the vocabulary shows the words that were recorded and no
stepper, rather than being forced into a state nobody chose. `PostalCarrier`
is the seam a real post-office API will be implemented against.

**Item 11 — the integrations page.** One card per outside service, from one
table: status, masked key, last error, a real test where a real test exists,
and a placeholder that says «به‌زودی» and offers no controls at all.

Browser-measured at the time: the parcels wizard stepped 1/1 → 4/4 with nav
and content in step and the report visible at the end; unticking a section
hid its panel in place; going back and changing the range rebuilt on the way
forward; both export URLs returned real XLSX with the right content type and
filename; the parcel's stepper read done/done/current/upcoming after a
transition with the rail filled up to the parcel and grey after it, and no
horizontal overflow at 1536px or 375px; and the integrations page listed
SMS (with a test that printed the provider's own refusal), post (no test),
and the «به‌زودی» placeholder.
"""

import pathlib
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from common import integrations
from sales import postal


from common.tests.ui_overhaul_helpers import (  # noqa: E402
    CODE,
    CSS,
    SCRIPT,
    TEMPLATES,
    function_body,
    ROOT,
    markup,
    media_block,
    rule,
)

PARCELS = (TEMPLATES / "reports" / "sales_documents.html").read_text(encoding="utf-8")
INBOUND = (TEMPLATES / "reports" / "inbound_sms.html").read_text(encoding="utf-8")
DOCUMENT_DETAIL = (TEMPLATES / "sales_documents" / "detail.html").read_text(encoding="utf-8")
INTEGRATIONS_PAGE = (TEMPLATES / "settings" / "integrations.html").read_text(encoding="utf-8")

User = get_user_model()
PASSWORD = "Aa!23456pass"


# ===========================================================================
# Item 9 — the report wizards
# ===========================================================================


class ReportWizardTests(SimpleTestCase):
    def test_there_is_one_driver_for_both_reports(self):
        self.assertEqual(SCRIPT.count("function setupReportWizard("), 1)
        # Calls, not the definition: the signature destructures its argument
        # and so matches the same text.
        calls = SCRIPT.count("setupReportWizard({") - SCRIPT.count("function setupReportWizard({")
        self.assertEqual(calls, 2)

    def test_it_steps_with_the_component_the_creation_wizards_use(self):
        """Not a second stepper written for reports."""
        body = function_body("setupReportWizard")
        self.assertIn("setupWizard(root, {", body)

    def test_the_window_is_the_shared_range_control(self):
        """A reader picking «۳۰ روز» here is doing the same thing as on every
        chart in the panel, so it is the same control — not a pair of date
        boxes this page invented."""
        body = function_body("setupReportWizard")
        self.assertIn("setupChartRange(", body)
        for text in (PARCELS, INBOUND):
            with self.subTest():
                self.assertNotIn('data-jalali="datetime"', text)

    def test_neither_page_keeps_its_old_filter_panel(self):
        """«فیلتر جدا نداشته باشند» — the whole point of the item."""
        for name, text in (("parcels", PARCELS), ("inbound", INBOUND)):
            with self.subTest(page=name):
                self.assertNotIn("list-filters", text)

    def test_both_wizards_have_the_same_four_steps(self):
        for name, text in (("parcels", PARCELS), ("inbound", INBOUND)):
            with self.subTest(page=name):
                self.assertEqual(text.count('data-kt-stepper-element="nav"'), 4)
                self.assertEqual(text.count('data-kt-stepper-element="content"'), 4)
                for title in ("بازهٔ زمانی", "پالایش", "چه چیزی را ببینیم", "نتیجه"):
                    self.assertIn(title, text)

    def test_the_steps_live_in_their_own_container(self):
        """KTStepper marks the current step by `KTUtil.index(element)` — the
        element's position among *its parent's* children. With the contents
        beside the nav row and the button row, every index came out one too
        high: measured live, the nav said 4 while the visible content was 3,
        so the built report could not be seen. The creation wizards have had
        this container all along, as their `<form>`."""
        for name, text in (("parcels", PARCELS), ("inbound", INBOUND)):
            with self.subTest(page=name):
                self.assertIn('<div class="report-steps">', text)
                steps = text.split('<div class="report-steps">')[1]
                self.assertEqual(steps.split("</div>\n\n        <div class=\"d-flex flex-stack")[0]
                                 .count('data-kt-stepper-element="content"'), 4)

    def test_both_offer_a_way_back(self):
        for name, text in (("parcels", PARCELS), ("inbound", INBOUND)):
            with self.subTest(page=name):
                self.assertIn('data-kt-stepper-action="previous"', text)
                self.assertIn("مرحلهٔ قبل", text)

    def test_a_report_with_no_sections_chosen_is_refused(self):
        """It would be a blank page with a heading."""
        body = function_body("setupReportWizard")
        self.assertIn('return chosenSections().length', body)
        self.assertIn("دست‌کم یک بخش را برای نمایش انتخاب کنید.", body)

    def test_reaching_the_last_step_rebuilds_rather_than_reusing(self):
        """Which is what makes "go back, change it, come forward" mean what
        it looks like."""
        body = function_body("setupReportWizard")
        self.assertIn("onReachLastStep: () => build()", body)

    def test_unticking_a_section_hides_its_panel_without_rebuilding(self):
        """The data is the same data; only what is shown changed."""
        body = function_body("setupReportWizard")
        self.assertIn("if (content && !content.hidden) applySections();", body)

    def test_the_export_carries_the_same_window_and_filters(self):
        body = function_body("setupReportWizard")
        self.assertIn("`${exportUrl}?${query()}`", body)

    def test_a_report_with_no_export_hides_the_button_rather_than_breaking_it(self):
        body = function_body("setupReportWizard")
        self.assertIn("} else if (exportButton) {", body)
        self.assertIn("exportButton.hidden = true;", body)

    def test_the_two_hand_rolled_query_builders_are_gone(self):
        """Both pages built their own `URLSearchParams` from their own form;
        the wizard builds one for both."""
        self.assertNotIn("function salesDocumentReportQuery", SCRIPT)
        self.assertNotIn("function inboundSMSReportQuery", SCRIPT)

    def test_the_drilldown_asks_the_wizard_for_the_window(self):
        """It used to read the form that no longer exists. A drill-down into
        a different range than the row that was clicked is a different
        question."""
        body = function_body("loadInboundSMSDrilldown")
        self.assertIn("inboundSMSReportWizard", body)

    def test_the_step_lays_its_children_out_in_a_column(self):
        """The same thing the invoice lines step needed, for the same
        reason: the theme makes a stepper's current content a flex row."""
        self.assertIn("flex-direction: column", rule(".report-step"))


class ReportExportTests(TestCase):
    def setUp(self):
        # `SensitiveRateThrottle` counts in the shared cache, which is not
        # reset between tests — a class that spends the bucket leaves the
        # next one to hit 429. Same `cache.clear()` the other API-touching
        # suites in this project already do.
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="rx.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )

    def _window(self):
        now = timezone.now()
        return {
            "period_start": (now - timedelta(days=30)).isoformat(),
            "period_end": now.isoformat(),
        }

    def test_the_parcels_export_is_a_workbook(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(self.manager)
        response = client.get("/api/v1/exports/sales-documents.xlsx", self._window())
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertIn("dolphin-sales-documents.xlsx", response["Content-Disposition"])
        # A real zip container, not an error page with the wrong header.
        self.assertTrue(b"".join(response.streaming_content
                                 if response.streaming else [response.content]).startswith(b"PK"))

    def test_it_runs_through_the_same_gates_as_the_page(self):
        """Subclassing the report view is what guarantees that — an export
        that reached the data another way could disagree with the report it
        was downloaded from."""
        from reports.financial_views import SalesDocumentReportExportView
        from reports.views import SalesDocumentReportView

        self.assertTrue(issubclass(SalesDocumentReportExportView, SalesDocumentReportView))

    def test_a_marketer_outside_the_report_scope_is_refused(self):
        from rest_framework.test import APIClient

        outsider = User.objects.create_user(
            username="rx.after", password=PASSWORD, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )
        client = APIClient()
        client.force_authenticate(outsider)
        response = client.get("/api/v1/exports/sales-documents.xlsx", self._window())
        self.assertEqual(response.status_code, 403)

    def test_a_backwards_window_is_refused_as_json_not_as_a_broken_workbook(self):
        from rest_framework.test import APIClient

        now = timezone.now()
        client = APIClient()
        client.force_authenticate(self.manager)
        response = client.get("/api/v1/exports/sales-documents.xlsx", {
            "period_start": now.isoformat(),
            "period_end": (now - timedelta(days=1)).isoformat(),
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("json", response["Content-Type"])


# ===========================================================================
# Item 10 — the postal states
# ===========================================================================


class PostalVocabularyTests(SimpleTestCase):
    def test_the_four_states_are_the_ones_that_were_asked_for(self):
        self.assertEqual(
            [state.label for state in postal.POSTAL_STATES],
            ["انبار فروشگاه", "ارسال به پست", "بستهٔ دست پست است", "ارسال به مشتری"],
        )

    def test_each_carries_its_own_icon_and_that_icon_exists(self):
        """A keenicon drawn with the wrong number of `path` spans renders as
        a smudge, so the count is declared beside the name and checked
        against the vendor's own demo page."""
        demo = (ROOT / "src" / "plugins" / "keenicons" / "duotone" / "demo.html").read_text(
            encoding="utf-8", errors="replace"
        )
        for state in postal.POSTAL_STATES:
            with self.subTest(state=state.key):
                match = re.search(
                    r'class="ki-duotone %s"[^>]*>((?:<span class="path\d+"></span>)*)'
                    % re.escape(state.icon),
                    demo,
                )
                self.assertIsNotNone(match, f"{state.icon} is not a keenicon")
                self.assertEqual(match.group(1).count("path"), state.icon_paths)

    def test_the_order_is_the_order_a_parcel_travels(self):
        keys = [state.key for state in postal.POSTAL_STATES]
        self.assertEqual(keys, ["in_store", "handed_to_post", "with_post", "out_for_delivery"])
        self.assertEqual(postal.DEFAULT_POSTAL_STATE, "in_store")

    def test_a_stepper_marks_before_current_and_after(self):
        stages = [step["stage"] for step in postal.stepper_for("with_post")]
        self.assertEqual(stages, ["done", "done", "current", "upcoming"])

    def test_free_text_gets_no_stepper_rather_than_a_wrong_one(self):
        """Four stops with none of them current would say something false
        about where the parcel is."""
        self.assertEqual(postal.stepper_for("روی میز انبار"), [])
        self.assertIsNone(postal.state_for("روی میز انبار"))

    def test_free_text_still_reads_as_what_was_recorded(self):
        """A vocabulary is not a reason to lose an existing deployment's
        rows (CLAUDE.md §7)."""
        self.assertEqual(postal.label_for("روی میز انبار"), "روی میز انبار")
        self.assertEqual(postal.label_for(""), "نامشخص")

    def test_a_label_typed_before_the_vocabulary_is_recognised(self):
        """A deployment that has been typing «ارسال به پست» for months is
        already using these words."""
        self.assertEqual(postal.state_for("ارسال به پست").key, "handed_to_post")
        self.assertEqual(postal.label_for("handed_to_post"), "ارسال به پست")


class PostalCarrierSeamTests(SimpleTestCase):
    def test_the_shipped_carrier_is_honest_about_being_manual(self):
        carrier = postal.carrier_for(None)
        self.assertFalse(carrier.supports_tracking)
        self.assertIsNone(carrier.track("anything"))

    def test_an_unknown_carrier_falls_back_rather_than_raising(self):
        """A deployment whose configured provider was dropped in a later
        build must still be able to open its own parcels page."""
        self.assertIs(postal.carrier_for("no-such-provider"), postal.carrier_for("manual"))

    def test_a_provider_status_nobody_mapped_is_none_not_a_default(self):
        """Quietly answering "in store" would hide the gap behind a
        plausible-looking screen."""
        self.assertIsNone(postal.map_carrier_status("manual", "IN_TRANSIT"))

    def test_a_subclass_needs_only_a_map_and_a_track(self):
        """The seam's whole purpose: a provider's own vocabulary is
        translated in one place and never reaches the database."""

        class Fake(postal.PostalCarrier):
            code = "fake"
            supports_tracking = True
            STATUS_MAP = {"HANDED_OVER": "handed_to_post"}

            def track(self, tracking_number):
                return ("handed_to_post", "HANDED_OVER")

        carrier = Fake()
        self.assertEqual(carrier.map_status("HANDED_OVER"), "handed_to_post")
        self.assertIsNone(carrier.map_status("SOMETHING_ELSE"))


class PostalStepperUITests(SimpleTestCase):
    def test_the_panel_draws_the_stops_the_server_sends(self):
        """Not a table of its own: `sales/postal.py` owns which states exist,
        and a second copy in the panel is the copy that goes stale."""
        body = function_body("renderPostalStepper")
        self.assertIn("steps.map((step, index)", body)
        self.assertIn("step.icon", body)
        self.assertIn("step.icon_paths", body)

    def test_an_unknown_status_hides_the_card(self):
        body = function_body("renderPostalStepper")
        self.assertIn("if (!steps || !steps.length) {", body)
        self.assertIn("card.hidden = true;", body)

    def test_the_current_stop_is_announced_and_not_only_coloured(self):
        body = function_body("renderPostalStepper")
        self.assertIn('item.setAttribute("aria-current", "step")', body)

    def test_the_rail_is_two_halves_that_meet_rather_than_one_that_overflows(self):
        """An item drawing the whole gap to its neighbour has to extend past
        its own edge, and the last one then pushes the page sideways —
        measured, 55px of horizontal scroll."""
        self.assertIn(".postal-step:not(:first-child)::before", CODE)
        self.assertIn(".postal-step:not(:last-child)::after", CODE)

    def test_the_filled_rail_outranks_the_grey_one(self):
        """`.postal-step-done::after` is (0,1,1) against the grey rule's
        (0,2,1), so without the same `:not()` the rail stays grey however far
        along the parcel is — measured before this was fixed."""
        self.assertIn(".postal-step-done:not(:first-child)::before", CODE)
        self.assertIn(".postal-step-done:not(:last-child)::after", CODE)

    def test_a_phone_gets_the_same_stops_stacked(self):
        phone = media_block("(max-width: 767.98px)", ".postal-stepper")
        self.assertIn(".postal-stepper", phone)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", phone)

    def test_both_forms_choose_from_the_vocabulary_rather_than_free_text(self):
        from common.templates import __file__ as _  # noqa: F401  (path anchor)

        listing = (TEMPLATES / "sales_documents" / "list.html").read_text(encoding="utf-8")
        self.assertIn('id="create-sales-document-status"', listing)
        self.assertIn('<select class="form-select form-select-solid" id="create-sales-document-status"', listing)
        self.assertIn('<select class="form-select form-select-solid" id="postal-to-status"', DOCUMENT_DETAIL)

    def test_one_loader_fills_every_such_selector(self):
        self.assertEqual(SCRIPT.count("function fillPostalStates("), 1)
        self.assertEqual(SCRIPT.count("fillPostalStates("), 4)

    def test_the_vocabulary_is_fetched_once_per_page(self):
        """Three surfaces want it and three requests for a four-row constant
        is two too many."""
        body = function_body("loadPostalStates")
        self.assertIn("postalStatesPromise ??=", body)
        # A failure is not cached as one: the next caller may succeed.
        self.assertIn("postalStatesPromise = null;", body)


class PostalApiTests(TestCase):
    def setUp(self):
        # `SensitiveRateThrottle` counts in the shared cache, which is not
        # reset between tests — a class that spends the bucket leaves the
        # next one to hit 429. Same `cache.clear()` the other API-touching
        # suites in this project already do.
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="ps.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )

    def test_the_states_endpoint_sends_the_vocabulary(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(self.manager)
        response = client.get("/api/v1/sales-documents/postal-states/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [row["key"] for row in response.data["results"]],
            [state.key for state in postal.POSTAL_STATES],
        )

    def test_a_document_carries_its_label_and_its_stepper(self):
        from rest_framework.test import APIClient

        from sales.models import Customer, SalesDocument

        customer = Customer.objects.create(full_name="مشتری پستی", created_by=self.manager)
        SalesDocument.objects.create(
            customer=customer,
            document_number="PS-1",
            postal_status="handed_to_post",
            registered_by=self.manager,
        )
        client = APIClient()
        client.force_authenticate(self.manager)
        row = client.get("/api/v1/sales-documents/").data["results"][0]
        self.assertEqual(row["postal_status_display"], "ارسال به پست")
        self.assertEqual([step["stage"] for step in row["postal_stepper"]],
                         ["done", "current", "upcoming", "upcoming"])

    def test_a_free_text_document_still_reads_and_draws_no_stepper(self):
        from rest_framework.test import APIClient

        from sales.models import Customer, SalesDocument

        customer = Customer.objects.create(full_name="مشتری قدیمی", created_by=self.manager)
        SalesDocument.objects.create(
            customer=customer,
            document_number="PS-2",
            postal_status="روی میز انبار",
            registered_by=self.manager,
        )
        client = APIClient()
        client.force_authenticate(self.manager)
        row = client.get("/api/v1/sales-documents/?search=PS-2").data["results"][0]
        self.assertEqual(row["postal_status_display"], "روی میز انبار")
        self.assertEqual(row["postal_stepper"], [])


# ===========================================================================
# Item 11 — the integrations page
# ===========================================================================


class IntegrationRegistryTests(SimpleTestCase):
    def test_the_four_rows_the_product_owner_asked_for(self):
        """Restated 2026-09-21: «پیامک + پست + جای خالیِ صریحاً به‌زودی» plus
        a fourth, `voip` — the product owner's own follow-up request that
        every "connect systems" page also name VoIP/telephony, with no code
        or scope behind it yet, so it gets the same honest-placeholder
        treatment `coming_soon` already had rather than a fake settings
        page (`CLAUDE.md` §27)."""
        self.assertEqual([row.key for row in integrations.INTEGRATIONS],
                         ["sms", "post", "voip", "coming_soon"])

    def test_the_placeholder_offers_no_controls_at_all(self):
        """A switch that does nothing is worse than an empty space. Both
        placeholders (`voip`, `coming_soon`) share this, not just the last
        one — checked by key, not by position, so this does not silently
        stop meaning anything if a third placeholder is ever added."""
        for key in ("voip", "coming_soon"):
            placeholder = next(row for row in integrations.INTEGRATIONS if row.key == key)
            self.assertIsNone(placeholder.settings_url_name)
            self.assertIsNone(placeholder.test_url)
            self.assertEqual(placeholder.status(None).state, "unavailable")
        self.assertEqual(integrations.STATE_LABELS["unavailable"][0], "به‌زودی")

    def test_a_test_button_exists_only_where_a_test_exists(self):
        """Restated 2026-09-21: `post` gained a real settings page and a
        real "تست اتصال" (`sales/postal_provider.py`) — it belongs beside
        `sms` here now, not with the placeholders, which still offer
        neither."""
        by_key = {row.key: row for row in integrations.INTEGRATIONS}
        self.assertTrue(by_key["sms"].test_url)
        self.assertTrue(by_key["post"].test_url)
        self.assertIsNone(by_key["voip"].test_url)
        self.assertIsNone(by_key["coming_soon"].test_url)

    def test_a_secret_is_hinted_at_and_never_shown(self):
        self.assertEqual(integrations.mask_secret("abcdefghijkl"), "••••••••ijkl")
        # Too short for a hint to mean anything.
        self.assertEqual(integrations.mask_secret("abc"), "•••")
        self.assertEqual(integrations.mask_secret(""), "")

    def test_the_template_draws_whatever_the_table_holds(self):
        """Adding a service must be one row and no template change."""
        self.assertIn("{% for row in integrations %}", INTEGRATIONS_PAGE)
        self.assertIn("{{ row.state_label }}", INTEGRATIONS_PAGE)
        self.assertIn("{{ row.secret_hint }}", INTEGRATIONS_PAGE)
        self.assertIn("{{ row.last_error }}", INTEGRATIONS_PAGE)


class IntegrationVisibilityTests(TestCase):
    def setUp(self):
        # `SensitiveRateThrottle` counts in the shared cache, which is not
        # reset between tests — a class that spends the bucket leaves the
        # next one to hit 429. Same `cache.clear()` the other API-touching
        # suites in this project already do.
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = User.objects.create_user(
            username="ig.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN
        )
        self.agent = User.objects.create_user(
            username="ig.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def test_a_platform_admin_sees_every_row(self):
        keys = [row["key"] for row in integrations.visible_integrations(self.admin)]
        self.assertEqual(keys, ["sms", "post", "voip", "coming_soon"])

    def test_a_marketer_sees_only_what_they_could_configure(self):
        """Plus both placeholders, which is the point of them — neither has
        a gate, so nothing is there to exclude a role from."""
        keys = [row["key"] for row in integrations.visible_integrations(self.agent)]
        self.assertNotIn("sms", keys)
        self.assertIn("voip", keys)
        self.assertIn("coming_soon", keys)

    def test_an_unconfigured_gateway_says_so_rather_than_claiming_a_connection(self):
        row = next(r for r in integrations.visible_integrations(self.admin) if r["key"] == "sms")
        self.assertIn(row["state"], {"unconfigured", "disabled"})
        self.assertEqual(row["secret_hint"], "")

    def test_the_page_answers_an_empty_list_rather_than_a_403(self):
        """"There is nothing here for you" is the true answer; a permission
        error would suggest something is being withheld."""
        self.client.force_login(self.agent)
        response = self.client.get("/settings/integrations/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "سامانهٔ پیامک")
        self.assertContains(response, "به‌زودی")

    def test_the_page_renders_for_an_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get("/settings/integrations/")
        self.assertEqual(response.status_code, 200)
        for label in ("سامانهٔ پیامک", "سرویس پست", "به‌زودی"):
            with self.subTest(label=label):
                self.assertContains(response, label)

    def test_it_is_reachable_from_the_settings_page(self):
        self.client.force_login(self.admin)
        response = self.client.get("/settings/")
        self.assertContains(response, 'id="open-integrations"')
