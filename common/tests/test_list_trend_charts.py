"""The direction chart beside each list page's composition chart.

Product-owner request 2026-09-19: «همه صفحه هایی که جدول و نمودار دایره ای
دارند، باید یک نمودار مدرن و جذاب خطی یا لوله ای نیز کنار ان داشته باشند تا به
یوزر حس انالیز و تحلیل بهتری بدهد». A ring says what a total is made of; it
never says which way that total is going, and the second question is the one a
person opens a list page asking.

What is worth pinning here, in order of what would actually break:

* **The two charts must share a scope.** They come from one request and one
  actor, but each is built by its own function, and a trend wired to a model
  manager instead of that module's selector would show rows the table beside it
  refuses to list. The date column each trend reads is checked against the real
  model too — a name that does not exist is a 500 nobody sees until they open
  that one page.
* **The markup is one include, not eleven copies.** It was eleven copies of an
  identical block before this change; the eleventh would have been the one
  nobody updated.
* **A key with no trend renders one chart, not one chart and a gap.**
"""

import pathlib
import re

from django.apps import apps
from django.test import SimpleTestCase, TestCase

from reports.list_charts import LIST_CHARTS, LIST_TRENDS, TREND_WEEKS


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "common" / "static" / "common" / "dolphin-app.js").read_text(encoding="utf-8")
TEMPLATES = ROOT / "common" / "templates" / "common"
INCLUDE = (TEMPLATES / "includes" / "list_charts.inc").read_text(encoding="utf-8")

#: Which model each trend's selector returns, so the dated column it reads can
#: be checked to exist. Named here rather than inferred from the selector,
#: because the point of the check is to catch the two drifting apart.
TREND_MODELS = {
    "invoices": ("billing", "Invoice"),
    "orders": ("billing", "Order"),
    "payments": ("billing", "Payment"),
    "payments-direction": ("billing", "Payment"),
    "products": ("sales", "Product"),
    "product-categories": ("sales", "ProductCategory"),
    "leads": ("sales", "Lead"),
    "after-sales": ("aftersales", "AfterSalesRequest"),
    "sales-documents": ("sales", "SalesDocument"),
    "inventory": ("inventory", "StockMovement"),
    "sales": ("sales", "Sale"),
    "interactions": ("sales", "Interaction"),
}


def _function_body(name):
    start = SCRIPT.index(f"function {name}(")
    following = SCRIPT.find("\n    function ", start + 1)
    return SCRIPT[start:following if following != -1 else len(SCRIPT)]


def _pages_with_a_list_chart():
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r'{% include "common/includes/list_charts\.inc" with chart_key="([a-z-]+)" %}', text)
        if match:
            yield path.relative_to(TEMPLATES).as_posix(), match.group(1), text


class TrendRegistryTests(SimpleTestCase):
    def test_every_dated_column_a_trend_reads_exists_on_its_model(self):
        for key, (_selector, field, _title) in LIST_TRENDS.items():
            with self.subTest(trend=key):
                app_label, model_name = TREND_MODELS[key]
                model = apps.get_model(app_label, model_name)
                # Raises FieldDoesNotExist if the column was renamed.
                model._meta.get_field(field)

    def test_each_trend_names_the_window_it_actually_covers(self):
        """A title that says one thing while the query does another is worse
        than no title.

        Restated 2026-09-20. The window used to be written into the title
        («… در دوازده هفتهٔ اخیر») because it was always twelve weeks. It is
        the reader's choice now, so a fixed string in the registry would be
        exactly the lie this test exists to prevent: the registry holds the
        *subject* and `trend_for` appends the window it actually drew. Both
        halves are checked — no registry title may name a window, and a real
        trend's title must name the one it covered."""
        self.assertEqual(TREND_WEEKS, 12)
        for key, (_selector, _field, title) in LIST_TRENDS.items():
            with self.subTest(trend=key):
                self.assertTrue(title.startswith("روند"))
                self.assertNotIn("اخیر", title)
                self.assertNotIn("هفته", title)

    def test_every_chart_key_that_has_a_trend_is_a_real_chart_key(self):
        """A trend for a key no chart declares would never be requested."""
        self.assertLessEqual(set(LIST_TRENDS), set(LIST_CHARTS))

    def test_the_inventory_trend_deliberately_reads_movements_not_balances(self):
        """`stock_items_for` rows are per product-and-warehouse balances whose
        `created_at` says when a balance row first appeared — not a fact
        anybody wants plotted. The movements behind them are."""
        selector, field, _title = LIST_TRENDS["inventory"]
        self.assertEqual(selector.__name__, "stock_movements_for")
        self.assertEqual(field, "occurred_at")

    def test_every_trend_starts_from_a_module_selector(self):
        """The whole scope guarantee. A trend built off `Model.objects` would
        count rows its own page refuses to list."""
        for key, (selector, _field, _title) in LIST_TRENDS.items():
            with self.subTest(trend=key):
                self.assertTrue(
                    selector.__name__.endswith("_for"),
                    f"{key} is built from {selector.__name__}, not a selector",
                )


class ListChartMarkupTests(SimpleTestCase):
    def test_eleven_list_pages_share_one_include(self):
        pages = list(_pages_with_a_list_chart())
        self.assertGreaterEqual(len(pages), 11)

    def test_no_page_still_carries_its_own_copy_of_the_block(self):
        """It was eleven identical copies before this change."""
        for path in sorted(TEMPLATES.rglob("*.html")):
            if path.name == "list_charts.inc":
                continue
            with self.subTest(page=path.relative_to(TEMPLATES).as_posix()):
                self.assertNotIn('data-list-chart-canvas', path.read_text(encoding="utf-8"))

    def test_every_key_a_page_asks_for_is_declared(self):
        for page, key, _text in _pages_with_a_list_chart():
            with self.subTest(page=page):
                self.assertIn(key, LIST_CHARTS)

    def test_the_include_carries_both_charts_side_by_side(self):
        self.assertIn('data-list-chart-canvas', INCLUDE)
        self.assertIn('data-list-trend-canvas', INCLUDE)
        self.assertEqual(INCLUDE.count('class="col-xl-6"'), 2)

    def test_the_trend_column_starts_hidden(self):
        """A key with no trend must render one full chart, not a half-width
        chart beside an empty gap."""
        self.assertRegex(INCLUDE, r'data-list-trend hidden')


class TrendTitleTests(TestCase):
    """The window a title names, measured on real output rather than on
    the registry string — which no longer holds one."""

    def test_a_drawn_trend_names_the_window_it_was_drawn_over(self):
        from datetime import timedelta

        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from reports.list_charts import trend_for

        User = get_user_model()
        actor = User.objects.create_user(
            username="trend.title", password="Aa!23456pass", role=User.Role.SALES_MANAGER
        )
        now = timezone.now()
        cases = (
            (7, "در هفتهٔ گذشته"),
            (30, "در ۳۰ روز گذشته"),
            (365, "در یک سال گذشته"),
        )
        for days, expected in cases:
            with self.subTest(days=days):
                trend = trend_for(
                    "leads", actor,
                    now=now,
                    period_start=now - timedelta(days=days),
                    period_end=now,
                )
                self.assertEqual(trend["title"], f"روند ثبت سرنخ {expected}")

    def test_a_custom_window_is_spelled_out_rather_than_named(self):
        """No preset fits it, so the only honest title is the two dates."""
        from datetime import timedelta

        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from reports.list_charts import trend_for

        User = get_user_model()
        actor = User.objects.create_user(
            username="trend.custom", password="Aa!23456pass", role=User.Role.SALES_MANAGER
        )
        now = timezone.now()
        trend = trend_for(
            "leads", actor,
            now=now,
            period_start=now - timedelta(days=200),
            period_end=now - timedelta(days=40),
        )
        self.assertTrue(trend["title"].startswith("روند ثبت سرنخ از "))
        self.assertIn(" تا ", trend["title"])


class ListChartScriptTests(SimpleTestCase):
    def test_one_request_feeds_both_charts(self):
        """Restated 2026-09-20 only for the extra argument: the trend now
        also receives the shared range filter's reset button, so the card
        header's «حالت پیش‌فرض» can undo a zoom on it. Still one request."""
        body = _function_body("setupListCharts")
        self.assertEqual(body.count("/api/v1/reports/list-chart/"), 1)
        self.assertIn("renderListTrend(card, report.trend, range && range.resetHost)", body)

    def test_a_failed_request_takes_the_trend_column_with_it(self):
        """Otherwise a trend column left open beside a «در دسترس نیست» message
        reads as a second chart still loading."""
        body = _function_body("setupListCharts")
        self.assertIn("trendColumn.hidden = true", body)

    def test_the_trend_is_drawn_with_the_shared_area_chart(self):
        """The same smooth area the dashboard's own twelve-week trend uses —
        which already carries the zoom-reset control (2.5.9)."""
        body = _function_body("renderListTrend")
        self.assertIn("renderAreaChart(", body)

    def test_an_absent_trend_hides_its_column_instead_of_drawing_nothing(self):
        body = _function_body("renderListTrend")
        self.assertIn("if (!trend || !trend.points?.length)", body)
        self.assertIn("column.hidden = true", body)
