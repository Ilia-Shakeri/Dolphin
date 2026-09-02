"""The lead follow-up calendar page: who gets a link to it, and that it opens."""

from django.test import TestCase

from accounts.models import User


PASSWORD = "Strong-pass-937!"


class LeadCalendarPageTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="cal.page.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="cal.page.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.after_sales_agent = User.objects.create_user(
            username="cal.page.aftersales", password=PASSWORD, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )

    def test_a_manager_can_open_the_calendar(self):
        self.client.force_login(self.manager)
        response = self.client.get("/leads/calendar/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="lead-calendar"', response.content.decode("utf-8"))

    def test_an_agent_can_open_the_calendar(self):
        self.client.force_login(self.agent)
        response = self.client.get("/leads/calendar/")
        self.assertEqual(response.status_code, 200)

    def test_the_fullcalendar_bundle_is_loaded_only_on_this_page(self):
        self.client.force_login(self.manager)
        page = self.client.get("/leads/calendar/").content.decode("utf-8")
        self.assertIn("plugins/custom/fullcalendar/fullcalendar.bundle.js", page)
        home = self.client.get("/").content.decode("utf-8")
        self.assertNotIn("plugins/custom/fullcalendar", home)

    def test_the_nav_link_is_offered_alongside_leads(self):
        self.client.force_login(self.manager)
        page = self.client.get("/").content.decode("utf-8")
        self.assertIn('href="/leads/calendar/"', page)
        self.assertIn("تقویم پیگیری", page)

    def test_the_nav_link_is_absent_for_after_sales(self):
        self.client.force_login(self.after_sales_agent)
        page = self.client.get("/").content.decode("utf-8")
        self.assertNotIn('href="/leads/calendar/"', page)

    def test_a_signed_out_visitor_is_sent_to_login(self):
        response = self.client.get("/leads/calendar/")
        self.assertRedirects(response, "/login/")
