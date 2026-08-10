import importlib.util
import json
import unittest
from pathlib import Path

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
        cls.wait = WebDriverWait(cls.browser, 10)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.quit()
        super().tearDownClass()

    def setUp(self):
        self.platform = User.objects.create_user(
            username="platform.browser",
            password=self.password,
            role=User.Role.PLATFORM_ADMIN,
        )

    def login(self):
        self.browser.get(f"{self.live_server_url}/login/")
        self.browser.find_element(By.ID, "login-username").send_keys(self.platform.username)
        self.browser.find_element(By.ID, "login-password").send_keys(self.password)
        self.browser.find_element(By.CSS_SELECTOR, "#login-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_to_be(f"{self.live_server_url}/"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "profile-form")))

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
