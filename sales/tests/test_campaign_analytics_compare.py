"""Campaign analysis compares the chosen campaigns side by side (2.40.23)."""

from datetime import timedelta
from pathlib import Path

from django.test import SimpleTestCase
from django.utils import timezone

from sales.campaigns import create_campaign
from sales.tests import test_campaigns as base

ROOT = Path(__file__).resolve().parents[2]


class ComparisonTests(base.Fixtures):
    def test_the_chosen_campaigns_come_side_by_side(self):
        other = create_campaign(actor=self.manager, name="تابستان", responsibles=[self.agent])
        self.member("09121110001")
        self.member("09121110002")
        self.member("09121110003", campaign=other)
        client = self.client_for(self.manager)
        data = client.get(f"/api/v1/campaigns/analytics/?campaigns={self.campaign.pk},{other.pk}").json()
        compared = {row["name"]: row for row in data["comparison"]["campaigns"]}
        self.assertEqual(set(compared), {"نوروز", "تابستان"})
        self.assertEqual(compared["نوروز"]["members"], 2)
        self.assertEqual(compared["تابستان"]["members"], 1)
        months = data["comparison"]["months"]
        self.assertTrue(all(len(row["invoices_by_month"]) == len(months) for row in compared.values()))

    def test_the_range_controls_window_is_accepted(self):
        now = timezone.now()
        client = self.client_for(self.manager)
        response = client.get("/api/v1/campaigns/analytics/", {
            "period_start": (now - timedelta(days=30)).isoformat(), "period_end": now.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        response = client.get("/api/v1/campaigns/analytics/", {"period_start": "2026-01-01T00:00:00"})
        self.assertEqual(response.status_code, 400)


class PageTests(SimpleTestCase):
    def test_the_page_is_a_step_by_step_report(self):
        template = (ROOT / "common" / "templates" / "common" / "campaigns" / "analytics.html").read_text(encoding="utf-8")
        for title in ("کمپین‌ها", "بازهٔ زمانی", "چه چیزی را ببینیم", "نتیجه"):
            self.assertIn(f'<h3 class="stepper-title">{title}</h3>', template)
        self.assertIn('data-report-panel="compare"', template)
        script = (ROOT / "common" / "static" / "common" / "js" / "features" / "campaigns" / "campaign-analytics.js").read_text(encoding="utf-8")
        self.assertIn('prefix: "campaign-analytics"', script)
        self.assertIn("renderGroupedBarChart(", script)

    def test_results_are_shown_before_charts_mount(self):
        driver = (ROOT / "common" / "static" / "common" / "js" / "ui" / "report-wizard.js").read_text(encoding="utf-8")
        body = driver.split("async function build() {")[1].split("\n    }\n")[0]
        self.assertLess(body.index("show(content);"), body.index("render(report);"))
