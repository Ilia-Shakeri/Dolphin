"""Dashboard, wizards, calendars, profile and Persian errors (2.40.35).

Product owner, 2026-10-07: company performance becomes a removable dashboard
widget that is off by default; the default dashboard is tidy and appears all
at once; single-figure widgets centre their number; wide widgets shrink to a
square; the lead wizard's «مسئول» offers only the campaign's responsibles;
«بعدی» is always on the left; the calendars swap their previous/next buttons;
every error is in Persian; the profile's password change and active sessions
open from its «بیشتر» menu.
"""

import socket
import urllib.error
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from rest_framework.exceptions import ErrorDetail
from rest_framework.test import APIClient

from accounts.models import User
from common.dashboard import dashboard_for
from common.dashboard_layout import (
    OPT_IN_WIDGETS, WIDGET_MIN_SIZES, effective_layout, reset_user_dashboard_layout, update_user_dashboard_layout,
)
from common.exceptions import BusinessRuleError
from common.persian_errors import http_answer, needs_persian, network_reason, persianise
from sales.campaigns import create_campaign
from sales.services import create_lead

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "common" / "static" / "common" / "js"
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")
PASSWORD = "Strong-pass-735!"


class PersianErrorTests(SimpleTestCase):
    def test_machine_worded_messages_are_replaced_by_their_code(self):
        payload = {
            "customer": [ErrorDetail("تایپ نامعتبر. باید pk ارسال می شد اما str ارسال شده است.", code="incorrect_type")],
            "due_date": [ErrorDetail("فرمت تاریخ اشتباه است. از یکی از این فرمت‌ها استفاده کنید: YYYY-MM-DD.", code="invalid")],
            "detail": ErrorDetail("No Attachment matches the given query.", code="not_found"),
        }
        cleaned = persianise(payload)
        self.assertEqual(cleaned["customer"][0], "نوع مقدار واردشده درست نیست.")
        self.assertIn("از تقویم", cleaned["due_date"][0])
        self.assertEqual(cleaned["detail"], "مورد خواسته‌شده پیدا نشد.")
        self.assertEqual(cleaned["detail"].code, "not_found")

    def test_a_business_message_keeps_its_own_words(self):
        for text in ("فایل xlsx معتبر نیست.", "فاکتور INV-12 قبلاً صادر شده است.", "مقدار معتبر نیست."):
            with self.subTest(text=text):
                self.assertFalse(needs_persian(text))

    def test_network_failures_are_named_in_persian(self):
        self.assertIn("رد کرد", network_reason(ConnectionRefusedError()))
        self.assertIn("زمان مقرر", network_reason(urllib.error.URLError(socket.timeout())))
        self.assertIn("پیدا نشد", network_reason(socket.gaierror()))
        self.assertEqual(http_answer(400, " bad "), "پاسخ سرور مقصد (کد 400): bad")


class PersianErrorApiTests(TestCase):
    def test_the_api_answers_in_persian(self):
        admin = User.objects.create_user(username="fa.errors", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        client = APIClient()
        client.force_login(admin)
        response = client.patch("/api/v1/dashboard/", {}, format="json")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["detail"], "این کار برای این بخش امکان‌پذیر نیست.")
        missing = client.get("/api/v1/attachments/999999/")
        self.assertEqual(missing.status_code, 404)
        self.assertNotRegex(missing.json()["detail"], "[A-Za-z]{3,}")


class PerformanceWidgetTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="perf.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)

    def test_it_is_off_by_default_and_on_once_added(self):
        self.assertIn("performance", OPT_IN_WIDGETS)
        self.assertIn("performance", effective_layout(self.manager)["hidden"])
        payload = dashboard_for(self.manager)
        self.assertIsNone(payload["performance"])
        self.assertIn("performance", {part["key"] for part in payload["hidden_available"]})

        update_user_dashboard_layout(actor=self.manager, shown_widgets=["performance"], hidden_widgets=["performance"])
        self.assertNotIn("performance", effective_layout(self.manager)["hidden"])
        self.assertEqual(dashboard_for(self.manager)["performance"]["title"], "عملکرد عملیاتی شرکت")

        update_user_dashboard_layout(actor=self.manager, shown_widgets=[])
        self.assertIn("performance", effective_layout(self.manager)["hidden"])

    def test_back_to_the_default_takes_it_off_again(self):
        update_user_dashboard_layout(actor=self.manager, shown_widgets=["performance"])
        reset_user_dashboard_layout(actor=self.manager)
        self.assertIn("performance", effective_layout(self.manager)["hidden"])

    def test_only_opt_in_keys_are_stored_as_shown(self):
        row = update_user_dashboard_layout(actor=self.manager, shown_widgets=["performance", "trend"])
        self.assertEqual(row.shown_widgets, ["performance"])

    def test_the_panel_is_a_widget_in_the_page_not_a_section_under_it(self):
        client = APIClient()
        client.force_login(self.manager)
        page = client.get("/").content.decode()
        self.assertIn('data-widget-key="performance" id="dashboard-performance-card" hidden', page)
        self.assertIn('class="dashboard-stage" id="dashboard-stage" data-booting', page)
        self.assertEqual(page.count('data-performance-panel="dashboard"'), 1)


class DashboardScriptTests(SimpleTestCase):
    SCRIPT = (JS / "features" / "dashboard" / "dashboard.js").read_text(encoding="utf-8")

    def test_every_box_is_revealed_at_once(self):
        self.assertIn("revealDashboard();", self.SCRIPT)
        self.assertIn(".dashboard-stage[data-booting] > :not(.dashboard-stage-loader)", CSS)
        # Shown by the stylesheet itself if the script never gets there.
        self.assertIn("animation: dashboard-stage-failsafe 0s linear 8s forwards;", CSS)

    def test_the_default_page_is_laid_out_in_shelves(self):
        self.assertIn("if (host.dataset.tidy && WIDE_GRID.matches) shelfLayout(host, rows);", self.SCRIPT)

    def test_wide_widgets_shrink_to_a_square(self):
        self.assertEqual(WIDGET_MIN_SIZES["trend"], "third")
        self.assertEqual(WIDGET_MIN_SIZES["agent_share"], "third")

    def test_a_single_figure_is_centred(self):
        block = CSS.split("[data-dashboard-grid] .dashboard-widget .kpi-card .dashboard-kpi-value {")[1].split("}")[0]
        self.assertIn("margin-block: auto;", block)
        self.assertIn("text-align: center;", block)


class LeadAssigneeTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="la.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.inside = User.objects.create_user(username="la.inside", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.outside = User.objects.create_user(username="la.outside", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.campaign = create_campaign(actor=self.manager, name="آزمون مسئول", responsibles=[self.inside])

    def test_a_manual_choice_is_one_of_the_campaigns_responsibles(self):
        self.assertEqual(create_lead(actor=self.manager, campaign=self.campaign, assignee=self.inside).assigned_to, self.inside)
        with self.assertRaises(BusinessRuleError):
            create_lead(actor=self.manager, campaign=self.campaign, assignee=self.outside)

    def test_the_wizard_lists_only_the_campaigns_responsibles(self):
        template = (ROOT / "common" / "templates" / "common" / "leads" / "list.html").read_text(encoding="utf-8")
        self.assertNotIn("create-lead-assignee-hint", template)
        self.assertIn('json_script:"create-lead-assignee-choices"', template)
        script = (JS / "features" / "leads" / "leads.js").read_text(encoding="utf-8")
        self.assertIn("assignable.filter(([pk]) => ids.has(String(pk)))", script)


class WizardAndCalendarTests(SimpleTestCase):
    def test_next_always_sits_at_the_inline_end(self):
        self.assertIn('.flex-stack:has(> [data-dolphin-stepper-action="previous"]) > :last-child {\n    margin-inline-start: auto;', CSS)

    def test_the_calendars_put_previous_on_the_right(self):
        script = (JS / "ui" / "calendar.js").read_text(encoding="utf-8")
        self.assertIn('start: "jalaliPrev,jalaliNext,prev,next today"', script)
        self.assertIn('jalaliPrev: {icon: "chevron-right"', script)
        self.assertIn('jalaliNext: {icon: "chevron-left"', script)


class ProfileMenuTests(TestCase):
    def test_password_and_sessions_open_dialogs_from_the_menu(self):
        admin = User.objects.create_user(username="pm.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        agent = User.objects.create_user(username="pm.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        client = APIClient()
        client.force_login(admin)
        page = client.get(f"/users/{agent.pk}/").content.decode()
        self.assertIn('data-profile-action="set-password"', page)
        self.assertIn('data-profile-action="sessions"', page)
        self.assertIn('<dialog id="set-password-dialog"', page)
        self.assertIn('<dialog id="user-sessions-dialog"', page)
