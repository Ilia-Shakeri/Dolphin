import importlib.util
import json
import unittest
from pathlib import Path

from django.core.cache import cache
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from accounts.models import User


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

    def login(self, user=None):
        user = user or self.platform
        self.browser.get(f"{self.live_server_url}/login/")
        self.browser.find_element(By.ID, "login-username").send_keys(user.username)
        self.browser.find_element(By.ID, "login-password").send_keys(self.password)
        self.browser.find_element(By.CSS_SELECTOR, "#login-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_to_be(f"{self.live_server_url}/"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "profile-form")))
        self.wait.until(
            expected_conditions.text_to_be_present_in_element_value(
                (By.ID, "profile-username"),
                user.username,
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

        self.assertEqual(self.browser.find_element(By.ID, "profile-username").get_attribute("value"), self.platform.username)
        self.assertEqual(self.browser.find_element(By.ID, "profile-role").get_attribute("value"), "مدیر پلتفرم")
        self.assertTrue(self.browser.find_element(By.ID, "app-sidebar").is_displayed())
        self.browser.find_element(By.CSS_SELECTOR, "#logout-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_to_be(f"{self.live_server_url}/login/"))
        self.assert_browser_clean()

    def test_mobile_navigation_and_user_list_flow(self):
        self.browser.set_window_size(390, 844)
        self.login()

        toggle = self.browser.find_element(By.ID, "nav-toggle")
        self.assertTrue(toggle.is_displayed())
        toggle.click()
        self.wait.until(lambda driver: "nav-open" in driver.find_element(By.TAG_NAME, "body").get_attribute("class").split())
        self.browser.get(f"{self.live_server_url}/users/")
        self.wait.until(expected_conditions.invisibility_of_element_located((By.ID, "users-loading")))
        self.assertIn(self.platform.username, self.browser.find_element(By.ID, "users-table-body").text)
        self.assert_browser_clean()

    def test_role_aware_landing_and_menus_for_three_experiences(self):
        self.browser.set_window_size(1440, 1000)
        cases = (
            (self.platform, "پنل مدیر پلتفرم", {"users", "audit"}, set()),
            (self.manager, "پنل مدیر فروشگاه", {"users"}, {"audit"}),
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
                if user.role == User.Role.SALES_MANAGER:
                    self.browser.get(f"{self.live_server_url}/users/")
                    self.wait.until(expected_conditions.invisibility_of_element_located((By.ID, "users-loading")))
                    rows = self.browser.find_element(By.ID, "users-table-body").text
                    self.assertIn(self.agent.username, rows)
                    self.assertNotIn(self.platform.username, rows)
                    self.assertNotIn(self.manager.username, rows)
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
