"""New leads shared out evenly among a campaign's responsibles (2.40.35).

Product owner, 2026-10-07: «در ساخت سرنخ‌های تازه، پنل باید به‌صورت اتوماتیک
سرنخ را به مسئولان آن کمپین اختصاص دهد؛ خودکار و شانسی، تا تمامی مسئولان آن
کمپین تعداد برابر سرنخ داشته باشند. باید بتوان دستی هم انتخاب کرد ولی به‌صورت
پیش‌فرض خودکار باشد.»
"""

from collections import Counter

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from common.exceptions import BusinessPermissionDenied
from sales.campaigns import create_campaign
from sales.models import LeadAssignmentHistory
from sales.services import create_lead

PASSWORD = "Strong-pass-274!"


class AutoAssignTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="aa.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agents = [
            User.objects.create_user(username=f"aa.agent{index}", password=PASSWORD, role=User.Role.SALES_AGENT)
            for index in range(3)
        ]
        self.campaign = create_campaign(actor=self.manager, name="آزمون تقسیم", responsibles=self.agents)

    def test_leads_are_shared_out_evenly(self):
        leads = [create_lead(actor=self.manager, campaign=self.campaign) for _ in range(9)]
        counts = Counter(lead.assigned_to_id for lead in leads)
        self.assertEqual(sorted(counts.values()), [3, 3, 3])
        self.assertEqual(set(counts), {agent.pk for agent in self.agents})
        self.assertEqual(LeadAssignmentHistory.objects.filter(lead__in=leads).count(), 9)

    def test_whoever_has_fewest_gets_the_next_one(self):
        for _ in range(2):
            create_lead(actor=self.manager, campaign=self.campaign, assignee=self.agents[0])
        create_lead(actor=self.manager, campaign=self.campaign, assignee=self.agents[1])
        nxt = create_lead(actor=self.manager, campaign=self.campaign)
        self.assertEqual(nxt.assigned_to, self.agents[2])

    def test_a_manager_may_choose_and_a_marketer_only_themselves(self):
        chosen = create_lead(actor=self.manager, campaign=self.campaign, assignee=self.agents[2])
        self.assertEqual(chosen.assigned_to, self.agents[2])
        own = create_lead(actor=self.agents[0], campaign=self.campaign, assignee=self.agents[0])
        self.assertEqual(own.assigned_to, self.agents[0])
        with self.assertRaises(BusinessPermissionDenied):
            create_lead(actor=self.agents[0], campaign=self.campaign, assignee=self.agents[1])

    def test_a_campaign_without_responsibles_leaves_the_lead_as_before(self):
        bare = create_campaign(actor=self.manager, name="بدون مسئول")
        self.assertIsNone(create_lead(actor=self.agents[1], campaign=bare).assigned_to)
        self.assertIsNone(create_lead(actor=self.manager, campaign=bare).assigned_to)

    def test_the_api_defaults_to_automatic_and_takes_a_choice(self):
        client = APIClient()
        client.force_login(self.manager)
        auto = client.post("/api/v1/leads/", {"campaign": self.campaign.pk}, format="json")
        self.assertEqual(auto.status_code, 201, auto.content)
        self.assertIn(auto.json()["assigned_to"], {agent.pk for agent in self.agents})
        manual = client.post("/api/v1/leads/", {"campaign": self.campaign.pk, "assign_to": self.agents[1].pk}, format="json")
        self.assertEqual(manual.json()["assigned_to"], self.agents[1].pk)
