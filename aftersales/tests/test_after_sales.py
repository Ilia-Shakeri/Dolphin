from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.test import APIClient

from accounts.models import User
from aftersales.models import AfterSalesHistory, AfterSalesRequest
from aftersales.services import (
    assign_after_sales_request,
    close_after_sales_request,
    create_after_sales_request,
    schedule_after_sales_appointment,
    transition_after_sales_status,
)
from common.exceptions import BusinessConflictError, BusinessPermissionDenied
from auditlog.models import ActivityLog
from sales.services import (
    assign_lead,
    create_customer_with_phone,
    create_lead,
    mark_sale,
    register_sales_document,
)


class AfterSalesContractTests(TestCase):
    password = "Strong-pass-983!"

    def setUp(self):
        self.manager = User.objects.create_user(
            username="after-manager", password=self.password, role=User.Role.SALES_MANAGER,
        )
        self.platform = User.objects.create_user(
            username="after-platform", password=self.password, role=User.Role.PLATFORM_ADMIN,
        )
        self.company_it = User.objects.create_user(
            username="after-it", password=self.password, role=User.Role.COMPANY_IT,
        )
        self.sales_agent = User.objects.create_user(
            username="after-sales-agent", password=self.password, role=User.Role.SALES_AGENT,
        )
        self.operator = User.objects.create_user(
            username="after-operator", password=self.password, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )
        self.other_operator = User.objects.create_user(
            username="after-other-operator", password=self.password, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )
        self.customer = create_customer_with_phone(actor=self.sales_agent, full_name="مشتری خدمات")
        self.lead = create_lead(actor=self.sales_agent, customer=self.customer, source="manual")
        assign_lead(actor=self.manager, lead=self.lead, to_user=self.sales_agent, reason="sale scope")
        self.sale = mark_sale(
            actor=self.sales_agent, lead=self.lead, total_amount=Decimal("50.00"), sold_at=timezone.now(),
        )
        self.document = register_sales_document(
            actor=self.manager, customer=self.customer, sale=self.sale,
            document_number="AFTER-DOC-1", postal_status="ثبت",
        )
        self.request = create_after_sales_request(
            actor=self.manager, customer=self.customer, sale=self.sale, document=self.document,
            subject="پیگیری نصب", description="شرح پرونده خدمات", status="جدید",
            assigned_to=self.operator,
        )

    def test_creation_relations_history_and_audit_are_safe(self):
        self.assertEqual(self.request.history.count(), 1)
        history = self.request.history.get()
        self.assertEqual((history.event, history.to_status, history.to_user), (AfterSalesHistory.Event.CREATED, "جدید", self.operator))
        log = ActivityLog.objects.get(operation="after_sales.created", object_id=str(self.request.pk))
        self.assertNotIn("شرح پرونده خدمات", str(log.safe_changes))
        self.assertNotIn("پیگیری نصب", str(log.safe_changes))
        with self.assertRaises(ProtectedError):
            self.request.delete()

    def test_manager_creates_assigns_transitions_and_closes_without_delete(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        created = client.post(
            "/api/v1/after-sales/",
            {
                "customer": self.customer.pk, "sale": self.sale.pk, "document": self.document.pk,
                "subject": "درخواست دوم", "description": "شرح دوم", "status": "ثبت‌شده",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        item_id = created.data["id"]
        assigned = client.post(
            f"/api/v1/after-sales/{item_id}/assign/",
            {"to_user": self.other_operator.pk, "reason": "تقسیم کار"}, format="json",
        )
        self.assertEqual(assigned.status_code, 200, assigned.data)
        changed = client.post(
            f"/api/v1/after-sales/{item_id}/transition-status/",
            {"to_status": "در حال پیگیری", "reason": "تماس شد"}, format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        closed = client.post(f"/api/v1/after-sales/{item_id}/close/", {"reason": "تمام"}, format="json")
        self.assertEqual(closed.status_code, 200, closed.data)
        self.assertIsNotNone(closed.data["closed_at"])
        self.assertEqual(AfterSalesRequest.objects.get(pk=item_id).history.count(), 4)
        self.assertEqual(client.patch(f"/api/v1/after-sales/{item_id}/", {"status": "بد"}, format="json").status_code, 405)
        self.assertEqual(client.delete(f"/api/v1/after-sales/{item_id}/").status_code, 405)
        self.assertEqual(
            client.post(f"/api/v1/after-sales/{item_id}/transition-status/", {"to_status": "باز"}, format="json").status_code,
            409,
        )

    def test_assigned_operator_has_only_assigned_case_and_status_action(self):
        hidden = create_after_sales_request(
            actor=self.manager, customer=self.customer, subject="پنهان", description="شرح پنهان",
            status="جدید", assigned_to=self.other_operator,
        )
        client = APIClient()
        client.force_authenticate(self.operator)
        listing = client.get("/api/v1/after-sales/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([item["id"] for item in listing.data["results"]], [self.request.pk])
        self.assertEqual(client.get(f"/api/v1/after-sales/{hidden.pk}/").status_code, 404)
        self.assertEqual(client.get(f"/api/v1/after-sales/{hidden.pk}/history/").status_code, 404)
        changed = client.post(
            f"/api/v1/after-sales/{self.request.pk}/transition-status/",
            {"to_status": "در حال بررسی"}, format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(client.post(f"/api/v1/after-sales/{self.request.pk}/close/", {}, format="json").status_code, 403)
        self.assertEqual(
            client.post(f"/api/v1/after-sales/{self.request.pk}/assign/", {"to_user": self.other_operator.pk}, format="json").status_code,
            403,
        )
        self.assertEqual(
            client.post("/api/v1/after-sales/", {"customer": self.customer.pk}, format="json").status_code,
            403,
        )

    def test_after_sales_operator_gets_no_customer_sale_or_document_scope(self):
        """An operator holds no sales capability, so the answer is 403.

        This used to be `200` with an empty page, because the selectors return
        an empty queryset for a caller with no capability. The data boundary
        held either way, but it disagreed with `users`, `activity-logs`, and
        `inbound-sms`, which already answered `403`. The answer is now uniform:
        no capability means refused, not "here is nothing".
        """
        client = APIClient()
        client.force_authenticate(self.operator)
        for path in ("customers", "leads", "interactions", "products", "sales", "sales-documents"):
            with self.subTest(path=path):
                response = client.get(f"/api/v1/{path}/")
                self.assertEqual(response.status_code, 403, response.data)
        for path in ("customer-phones",):
            with self.subTest(path=path):
                self.assertEqual(client.get(f"/api/v1/{path}/").status_code, 403)
        # Writing is refused for the same reason, not merely reading.
        self.assertEqual(
            client.post("/api/v1/customers/", {"full_name": "x"}, format="json").status_code,
            403,
        )
        # Direct-ID access stays closed exactly as before.
        self.assertEqual(client.get(f"/api/v1/customers/{self.customer.pk}/").status_code, 403)
        self.assertEqual(client.get(f"/api/v1/sales/{self.sale.pk}/").status_code, 403)
        self.assertEqual(client.get(f"/api/v1/sales-documents/{self.document.pk}/").status_code, 403)
        self.assertEqual(client.get("/api/v1/reports/user-performance/").status_code, 403)
        self.assertEqual(client.get("/api/v1/reports/sales-documents/").status_code, 403)

    def test_sales_roles_still_reach_their_own_modules(self):
        """The uniform 403 must not narrow anyone who does hold the capability."""
        for actor in (self.sales_agent, self.manager, self.company_it, self.platform):
            client = APIClient()
            client.force_authenticate(actor)
            for path in ("customers", "leads", "interactions", "products", "sales", "sales-documents"):
                with self.subTest(role=actor.role, path=path):
                    self.assertEqual(client.get(f"/api/v1/{path}/").status_code, 200)

    def test_normal_agent_has_no_after_sales_access(self):
        # A caller holding neither `after_sales.company` nor `.assigned` is
        # refused outright (403) rather than shown an empty page — the same
        # fix `HasSalesCapability` already applies to customers/leads/etc.,
        # extended here by `HasAfterSalesCapability`.
        client = APIClient()
        client.force_authenticate(self.sales_agent)
        self.assertEqual(client.get("/api/v1/after-sales/").status_code, 403)
        self.assertEqual(client.get(f"/api/v1/after-sales/{self.request.pk}/").status_code, 403)
        self.assertEqual(client.post("/api/v1/after-sales/", {}, format="json").status_code, 403)
        self.client.force_login(self.sales_agent)
        self.assertEqual(self.client.get("/after-sales/").status_code, 403)
        self.assertNotContains(self.client.get("/"), 'data-module="after-sales"')

    def test_all_elevated_roles_see_all_cases_and_controls(self):
        for actor in (self.manager, self.company_it, self.platform):
            with self.subTest(role=actor.role):
                client = APIClient()
                client.force_authenticate(actor)
                self.assertEqual(client.get(f"/api/v1/after-sales/{self.request.pk}/").status_code, 200)
                self.client.force_login(actor)
                page = self.client.get(f"/after-sales/{self.request.pk}/")
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, 'id="after-sales-assign-form"')

    def test_assignment_rejects_wrong_workstream_inactive_and_elevated_users(self):
        inactive = User.objects.create_user(
            username="after-inactive", password=self.password, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES, is_active=False,
        )
        client = APIClient()
        client.force_authenticate(self.manager)
        for target in (self.sales_agent, inactive, self.manager):
            with self.subTest(target=target.username):
                response = client.post(
                    f"/api/v1/after-sales/{self.request.pk}/assign/",
                    {"to_user": target.pk}, format="json",
                )
                self.assertEqual(response.status_code, 400)

    def test_relation_mismatch_server_fields_filters_and_history_constraint(self):
        other_customer = create_customer_with_phone(actor=self.manager, full_name="مشتری دیگر")
        client = APIClient()
        client.force_authenticate(self.manager)
        mismatch = client.post(
            "/api/v1/after-sales/",
            {
                "customer": other_customer.pk, "sale": self.sale.pk, "subject": "ناسازگار",
                "description": "شرح", "status": "جدید",
            }, format="json",
        )
        self.assertEqual(mismatch.status_code, 400)
        server = client.post(
            "/api/v1/after-sales/",
            {
                "customer": self.customer.pk, "subject": "فیلد سرور", "description": "شرح",
                "status": "جدید", "closed_at": timezone.now().isoformat(),
            }, format="json",
        )
        self.assertEqual(server.status_code, 400)
        self.assertIn("closed_at", server.data)
        self.assertEqual(client.get("/api/v1/after-sales/?is_closed=false&status=جدید").status_code, 200)
        self.assertEqual(client.get("/api/v1/after-sales/?unknown=1").status_code, 400)
        self.assertEqual(client.get("/api/v1/after-sales/?status=جدید&status=باز").status_code, 400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AfterSalesHistory.objects.create(request=self.request, event="bad", actor=self.manager)

    def test_audit_failure_rolls_back_create_and_status_transition(self):
        with mock.patch("aftersales.services.log_activity", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                create_after_sales_request(
                    actor=self.manager, customer=self.customer, subject="برگشت", description="شرح", status="جدید",
                )
        self.assertFalse(AfterSalesRequest.objects.filter(subject="برگشت").exists())
        with mock.patch("aftersales.services.log_activity", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                transition_after_sales_status(
                    actor=self.operator, request=self.request, to_status="نباید بماند",
                )
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "جدید")
        self.assertEqual(self.request.history.count(), 1)

        with mock.patch("aftersales.services.log_activity", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                assign_after_sales_request(actor=self.manager, request=self.request, to_user=self.other_operator)
        self.request.refresh_from_db()
        self.assertEqual(self.request.assigned_to, self.operator)
        self.assertEqual(self.request.history.count(), 1)

        with mock.patch("aftersales.services.log_activity", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                close_after_sales_request(actor=self.manager, request=self.request)
        self.request.refresh_from_db()
        self.assertIsNone(self.request.closed_at)
        self.assertEqual(self.request.history.count(), 1)

    def test_operator_browser_landing_navigation_and_direct_id_are_scoped(self):
        hidden = create_after_sales_request(
            actor=self.manager, customer=self.customer, subject="پنهان دوم", description="شرح",
            status="جدید", assigned_to=self.other_operator,
        )
        self.client.force_login(self.operator)
        home = self.client.get("/")
        self.assertContains(home, "میز کار خدمات پس از فروش")
        self.assertContains(home, 'data-module="after-sales"')
        for module in ("customers", "leads", "interactions", "products", "sales", "sales-documents", "users", "audit"):
            self.assertNotContains(home, f'data-module="{module}"')
        page = self.client.get(f"/after-sales/{self.request.pk}/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'id="after-sales-status-form"')
        self.assertNotContains(page, 'id="after-sales-assign-form"')
        self.assertEqual(self.client.get(f"/after-sales/{hidden.pk}/").status_code, 404)


class AfterSalesAppointmentTests(AfterSalesContractTests):
    """The after-sales side of the follow-up calendar
    (DOLPHIN_FEATURE_MAP_AND_ROADMAP.md §7 phase E) — same setUp fixture.
    """

    def setUp(self):
        super().setUp()
        # `schedule-appointment` is a `sensitive_actions` route (throttled at
        # 30/min per user). The test DB's rolled-back autoincrement can hand a
        # later test's user the same pk an earlier test's user already spent
        # throttle quota under, in the same process-wide cache — this class
        # exercises several sensitive POSTs, so it clears the slate rather
        # than risk leaking a 429 into whatever test runs next (the same
        # defensive clear already used by billing/tests/test_payment_
        # correction.py and several others). Cleared on both ends: setUp so
        # an earlier test's pollution cannot reach this class, tearDown so
        # this class's own sensitive POSTs cannot reach whatever runs next.
        cache.clear()
        self.addCleanup(cache.clear)

    def test_a_manager_schedules_and_then_clears_an_appointment(self):
        when = timezone.now() + timezone.timedelta(days=2)
        item = schedule_after_sales_appointment(actor=self.manager, request=self.request, appointment_at=when, reason="هماهنگی با مشتری")
        self.assertEqual(item.next_appointment_at, when)
        self.assertTrue(
            AfterSalesHistory.objects.filter(request=item, event="appointment_scheduled", appointment_at=when).exists()
        )
        self.assertTrue(ActivityLog.objects.filter(operation="after_sales.appointment_scheduled", object_id=str(item.pk)).exists())

        cleared = schedule_after_sales_appointment(actor=self.manager, request=item, appointment_at=None)
        self.assertIsNone(cleared.next_appointment_at)
        self.assertTrue(AfterSalesHistory.objects.filter(request=item, event="appointment_scheduled", appointment_at__isnull=True).exists())

    def test_the_assigned_operator_may_schedule_their_own_case(self):
        when = timezone.now() + timezone.timedelta(days=1)
        item = schedule_after_sales_appointment(actor=self.operator, request=self.request, appointment_at=when)
        self.assertEqual(item.next_appointment_at, when)

    def test_an_operator_not_assigned_to_the_case_is_refused(self):
        with self.assertRaises(BusinessPermissionDenied):
            schedule_after_sales_appointment(
                actor=self.other_operator, request=self.request, appointment_at=timezone.now() + timezone.timedelta(days=1),
            )

    def test_a_plain_sales_agent_is_refused(self):
        with self.assertRaises(BusinessPermissionDenied):
            schedule_after_sales_appointment(
                actor=self.sales_agent, request=self.request, appointment_at=timezone.now() + timezone.timedelta(days=1),
            )

    def test_a_closed_case_cannot_be_scheduled(self):
        close_after_sales_request(actor=self.manager, request=self.request, reason="تمام")
        with self.assertRaises(BusinessConflictError):
            schedule_after_sales_appointment(actor=self.manager, request=self.request, appointment_at=timezone.now())

    def test_scheduling_the_exact_same_value_again_is_a_conflict(self):
        with self.assertRaises(BusinessConflictError):
            schedule_after_sales_appointment(actor=self.manager, request=self.request, appointment_at=None)

    def test_the_endpoint_schedules_and_the_calendar_window_filters_by_it(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        when = timezone.now().replace(microsecond=0) + timezone.timedelta(days=3)
        scheduled = client.post(
            f"/api/v1/after-sales/{self.request.pk}/schedule-appointment/",
            {"appointment_at": when.isoformat()}, format="json",
        )
        self.assertEqual(scheduled.status_code, 200, scheduled.data)
        self.assertEqual(parse_datetime(scheduled.data["next_appointment_at"]), when)

        inside = client.get("/api/v1/after-sales/", {
            "appointment_from": (when - timezone.timedelta(hours=1)).isoformat(),
            "appointment_to": (when + timezone.timedelta(hours=1)).isoformat(),
        })
        self.assertEqual(inside.status_code, 200)
        self.assertIn(self.request.pk, [row["id"] for row in inside.data["results"]])

        outside = client.get("/api/v1/after-sales/", {
            "appointment_from": (when + timezone.timedelta(days=10)).isoformat(),
            "appointment_to": (when + timezone.timedelta(days=20)).isoformat(),
        })
        self.assertEqual(outside.status_code, 200)
        self.assertNotIn(self.request.pk, [row["id"] for row in outside.data["results"]])

    def test_next_appointment_at_is_read_only_on_plain_create(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        response = client.post(
            "/api/v1/after-sales/",
            {
                "customer": self.customer.pk, "subject": "تلاش نوشتن مستقیم", "description": "شرح",
                "status": "جدید", "next_appointment_at": timezone.now().isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("next_appointment_at", response.data)
