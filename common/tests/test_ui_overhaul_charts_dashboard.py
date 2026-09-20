"""Batch B of the 2026-09-20 UI pass: the chart controls and the dashboard editor.

Two product-owner items, and the thing they have in common is that both
replaced several near-copies with one component.

**Item 4 — the line charts.** Three different time filters existed: the
customers page offered «هفتگی/ماهانه/بازه دلخواه», the seller profile offered
«هفتگی/ماهانه», and the eleven list pages offered nothing. Two of the three
were also asking the wrong question — a bucket width is not what a reader
picks, a window is — so the presets are windows now and the bucket width is
derived from the window, once, on the server. Each chart's title names the
window it actually drew, the charts that can be narrowed declare their own
filters, and Apex's floating magnifier is gone with the reset moved into the
card header as «حالت پیش‌فرض».

**Item 5 — the dashboard.** The editor edited half the page: its bar sat
inside the insights section, below the capability tiles it could not touch.
It now sits at the top and walks every `[data-dashboard-grid]`. The six-dot
handle is gone (the whole box was already draggable), the size `<select>`
became a corner grip that snaps across the four widths the server accepts,
and the hide button is held clear of the corner.

Most of this is read out of the shipped source, which needs no browser. What
a browser was actually used for, at the time: the range group measured
360×35 in the card header with no horizontal page scroll, «۳۰ روز» → «۷ روز»
took the trend from 31 x-axis labels to 8 and the title from «در ۳۰ روز
گذشته» to «در هفتهٔ گذشته», «امروز» produced hourly labels, choosing a
marketer left the choice selected across the redraw, and `.apexcharts-toolbar`
/ `.apexcharts-zoom-icon` were absent from every chart on the page.
"""

import pathlib
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from common.dashboard_layout import (
    CAPABILITY_WIDGET_PREFIX,
    WIDGET_SIZES,
    arrange_capability_tiles,
    capability_widget_key,
    update_user_dashboard_layout,
)
from common.exceptions import BusinessRuleError
from reports import ranges
from reports.list_charts import CHART_FILTERS, LIST_CHARTS, filters_for, narrowing


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

HOME = (TEMPLATES / "home.html").read_text(encoding="utf-8")
LIST_CHART_INCLUDE = (TEMPLATES / "includes" / "list_charts.inc").read_text(encoding="utf-8")

User = get_user_model()
PASSWORD = "Aa!23456pass"


# ===========================================================================
# Item 4 — one time filter, on every chart that has a time axis
# ===========================================================================


class SharedRangeFilterTests(SimpleTestCase):
    def test_there_is_exactly_one_range_component(self):
        """The whole point of the item. Three near-copies became one, and a
        fourth page adding its own would put us back where we started."""
        self.assertEqual(SCRIPT.count("function setupChartRange("), 1)
        self.assertEqual(SCRIPT.count("const CHART_RANGES = "), 1)

    def test_the_presets_are_the_ones_that_were_asked_for(self):
        body = SCRIPT.split("const CHART_RANGES = ")[1].split("]);")[0]
        for label in ("امروز", "۷ روز", "۳۰ روز", "۳ ماه", "یک سال", "بازه دلخواه"):
            with self.subTest(preset=label):
                self.assertIn(f'label: "{label}"', body)

    def test_a_preset_is_a_window_not_a_bucket_width(self):
        """The mistake the two old filters made. «هفتگی/ماهانه» is how wide a
        bar is; a reader is choosing how much time to look at."""
        body = SCRIPT.split("const CHART_RANGES = ")[1].split("]);")[0]
        self.assertIn("days: 30", body)
        self.assertNotIn("granularity", body)

    def test_the_component_sends_no_granularity_at_all(self):
        body = function_body("chartRangeWindow")
        self.assertIn("period_start", body)
        self.assertIn("period_end", body)
        self.assertNotIn("granularity", body)

    def test_a_preset_window_ends_now_rather_than_at_the_end_of_today(self):
        """A last bucket running into the future draws a cliff down to zero
        on every page load after midnight."""
        body = function_body("chartRangeWindow")
        self.assertIn("const end = new Date();", body)
        self.assertIn("end.getTime() - preset.days * 86400000", body)

    def test_a_half_finished_custom_range_sends_nothing(self):
        """Half a window is not a window; the chart keeps what it has until
        both ends are named."""
        body = function_body("chartRangeWindow")
        self.assertIn("return start && end ? {period_start: start, period_end: end} : {};", body)

    def test_the_three_pages_that_had_their_own_filters_no_longer_do(self):
        for gone in ("data-growth-range", "data-trend-range"):
            with self.subTest(attribute=gone):
                self.assertNotIn(gone, SCRIPT)
                for name in ("customers/list.html", "users/profile.html"):
                    self.assertNotIn(gone, (TEMPLATES / name).read_text(encoding="utf-8"))

    def test_each_of_those_pages_now_declares_the_shared_slot(self):
        self.assertIn('id="customer-growth-controls"',
                      (TEMPLATES / "customers" / "list.html").read_text(encoding="utf-8"))
        self.assertIn('id="profile-trend-controls"',
                      (TEMPLATES / "users" / "profile.html").read_text(encoding="utf-8"))
        # One slot in one include covers all eleven list pages.
        self.assertIn("data-chart-range", LIST_CHART_INCLUDE)

    def test_the_two_growth_charts_open_on_a_year_as_they_always_did(self):
        """Their default is not the list pages' thirty days: both are a
        «رشد در یک سال» reading and changing that silently would be a
        different chart, not a new filter."""
        self.assertEqual(SCRIPT.count('{initial: "1y"'), 2)

    def test_the_slot_and_the_buttons_do_not_share_an_attribute(self):
        """`[data-chart-range]` is the slot a page declares. If the buttons
        carried it too, a page-level query for the slot would match seven
        elements, six of them buttons."""
        body = function_body("setupChartRange")
        self.assertIn("button.dataset.chartPreset = range.key;", body)
        self.assertNotIn("button.dataset.chartRange", body)

    def test_the_custom_fields_are_the_shared_jalali_picker(self):
        """Not a second date control. `setupJalaliInputs` is idempotent and
        takes a subtree, which is why it can be called on freshly built
        markup."""
        body = function_body("setupChartRange")
        self.assertIn('field.dataset.jalali = "date";', body)
        self.assertIn("setupJalaliInputs(host);", body)

    def test_the_component_is_not_mounted_twice_on_one_slot(self):
        body = function_body("setupChartRange")
        self.assertIn('host.dataset.chartRangeReady === "1"', body)


class GranularityDerivationTests(SimpleTestCase):
    """The rule that replaced «هفتگی/ماهانه»: one function, on the server."""

    def test_a_window_picks_its_own_bucket_width(self):
        now = timezone.now()
        cases = (
            (timedelta(hours=6), "hour"),
            (timedelta(days=1), "hour"),
            (timedelta(days=7), "day"),
            (timedelta(days=30), "day"),
            (timedelta(days=90), "week"),
            (timedelta(days=365), "week"),
            (timedelta(days=900), "month"),
        )
        for span, expected in cases:
            with self.subTest(span=span):
                self.assertEqual(ranges.granularity_for(now - span, now), expected)

    def test_no_derived_width_can_exceed_the_bucket_cap(self):
        """The cap is what stops an unreadable chart; a derivation that
        could break it would make the cap a 400 instead of a guard."""
        now = timezone.now()
        for granularity, longest in ranges._THRESHOLDS:
            with self.subTest(granularity=granularity):
                starts = ranges.local_bucket_starts(granularity, now - longest, now)
                self.assertLessEqual(len(starts), ranges.MAX_BUCKETS)

    def test_the_bucket_helpers_live_in_one_module_now(self):
        """They were duplicated line for line in `customer_insights` and
        `sales_insights`, which is how one of the two could gain a
        granularity the other did not."""
        for name in ("customer_insights", "sales_insights"):
            source = (ROOT / "reports" / f"{name}.py").read_text(encoding="utf-8")
            with self.subTest(module=name):
                self.assertIn("from reports.ranges import (", source)
                self.assertNotIn("def _bucket_sequence(", source)
                self.assertNotIn("def _next_bucket(", source)
                self.assertNotIn("def _truncation(", source)

    def test_an_hourly_bucket_key_stays_a_datetime(self):
        """`.date()` would collapse a day's twenty-four buckets into one."""
        moment = timezone.now()
        hourly = ranges.bucket_key("hour", moment)
        self.assertEqual(hourly.minute, 0)
        self.assertEqual(hourly.second, 0)
        self.assertEqual(ranges.bucket_key("day", moment), timezone.localtime(moment).date())

    def test_a_row_lands_in_the_bucket_it_belongs_to(self):
        now = timezone.localtime(timezone.now())
        starts = ranges.local_bucket_starts("day", now - timedelta(days=5), now)
        self.assertEqual(ranges.bucket_index("day", starts, now), len(starts) - 1)
        self.assertEqual(ranges.bucket_index("day", starts, starts[0]), 0)
        self.assertIsNone(ranges.bucket_index("day", starts, now - timedelta(days=40)))


class HourlyLabelTests(SimpleTestCase):
    def test_an_hourly_point_is_labelled_with_its_hour(self):
        """Measured on a live hourly chart before this: Apex trimmed the full
        «۱۴۰۵/۰۶/۲۸ ۱۹:۰۰» to «۱۴۰۵/۰۶/۲۸ ۱۹…», cutting off the one part
        that differs between neighbouring points."""
        body = function_body("bucketLabel")
        self.assertIn('if (granularity !== "hour") return displayDay(bucket);', body)
        self.assertIn('`${pad2(parts.hour)}:00`', body)

    def test_every_caller_labels_through_it_rather_than_guessing(self):
        self.assertIn("bucketLabel(row.bucket, report.granularity)", SCRIPT)
        self.assertEqual(SCRIPT.count("bucketLabel(row.bucket, report.granularity)"), 2)


class ChartToolbarTests(SimpleTestCase):
    def test_the_magnifier_is_gone_from_the_whole_file(self):
        self.assertNotIn("zoom: true,", SCRIPT)

    def test_the_way_back_is_a_real_button_in_the_header(self):
        self.assertEqual(SCRIPT.count("function chartResetButton("), 1)
        body = function_body("chartResetButton")
        self.assertIn('reset.title = "حالت پیش‌فرض"', body)
        self.assertIn("dolphin-chart-reset", body)

    def test_the_dashboard_trend_gets_one_even_without_a_range_filter(self):
        """It is zoomable and has no filter beside it to carry the reset, so
        removing Apex's toolbar without this would leave a reader who
        drag-zoomed it with no way back."""
        self.assertIn('id="dashboard-trend-controls"', HOME)
        self.assertIn('document.getElementById("dashboard-trend-controls")', SCRIPT)


class ChartControlStyleTests(SimpleTestCase):
    def test_the_controls_row_wraps_without_collapsing_its_gaps(self):
        declarations = rule(".dolphin-chart-controls")
        self.assertIn("flex-wrap: wrap", declarations)
        self.assertIn("gap:", declarations)

    def test_the_button_group_itself_does_not_wrap(self):
        """A wrapped `btn-group` loses its own joined corners."""
        self.assertIn("flex-wrap: nowrap", rule(".dolphin-chart-range"))

    def test_the_group_becomes_the_whole_row_on_a_phone(self):
        phone = media_block("(max-width: 575.98px)", ".dolphin-chart-range")
        self.assertIn(".dolphin-chart-range", phone)
        self.assertIn("flex: 1 1 100%", phone)

    def test_the_custom_fields_are_narrow_enough_to_sit_beside_a_heading(self):
        self.assertIn("inline-size: 8.5rem", rule(".dolphin-chart-range-custom input"))


# ===========================================================================
# Item 4 — the per-chart filters
# ===========================================================================


class ChartFilterRegistryTests(SimpleTestCase):
    def test_the_three_the_product_owner_named_all_exist(self):
        params = {entry.param for entries in CHART_FILTERS.values() for entry in entries}
        # Marketer, status, lead source.
        self.assertTrue({"assigned_to", "sold_by", "agent"} & params)
        self.assertIn("status", params)
        self.assertIn("source", params)

    def test_every_filtered_key_is_a_real_chart(self):
        self.assertLessEqual(set(CHART_FILTERS), set(LIST_CHARTS))

    def test_every_lookup_names_a_column_the_model_really_has(self):
        """A lookup that does not resolve is a 500 nobody sees until they
        open that one page — which is exactly how the first draft of this
        table shipped `created_by_id` for a model whose column is `agent`."""
        from django.apps import apps

        models = {
            "leads": ("sales", "Lead"),
            "sales": ("sales", "Sale"),
            "orders": ("billing", "Order"),
            "interactions": ("sales", "Interaction"),
            # Added in 3.0.0 with the postal vocabulary.
            "sales-documents": ("sales", "SalesDocument"),
        }
        for key, entries in CHART_FILTERS.items():
            model = apps.get_model(*models[key])
            for entry in entries:
                with self.subTest(chart=key, filter=entry.param):
                    model._meta.get_field(entry.lookup.removesuffix("_id"))

    def test_every_filter_names_its_own_any_option(self):
        """«همهٔ» plus a singular noun is wrong Persian for half of them, so
        the text is written per filter rather than composed in the panel."""
        for key, entries in CHART_FILTERS.items():
            for entry in entries:
                with self.subTest(chart=key, filter=entry.param):
                    self.assertTrue(entry.all_label.startswith("همهٔ "))


class ChartFilterBehaviourTests(TestCase):
    def setUp(self):
        # `SensitiveRateThrottle` counts in the shared cache, which is not
        # reset between tests — a class that spends the bucket leaves the
        # next one to hit 429. Same `cache.clear()` the other API-touching
        # suites in this project already do.
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="cf.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="cf.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def _lead(self, *, assigned_to=None, **kwargs):
        """`lead_assignment_fields_consistent` requires all three assignment
        columns together or none of them, so the helper sets them together."""
        from sales.models import Lead

        if assigned_to is not None:
            kwargs.update(
                assigned_to=assigned_to,
                assigned_by=self.manager,
                assigned_at=timezone.now(),
            )
        return Lead.objects.create(created_by=self.manager, **kwargs)

    def test_a_filter_only_offers_values_that_occur_in_this_readers_scope(self):
        """Which is what makes the option list safe without a second
        permission rule: a reader offered the marketers whose leads they can
        already list is being offered nothing new."""
        self._lead(source="tv", assigned_to=self.agent)
        offered = {entry["param"]: entry for entry in filters_for("leads", self.manager)}
        self.assertEqual(
            [option["label"] for option in offered["assigned_to"]["options"]],
            ["cf.agent"],
        )
        self.assertEqual([option["value"] for option in offered["source"]["options"]], ["tv"])

    def test_a_filter_with_no_values_is_dropped_rather_than_drawn_empty(self):
        offered = {entry["param"] for entry in filters_for("leads", self.manager)}
        # No lead has a source or an assignee yet; status is a fixed
        # vocabulary and is always offered.
        self.assertNotIn("assigned_to", offered)
        self.assertNotIn("source", offered)
        self.assertIn("status", offered)

    def test_a_chart_with_no_declared_filters_offers_none(self):
        self.assertEqual(filters_for("products", self.manager), [])

    def test_narrowing_applies_the_choice_to_the_scoped_queryset(self):
        from sales.models import Lead

        self._lead(source="tv", assigned_to=self.agent)
        self._lead(source="instagram")
        narrow = narrowing("leads", self.manager, {"source": "tv"})
        self.assertEqual(narrow(Lead.objects.all()).count(), 1)

    def test_a_value_that_was_never_offered_is_refused_not_ignored(self):
        """Ignoring it would answer a different question than the URL asks;
        accepting it would let the query string reach a column the registry
        never declared."""
        from reports.list_charts import UnknownChartFilter

        self._lead(source="tv")
        with self.assertRaises(UnknownChartFilter):
            narrowing("leads", self.manager, {"source": "not-a-source"})

    def test_no_filters_means_no_narrowing_rather_than_an_empty_filter(self):
        self.assertIsNone(narrowing("leads", self.manager, {}))
        self.assertIsNone(narrowing("products", self.manager, {"source": "tv"}))

    def test_the_endpoint_narrows_both_charts_together(self):
        """A composition chart counting one marketer's leads beside a trend
        counting everybody's would be two answers to one question."""
        from rest_framework.test import APIClient

        self._lead(source="tv", assigned_to=self.agent)
        self._lead(source="instagram")
        client = APIClient()
        client.force_authenticate(self.manager)
        response = client.get("/api/v1/reports/list-chart/leads/?source=tv")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(sum(row["value"] for row in response.data["results"]), 1)
        self.assertEqual(
            sum(point["value"] for point in response.data["trend"]["points"]), 1
        )

    def test_the_endpoint_refuses_a_value_it_never_offered(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(self.manager)
        response = client.get("/api/v1/reports/list-chart/leads/?status=not-a-status")
        self.assertEqual(response.status_code, 400)

    def test_the_endpoint_draws_the_window_it_is_given(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(self.manager)
        now = timezone.now()
        response = client.get(
            "/api/v1/reports/list-chart/leads/",
            {
                "period_start": (now - timedelta(days=7)).isoformat(),
                "period_end": now.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["trend"]["granularity"], "day")
        self.assertEqual(len(response.data["trend"]["points"]), 8)
        self.assertIn("هفتهٔ گذشته", response.data["trend"]["title"])


# ===========================================================================
# Item 5 — the dashboard editor
# ===========================================================================


class DashboardEditorPlacementTests(SimpleTestCase):
    def test_the_editor_bar_is_above_every_box_on_the_page(self):
        """It used to sit inside the insights section, below the capability
        tiles — lower than the thing it edits, and blind to half of it."""
        bar = HOME.index('id="dashboard-editor-bar"')
        tiles = HOME.index('id="dashboard-capability-tiles"')
        insights = HOME.index('id="dashboard-insights"')
        self.assertLess(bar, tiles)
        self.assertLess(bar, insights)

    def test_both_rows_declare_themselves_editable(self):
        # Counted on the attribute in markup, not on every mention: the
        # template explains itself in comments that name it too.
        markup = re.sub(r"\{% comment %\}.*?\{% endcomment %\}", "", HOME, flags=re.S)
        self.assertEqual(markup.count("data-dashboard-grid"), 2)

    def test_the_editor_walks_every_declared_grid(self):
        body = function_body("setupDashboardEditor")
        self.assertIn('document.querySelectorAll("[data-dashboard-grid]")', body)
        self.assertIn("grids.flatMap((host) => Array.from(host.children))", body)

    def test_a_capability_tile_carries_a_layout_key_and_its_own_width(self):
        self.assertIn('data-widget-key="{{ widget.key }}"', HOME)
        self.assertIn('class="dashboard-widget {{ widget.size }}"', HOME)

    def test_the_capability_row_keeps_the_themes_scrollbar_not_the_flipped_one(self):
        """`.dolphin-hover-scroll` flips its container to `direction: ltr` to
        put the bar on the right; this container is a Bootstrap flex row, and
        flipping it reverses the visual order of the tiles."""
        section = HOME.split('id="dashboard-capability-tiles"')[0].rsplit("<section", 1)[1]
        self.assertIn("hover-scroll-overlay-y", section)
        self.assertNotIn("dolphin-hover-scroll", section)

    def test_editing_lifts_the_rows_own_scroll_cap(self):
        """A tile dragged towards a position scrolled out of view cannot be
        dropped there."""
        declarations = rule(".dashboard-capability-grid.dashboard-widgets-editing")
        self.assertIn("max-height: none", declarations)
        self.assertIn("overflow: visible", declarations)


class DashboardDragTests(SimpleTestCase):
    def test_the_six_dot_handle_is_gone(self):
        """The whole box was already `draggable`, so the handle was a picture
        of a thing that was not needed."""
        self.assertNotIn("dashboard-widget-handle", SCRIPT)
        self.assertNotIn("dashboard-widget-handle", CSS)
        self.assertNotIn("⠿", SCRIPT)

    def test_the_whole_box_is_still_what_starts_a_drag(self):
        body = function_body("setupDashboardEditor")
        self.assertIn("column.draggable = true;", body)

    def test_a_box_may_not_be_dropped_into_the_other_grid(self):
        """The two rows are different shapes; a card dropped into the capped
        tile strip would be cut off by its own cap."""
        body = function_body("setupDashboardEditor")
        self.assertIn("if (target.parentElement !== dragged.parentElement) return;", body)

    def test_the_saved_order_spans_both_rows(self):
        body = function_body("setupDashboardEditor")
        self.assertIn("return allBoxes()", body)


class DashboardResizeTests(SimpleTestCase):
    def test_the_size_select_became_a_corner_grip(self):
        self.assertNotIn("dashboard-widget-size", SCRIPT)
        self.assertIn("function resizeGrip(", SCRIPT)

    def test_the_grip_sits_on_the_edge_a_box_grows_towards(self):
        """A column in an RTL row is anchored at the row's right and extends
        leftwards, so the edge that moves when it widens is the physical
        left one — `inset-inline-end` here, the same property the hide
        control uses to reach the top left."""
        declarations = rule(".dashboard-widget .dashboard-widget-resize")
        self.assertIn("inset-block-end:", declarations)
        self.assertIn("inset-inline-end:", declarations)
        self.assertIn("cursor: nesw-resize", declarations)

    def test_the_grip_rule_outranks_bootstraps_own_button_cursor(self):
        """Measured: with a lone class the grip rendered `cursor: pointer`,
        because Bootstrap's reset carries `button:not(:disabled)` at (0,1,1)
        and a single class is (0,1,0)."""
        self.assertIn(".dashboard-widget .dashboard-widget-resize {", CODE)
        # The bare class, at the start of a line — the form that lost.
        self.assertNotIn("\n.dashboard-widget-resize {", CODE)

    def test_dragging_left_widens_because_the_panel_is_rtl(self):
        body = function_body("setupDashboardEditor")
        self.assertIn("const widened = startWidth + (startX - event.clientX);", body)

    def test_the_min_and_max_are_the_widths_the_server_accepts(self):
        """Not free pixels: a box has to keep lining up with every other card
        and has to collapse to full width on a phone, which is what the
        theme's twelve-column grid already does."""
        body = function_body("setupDashboardEditor")
        self.assertIn("const steps = sizeChoices.length ? sizeChoices : DASHBOARD_SIZE_FALLBACK;", body)
        self.assertEqual(set(WIDGET_SIZES), {"quarter", "third", "half", "full"})

    def test_the_grip_is_reachable_by_keyboard(self):
        body = function_body("setupDashboardEditor")
        self.assertIn('grip.addEventListener("keydown"', body)
        self.assertIn('event.key === "ArrowLeft"', body)

    def test_the_grip_is_a_button_with_an_accessible_name(self):
        body = function_body("setupDashboardEditor")
        self.assertIn('grip.type = "button";', body)
        self.assertIn('grip.setAttribute("aria-label", `تغییر اندازهٔ ${boxLabel(key)}`)', body)


class DashboardHideButtonTests(SimpleTestCase):
    def test_it_is_held_clear_of_the_corner(self):
        declarations = rule(".dashboard-widget-controls")
        self.assertIn("top: 0.75rem", declarations)
        self.assertIn("inset-inline-end: 0.75rem", declarations)

    def test_it_is_a_real_icon_button_rather_than_a_bare_multiplication_sign(self):
        body = function_body("setupDashboardEditor")
        self.assertIn('hide.innerHTML = \'<i class="ki-outline ki-cross fs-4"></i>\'', body)
        self.assertIn('hide.className = "btn btn-icon btn-sm btn-danger dashboard-widget-hide"', body)

    def test_it_names_the_box_it_would_hide(self):
        body = function_body("setupDashboardEditor")
        self.assertIn('`پنهان کردن ${boxLabel(key)}`', body)


class CapabilityTileLayoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ct.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.tiles = [
            {"capability": "leads.company", "label": "سرنخ‌های شرکت", "value": 3},
            {"capability": "sales.company", "label": "فروش‌های شرکت", "value": 7},
        ]

    def test_a_tile_gets_a_key_derived_from_its_capability(self):
        """Derived, not declared: which tiles exist depends on the reader's
        own capabilities, so there is no static list to write down."""
        self.assertEqual(
            capability_widget_key("leads.company"),
            f"{CAPABILITY_WIDGET_PREFIX}leads.company",
        )

    def test_a_tile_carries_its_own_width(self):
        arranged = arrange_capability_tiles(self.tiles, self.user)
        self.assertEqual(len(arranged), 2)
        for tile in arranged:
            self.assertIn("col-", tile["size"])

    def test_the_reader_s_own_order_is_honoured(self):
        update_user_dashboard_layout(
            actor=self.user,
            widget_order=[capability_widget_key("sales.company"),
                          capability_widget_key("leads.company")],
        )
        arranged = arrange_capability_tiles(self.tiles, self.user)
        self.assertEqual([tile["capability"] for tile in arranged],
                         ["sales.company", "leads.company"])

    def test_the_reader_s_own_width_is_honoured(self):
        update_user_dashboard_layout(
            actor=self.user,
            widget_sizes={capability_widget_key("leads.company"): "half"},
        )
        arranged = {tile["capability"]: tile for tile in arrange_capability_tiles(self.tiles, self.user)}
        self.assertEqual(arranged["leads.company"]["size"], WIDGET_SIZES["half"][1])
        self.assertEqual(arranged["sales.company"]["size"], WIDGET_SIZES["quarter"][1])

    def test_a_hidden_tile_does_not_render(self):
        update_user_dashboard_layout(
            actor=self.user, hidden_widgets=[capability_widget_key("leads.company")]
        )
        arranged = arrange_capability_tiles(self.tiles, self.user)
        self.assertEqual([tile["capability"] for tile in arranged], ["sales.company"])

    def test_a_malformed_capability_key_is_still_refused(self):
        """The key's *shape* is what is validated, since there is no list of
        names — but it is validated, so the field cannot hold free text."""
        for bad in ("capability:", "capability:one", "capability:a.b.c", "nonsense"):
            with self.subTest(key=bad):
                with self.assertRaises(BusinessRuleError):
                    update_user_dashboard_layout(actor=self.user, hidden_widgets=[bad])

    def test_a_capability_key_arranges_nothing_it_should_not(self):
        """Saving a key for a capability the reader does not hold is
        harmless: no tile is rendered for it, so there is nothing to
        arrange."""
        update_user_dashboard_layout(
            actor=self.user, hidden_widgets=[capability_widget_key("nobody.holds_this")]
        )
        self.assertEqual(len(arrange_capability_tiles(self.tiles, self.user)), 2)

    def test_one_reset_clears_both_rows(self):
        from common.dashboard_layout import reset_user_dashboard_layout

        update_user_dashboard_layout(
            actor=self.user,
            hidden_widgets=[capability_widget_key("leads.company"), "trend"],
        )
        reset_user_dashboard_layout(actor=self.user)
        self.assertEqual(len(arrange_capability_tiles(self.tiles, self.user)), 2)
