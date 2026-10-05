"""Every sidebar link a role is shown opens for that role (2.39.26).

The menu is drawn from the same capability and feature checks the pages enforce;
this keeps the two in step: no role is offered a page that answers 403/404, for
each role and workstream.
"""

import re

from django.core.cache import cache
from django.test import TestCase

from accounts.models import User

PASSWORD = "Strong-pass-937!"
LINK = re.compile(r'<a data-module="([^"]+)"[^>]*href="(/[^"]*)"')


class SidebarReachabilityTests(TestCase):
    def setUp(self):
        cache.clear()

    def sidebar_links(self, html):
        start = html.index('id="app-sidebar"')
        return LINK.findall(html[start:])

    def check(self, user):
        self.client.force_login(user)
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        links = self.sidebar_links(page.content.decode("utf-8"))
        self.assertTrue(links, user.username)
        for module, href in links:
            with self.subTest(role=user.role, workstream=user.workstream, module=module, href=href):
                response = self.client.get(href)
                self.assertIn(response.status_code, (200, 302), f"{module} {href}")

    def test_each_role_reaches_every_link_it_is_shown(self):
        cases = [
            (User.Role.SALES_AGENT, User.Workstream.SALES),
            (User.Role.SALES_AGENT, User.Workstream.AFTER_SALES),
            (User.Role.SALES_MANAGER, User.Workstream.SALES),
            (User.Role.COMPANY_IT, User.Workstream.SALES),
            (User.Role.PLATFORM_ADMIN, User.Workstream.SALES),
        ]
        for index, (role, workstream) in enumerate(cases):
            user = User.objects.create_user(
                username=f"nav.{index}", password=PASSWORD, role=role, workstream=workstream
            )
            self.check(user)

    def test_a_marketer_is_not_shown_money_pages(self):
        agent = User.objects.create_user(username="nav.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.client.force_login(agent)
        modules = {module for module, _ in self.sidebar_links(self.client.get("/").content.decode("utf-8"))}
        self.assertFalse(modules & {"payments", "disbursements", "cheques", "installments", "receivables-report", "profit-report"})


class PageNamesMatchTheMenuTests(TestCase):
    """A page's <title> and breadcrumb read exactly as its menu entry (2.40.0)."""

    TITLE = re.compile(r"<title>(.*?) \|", re.S)
    LINK = re.compile(r'<a (?:id="[^"]+" )?data-module="([^"]+)" class="menu-link" href="(/[^"]*)">(?:<span class="menu-bullet">.*?</span></span>)?\s*(?:<span class="menu-icon">.*?</span>\s*)?<span class="menu-title">(.*?)</span>', re.S)

    def test_title_and_breadcrumb_equal_the_menu_label(self):
        cache.clear()
        for index, role in enumerate((User.Role.SALES_MANAGER, User.Role.PLATFORM_ADMIN, User.Role.SALES_AGENT)):
            user = User.objects.create_user(username=f"names.{index}", password=PASSWORD, role=role)
            self.client.force_login(user)
            home = self.client.get("/").content.decode("utf-8")
            sidebar = home[home.index('id="app-sidebar"'):]
            links = self.LINK.findall(sidebar)
            self.assertGreater(len(links), 5, role)
            for module, href, label in links:
                if href == "/":
                    continue  # the dashboard's title names the role's own panel
                page = self.client.get(href)
                if page.status_code != 200:
                    continue
                html = page.content.decode("utf-8")
                crumb = re.search(r'<li class="breadcrumb-item text-gray-900">(.*?)</li>', html, re.S)
                with self.subTest(role=role, module=module):
                    self.assertEqual(self.TITLE.search(html).group(1).strip(), label.strip())
                    self.assertEqual(crumb.group(1).strip(), label.strip())
