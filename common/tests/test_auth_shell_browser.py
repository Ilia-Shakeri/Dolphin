import importlib.util
import json
import unittest
from pathlib import Path

from django.core.cache import cache
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.utils import timezone

from accounts.models import User
from sales.models import Customer, Lead, Product, Sale


SELENIUM_AVAILABLE = importlib.util.find_spec("selenium") is not None

if SELENIUM_AVAILABLE:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions
    from selenium.webdriver.support.ui import WebDriverWait


@unittest.skipUnless(SELENIUM_AVAILABLE, "Selenium is not installed.")
class AuthShellRealBrowserTests(StaticLiveServerTestCase):
    password = "Strong-pass-937!"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        options = webdriver.ChromeOptions()
        chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        if chrome.exists():
            options.binary_location = str(chrome)
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.set_capability("goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"})
        try:
            cls.browser = webdriver.Chrome(options=options)
        except WebDriverException as exc:
            super().tearDownClass()
            raise unittest.SkipTest(f"Chrome WebDriver unavailable: {exc.msg}") from exc
        cls.wait = WebDriverWait(cls.browser, 15)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.quit()
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        self.browser.delete_all_cookies()
        self.browser.get_log("browser")
        self.browser.get_log("performance")
        self.platform = User.objects.create_user(
            username="platform.browser",
            password=self.password,
            role=User.Role.PLATFORM_ADMIN,
        )
        self.manager = User.objects.create_user(
            username="manager.browser",
            password=self.password,
            role=User.Role.SALES_MANAGER,
        )
        self.agent = User.objects.create_user(
            username="agent.browser",
            password=self.password,
            role=User.Role.SALES_AGENT,
        )
        self.product = Product.objects.create(
            sku="BROWSER-DASHBOARD",
            name="محصول آزمون داشبورد",
            current_price="100.00",
            created_by=self.manager,
            updated_by=self.manager,
        )
        agent_customer = Customer.objects.create(full_name="مشتری بازاریاب", created_by=self.agent)
        manager_customer = Customer.objects.create(full_name="مشتری مدیر", created_by=self.manager)
        agent_lead = Lead.objects.create(
            customer=agent_customer,
            assigned_to=self.agent,
            assigned_by=self.manager,
            assigned_at=timezone.now(),
            created_by=self.manager,
        )
        manager_lead = Lead.objects.create(customer=manager_customer, created_by=self.manager)
        sold_at = timezone.now()
        Sale.objects.create(
            lead=agent_lead, customer=agent_customer, sold_by=self.agent, product=self.product,
            quantity=1, unit_price_snapshot="100.00", total_amount="100.00", sold_at=sold_at,
        )
        Sale.objects.create(
            lead=manager_lead, customer=manager_customer, sold_by=self.manager, product=self.product,
            quantity=1, unit_price_snapshot="200.00", total_amount="200.00", sold_at=sold_at,
        )

    def login(self, user=None):
        user = user or self.platform
        self.browser.get(f"{self.live_server_url}/login/")
        login_mark = self.browser.find_element(By.CSS_SELECTOR, ".brand-mark-login")
        self.assertTrue(login_mark.is_displayed())
        self.assertGreater(self.browser.execute_script("return arguments[0].naturalWidth", login_mark), 0)
        self.browser.find_element(By.ID, "login-username").send_keys(user.username)
        self.browser.find_element(By.ID, "login-password").send_keys(self.password)
        self.browser.find_element(By.CSS_SELECTOR, "#login-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_to_be(f"{self.live_server_url}/"))
        # The account button is the proof the shell rendered signed in. It is
        # the button and not the name beside it: the name carries `d-none
        # d-md-flex`, so a visibility wait on it can never pass on mobile.
        #
        # The profile form used to stand in for all of this and no longer can —
        # it lives in a dialog now, and is not visible until it is opened.
        self.wait.until(
            expected_conditions.visibility_of_element_located((By.ID, "user-menu-toggle"))
        )
        # Read rather than seen, so this holds at any width: the element
        # is in the DOM on mobile too, just not displayed.
        self.wait.until(
            lambda driver: user.get_full_name() or user.username
            in driver.execute_script(
                "return document.getElementById('user-menu-username').textContent"
            )
        )

    def assert_browser_clean(self):
        self.assertEqual(self.browser.execute_script("return document.documentElement.lang"), "fa")
        self.assertEqual(self.browser.execute_script("return document.documentElement.dir"), "rtl")
        severe = [entry for entry in self.browser.get_log("browser") if entry["level"] == "SEVERE"]
        self.assertEqual(severe, [])
        failed = []
        for entry in self.browser.get_log("performance"):
            message = json.loads(entry["message"])["message"]
            if message["method"] != "Network.responseReceived":
                continue
            response = message["params"]["response"]
            if response["url"].startswith(self.live_server_url) and response["status"] >= 400:
                failed.append((response["status"], response["url"]))
        self.assertEqual(failed, [])

    def test_desktop_login_profile_and_logout_flow(self):
        self.browser.set_window_size(1440, 1000)
        self.login()

        # The profile moved out of the dashboard and into a dialog on the
        # account menu, so reaching it is now part of what this test covers.
        self.browser.find_element(By.ID, "user-menu-toggle").click()
        self.browser.find_element(By.ID, "open-profile").click()
        self.wait.until(
            expected_conditions.visibility_of_element_located((By.ID, "profile-form"))
        )
        self.wait.until(
            expected_conditions.text_to_be_present_in_element_value(
                (By.ID, "profile-username"), self.platform.username
            )
        )
        self.assertEqual(self.browser.find_element(By.ID, "profile-role").get_attribute("value"), "مدیر پلتفرم")
        # And it closes again, so the rest of the flow is not behind a modal.
        self.browser.find_element(
            By.CSS_SELECTOR, "#profile-dialog [data-close-dialog]"
        ).click()
        self.wait.until_not(
            expected_conditions.visibility_of_element_located((By.ID, "profile-form"))
        )
        self.assertTrue(self.browser.find_element(By.ID, "app-sidebar").is_displayed())
        sidebar_mark = self.browser.find_element(By.CSS_SELECTOR, ".brand-mark-sidebar")
        self.assertTrue(sidebar_mark.is_displayed())
        self.assertGreater(self.browser.execute_script("return arguments[0].naturalWidth", sidebar_mark), 0)
        # Signing out lives in the header user menu now, so it has to be opened
        # first — which is exactly what a user does.
        self.browser.find_element(By.ID, "user-menu-toggle").click()
        self.wait.until(
            expected_conditions.element_to_be_clickable(
                (By.CSS_SELECTOR, "#logout-form button[type='submit']")
            )
        ).click()
        self.wait.until(expected_conditions.url_to_be(f"{self.live_server_url}/login/"))
        self.assert_browser_clean()

    def test_mobile_navigation_and_user_list_flow(self):
        self.browser.set_window_size(390, 844)
        self.login()

        toggle = self.browser.find_element(By.ID, "nav-toggle")
        self.assertTrue(toggle.is_displayed())
        mobile_mark = self.browser.find_element(By.CSS_SELECTOR, ".brand-mark-mobile")
        self.assertTrue(mobile_mark.is_displayed())
        self.assertGreater(self.browser.execute_script("return arguments[0].naturalWidth", mobile_mark), 0)
        toggle.click()
        # The sidebar is the theme's own drawer now, so its open state is the
        # `drawer-on` class the theme sets — not a second class of our own.
        self.wait.until(
            lambda driver: "drawer-on"
            in driver.find_element(By.ID, "app-sidebar").get_attribute("class").split()
        )
        self.assertEqual(
            self.browser.find_element(By.ID, "nav-toggle").get_attribute("aria-expanded"), "true"
        )
        self.browser.get(f"{self.live_server_url}/users/")
        self.wait.until(expected_conditions.invisibility_of_element_located((By.ID, "users-loading")))
        self.assertIn(self.platform.username, self.browser.find_element(By.ID, "users-table-body").text)
        self.assert_browser_clean()

    def test_role_aware_landing_and_menus_for_three_experiences(self):
        self.browser.set_window_size(1440, 1000)
        # User administration is platform_admin only, so the Sales Manager
        # navigation carries no user module and the page itself is denied.
        cases = (
            (self.platform, "پنل مدیر پلتفرم", {"users", "audit"}, set()),
            (self.manager, "پنل مدیر فروشگاه", set(), {"users", "audit"}),
            (self.agent, "میز کار بازاریاب", set(), {"users", "audit"}),
        )
        for user, title, visible, hidden in cases:
            with self.subTest(role=user.role):
                self.browser.delete_all_cookies()
                self.login(user)
                self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "dashboard-title"), title))
                modules = {
                    item.get_attribute("data-module")
                    for item in self.browser.find_elements(By.CSS_SELECTOR, "#app-sidebar [data-module]")
                }
                self.assertTrue(visible.issubset(modules))
                self.assertTrue(hidden.isdisjoint(modules))
                # The denial of /users/ for non-admin roles is asserted at the
                # Django level (accounts/tests/test_user_administration_policy.py
                # and common/tests/test_auth_shell.py). Requesting it here would
                # log an expected 403 and defeat assert_browser_clean().
                if user.role == User.Role.PLATFORM_ADMIN:
                    self.browser.get(f"{self.live_server_url}/users/{self.agent.pk}/")
                    self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "user-detail-content")))
                    toggle = self.browser.find_element(By.ID, "toggle-user-active")
                    self.assertEqual(toggle.text, "غیرفعال کردن کاربر")
                    toggle.click()
                    self.wait.until(expected_conditions.alert_is_present()).accept()
                    self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "toggle-user-active"), "فعال کردن دوباره کاربر"))
                    self.browser.find_element(By.ID, "toggle-user-active").click()
                    self.wait.until(expected_conditions.alert_is_present()).accept()
                    self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "toggle-user-active"), "غیرفعال کردن کاربر"))
                self.assert_browser_clean()

    def chart_names(self, chart_id):
        """The category labels ApexCharts drew, once it has drawn them.

        Two things this has to do that reading `.text` off the container did
        not. Apex renders asynchronously, so the element is present and empty
        for a moment after the panel's KPIs have already filled in — a bare read
        races it. And Apex puts a `<title>` next to each label's `tspan` for its
        own tooltip, so the label group's text contains every name twice; the
        `tspan` alone is the name.
        """
        chart = self.browser.find_element(By.ID, chart_id)
        selector = ".apexcharts-yaxis-label tspan"
        self.wait.until(lambda driver: chart.find_elements(By.CSS_SELECTOR, selector))
        return [
            node.get_attribute("textContent").strip()
            for node in chart.find_elements(By.CSS_SELECTOR, selector)
        ]

    def test_manager_and_agent_dashboard_data_stay_role_scoped(self):
        self.browser.set_window_size(1440, 1000)

        self.login(self.manager)
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "dashboard-performance-content")))
        self.assertEqual(
            self.browser.find_element(By.CSS_SELECTOR, '[data-performance-panel="dashboard"] [data-kpi="sales_count"]').text,
            "2",
        )
        self.assertTrue(self.browser.find_element(By.ID, "dashboard-user").is_displayed())
        manager_chart = self.chart_names("dashboard-performance-chart")
        self.assertIn(self.manager.username, manager_chart)
        self.assertIn(self.agent.username, manager_chart)
        self.assert_browser_clean()

        self.browser.delete_all_cookies()
        self.login(self.agent)
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "dashboard-performance-content")))
        self.assertEqual(
            self.browser.find_element(By.CSS_SELECTOR, '[data-performance-panel="dashboard"] [data-kpi="sales_count"]').text,
            "1",
        )
        self.assertEqual(self.browser.find_elements(By.ID, "dashboard-user"), [])
        agent_chart = self.chart_names("dashboard-performance-chart")
        self.assertIn(self.agent.username, agent_chart)
        self.assertNotIn(self.manager.username, agent_chart)
        self.assert_browser_clean()
