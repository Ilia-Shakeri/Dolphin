"""The user profile page: who may open which one, and what it renders.

Since 2.19.0 `/users/<id>/` is the one person profile for a colleague —
what used to be the «جزئیات کاربر» page (User Management) and the seller
«پروفایل» page (`/users/<id>/profile/`) are tabs of it. Who may open it is the
union of the scopes those two pages had, plus the reader themselves:

- the accounts they administer (`users.manage_*`),
- the people whose performance they may read (`users_for_performance_report`),
- their own.

`/users/<id>/profile/` and `/profile/` redirect to it, on its «عملکرد» tab.
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
        response = self.client.get(f"/users/{self.agent.pk}/")
        self.assertEqual(response.status_code, 200)
        page = response.content.decode("utf-8")
        self.assertIn("سارا احمدی", page)
        # Shown the way it is written in Iran, dialled in E.164.
        self.assertIn("۰۹۱۲۰۰۰۰۰۰۰", page)
        self.assertIn('href="tel:+989120000000"', page)

    def test_an_agent_may_not_open_another_agents_profile(self):
        self.client.force_login(self.agent)
        response = self.client.get(f"/users/{self.other_agent.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_a_manager_may_open_any_sellers_profile(self):
        self.client.force_login(self.manager)
        response = self.client.get(f"/users/{self.agent.pk}/")
        self.assertEqual(response.status_code, 200)
        page = response.content.decode("utf-8")
        self.assertIn("سارا احمدی", page)
        self.assertIn('data-profile-tab="performance"', page)

    def test_an_after_sales_agent_has_a_profile_but_no_performance_tab(self):
        """Their own page opens — everyone has one — but the report behind
        «عملکرد» refuses them, so the tab is not rendered at all."""
        self.client.force_login(self.after_sales_agent)
        response = self.client.get(f"/users/{self.after_sales_agent.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-profile-tab="performance"')
        self.assertNotContains(response, 'id="profile-performance-filter-form"')

    def test_the_short_link_redirects_to_the_callers_own_profile(self):
        self.client.force_login(self.agent)
        response = self.client.get("/profile/")
        self.assertRedirects(response, f"/users/{self.agent.pk}/?tab=performance")

    def test_the_old_profile_address_redirects_to_the_performance_tab(self):
        self.client.force_login(self.manager)
        response = self.client.get(f"/users/{self.agent.pk}/profile/")
        self.assertRedirects(response, f"/users/{self.agent.pk}/?tab=performance")

    def test_the_requested_tab_opens_first(self):
        self.client.force_login(self.manager)
        page = self.client.get(f"/users/{self.agent.pk}/?tab=performance").content.decode("utf-8")
        self.assertIn('data-active-tab="performance"', page)
        self.assertIn('id="profile-pane-overview" role="tabpanel" aria-labelledby="profile-tab-overview" data-profile-pane="overview" hidden', page)

    def test_an_unknown_or_withheld_tab_falls_back_to_the_overview(self):
        self.client.force_login(self.agent)
        page = self.client.get(f"/users/{self.agent.pk}/?tab=access").content.decode("utf-8")
        self.assertIn('data-active-tab="overview"', page)
        self.assertNotIn('data-profile-tab="access"', page)

    def test_the_target_user_id_is_carried_for_the_scripts_to_read(self):
        self.client.force_login(self.manager)
        page = self.client.get(f"/users/{self.agent.pk}/").content.decode("utf-8")
        self.assertIn(f'data-target-user-id="{self.agent.pk}"', page)
        self.assertIn('data-target-username="prof.agent"', page)
        self.assertIn(f'data-person-id="{self.agent.pk}"', page)

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
