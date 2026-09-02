"""The seller profile page: who may open which one, and what it renders.

Mirrors the scope story everywhere else in this module: `reports.own` /
`reports.company` decide whether the page opens at all, and
`users_for_performance_report` decides whose id may follow `/users/<id>/profile/`
— a Sales Agent's own id and nobody else's, any crm identity's id for an
elevated role. `/profile/` is the same page reached without knowing your own id.
"""

from django.test import TestCase

from accounts.models import User


PASSWORD = "Strong-pass-937!"


class SellerProfileAccessTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="prof.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="prof.agent", password=PASSWORD, role=User.Role.SALES_AGENT,
            first_name="سارا", last_name="احمدی", phone="09120000000",
        )
        self.other_agent = User.objects.create_user(
            username="prof.other", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.after_sales_agent = User.objects.create_user(
            username="prof.aftersales", password=PASSWORD, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )

    def test_an_agent_may_open_their_own_profile(self):
        self.client.force_login(self.agent)
        response = self.client.get(f"/users/{self.agent.pk}/profile/")
        self.assertEqual(response.status_code, 200)
        page = response.content.decode("utf-8")
        self.assertIn("سارا احمدی", page)
        self.assertIn("09120000000", page)

    def test_an_agent_may_not_open_another_agents_profile(self):
        self.client.force_login(self.agent)
        response = self.client.get(f"/users/{self.other_agent.pk}/profile/")
        self.assertEqual(response.status_code, 404)

    def test_a_manager_may_open_any_sellers_profile(self):
        self.client.force_login(self.manager)
        response = self.client.get(f"/users/{self.agent.pk}/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("سارا احمدی", response.content.decode("utf-8"))

    def test_an_after_sales_agent_has_no_profile_page(self):
        self.client.force_login(self.after_sales_agent)
        response = self.client.get(f"/users/{self.after_sales_agent.pk}/profile/")
        self.assertEqual(response.status_code, 403)

    def test_the_short_link_redirects_to_the_callers_own_profile(self):
        self.client.force_login(self.agent)
        response = self.client.get("/profile/")
        self.assertRedirects(response, f"/users/{self.agent.pk}/profile/")

    def test_the_target_user_id_is_carried_for_the_scripts_to_read(self):
        self.client.force_login(self.manager)
        page = self.client.get(f"/users/{self.agent.pk}/profile/").content.decode("utf-8")
        self.assertIn(f'data-target-user-id="{self.agent.pk}"', page)
        self.assertIn('data-target-username="prof.agent"', page)

    def test_the_own_profile_menu_entry_is_offered_to_a_sales_agent(self):
        self.client.force_login(self.agent)
        page = self.client.get("/").content.decode("utf-8")
        self.assertIn('id="open-own-performance"', page)
        self.assertIn('href="/profile/"', page)

    def test_the_own_profile_menu_entry_is_absent_for_after_sales(self):
        self.client.force_login(self.after_sales_agent)
        page = self.client.get("/").content.decode("utf-8")
        self.assertNotIn('id="open-own-performance"', page)

    def test_a_signed_out_visitor_is_sent_to_login(self):
        response = self.client.get("/profile/")
        self.assertRedirects(response, "/login/")
