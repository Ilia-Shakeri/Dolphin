"""The whole panel live (2.40.34).

Product owner, 2026-10-07: «کل پنل (مخصوصاً داشبورد) باید لایو باشد و اگر
تغییراتی اعمال شد در لحظه بدون رفرش اعمال شود» and «نوتیفیکیشن پیام‌های
جدید به‌صورت پاپ‌آپ در پایین سمت چپ صفحه نشان داده شود».
"""

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase

from accounts.models import User
from common import realtime_signals

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "common" / "static" / "common" / "js"


class SignalTests(TestCase):
    def test_the_rest_of_the_panel_announces_itself(self):
        for label in ("sales.SalesDocument", "sales.Product", "billing.Quotation", "billing.Cheque",
                      "tasks.Task", "communications.InboundSMS", "accounts.User"):
            with self.subTest(label=label):
                self.assertIn(label, realtime_signals.LIST_KINDS)

    def test_a_sign_in_is_not_announced(self):
        user = User.objects.create_user(username="lp.user", password="Strong-pass-274!", role=User.Role.SALES_AGENT)
        with mock.patch("common.realtime_signals.realtime.publish") as publish:
            user.save(update_fields=["last_login"])
            publish.assert_not_called()
            user.first_name = "تازه"
            user.save(update_fields=["first_name"])
            publish.assert_called_once_with("user", object_id=user.pk)


class PageTests(SimpleTestCase):
    def read(self, name):
        return (JS / name).read_text(encoding="utf-8")

    def test_the_dashboard_redraws_in_place(self):
        dashboard = self.read("features/dashboard/dashboard.js")
        self.assertIn("onRealtime(ALL_BUSINESS_KINDS, refreshDashboard", dashboard)
        self.assertIn("current.column.replaceChildren(...column.children)", dashboard)
        self.assertIn('document.body.classList.contains("dashboard-editing")', dashboard)

    def test_boards_calendars_charts_and_reports_follow(self):
        for name, needle in (
            ("features/leads/lead-board.js", 'onRealtime(["lead"]'),
            ("features/billing/order-board.js", 'onRealtime(["order"]'),
            ("ui/calendar.js", "onRealtime(liveKinds, () => calendar.refetchEvents())"),
            ("ui/list-charts.js", "onRealtime(kinds, () => load()"),
            ("features/billing/profit-report.js", "onRealtime("),
        ):
            with self.subTest(module=name):
                self.assertIn(needle, self.read(name))

    def test_a_record_page_follows_its_record_but_not_its_own_saves(self):
        page = self.read("shell/live-page.js")
        self.assertIn("Date.now() - lastWriteAt() < OWN_ECHO_MS", page)
        self.assertIn('detail.kind === "resync"', page)
        self.assertIn("lastWrite = Date.now();", self.read("core/api.js"))

    def test_without_a_stream_the_panel_still_rereads(self):
        self.assertIn("FALLBACK_RESYNC_MS", self.read("shell/realtime.js"))

    def test_new_messages_show_bottom_left_and_open_their_conversation(self):
        toast = self.read("shell/chat-toast.js")
        self.assertIn('onRealtime(["chat"], read', toast)
        self.assertIn("dolphin:chat-open-thread", toast)
        self.assertIn("document.body.dataset.chatOpenThread", toast)
        css = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")
        block = css[css.index(".chat-toasts {"):]
        self.assertIn("left: 1.25rem;", block[:200])
        self.assertIn("bottom: 1.25rem;", block[:200])
        self.assertIn('document.addEventListener("dolphin:chat-open-thread"', self.read("shell/chat.js"))


class MonthGridTests(SimpleTestCase):
    """2.40.35: «تقویم‌ها در حالت ماهانه در بعضی از ماه‌های آینده خراب می‌شود».
    A day grid is broken into week rows only over whole weeks; a bare 29–31
    day range not starting on Saturday drew as one row of thirty cells
    (measured: آبان، دی، بهمن و اسفند ۱۴۰۵). The range is widened to whole
    weeks and the days it adds are blank and empty."""

    def test_the_month_view_spans_whole_weeks(self):
        calendar = (JS / "ui" / "calendar.js").read_text(encoding="utf-8")
        self.assertIn("visibleRange: (current) => weekAligned(jalaliMonthRange(current))", calendar)
        self.assertIn("first.setDate(first.getDate() - ((first.getDay() + 1) % 7)); // back to Saturday", calendar)
        self.assertIn('["fc-day-disabled", "jalali-outside"]', calendar)
        self.assertIn("!isOutsideJalaliMonth(new Date(event.start), calendar.view)", calendar)
