"""The system-events page's date window (product-owner request 2026-09-20).

This page is read when something went wrong at a known time, and until now the
only way to reach a given day was to page back through everything recorded
since. The rule itself is `common.viewsets.filter_by_date_window`, shared with
the customers page's registration-date filter — one implementation, because
two pages asking the same question of two different columns should not be able
to disagree about what "to this day" includes.

Two properties are worth pinning, and they are the two a date filter gets
wrong:

* the upper bound covers the *whole* closing day, not up to its midnight —
  a row recorded at 23:59 on the day someone typed is inside the window they
  meant;
* a malformed date is a request error rather than an ignored parameter.
  Quietly dropping it would show the wrong rows while looking like the filter
  worked.

Scope is checked too: a date bound narrows what `activity_logs_for` already
allowed and can never reach past it.
"""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog


PASSWORD = "Strong-pass-822!"


class ActivityLogDateWindowTests(TestCase):
    def setUp(self):
        # Throttle buckets are keyed by user id and rolled-back tests reuse
        # those ids, so without this a test inherits the previous one's spend.
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = User.objects.create_user(
            username="alw.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

        now = timezone.localtime()
        self.today = now.date()
        self.entries = {}
        for label, moment in {
            "old": now - timedelta(days=10),
            "edge": now.replace(hour=23, minute=59, second=0, microsecond=0) - timedelta(days=1),
            "today": now,
        }.items():
            entry = ActivityLog.objects.create(
                actor=self.admin, operation=f"test.{label}", object_type="probe", object_id="1",
            )
            # `created_at` is auto_now_add, so it is moved afterwards.
            ActivityLog.objects.filter(pk=entry.pk).update(created_at=moment)
            self.entries[label] = entry

    def _operations(self, query=""):
        response = self.client.get(f"/api/v1/activity-logs/{query}")
        self.assertEqual(response.status_code, 200, response.data)
        return {row["operation"] for row in response.data["results"]}

    def test_without_a_window_every_entry_is_listed(self):
        self.assertEqual(
            self._operations(), {"test.old", "test.edge", "test.today"}
        )

    def test_a_lower_bound_drops_everything_before_it(self):
        since = (self.today - timedelta(days=2)).isoformat()
        self.assertEqual(self._operations(f"?created_from={since}"), {"test.edge", "test.today"})

    def test_the_closing_day_is_included_whole(self):
        """The one a date filter usually gets wrong: an entry at 23:59 on the
        closing day is inside the window a person asked for."""
        yesterday = (self.today - timedelta(days=1)).isoformat()
        self.assertIn("test.edge", self._operations(f"?created_to={yesterday}"))

    def test_both_bounds_together_narrow_to_the_window(self):
        yesterday = (self.today - timedelta(days=1)).isoformat()
        self.assertEqual(
            self._operations(f"?created_from={yesterday}&created_to={yesterday}"),
            {"test.edge"},
        )

    def test_an_empty_bound_narrows_nothing(self):
        self.assertEqual(
            self._operations("?created_from=&created_to="),
            {"test.old", "test.edge", "test.today"},
        )

    def test_a_malformed_date_is_a_request_error(self):
        response = self.client.get("/api/v1/activity-logs/?created_from=yesterday")
        self.assertEqual(response.status_code, 400)
        self.assertIn("created_from", response.data)

    def test_both_bounds_are_declared_parameters(self):
        """`StrictQueryParametersMixin` rejects anything undeclared, so a
        parameter the page sends but the viewset never listed would 400 on
        every load."""
        from auditlog.views import ActivityLogViewSet

        self.assertEqual(
            set(ActivityLogViewSet.list_query_parameters), {"created_from", "created_to"}
        )

    def test_a_reader_with_no_audit_access_is_still_refused_with_a_window(self):
        """The bound narrows what scope already allowed; it cannot reach past
        it."""
        agent = User.objects.create_user(
            username="alw.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        client = APIClient()
        client.force_authenticate(agent)
        since = (self.today - timedelta(days=30)).isoformat()
        response = client.get(f"/api/v1/activity-logs/?created_from={since}")
        self.assertIn(response.status_code, (403, 404))
