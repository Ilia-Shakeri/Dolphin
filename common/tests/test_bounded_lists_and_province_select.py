"""Three unrelated fixes from the same design review (2026-09-12), each
pinned by source pattern since none needs a browser or a database:

* the lead/order kanban columns show roughly five cards before scrolling
  internally, raised from four;
* the performance panel's own "جزئیات همان محدوده مجاز" table (shared by the
  dashboard and the standalone عملکرد report) is capped and scrollable the
  same way, so a company-wide scope with many users no longer pushes
  everything below it down the page;
* a customer's province is chosen from the same fixed list the choropleth
  map itself reads, not typed free-text — a typo or variant spelling used to
  mean a customer's own province never matched a region on the map, silently.
"""

import pathlib

from django.test import SimpleTestCase

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
CSS = (REPOSITORY_ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")
SCRIPT = (
    REPOSITORY_ROOT / "common" / "static" / "common" / "dolphin-app.js"
).read_text(encoding="utf-8")
TEMPLATES = REPOSITORY_ROOT / "common" / "templates" / "common"


def _function_body(name):
    start = SCRIPT.index(f"function {name}(")
    end = SCRIPT.index("\n    function ", start + 1)
    return SCRIPT[start:end]


def _css_rule(selector):
    start = CSS.index(selector)
    return CSS[start:CSS.index("}", start)]


class KanbanColumnHeightTests(SimpleTestCase):
    def test_the_column_height_was_raised_from_four_cards_to_five(self):
        rule = _css_rule("#lead-board .kanban-drag,\n#order-board .kanban-drag {")
        self.assertIn("max-height: 37.5rem;", rule)
        self.assertNotIn("max-height: 30rem;", rule)

    def test_the_column_still_scrolls_internally_rather_than_growing_the_page(self):
        rule = _css_rule("#lead-board .kanban-drag,\n#order-board .kanban-drag {")
        self.assertIn("padding-inline-end: 0.35rem;", rule)


class PerformanceScopeTableTests(SimpleTestCase):
    def test_the_scope_table_carries_the_bounded_scroll_class(self):
        content = (TEMPLATES / "includes" / "performance_panel.inc").read_text(encoding="utf-8")
        self.assertIn('class="table-responsive performance-scope-table-wrap hover-scroll-overlay-y"', content)

    def test_the_bounded_class_actually_caps_and_scrolls(self):
        rule = _css_rule(".performance-scope-table-wrap {")
        self.assertIn("max-height:", rule)
        self.assertIn("overflow-y: auto;", rule)


class ProvinceSelectTests(SimpleTestCase):
    """A typo-proof dropdown, not a second hand-typed list — see
    `fillProvinceSelect`'s own docstring in dolphin-app.js."""

    def test_fill_province_select_reads_the_same_source_the_map_uses(self):
        body = _function_body("fillProvinceSelect")
        self.assertIn("await loadIranMap()", body)
        self.assertIn("province.name", body)

    def test_an_unmatched_existing_value_is_kept_not_dropped(self):
        """Opening the edit form must never silently rewrite a customer's
        own stored record just because it predates this dropdown."""
        body = _function_body("fillProvinceSelect")
        self.assertIn("!names.includes(selectedValue)", body)
        self.assertIn("select.value = selectedValue", body)

    def test_both_customer_forms_use_a_select_not_free_text(self):
        for relative_path, field_id in (
            ("customers/list.html", "create-customer-province"),
            ("customers/detail.html", "edit-customer-province"),
        ):
            content = (TEMPLATES / relative_path).read_text(encoding="utf-8")
            with self.subTest(template=relative_path):
                self.assertIn(f'<select class="form-select form-select-solid" id="{field_id}"', content)
                self.assertNotIn(f'<input class="form-control form-control-solid" id="{field_id}"', content)

    def test_both_forms_are_actually_wired_to_fill_the_select(self):
        self.assertIn(
            'fillProvinceSelect(document.getElementById("create-customer-province"))', SCRIPT
        )
        self.assertIn(
            'fillProvinceSelect(document.getElementById("edit-customer-province"), value.province || "")',
            SCRIPT,
        )
