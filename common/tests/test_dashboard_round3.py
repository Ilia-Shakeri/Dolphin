"""The dashboard editor, third round (2.18.1 onward).

Product-owner requests of 2026-09-27, one class per request so a later
reader can find which sentence a test is holding the page to.
"""

import json
import re

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from common.dashboard_layout import update_user_dashboard_layout
from common.tests.ui_overhaul_helpers import SCRIPT, TEMPLATES, function_body, rule

HOME = (TEMPLATES / "home.html").read_text(encoding="utf-8")

User = get_user_model()
PASSWORD = "Aa!23456pass"


def block(name, source=HOME):
    """One `{% block name %}` of a template, as text."""
    return source.split("{% block " + name + " %}")[1].split("{% endblock %}")[0]


class PencilPlacementTests(SimpleTestCase):
    """«آیکون مداد ویرایش داشبورد باید بالاتر و نزدیک‌تر به بخش بالایی باشد»."""

    def test_the_editor_controls_sit_in_the_page_toolbar(self):
        """The theme's own `page_actions` slot is the highest point on the
        page, on the same row as the page title — not a row of its own
        under it."""
        actions = block("page_actions")
        for control in ("dashboard-edit-toggle", "dashboard-edit-done", "dashboard-edit-reset",
                        "dashboard-add-widget-open"):
            with self.subTest(control=control):
                self.assertIn(f'id="{control}"', actions)
        self.assertNotIn('id="dashboard-edit-toggle"', block("content"))

    def test_the_pencil_is_the_last_control_so_it_lands_on_the_left_edge(self):
        actions = block("page_actions")
        self.assertGreater(actions.index('id="dashboard-edit-toggle"'), actions.index('id="dashboard-edit-done"'))

    def test_the_controls_only_render_where_arranging_can_be_saved(self):
        """A pencil whose save answers 404 is a control with no behaviour."""
        actions = block("page_actions")
        self.assertIn("{% if can_arrange_dashboard %}", actions)


class FirstRowEditableTests(SimpleTestCase):
    """«ردیف اول داشبورد باید قابل ویرایش باشد و جایشان قابل تغییر باشد»."""

    def test_the_editor_no_longer_depends_on_insight_widgets_existing(self):
        """Before 2.18.1 the editor was started at the very end of
        `setupDashboardInsights`, after two early returns — a reader with no
        insight widgets never got one, and the tile row could not move."""
        insights = function_body("setupDashboardInsights")
        self.assertNotIn("setupDashboardEditor(", insights)
        self.assertIn("return pageState ? {grid, widgets, layout, hiddenAvailable} : null;", insights)
        self.assertIn("return emptyEditorState();", insights)
        dashboard = function_body("setupDashboard")
        self.assertIn("setupDashboardEditor(grid)", dashboard)

    def test_the_editor_state_is_rendered_into_the_page(self):
        self.assertIn('dashboard_layout_state|json_script:"dashboard-layout-state"', HOME)
        self.assertIn('document.getElementById("dashboard-layout-state")', function_body("dashboardLayoutState"))

    def test_links_inside_a_box_cannot_start_a_native_drag_while_editing(self):
        """A pressed link that moves starts the browser's own link drag,
        which cancels the pointer stream the editor's drag runs on — every
        first-row tile is a link."""
        body = function_body("setupDashboardEditor")
        self.assertIn('node.setAttribute("draggable", "false")', body)
        self.assertIn("suppressNativeDrag(column);", body)
        self.assertIn("restoreNativeDrag(column);", body)
        self.assertIn("-webkit-user-drag: none", rule(".dashboard-widget.editing a"))

    def test_a_box_does_not_navigate_while_editing(self):
        body = function_body("setupDashboardEditor")
        self.assertIn('if (editing && event.target.closest("a[href]")) event.preventDefault();', body)


class LayoutStateRenderTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="round3.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN,
        )

    def state(self):
        self.client.force_login(self.admin)
        page = self.client.get("/").content.decode("utf-8")
        match = re.search(r'<script id="dashboard-layout-state" type="application/json">(.*?)</script>', page, re.S)
        self.assertIsNotNone(match, "the editor's state was not rendered into the page")
        return json.loads(match.group(1))

    def test_the_rendered_state_carries_what_the_editor_starts_from(self):
        state = self.state()
        self.assertEqual(
            set(state), {"order", "hidden", "sizes", "locked_hidden", "is_customised"},
        )
        self.assertFalse(state["is_customised"])

    def test_the_rendered_state_follows_the_readers_own_overlay(self):
        update_user_dashboard_layout(
            actor=self.admin,
            widget_order=["capability:leads.company", "capability:customers.company"],
            widget_sizes={"capability:leads.company": "half"},
        )
        state = self.state()
        self.assertTrue(state["is_customised"])
        self.assertEqual(state["order"][:2], ["capability:leads.company", "capability:customers.company"])
        self.assertEqual(state["sizes"], {"capability:leads.company": "half"})


class AddWidgetDialogTests(SimpleTestCase):
    """«در مودال افزودن ویجت باید همهٔ ویجت‌های موجود نمایش داده شود و
    پیش‌نمایش داشته باشد»."""

    def test_the_dialog_has_an_addable_group_and_an_on_the_dashboard_group(self):
        self.assertIn('id="dashboard-add-widget-grid"', HOME)
        self.assertIn('id="dashboard-add-widget-placed"', HOME)

    def test_every_source_of_widgets_feeds_the_dialog(self):
        body = function_body("setupDashboardEditor")
        self.assertIn('document.getElementById("dashboard-tile-catalog")', body)
        self.assertIn("widgets.forEach((widget) => {", body)
        self.assertIn("(hiddenAvailable || []).forEach((part) => {", body)

    def test_a_placed_widget_can_be_taken_off_from_the_dialog(self):
        body = function_body("setupDashboardEditor")
        self.assertIn("if (hidden.includes(entry.key)) addBackWidget(entry.key);", body)
        self.assertIn("else hideWidget(entry.key);", body)

    def test_dialog_cards_do_not_collide_with_dashboard_boxes(self):
        """The dialog sits before both grids; a card carrying
        `data-widget-key` would be what every box lookup found first."""
        body = function_body("setupDashboardEditor")
        self.assertIn("card.dataset.addWidgetKey = entry.key;", body)
        self.assertNotIn("card.dataset.widgetKey", body)

    def test_a_tile_preview_shows_its_real_figure(self):
        body = function_body("renderWidgetPreview")
        self.assertIn('entry.family === "tile"', body)
        self.assertIn("toPersianDigits(String(data.value ?? 0))", body)

    def test_the_hidden_bar_names_a_box_hidden_before_the_page_loaded(self):
        """It used to fall back to the raw key, e.g. `capability:audit.all`."""
        body = function_body("setupDashboardEditor")
        self.assertIn("const listed = catalogLabel(key);", body)


class HiddenAvailableTests(TestCase):
    def setUp(self):
        from common.models import DashboardSettings

        self.admin = User.objects.create_user(
            username="round3.dialog", password=PASSWORD, role=User.Role.PLATFORM_ADMIN,
        )
        self.settings_row = DashboardSettings.objects.get_or_create(singleton=DashboardSettings.SINGLETON)[0]

    def payload(self):
        return {
            "kpis": [
                {"key": "sales_count_this_month", "label": "a", "display": "۱"},
                {"key": "outstanding", "label": "b", "display": "۲"},
            ],
            "trend": {"title": "روند", "points": [], "counts": []},
            "breakdown": None,
            "gauges": [{"key": "lead_conversion_rate", "label": "c", "value": 40}],
            "agent_share": None,
        }

    def test_a_part_the_reader_hid_travels_with_its_real_figure(self):
        from common.dashboard_layout import apply_layout

        update_user_dashboard_layout(actor=self.admin, hidden_widgets=["sales_count_this_month", "trend"])
        result = apply_layout(self.payload(), self.admin)
        available = {item["key"]: item for item in result["hidden_available"]}
        self.assertEqual(set(available), {"sales_count_this_month", "trend"})
        self.assertEqual(available["sales_count_this_month"]["family"], "kpi")
        self.assertEqual(available["sales_count_this_month"]["display"], "۱")
        self.assertEqual(available["trend"]["family"], "trend")
        self.assertNotIn("sales_count_this_month", [kpi["key"] for kpi in result["kpis"]])

    def test_a_deployment_hidden_part_is_never_offered(self):
        from common.dashboard_layout import apply_layout

        self.settings_row.hidden_widgets = ["outstanding"]
        self.settings_row.save()
        update_user_dashboard_layout(actor=self.admin, hidden_widgets=["outstanding"])
        result = apply_layout(self.payload(), self.admin)
        self.assertEqual(result["hidden_available"], [])

    def test_the_tile_catalog_keeps_reader_hidden_tiles_and_drops_deployment_hidden_ones(self):
        from common.dashboard_layout import capability_tile_catalog, effective_layout

        self.settings_row.hidden_widgets = ["capability:audit.all"]
        self.settings_row.save()
        update_user_dashboard_layout(actor=self.admin, hidden_widgets=["capability:leads.company"])
        tiles = [
            {"capability": "leads.company", "label": "سرنخ", "value": 3, "icon": "ki-x", "icon_paths": 2, "accent": "info"},
            {"capability": "audit.all", "label": "رویداد", "value": 9, "icon": "ki-y", "icon_paths": 2, "accent": "dark"},
        ]
        catalog = capability_tile_catalog(tiles, effective_layout(self.admin))
        self.assertEqual([entry["key"] for entry in catalog], ["capability:leads.company"])
        self.assertEqual(catalog[0]["value"], 3)
        self.assertEqual(catalog[0]["family"], "tile")

    def test_the_page_renders_the_tile_catalog(self):
        self.client.force_login(self.admin)
        page = self.client.get("/").content.decode("utf-8")
        self.assertIn('<script id="dashboard-tile-catalog" type="application/json">', page)
