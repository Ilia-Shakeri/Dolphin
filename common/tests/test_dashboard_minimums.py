"""Dashboard boxes have a smallest readable size, drops push down (2.40.2).

* every widget may declare a minimum width step and row count
  (`WIDGET_MIN_SIZES` / `WIDGET_MIN_ROWS`); the editor stops there, the
  server raises a smaller saved value to it, and a layout saved before the
  minimum existed is *read* at the minimum without being rewritten;
* a box dropped on others lands exactly there and pushes them down; only
  «مرتب‌سازی» moves boxes up;
* changes are a draft until «ذخیره»; Escape or «انصراف» discards them;
* below 768px there is nothing to place, so editing says so instead.
"""

from pathlib import Path

from django.test import SimpleTestCase, TestCase

from accounts.models import User
from common.dashboard_layout import (
    WIDGET_KEYS,
    WIDGET_MIN_ROWS,
    WIDGET_MIN_SIZES,
    WIDGET_SIZES,
    apply_layout,
    clamp_size,
    effective_layout,
    size_class,
    update_user_dashboard_layout,
    widget_minimums,
)
from common.models import UserDashboardLayout

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "common" / "static" / "common" / "js" / "features" / "dashboard" / "dashboard.js").read_text(encoding="utf-8")
HOME = (ROOT / "common" / "templates" / "common" / "home.html").read_text(encoding="utf-8")


class RegistryTests(SimpleTestCase):
    def test_every_minimum_names_a_real_widget_and_step(self):
        self.assertLessEqual(set(WIDGET_MIN_SIZES) | set(WIDGET_MIN_ROWS), WIDGET_KEYS)
        self.assertLessEqual(set(WIDGET_MIN_SIZES.values()), set(WIDGET_SIZES))

    def test_the_trend_cannot_be_a_quarter(self):
        """The case that broke: twelve weekly bars and a legend in a quarter."""
        self.assertEqual(clamp_size("trend", "quarter"), "half")
        self.assertEqual(clamp_size("trend", "full"), "full")
        self.assertEqual(clamp_size("outstanding", "quarter"), "quarter")

    def test_the_editor_receives_the_minimums(self):
        self.assertEqual(widget_minimums()["trend"], ["half", WIDGET_MIN_ROWS["trend"]])


class ServerClampTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="minimum.reader", password="Strong-pass-661!", role=User.Role.SALES_MANAGER)
        self.payload = {"kpis": [], "trend": {"title": "t", "points": [], "counts": []}, "breakdown": None,
                        "gauges": [], "agent_share": None}

    def test_a_saved_size_below_the_minimum_is_raised(self):
        update_user_dashboard_layout(actor=self.user, widget_sizes={"trend": "quarter", "outstanding": "quarter"})
        self.assertEqual(effective_layout(self.user)["sizes"], {"trend": "half", "outstanding": "quarter"})

    def test_a_saved_height_below_the_minimum_is_raised(self):
        update_user_dashboard_layout(actor=self.user, widget_heights={"trend": "r10"})
        self.assertEqual(effective_layout(self.user)["heights"], {"trend": f"r{WIDGET_MIN_ROWS['trend']}"})

    def test_an_old_layout_is_read_at_the_minimum_and_not_rewritten(self):
        UserDashboardLayout.objects.create(pk=self.user.pk, widget_sizes={"trend": "quarter"}, widget_heights={"trend": "r8"})
        arranged = apply_layout(self.payload, self.user)["trend"]
        self.assertEqual(arranged["size"], WIDGET_SIZES["half"][1])
        self.assertEqual(arranged["height"], WIDGET_MIN_ROWS["trend"])
        self.assertEqual(UserDashboardLayout.objects.get(pk=self.user.pk).widget_sizes, {"trend": "quarter"})
        self.assertEqual(size_class("trend", {"trend": "quarter"}), WIDGET_SIZES["half"][1])


class EditorTests(SimpleTestCase):
    def test_resizing_stops_at_the_minimum_with_feedback(self):
        self.assertIn("if (belowMinimumWidth(key, token)) { flagMinimum(column); return false; }", SCRIPT)
        self.assertIn("if (rows < minimumRows(key)) { flagMinimum(column); return false; }", SCRIPT)

    def test_fitting_rows_respects_the_minimum(self):
        self.assertIn("const floor = Number(column.dataset.minRows) || 6;", SCRIPT)

    def test_a_drop_pushes_others_down_where_it_lands(self):
        self.assertIn("setBoxSpot(dragged, dropSpot.x, dropSpot.y);\n                    pushDownAround(host, dragged);", SCRIPT)
        self.assertNotIn("nearestFreeSpot", SCRIPT)

    def test_only_the_sort_button_moves_boxes_up(self):
        # The definition and the one call, from the «مرتب‌سازی» button.
        self.assertEqual(SCRIPT.count("compactUpward("), 2)
        self.assertIn('id="dashboard-edit-compact"', HOME)

    def test_changes_are_a_draft_until_saved(self):
        save = SCRIPT.split("    function save(body) {")[1].split("\n    }\n")[0]
        self.assertNotIn("apiRequest", save)
        self.assertIn("if (await flush()) setEditing(false);", SCRIPT)
        self.assertIn('id="dashboard-edit-done" hidden disabled>ذخیره<', HOME)

    def test_escape_and_cancel_discard_the_draft(self):
        self.assertIn('event.key === "Escape" && !document.querySelector("dialog[open]")) discard();', SCRIPT)
        self.assertIn('cancelButton.addEventListener("click", discard)', SCRIPT)

    def test_adding_a_widget_saves_the_draft_before_reloading(self):
        self.assertIn("if (addWidgetAdded) flush().then((ok) => { if (ok) window.location.reload(); });", SCRIPT)

    def test_a_phone_is_told_rather_than_given_a_broken_editor(self):
        self.assertIn('window.matchMedia("(max-width: 767.98px)")', SCRIPT)
        self.assertIn('id="dashboard-edit-narrow"', HOME)


class OneGridTests(SimpleTestCase):
    """2.40.19: tiles and insight boxes share one grid, so any box can sit in
    any row («تمامی ویجت ها باید بتوانند هرجا قرار بگیرند»)."""

    def test_the_tiles_move_into_the_insight_grid(self):
        self.assertIn('const tilesHost = document.getElementById("dashboard-capability-tiles");', SCRIPT)
        self.assertIn("grid.appendChild(tiles.get(key));", SCRIPT)
        self.assertIn('tilesHost.removeAttribute("data-dashboard-grid");', SCRIPT)

    def test_order_interleaves_tiles_and_insights(self):
        body = SCRIPT.split('const placed = new Set();\n    (layout.order || []).forEach((key) => {')[1].split("});")[0]
        self.assertIn("if (tiles.has(key)) {", body)
        self.assertIn("placeDashboardWidget(grid, widget);", body)

    def test_a_layout_from_two_grids_is_lifted_once(self):
        body = SCRIPT.split("function liftLegacyPositions(grid, tiles) {")[1].split("\n}\n")[0]
        self.assertIn("if (!overlapping) return;", body)
        self.assertIn("setBoxSpot(column, spot.x, spot.y + below - top);", body)
