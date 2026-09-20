"""Three more 2026-09-20 requests, on the report pages and the system log.

* **Report toolbars.** «فیلد جستجو و دکمه فیلتر باید سمت راست باشند… دکمه
  خروجی در خارج از فیلتر و در بالای صفحه قرار بگیرد». Four report pages wrapped
  their search and filter in a `.card-title` carrying the theme's own centring,
  so both controls sat in the middle of a 909px row instead of at the reading
  edge — measured, the search box started 391px in. The three export links also
  lived *inside* the filter form, so getting a spreadsheet meant opening a
  filter popover first.
* **The postal page was renamed** from «اسناد فروش داخلی» to «رهگیری پستی».
* **The system-events page got a date window.** It is read when something went
  wrong at a known time, and without one the only way to reach a day was to
  page back through everything since.

The date filter is worth more than a template check, so it also gets a real
one: `filter_by_date_window` is now shared by this page and the customers page,
and the point of sharing it is that the two cannot drift about what "to this
day" includes. `sales/tests/test_list_filters.py` covers the customer half;
this covers the audit half against a real database.
"""

import pathlib

from django.test import SimpleTestCase


ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "common" / "templates" / "common"
SCRIPT = (ROOT / "common" / "static" / "common" / "dolphin-app.js").read_text(encoding="utf-8")

#: The report pages that carry a search box and a filter popover.
REPORT_PAGES = sorted(
    p for p in (TEMPLATES / "reports").glob("*.html")
    if "list-filters" in p.read_text(encoding="utf-8")
)


def _read(path):
    return path.read_text(encoding="utf-8")


class ReportToolbarTests(SimpleTestCase):
    def test_there_are_report_pages_to_check(self):
        """Restated 2026-09-20: two of the six lost their filter form when
        they were rebuilt as step-by-step wizards in 3.0.0 («فیلتر جدا
        نداشته باشند»), so this set is four. It is still worth asserting a
        floor — the tests below say nothing at all if the glob quietly
        matches nothing."""
        self.assertGreaterEqual(len(REPORT_PAGES), 4)

    def test_the_two_rebuilt_reports_are_deliberately_outside_this_set(self):
        """Their toolbar is the wizard's own result step, and the rules
        below are about a filter popover they no longer have."""
        names = {path.name for path in REPORT_PAGES}
        self.assertNotIn("sales_documents.html", names)
        self.assertNotIn("inbound_sms.html", names)

    def test_no_report_header_is_centred_any_more(self):
        """The class soup that carried the centring, gone from all four that
        had it. A centred header puts the search box in the middle of the
        card instead of at the edge a Persian reader starts from."""
        for path in REPORT_PAGES:
            with self.subTest(page=path.name):
                self.assertNotIn(
                    "card-title flex-column flex-md-row align-items-stretch"
                    " align-items-md-center gap-3 w-100 m-0",
                    _read(path),
                )

    def test_every_report_toolbar_starts_at_the_reading_edge(self):
        for path in REPORT_PAGES:
            text = _read(path)
            if 'class="card-title' not in text:
                # The other shape these pages use is a plain `d-flex` row,
                # which already starts at the inline-start edge.
                continue
            with self.subTest(page=path.name):
                self.assertIn("justify-content-start", text)

    def test_the_search_box_comes_before_the_filter(self):
        """DOM order is visual order in this RTL panel: the first child sits
        rightmost, so the search box has to be declared first.

        Matched on the class attributes, not on the bare names — every one of
        these files also mentions `form.list-filters` in a comment above the
        markup, which is not what is being ordered here.
        """
        for path in REPORT_PAGES:
            text = _read(path)
            if 'class="list-search"' not in text:
                continue
            with self.subTest(page=path.name):
                self.assertLess(
                    text.index('class="list-search"'),
                    text.index('class="list-filters"'),
                )

    def test_no_export_link_is_trapped_inside_a_filter_form(self):
        """Getting a spreadsheet should not require opening a filter first."""
        for path in REPORT_PAGES:
            text = _read(path)
            if "-export" not in text:
                continue
            with self.subTest(page=path.name):
                form = text.split('class="list-filters"')[1].split("</form>")[0]
                self.assertNotIn("-export", form)

    def test_every_export_link_now_sits_in_the_page_toolbar(self):
        exports = [p for p in REPORT_PAGES if "-export" in _read(p)]
        self.assertGreaterEqual(len(exports), 3)
        for path in exports:
            with self.subTest(page=path.name):
                text = _read(path)
                actions = text.split("{% block page_actions %}")[1].split("{% endblock %}")[0]
                self.assertIn("-export", actions)


class PostalTrackingRenameTests(SimpleTestCase):
    def test_the_old_name_is_gone_from_the_product(self):
        stale = []
        for path in ROOT.rglob("*.html"):
            if "node_modules" in path.parts or "assets" in path.parts:
                continue
            if "اسناد فروش داخلی" in path.read_text(encoding="utf-8", errors="ignore"):
                stale.append(path.name)
        self.assertEqual(stale, [])

    def test_the_page_and_its_menu_entry_carry_the_new_name(self):
        self.assertIn("رهگیری پستی", _read(TEMPLATES / "sales_documents" / "list.html"))
        self.assertIn("رهگیری پستی", _read(TEMPLATES / "base.html"))

    def test_the_module_permission_label_was_renamed_with_it(self):
        """Otherwise the permissions screen would still offer the page under
        its old name while the sidebar used the new one."""
        source = (ROOT / "accounts" / "module_permissions.py").read_text(encoding="utf-8")
        self.assertIn("رهگیری پستی", source)
        self.assertNotIn("اسناد فروش داخلی", source)


class ActivityLogFilterMarkupTests(SimpleTestCase):
    def test_the_page_offers_a_date_window(self):
        text = _read(TEMPLATES / "activity_logs" / "list.html")
        self.assertIn('id="activity-log-from"', text)
        self.assertIn('id="activity-log-to"', text)
        self.assertIn('name="created_from"', text)
        self.assertIn('name="created_to"', text)

    def test_both_boxes_use_the_products_own_jalali_picker(self):
        text = _read(TEMPLATES / "activity_logs" / "list.html")
        self.assertEqual(text.count('data-jalali="date"'), 2)

    def test_the_bounds_are_sent_as_the_api_stores_them(self):
        start = SCRIPT.index("function setupActivityLogs(")
        body = SCRIPT[start:SCRIPT.index("\n    async function ", start)]
        self.assertIn('apiDate(document.getElementById("activity-log-from").value)', body)
        self.assertIn('query.set("created_from", from)', body)
        self.assertIn('query.set("created_to", to)', body)

    def test_an_untouched_filter_sends_nothing(self):
        start = SCRIPT.index("function setupActivityLogs(")
        body = SCRIPT[start:SCRIPT.index("\n    async function ", start)]
        self.assertIn("if (from) query.set", body)
        self.assertIn("if (to) query.set", body)
