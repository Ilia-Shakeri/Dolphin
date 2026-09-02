"""The lead follow-up calendar's own backend surface.

Two things only: `follow_up_from`/`follow_up_to` narrow `/api/v1/leads/` to a
`next_follow_up_at` window (the calendar's event source), and that window
never widens the ordinary `leads_for` scope — an agent still gets only their
own leads, an elevated role still gets the whole company.
"""

from datetime import UTC, datetime, timedelta

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from sales.models import Lead
from sales.services import assign_lead, create_customer_with_phone, create_lead, update_lead


PASSWORD = "Strong-pass-937!"


class LeadFollowUpFilterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="cal.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="cal.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.other_agent = User.objects.create_user(
            username="cal.other", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        customer = create_customer_with_phone(
            actor=self.agent, full_name="مشتری تقویم",
            phone={"raw_phone": "09121234567", "is_primary": True},
        )
        other_customer = create_customer_with_phone(
            actor=self.other_agent, full_name="مشتری دیگر",
            phone={"raw_phone": "09127654321", "is_primary": True},
        )

        self.in_range = create_lead(actor=self.agent, customer=customer, source="manual")
        assign_lead(actor=self.manager, lead=self.in_range, to_user=self.agent, reason="setup")
        update_lead(actor=self.manager, lead=self.in_range, next_follow_up_at=datetime(2026, 1, 15, 8, tzinfo=UTC))

        self.out_of_range = create_lead(actor=self.agent, customer=customer, source="manual")
        assign_lead(actor=self.manager, lead=self.out_of_range, to_user=self.agent, reason="setup")
        update_lead(actor=self.manager, lead=self.out_of_range, next_follow_up_at=datetime(2026, 3, 1, 8, tzinfo=UTC))

        self.no_follow_up = create_lead(actor=self.agent, customer=customer, source="manual")
        assign_lead(actor=self.manager, lead=self.no_follow_up, to_user=self.agent, reason="setup")

        self.others_lead = create_lead(actor=self.other_agent, customer=other_customer, source="manual")
        assign_lead(actor=self.manager, lead=self.others_lead, to_user=self.other_agent, reason="setup")
        update_lead(actor=self.manager, lead=self.others_lead, next_follow_up_at=datetime(2026, 1, 16, 8, tzinfo=UTC))

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def _window(self):
        return {
            "follow_up_from": "2026-01-01T00:00:00Z",
            "follow_up_to": "2026-02-01T00:00:00Z",
        }

    def test_only_leads_with_a_follow_up_inside_the_window_are_returned(self):
        response = self.client_for(self.manager).get("/api/v1/leads/", self._window())
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.json()["results"]}
        self.assertIn(self.in_range.pk, ids)
        self.assertNotIn(self.out_of_range.pk, ids)
        self.assertNotIn(self.no_follow_up.pk, ids)

    def test_the_upper_bound_is_exclusive(self):
        response = self.client_for(self.manager).get("/api/v1/leads/", {
            "follow_up_from": "2026-01-15T08:00:00Z",
            "follow_up_to": "2026-01-15T08:00:00Z",
        })
        self.assertEqual(response.json()["results"], [])

    def test_an_agent_only_sees_their_own_leads_in_the_window(self):
        response = self.client_for(self.agent).get("/api/v1/leads/", self._window())
        ids = {row["id"] for row in response.json()["results"]}
        self.assertIn(self.in_range.pk, ids)
        self.assertNotIn(self.others_lead.pk, ids)

    def test_a_manager_sees_every_agents_lead_in_the_window(self):
        response = self.client_for(self.manager).get("/api/v1/leads/", self._window())
        ids = {row["id"] for row in response.json()["results"]}
        self.assertIn(self.in_range.pk, ids)
        self.assertIn(self.others_lead.pk, ids)

    def test_a_malformed_bound_is_a_400_not_a_silent_ignore(self):
        response = self.client_for(self.manager).get("/api/v1/leads/", {"follow_up_from": "not-a-date"})
        self.assertEqual(response.status_code, 400)

    def test_a_naive_datetime_is_refused(self):
        response = self.client_for(self.manager).get("/api/v1/leads/", {"follow_up_from": "2026-01-01T00:00:00"})
        self.assertEqual(response.status_code, 400)

    def test_a_repeated_bound_is_refused(self):
        response = self.client_for(self.manager).get(
            "/api/v1/leads/?follow_up_from=2026-01-01T00:00:00Z&follow_up_from=2026-01-02T00:00:00Z"
        )
        self.assertEqual(response.status_code, 400)

    def test_dragging_an_event_to_a_new_day_is_a_plain_lead_patch(self):
        """The calendar's reschedule is not a special endpoint — confirms the
        same PATCH the drag handler sends actually moves the date."""
        response = self.client_for(self.agent).patch(
            f"/api/v1/leads/{self.in_range.pk}/",
            {"next_follow_up_at": "2026-01-20T09:00:00Z"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.in_range.refresh_from_db()
        self.assertEqual(self.in_range.next_follow_up_at, datetime(2026, 1, 20, 9, tzinfo=UTC))

    def test_an_agent_cannot_reschedule_someone_elses_lead(self):
        response = self.client_for(self.agent).patch(
            f"/api/v1/leads/{self.others_lead.pk}/",
            {"next_follow_up_at": "2026-01-20T09:00:00Z"},
            format="json",
        )
        self.assertIn(response.status_code, (403, 404))
