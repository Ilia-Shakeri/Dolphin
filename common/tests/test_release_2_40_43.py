"""The rest of the kit slimming, and the polled endpoints (2.40.43).

ApexCharts became its own file, fetched the first time a chart is drawn; jQuery
left the vendor bundle; the served kit files are built from `ui_kit/` (see
`test_ui_kit_build`). And from the server's own request log: the polled
reminder badge built every group in full to read one number, and the
dashboard's figures took four round trips where one does.
"""

from decimal import Decimal
from pathlib import Path

from django.db import connection
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext

from common import dashboard, reminders
from common.tests.test_dashboard_insights import DashboardFixtures

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "common" / "static" / "common" / "js"
UI = ROOT / "common" / "static" / "common" / "ui"


def queries_on(captured, table):
    return [query["sql"] for query in captured if f'FROM "{table}"' in query["sql"]]


class ChartsOnDemandTests(SimpleTestCase):
    CHARTS = (JS / "ui" / "charts.js").read_text(encoding="utf-8")

    def test_every_chart_is_drawn_through_one_place(self):
        """`drawApex` waits for the library; a direct `new ApexCharts` would
        throw on a page that has not fetched it yet."""
        script = "\n".join(path.read_text(encoding="utf-8") for path in JS.rglob("*.js"))
        self.assertEqual(script.count("new ApexCharts("), 1)
        self.assertIn("const instance = new ApexCharts(host, options);", self.CHARTS)

    def test_the_library_is_fetched_once_from_the_address_the_page_gives(self):
        self.assertIn('document.querySelector(\'meta[name="dolphin-charts"]\')?.content', self.CHARTS)
        self.assertIn("if (!apexLoading) {", self.CHARTS)
        self.assertIn("if (window.ApexCharts) return Promise.resolve(window.ApexCharts);", self.CHARTS)

    def test_only_the_latest_draw_waits_and_an_emptied_chart_is_not_drawn(self):
        self.assertIn("if (waitingDraws.get(host) !== draw) return;", self.CHARTS)
        empty = self.CHARTS.split("export function showEmptyChart(chart, empty) {")[1].split("\n}\n")[0]
        self.assertIn("waitingDraws.delete(chart);", empty)

    def test_the_vendor_bundle_left_jquery_behind(self):
        bundle = (UI / "js" / "dolphin-plugins.js").read_text(encoding="utf-8")
        self.assertNotIn("jQuery JavaScript Library", bundle)
        # The theme only ever reached for it behind guards for plugins it no
        # longer has; those guards are what keep it working without.
        theme = (UI / "js" / "dolphin-theme.js").read_text(encoding="utf-8")
        self.assertEqual(theme.count("if (typeof jQuery == 'undefined') {"), 2)


class PolledEndpointTests(DashboardFixtures):
    SOURCE_TABLES = ("sales_lead", "sales_targetaudiencemember", "tasks_task", "aftersales_aftersalesrequest",
                     "billing_cheque", "billing_installment")

    def test_the_reminder_badge_counts_and_builds_no_rows(self):
        with CaptureQueriesContext(connection) as captured:
            count = reminders.reminder_count_for(self.manager)
        rows = [sql for table in self.SOURCE_TABLES for sql in queries_on(captured, table) if "COUNT(" not in sql]
        self.assertEqual(rows, [])
        self.assertEqual(count, reminders.reminders_for(self.manager)["count"])

    def test_this_month_and_last_are_one_query(self):
        self._an_issued_invoice()
        with CaptureQueriesContext(connection) as captured:
            amount, count = dashboard._sales_kpis(self.manager, now=self.now, unit="rial")
        # One `exists()` choosing the source, one aggregate for both months.
        self.assertEqual(len(queries_on(captured, "billing_invoice")), 2)
        self.assertEqual(count["display"], "۱")
        self.assertNotEqual(amount["display"], "۰ ریال")

    def test_what_is_owed_is_one_query_and_the_same_sum(self):
        invoice = self._an_issued_invoice()
        with CaptureQueriesContext(connection) as captured:
            [kpi] = dashboard._receivables_kpi(self.manager, now=self.now, unit="rial")
        self.assertEqual(len(queries_on(captured, "billing_invoice")), 1)
        from billing.models import Invoice

        expected = sum((row.balance_due for row in Invoice.objects.filter(status="issued")), Decimal("0"))
        self.assertEqual(expected, invoice.total_amount)
        self.assertEqual(kpi["full_display"], dashboard.formatting.money(expected, "rial"))
        self.assertIn("۱ فاکتور", kpi["hint"])

    def test_after_sales_and_call_figures_are_one_query_each(self):
        with CaptureQueriesContext(connection) as captured:
            dashboard._after_sales_kpis(self.manager, now=self.now)
        self.assertEqual(len(queries_on(captured, "aftersales_aftersalesrequest")), 1)
        with CaptureQueriesContext(connection) as captured:
            dashboard._call_kpi(self.manager, now=self.now)
        self.assertEqual(len(queries_on(captured, "sales_interaction")), 1)
