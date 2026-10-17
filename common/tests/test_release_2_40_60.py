"""2.40.60 — after-sales stages, types, priorities and deadlines (BIZ-008, part one).

Product owner, 2026-10-17: seven default stages; a separate final result for a
closed case; reopening with a reason and history; seven types, each with its
own stages, priority and deadlines when wanted; normal / urgent / critical
with default first-response and resolution deadlines (critical: a handling
plan, resolution by type), set per company and counted in working time without
official holidays; older cases mapped to the nearest stage keeping their status
and history.
"""

import importlib
from datetime import date, datetime, timedelta

from django.apps import apps as django_apps
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from aftersales import workflow
from aftersales.models import AfterSalesHistory, AfterSalesRequest, CaseStage, CaseType, Holiday, SlaPolicy
from aftersales.services import close_after_sales_request, create_after_sales_request, transition_after_sales_status
from aftersales.sla import WorkingTime
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from sales.services import create_customer_with_phone

PASSWORD = "Strong-pass-960!"


def tehran(*args):
    return timezone.make_aware(datetime(*args), timezone.get_current_timezone())


class WorkingTimeTests(TestCase):
    """The default week: Saturday–Wednesday 08:00–16:00, Thursday 08:00–13:00, Friday closed.
    2026-10-17 is a Saturday."""

    def test_hours_carry_over_closing_time_and_the_weekend(self):
        clock = WorkingTime()
        self.assertEqual(clock.add_hours(tehran(2026, 10, 17, 10, 0), 4), tehran(2026, 10, 17, 14, 0))
        self.assertEqual(clock.add_hours(tehran(2026, 10, 17, 15, 0), 4), tehran(2026, 10, 18, 11, 0))
        # Thursday 12:00 + 4h: one hour on Thursday, Friday closed, three on Saturday.
        self.assertEqual(clock.add_hours(tehran(2026, 10, 22, 12, 0), 4), tehran(2026, 10, 24, 11, 0))
        # Filed at night: the clock starts at the next opening.
        self.assertEqual(clock.add_hours(tehran(2026, 10, 17, 20, 0), 1), tehran(2026, 10, 18, 9, 0))

    def test_days_are_the_same_working_moment_later(self):
        clock = WorkingTime()
        self.assertEqual(clock.add_days(tehran(2026, 10, 17, 10, 0), 1), tehran(2026, 10, 18, 10, 0))
        # Wednesday 10:00 + 2 days: Thursday, then Saturday (Friday closed).
        self.assertEqual(clock.add_days(tehran(2026, 10, 21, 10, 0), 2), tehran(2026, 10, 24, 10, 0))
        # Wednesday 15:00 + 1 day lands on Thursday, which closes at 13:00.
        self.assertEqual(clock.add_days(tehran(2026, 10, 21, 15, 0), 1), tehran(2026, 10, 22, 13, 0))
        # Filed on Friday: Saturday opening starts the clock.
        self.assertEqual(clock.add_days(tehran(2026, 10, 23, 10, 0), 1), tehran(2026, 10, 25, 8, 0))

    def test_holidays_are_left_out(self):
        clock = WorkingTime(holidays=[date(2026, 10, 18)])
        self.assertEqual(clock.add_days(tehran(2026, 10, 17, 10, 0), 1), tehran(2026, 10, 19, 10, 0))
        self.assertEqual(clock.add_hours(tehran(2026, 10, 17, 15, 0), 2), tehran(2026, 10, 19, 9, 0))


class Base(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="as.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="as.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.operator = User.objects.create_user(
            username="as.operator", password=PASSWORD, role=User.Role.SALES_AGENT, workstream=User.Workstream.AFTER_SALES,
        )
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری خدمات", phone={"raw_phone": "09121110600", "is_primary": True},
        )

    def case(self, **extra):
        data = {"customer": self.customer, "subject": "خرابی", "description": "شرح", "assigned_to": self.operator, **extra}
        return create_after_sales_request(actor=self.manager, **data)


class DefaultTests(Base):
    def test_the_owners_defaults(self):
        self.assertEqual([item.label for item in CaseType.objects.order_by("position")], [
            "شکایت", "تعمیر", "گارانتی", "پرسش", "مرجوعی", "پیگیری ارسال", "سایر",
        ])
        self.assertEqual([stage.label for stage in workflow.stages_for(None)], [
            "ثبت‌شده", "در حال بررسی", "منتظر مشتری یا اطلاعات تکمیلی", "منتظر قطعه یا تأمین‌کننده",
            "در حال انجام", "آماده تحویل یا اعلام نتیجه", "بسته‌شده",
        ])
        policies = {item.priority: item for item in SlaPolicy.objects.filter(case_type__isnull=True)}
        self.assertEqual((policies["normal"].response_value, policies["normal"].response_unit), (1, "day"))
        self.assertEqual((policies["normal"].resolution_value, policies["normal"].resolution_unit), (5, "day"))
        self.assertEqual((policies["urgent"].response_value, policies["urgent"].response_unit), (4, "hour"))
        self.assertEqual((policies["urgent"].resolution_value, policies["urgent"].resolution_unit), (2, "day"))
        self.assertEqual((policies["critical"].response_value, policies["critical"].plan_value), (1, 4))
        self.assertIsNone(policies["critical"].resolution_value)


class CaseTests(Base):
    def test_a_case_starts_with_a_type_its_priority_and_deadlines(self):
        complaint = CaseType.objects.get(key="complaint")
        CaseType.objects.filter(pk=complaint.pk).update(default_priority="urgent")
        complaint.refresh_from_db()
        case = self.case(case_type=complaint)
        self.assertEqual((case.stage, case.status, case.priority), ("registered", "ثبت‌شده", "urgent"))
        self.assertIsNotNone(case.response_due)
        self.assertIsNotNone(case.resolution_due)
        self.assertIsNone(case.plan_due)
        critical = self.case(priority="critical")
        self.assertIsNotNone(critical.plan_due)
        self.assertIsNone(critical.resolution_due)

    def test_stages_come_from_the_list_and_the_first_move_is_the_first_response(self):
        case = self.case()
        with self.assertRaises(BusinessRuleError):
            transition_after_sales_status(actor=self.operator, request=case, to_status="هر چیزی")
        with self.assertRaises(BusinessRuleError):
            transition_after_sales_status(actor=self.operator, request=case, to_status="closed")
        moved = transition_after_sales_status(actor=self.operator, request=case, to_status="waiting_parts")
        self.assertEqual((moved.stage, moved.status), ("waiting_parts", "منتظر قطعه یا تأمین‌کننده"))
        self.assertIsNotNone(moved.responded_at)

    def test_closing_needs_a_final_result_and_reopening_a_reason(self):
        case = self.case()
        with self.assertRaises(BusinessRuleError):
            close_after_sales_request(actor=self.manager, request=case)
        with self.assertRaises(BusinessPermissionDenied):
            close_after_sales_request(actor=self.operator, request=case, final_result="resolved")
        closed = close_after_sales_request(actor=self.manager, request=case, final_result="agreed")
        self.assertEqual((closed.stage, closed.final_result), ("closed", "agreed"))
        with self.assertRaises(BusinessConflictError):
            transition_after_sales_status(actor=self.manager, request=case, to_status="reviewing")
        with self.assertRaises(BusinessRuleError):
            workflow.reopen(actor=self.manager, request=case, reason=" ")
        reopened = workflow.reopen(actor=self.manager, request=case, reason="مشتری دوباره تماس گرفت", to_stage="in_progress")
        self.assertEqual((reopened.stage, reopened.final_result, reopened.closed_at), ("in_progress", "", None))
        self.assertEqual(
            list(case.history.values_list("event", flat=True)),
            [AfterSalesHistory.Event.REOPENED, AfterSalesHistory.Event.CLOSED, AfterSalesHistory.Event.CREATED],
        )

    def test_a_new_priority_counts_the_deadlines_again_and_critical_needs_a_plan(self):
        case = self.case()
        before = case.response_due
        changed = workflow.set_priority(actor=self.manager, request=case, priority="critical", reason="تولید متوقف است")
        self.assertLess(changed.response_due, before)
        self.assertIsNotNone(changed.plan_due)
        with self.assertRaises(BusinessRuleError):
            workflow.record_plan(actor=self.operator, request=case, note=" ")
        planned = workflow.record_plan(actor=self.operator, request=case, note="قطعه از انبار مرکزی")
        self.assertIsNotNone(planned.planned_at)

    def test_a_type_with_its_own_stages(self):
        repair = CaseType.objects.get(key="repair")
        workflow.give_type_own_stages(actor=self.admin, case_type=repair)
        added = workflow.create_stage(actor=self.admin, label="ارسال به تعمیرگاه", case_type=repair)
        keys = [stage.key for stage in workflow.stages_for(repair)]
        self.assertEqual(keys[-2:], [added.key, "closed"])
        case = self.case(case_type=repair)
        transition_after_sales_status(actor=self.operator, request=case, to_status="ارسال به تعمیرگاه")
        with self.assertRaises(BusinessRuleError):
            transition_after_sales_status(actor=self.operator, request=self.case(), to_status="ارسال به تعمیرگاه")

    def test_overdue_cases_are_found(self):
        late = self.case()
        AfterSalesRequest.objects.filter(pk=late.pk).update(resolution_due=timezone.now() - timedelta(hours=1))
        self.case()
        client = APIClient()
        client.force_authenticate(self.manager)
        rows = client.get("/api/v1/after-sales/?overdue=true").json()["results"]
        self.assertEqual([row["id"] for row in rows], [late.pk])
        self.assertEqual(rows[0]["overdue"], ["resolution"])


class SettingsTests(Base):
    def test_the_company_shapes_types_deadlines_calendar_and_holidays(self):
        with self.assertRaises(BusinessPermissionDenied):
            workflow.create_type(actor=self.manager, label="نصب")
        item = workflow.create_type(actor=self.admin, label="نصب", default_priority="urgent")
        self.assertEqual(item.key, "c1")
        workflow.set_policy(actor=self.admin, priority="critical", case_type=item, resolution={"value": 3, "unit": "day"})
        case = self.case(case_type=item)
        self.assertEqual(case.priority, "urgent")
        critical = self.case(case_type=item, priority="critical")
        self.assertIsNotNone(critical.resolution_due)
        with self.assertRaises(BusinessRuleError):
            workflow.set_policy(actor=self.admin, priority="normal", response={"value": 0, "unit": "hour"})
        workflow.update_calendar(actor=self.admin, hours={"5": ["09:00", "17:00"]}, skip_holidays=True)
        with self.assertRaises(BusinessRuleError):
            workflow.update_calendar(actor=self.admin, hours={"5": ["17:00", "09:00"]})
        added = workflow.add_fixed_holidays(actor=self.admin, jalali_year=1405)
        self.assertEqual(added, 10)
        self.assertTrue(Holiday.objects.filter(day=date(2026, 3, 21), title="عید نوروز").exists())
        self.assertEqual(workflow.add_fixed_holidays(actor=self.admin, jalali_year=1405), 0)

    def test_the_settings_api_and_tab(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        payload = client.get("/api/v1/after-sales-settings/").json()
        self.assertEqual(len(payload["types"]), 7)
        self.assertEqual(client.post("/api/v1/after-sales-settings/types/", {"label": "نصب"}, format="json").status_code, 201)
        holiday = client.post("/api/v1/after-sales-settings/holidays/", {"day": "2026-10-20", "title": "تعطیل شرکت"}, format="json")
        self.assertEqual(holiday.status_code, 201, holiday.content)
        row = next(item for item in holiday.json()["holidays"] if item["day"] == "2026-10-20")
        self.assertEqual(client.delete(f"/api/v1/after-sales-settings/holidays/{row['id']}/").status_code, 200)
        manager = APIClient()
        manager.force_authenticate(self.manager)
        self.assertEqual(manager.get("/api/v1/after-sales-settings/").status_code, 403)
        features = frozenset(ALL_FEATURES) - {"after_sales"}
        with override_active_profile(DeploymentProfile(profile_id="x", features=features, source="signed-manifest")):
            self.assertEqual(client.get("/api/v1/after-sales-settings/").status_code, 404)
        self.client.force_login(self.admin)
        page = self.client.get("/settings/?tab=after-sales").content.decode()
        self.assertIn('id="case-types-body"', page)
        self.assertIn('id="case-calendar-form"', page)


class MigrationTests(Base):
    def test_older_cases_go_to_the_nearest_stage_keeping_their_words(self):
        migration = importlib.import_module("aftersales.migrations.0004_seed_case_workflow")
        rows = {}
        for words in ("در انتظار قطعه", "در حال بررسی فنی", "منتظر مشتری", "آماده تحویل", "تعمیر", "یک واژهٔ آزاد"):
            case = self.case()
            AfterSalesRequest.objects.filter(pk=case.pk).update(status=words, stage="registered")
            rows[words] = case.pk
        closed = self.case()
        AfterSalesRequest.objects.filter(pk=closed.pk).update(status="بسته شد", closed_at=timezone.now(), stage="registered")
        migration.forward(django_apps, None)
        stages = dict(AfterSalesRequest.objects.values_list("pk", "stage"))
        self.assertEqual([stages[rows[words]] for words in rows], [
            "waiting_parts", "reviewing", "waiting_customer", "ready", "in_progress", "reviewing",
        ])
        closed.refresh_from_db()
        self.assertEqual((closed.stage, closed.status, closed.final_result), ("closed", "بسته شد", ""))
        self.assertEqual(CaseStage.objects.filter(case_type__isnull=True).count(), 7)
