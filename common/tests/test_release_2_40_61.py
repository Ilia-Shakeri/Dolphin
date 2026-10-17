"""2.40.61 — after-sales deadline warnings, escalation and the survey (BIZ-008, part two).

Product owner, 2026-10-17: a deadline near or passed is shown in the panel to
the assignee, and to the manager when needed; texts and automatic escalation
of overdue cases to the manager can be turned on; after a case closes, a
satisfaction survey text in the company's own words can be sent.
"""

from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from aftersales import alerts, workflow
from aftersales.models import AfterSalesHistory, AfterSalesRequest, SlaAlert
from aftersales.services import create_after_sales_request
from common.reminders import reminder_count_for, reminders_for
from sales.services import create_customer_with_phone

PASSWORD = "Strong-pass-961!"


def sent_message(*args, **kwargs):
    status = "sent"
    return SimpleNamespace(status=status, Status=SimpleNamespace(SENT="sent"))


class Base(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="al.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(
            username="al.manager", password=PASSWORD, role=User.Role.SALES_MANAGER, phone="09121110611",
        )
        self.operator = User.objects.create_user(
            username="al.operator", password=PASSWORD, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES, phone="09121110612",
        )
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری هشدار", phone={"raw_phone": "09121110610", "is_primary": True},
        )

    def case(self, **deadlines):
        case = create_after_sales_request(
            actor=self.manager, customer=self.customer, subject="خرابی دستگاه", description="شرح",
            assigned_to=self.operator,
        )
        created = timezone.now() - timedelta(hours=10)
        AfterSalesRequest.objects.filter(pk=case.pk).update(created_at=created, **deadlines)
        case.refresh_from_db()
        return case


class WarningTests(Base):
    def test_near_at_four_fifths_and_past_at_the_deadline(self):
        now = timezone.now()
        near = self.case(response_due=now + timedelta(hours=1), resolution_due=now + timedelta(days=5))
        past = self.case(response_due=now - timedelta(minutes=5), resolution_due=now + timedelta(days=5))
        early = self.case(response_due=now + timedelta(hours=20), resolution_due=now + timedelta(days=5))
        self.assertEqual([(kind, level) for kind, level, _ in alerts.warnings_for(near, now)], [("response", "approaching")])
        self.assertEqual([(kind, level) for kind, level, _ in alerts.warnings_for(past, now)], [("response", "breached")])
        self.assertEqual(alerts.warnings_for(early, now), [])
        workflow.set_stage(actor=self.operator, request=past, to_stage="reviewing")
        past.refresh_from_db()
        self.assertEqual(alerts.warnings_for(past, now), [])

    def test_the_bell_shows_the_assignee_near_and_past_and_the_manager_past_only(self):
        now = timezone.now()
        self.case(response_due=now + timedelta(hours=1), resolution_due=now + timedelta(days=5))
        late = self.case(response_due=now - timedelta(minutes=5), resolution_due=now + timedelta(days=5))
        self.assertEqual(reminder_count_for(self.operator), 2)
        groups = {group["kind"]: group for group in reminders_for(self.manager)["groups"]}
        self.assertEqual([item["id"] for item in groups["after_sales_deadline"]["items"]], [late.pk])
        self.assertTrue(groups["after_sales_deadline"]["items"][0]["overdue"])


class CheckTests(Base):
    def test_each_warning_once_texts_off_by_default_and_escalation_when_on(self):
        now = timezone.now()
        late = self.case(response_due=now - timedelta(minutes=5), resolution_due=now + timedelta(days=5))
        first = alerts.check_deadlines(now=now)
        self.assertEqual((first["alerts"], first["texts"], first["escalated"]), (1, 0, 0))
        self.assertEqual(alerts.check_deadlines(now=now)["alerts"], 0)
        alerts.update_settings(actor=self.admin, escalate_overdue=True)
        SlaAlert.objects.all().delete()
        counts = alerts.check_deadlines(now=now)
        self.assertEqual(counts["escalated"], 1)
        late.refresh_from_db()
        self.assertIsNotNone(late.escalated_at)
        escalation = late.history.get(event=AfterSalesHistory.Event.ESCALATED)
        self.assertIsNone(escalation.actor)
        SlaAlert.objects.all().delete()
        self.assertEqual(alerts.check_deadlines(now=now)["escalated"], 0)

    def test_texts_go_to_the_assignee_and_past_a_deadline_to_the_managers(self):
        now = timezone.now()
        self.case(response_due=now - timedelta(minutes=5), resolution_due=now + timedelta(days=5))
        alerts.update_settings(actor=self.admin, sms_alerts=True)
        with mock.patch("aftersales.alerts.sms_available", return_value=True), \
                mock.patch("communications.services.send_system_sms", side_effect=sent_message) as send:
            counts = alerts.check_deadlines(now=now)
        phones = sorted(call.kwargs["phone"] for call in send.call_args_list)
        self.assertEqual(phones, ["+989121110611", "+989121110612"])
        self.assertEqual(counts["texts"], 2)

    def test_the_command(self):
        out = StringIO()
        call_command("check_after_sales_deadlines", stdout=out)
        self.assertIn("after-sales deadlines:", out.getvalue())


class SurveyTests(Base):
    def test_closing_sends_the_survey_in_the_companys_words(self):
        alerts.update_settings(actor=self.admin, survey_sms=True, survey_text="{نام} عزیز، پروندهٔ {پرونده} بسته شد؛ از ۱ تا ۵؟")
        case = self.case()
        with mock.patch("aftersales.alerts.sms_available", return_value=True), \
                mock.patch("communications.services.send_system_sms", side_effect=sent_message) as send, \
                self.captureOnCommitCallbacks(execute=True):
            workflow.close(actor=self.manager, request=case, final_result="resolved")
        self.assertEqual(send.call_args.kwargs["body"], f"مشتری هشدار عزیز، پروندهٔ #{case.pk} بسته شد؛ از ۱ تا ۵؟")
        self.assertTrue(case.history.filter(event=AfterSalesHistory.Event.SURVEY_SENT).exists())

    def test_no_survey_when_off_or_without_sms(self):
        case = self.case()
        with mock.patch("communications.services.send_system_sms") as send, self.captureOnCommitCallbacks(execute=True):
            workflow.close(actor=self.manager, request=case, final_result="resolved")
        send.assert_not_called()


class SettingsTests(Base):
    def test_the_settings_api(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        answer = client.patch("/api/v1/after-sales-settings/alerts/", {"sms_alerts": True, "survey_text": "  "}, format="json")
        self.assertEqual(answer.status_code, 400)
        answer = client.patch("/api/v1/after-sales-settings/alerts/", {"escalate_overdue": True}, format="json")
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertTrue(answer.json()["escalate_overdue"])
        self.assertFalse(answer.json()["sms_available"])
        manager = APIClient()
        manager.force_authenticate(self.manager)
        self.assertEqual(manager.get("/api/v1/after-sales-settings/alerts/").status_code, 403)
        self.client.force_login(self.admin)
        self.assertIn('id="case-alerts-form"', self.client.get("/settings/?tab=after-sales").content.decode())
