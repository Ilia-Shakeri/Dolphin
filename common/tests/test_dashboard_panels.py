"""The list and calendar dashboard widgets (`common.dashboard_panels`).

Real rows from each module's own selector, gated by feature and capability,
sized/ordered/hidden like every other widget.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from chat.services import get_or_create_direct_thread, send_message
from common import dashboard, dashboard_layout
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from tasks.models import Task

PASSWORD = "Strong-pass-471!"


def panel(payload, key):
    return next((item for item in payload["panels"] if item["key"] == key), None)


class DashboardPanelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="panel.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.other = User.objects.create_user(username="panel.other", password=PASSWORD, role=User.Role.SALES_AGENT)

    def test_tasks_panel_lists_only_my_open_tasks_soonest_first(self):
        now = timezone.now()
        Task.objects.create(title="دیر", assignee=self.admin, created_by=self.admin, due_at=now + timedelta(days=3))
        Task.objects.create(title="زود", assignee=self.admin, created_by=self.admin, due_at=now - timedelta(hours=1))
        Task.objects.create(title="بی‌موعد", assignee=self.admin, created_by=self.admin)
        Task.objects.create(
            title="انجام‌شده", assignee=self.admin, created_by=self.admin, status=Task.Status.DONE,
            completed_at=now,
        )
        Task.objects.create(title="دیگری", assignee=self.other, created_by=self.other)
        result = panel(dashboard.dashboard_for(self.admin), "panel_tasks")
        self.assertEqual([row["title"] for row in result["items"]], ["زود", "دیر", "بی‌موعد"])
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["items"][0]["badge"], "معوق")
        self.assertEqual(result["family"], "panel")
        self.assertEqual(result["size"], "col-12 col-sm-6 col-xl-4")

    def test_tasks_panel_is_empty_not_absent_for_a_reader_with_no_tasks(self):
        result = panel(dashboard.dashboard_for(self.admin), "panel_tasks")
        self.assertEqual(result["items"], [])
        self.assertTrue(result["empty"])

    def test_chat_panel_shows_unread_from_the_other_side(self):
        thread = get_or_create_direct_thread(actor=self.other, other_user_id=self.admin.pk)
        send_message(actor=self.other, thread_id=thread["id"] if isinstance(thread, dict) else thread.pk, body="سلام")
        result = panel(dashboard.dashboard_for(self.admin), "panel_chat")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["meta"], "سلام")
        self.assertEqual(result["items"][0]["badge"], "۱")
        mine = panel(dashboard.dashboard_for(self.other), "panel_chat")
        self.assertEqual(mine["count"], 0)
        self.assertIsNone(mine["items"][0]["badge"])

    def test_calendar_marks_days_with_open_tasks_this_month(self):
        now = timezone.now()
        Task.objects.create(title="امروز", assignee=self.admin, created_by=self.admin, due_at=now)
        calendar = panel(dashboard.dashboard_for(self.admin), "panel_calendar")
        self.assertIn(calendar["today"], calendar["marked"])
        self.assertTrue(28 <= calendar["days_in_month"] <= 31)
        self.assertTrue(0 <= calendar["offset"] <= 6)

    def test_agenda_carries_todays_jalali_date(self):
        agenda = panel(dashboard.dashboard_for(self.admin), "panel_agenda")
        self.assertIn(agenda["weekday"], ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"))
        self.assertTrue(agenda["month_name"])

    def test_disabled_features_leave_no_panel(self):
        profile = DeploymentProfile(
            profile_id="client-1",
            features=frozenset(ALL_FEATURES) - frozenset({"tasks", "internal_chat", "telephony", "reminders"}),
            source="signed-manifest",
        )
        with override_active_profile(profile):
            self.assertEqual(dashboard.dashboard_for(self.admin)["panels"], [])

    def test_hidden_panel_leaves_the_grid_but_stays_addable(self):
        dashboard_layout.update_user_dashboard_layout(actor=self.admin, hidden_widgets=["panel_tasks"])
        payload = dashboard.dashboard_for(self.admin)
        self.assertIsNone(panel(payload, "panel_tasks"))
        offered = [row for row in payload["hidden_available"] if row["key"] == "panel_tasks"]
        self.assertEqual(len(offered), 1)
        self.assertEqual(offered[0]["family"], "panel")

    def test_panels_can_be_resized_and_reordered(self):
        dashboard_layout.update_user_dashboard_layout(
            actor=self.admin,
            widget_sizes={"panel_chat": "half"},
            widget_order=["panel_calendar", "panel_chat"],
        )
        payload = dashboard.dashboard_for(self.admin)
        self.assertEqual(panel(payload, "panel_chat")["size"], "col-12 col-xl-6")
        keys = [row["key"] for row in payload["panels"]]
        self.assertLess(keys.index("panel_calendar"), keys.index("panel_chat"))
