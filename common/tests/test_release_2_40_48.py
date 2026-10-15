"""2.40.48 — access and deactivated users (stage 2 of 2026-10-14's decisions).

* `audit.team` (BIZ-011): the one audit capability the Platform Admin may
  grant, to a store manager only; it shows the sales team's work on business
  records and nothing about users, permissions, settings or IT;
* role-level permission defaults (BIZ-005): the Platform Admin narrows a role
  for everyone holding it, with the same protected boundaries as a person;
* returned work (BIZ-013): a deactivated account's open leads and campaign
  people come back to the managers, who are alerted and decide — split among
  the campaign's other responsibles, or one person.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.access import capabilities_for
from accounts.models import RoleCapabilityOverride, User
from accounts.services import update_crm_user
from auditlog.models import ActivityLog
from auditlog.selectors import activity_logs_for
from auditlog.services import log_activity
from common.reminders import reminders_for
from sales.campaigns import add_campaign_member, create_campaign
from sales.models import Lead, LeadAssignmentHistory, TargetAudienceMember
from sales.services import AUTO_ASSIGN, create_lead, reassign_lead

PASSWORD = "Strong-pass-748!"


def make(username, role, **extra):
    return User.objects.create_user(username=username, password=PASSWORD, role=role, **extra)


def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class TeamAuditTests(TestCase):
    def setUp(self):
        self.admin = make("t.admin", User.Role.PLATFORM_ADMIN)
        self.manager = make("t.manager", User.Role.SALES_MANAGER)
        self.agent = make("t.agent", User.Role.SALES_AGENT)
        self.it = make("t.it", User.Role.COMPANY_IT)

    def grant(self, target, read=True):
        matrix = api(self.admin).get(f"/api/v1/users/{target.pk}/permissions/").json()["matrix"]
        payload = {key: {"read": row["read"], "write": row["write"], "delete": row["delete"]} for key, row in matrix.items()}
        payload["audit_team"] = {"read": read}
        return api(self.admin).patch(f"/api/v1/users/{target.pk}/permissions/", {"matrix": payload}, format="json")

    def test_only_a_store_manager_is_offered_and_given_it(self):
        self.assertIn("audit_team", api(self.admin).get(f"/api/v1/users/{self.manager.pk}/permissions/").json()["matrix"])
        self.assertNotIn("audit_team", api(self.admin).get(f"/api/v1/users/{self.agent.pk}/permissions/").json()["matrix"])
        self.assertEqual(self.grant(self.manager).status_code, 200)
        self.assertIn("audit.team", capabilities_for(self.manager))
        refused = api(self.admin).patch(
            f"/api/v1/users/{self.agent.pk}/permissions/", {"matrix": {"audit_team": {"read": True}}}, format="json"
        )
        self.assertNotIn("audit.team", capabilities_for(self.agent))
        self.assertEqual(refused.status_code, 400)

    def test_it_shows_the_teams_business_work_and_nothing_else(self):
        customer_event = log_activity(actor=self.agent, operation="customer.created", instance=self.agent)
        customer_event.object_type = "sales.customer"
        customer_event.save()
        user_event = log_activity(actor=self.agent, operation="user.profile_updated", instance=self.agent)
        it_event = ActivityLog.objects.create(actor=self.it, actor_role_snapshot="company_it", operation="customer.created",
                                              object_type="sales.customer", object_id="9")
        self.assertEqual(api(self.manager).get("/api/v1/activity-logs/").status_code, 403)
        self.grant(self.manager)
        visible = set(activity_logs_for(self.manager))
        self.assertIn(customer_event, visible)
        self.assertNotIn(user_event, visible)
        self.assertNotIn(it_event, visible)
        self.assertEqual(api(self.manager).get("/api/v1/activity-logs/").status_code, 200)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get("/activity-logs/").status_code, 200)

    def test_only_the_platform_admin_edits_permissions(self):
        response = api(self.it).patch(f"/api/v1/users/{self.manager.pk}/permissions/", {"matrix": {"audit_team": {"read": True}}}, format="json")
        self.assertEqual(response.status_code, 403)


class RolePermissionTests(TestCase):
    def setUp(self):
        self.admin = make("r.admin", User.Role.PLATFORM_ADMIN)
        self.manager = make("r.manager", User.Role.SALES_MANAGER)
        self.other_manager = make("r.manager2", User.Role.SALES_MANAGER)

    def matrix(self, key):
        return api(self.admin).get(f"/api/v1/role-permissions/{key}/").json()["matrix"]

    def put(self, key, changes):
        payload = {k: {"read": v["read"], "write": v["write"], "delete": v["delete"]} for k, v in self.matrix(key).items()}
        payload.update(changes)
        return api(self.admin).put(f"/api/v1/role-permissions/{key}/", {"matrix": payload}, format="json")

    def test_narrowing_a_role_narrows_everyone_holding_it(self):
        self.assertIn("inventory.manage", capabilities_for(self.manager))
        response = self.put("sales_manager", {"inventory": {"read": True, "write": False, "delete": False}})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["matrix"]["inventory"]["is_custom"])
        for person in (self.manager, self.other_manager):
            self.assertNotIn("inventory.manage", capabilities_for(person))
            self.assertIn("inventory.read", capabilities_for(person))
        # A person's own override still applies on top of the role.
        user_matrix = api(self.admin).get(f"/api/v1/users/{self.manager.pk}/permissions/").json()["matrix"]
        self.assertFalse(user_matrix["inventory"]["write"])
        self.assertFalse(user_matrix["inventory"]["is_custom"])
        # Reset: back to what the release ships.
        reset = api(self.admin).post("/api/v1/role-permissions/sales_manager/reset/", {}, format="json")
        self.assertEqual(reset.status_code, 200)
        self.assertIn("inventory.manage", capabilities_for(self.manager))
        self.assertEqual(ActivityLog.objects.filter(operation__startswith="role.permissions").count(), 2)

    def test_narrowing_read_never_changes_scope(self):
        self.put("sales_manager", {"customers": {"read": False, "write": False, "delete": False}})
        self.assertNotIn("customers.company", capabilities_for(self.manager))
        self.assertNotIn("customers.scoped", capabilities_for(self.manager))
        api(self.admin).post("/api/v1/role-permissions/sales_manager/reset/", {}, format="json")
        self.assertIn("customers.company", capabilities_for(self.manager))
        self.assertNotIn("customers.scoped", capabilities_for(self.manager))

    def test_the_boundaries_hold(self):
        self.assertEqual(api(self.manager).get("/api/v1/role-permissions/sales_manager/").status_code, 403)
        self.assertEqual(api(self.admin).get("/api/v1/role-permissions/platform_admin/").status_code, 400)
        keys = [row["key"] for row in api(self.admin).get("/api/v1/role-permissions/").json()]
        self.assertEqual(keys, ["sales_agent", "after_sales_agent", "sales_manager", "company_it"])
        refused = self.put("sales_agent", {"audit_team": {"read": True}})
        self.assertFalse(RoleCapabilityOverride.objects.filter(capability="audit.team").exists())
        self.assertEqual(refused.status_code, 400)
        # The store manager's role may carry it.
        self.assertEqual(self.put("sales_manager", {"audit_team": {"read": True}}).status_code, 200)
        self.assertIn("audit.team", capabilities_for(self.manager))


class ReturnedWorkTests(TestCase):
    def setUp(self):
        self.admin = make("w.admin", User.Role.PLATFORM_ADMIN)
        self.manager = make("w.manager", User.Role.SALES_MANAGER, first_name="مدیر")
        self.leaving = make("w.leaving", User.Role.SALES_AGENT, first_name="علی")
        self.staying = make("w.staying", User.Role.SALES_AGENT, first_name="سارا")
        self.spare = make("w.spare", User.Role.SALES_AGENT, first_name="رضا")
        self.campaign = create_campaign(actor=self.manager, name="پاییز", responsibles=[self.leaving, self.staying])
        self.lonely = create_campaign(actor=self.manager, name="تنها", responsibles=[self.leaving])
        self.leads = [create_lead(actor=self.manager, campaign=self.campaign, assignee=self.leaving, source=f"منبع {i}") for i in range(2)]
        self.lonely_lead = create_lead(actor=self.manager, campaign=self.lonely, assignee=self.leaving, source="تنها")
        self.done = create_lead(actor=self.manager, campaign=self.campaign, assignee=self.leaving, source="تمام")
        Lead.objects.filter(pk=self.done.pk).update(status=Lead.Status.COMPLETED)
        self.member = add_campaign_member(actor=self.manager, campaign=self.campaign, full_name="مریم", raw_phone="09125550148", assigned_to=self.leaving)

    def deactivate(self):
        update_crm_user(actor=self.admin, target=self.leaving, is_active=False)

    def test_deactivation_returns_open_work_and_alerts_the_managers(self):
        self.deactivate()
        returned = Lead.objects.filter(returned_from=self.leaving, assigned_to__isnull=True)
        self.assertEqual(set(returned), {*self.leads, self.lonely_lead})
        self.assertEqual(Lead.objects.get(pk=self.done.pk).assigned_to, self.leaving)
        member = TargetAudienceMember.objects.get(pk=self.member.pk)
        self.assertEqual((member.assigned_to, member.returned_from), (None, self.leaving))
        self.assertTrue(ActivityLog.objects.filter(operation="user.work_returned").exists())
        groups = {group["kind"]: group for group in reminders_for(self.manager)["groups"]}
        self.assertIn("returned_work", groups)
        self.assertIn(f"returned_from={self.leaving.pk}", groups["returned_work"]["items"][0]["url"])
        self.assertNotIn("returned_work", {group["kind"] for group in reminders_for(self.staying)["groups"]})
        response = api(self.manager).get(f"/api/v1/leads/?returned_from={self.leaving.pk}")
        self.assertEqual(response.status_code, 200, response.content)
        listed = response.json()["results"]
        self.assertEqual(len(listed), 3)

    def test_split_goes_to_the_campaigns_other_responsibles_and_needs_people_for_the_rest(self):
        self.deactivate()
        missing = api(self.manager).post("/api/v1/returned-work/resolve/", {"from_user": self.leaving.pk, "action": "split"}, format="json")
        self.assertEqual(missing.status_code, 400)
        self.assertIn("fallback_users", missing.json())
        self.assertEqual(Lead.objects.filter(returned_from=self.leaving).count(), 3)
        done = api(self.manager).post("/api/v1/returned-work/resolve/", {
            "from_user": self.leaving.pk, "action": "split", "fallback_users": [self.spare.pk],
        }, format="json")
        self.assertEqual(done.status_code, 200, done.content)
        self.assertEqual(done.json()["assigned_count"], 4)
        for lead in self.leads:
            self.assertEqual(Lead.objects.get(pk=lead.pk).assigned_to, self.staying)
        self.assertEqual(Lead.objects.get(pk=self.lonely_lead.pk).assigned_to, self.spare)
        self.assertEqual(TargetAudienceMember.objects.get(pk=self.member.pk).assigned_to, self.staying)
        self.assertFalse(Lead.objects.filter(returned_from__isnull=False).exists())
        self.assertEqual(LeadAssignmentHistory.objects.filter(from_user=self.leaving, to_user=self.staying).count(), 2)
        self.assertEqual(api(self.manager).get("/api/v1/returned-work/").json(), [])

    def test_assign_hands_everything_to_one_person(self):
        self.deactivate()
        done = api(self.manager).post("/api/v1/returned-work/resolve/", {
            "from_user": self.leaving.pk, "action": "assign", "to_user": self.spare.pk,
        }, format="json")
        self.assertEqual(done.status_code, 200, done.content)
        self.assertEqual(Lead.objects.filter(assigned_to=self.spare).count(), 3)
        self.assertEqual(TargetAudienceMember.objects.get(pk=self.member.pk).assigned_to, self.spare)

    def test_a_marketer_cannot_decide_and_one_by_one_clears_the_mark(self):
        self.deactivate()
        self.assertEqual(api(self.staying).get("/api/v1/returned-work/").status_code, 403)
        self.assertEqual(api(self.staying).post("/api/v1/returned-work/resolve/", {
            "from_user": self.leaving.pk, "action": "assign", "to_user": self.staying.pk,
        }, format="json").status_code, 403)
        reassign_lead(actor=self.manager, lead=self.lonely_lead, to_user=self.spare)
        lead = Lead.objects.get(pk=self.lonely_lead.pk)
        self.assertEqual((lead.assigned_to, lead.returned_from), (self.spare, None))

    def test_the_page_offers_the_decision_to_managers(self):
        self.deactivate()
        self.client.force_login(self.manager)
        page = self.client.get("/leads/")
        self.assertContains(page, 'id="returned-work-dialog"')
        self.client.force_login(self.staying)
        self.assertNotContains(self.client.get("/leads/"), 'id="returned-work-dialog"')
