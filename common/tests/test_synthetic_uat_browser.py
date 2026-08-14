import importlib.util
import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.core.management import call_command


SELENIUM_AVAILABLE = importlib.util.find_spec("selenium") is not None

if SELENIUM_AVAILABLE:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions
    from selenium.webdriver.support.ui import WebDriverWait


@unittest.skipUnless(SELENIUM_AVAILABLE, "Selenium is not installed.")
class SyntheticUatRealBrowserTests(StaticLiveServerTestCase):
    password = "Uat-Only-Safe-Pass-963!"

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
        self.browser.get("about:blank")
        self.browser.delete_all_cookies()
        self.browser.get_log("browser")
        self.browser.get_log("performance")
        environment = {
            "KARIZ_ALLOW_UAT_SEED": "1",
            "KARIZ_UAT_PASSWORD": self.password,
            "TEMP": tempfile.gettempdir(),
            "TMP": tempfile.gettempdir(),
        }
        if os.environ.get("SystemRoot"):
            environment["SystemRoot"] = os.environ["SystemRoot"]
        with patch.dict(os.environ, environment, clear=True), patch(
            "accounts.management.commands.seed_synthetic_uat.Command._database_is_allowed",
            return_value=True,
        ):
            call_command(
                "seed_synthetic_uat",
                confirm_synthetic_data=True,
                stdout=StringIO(),
                stderr=StringIO(),
            )

    def tearDown(self):
        self.browser.get("about:blank")
        self.browser.delete_all_cookies()
        for key in ("browser", "performance"):
            self.browser.get_log(key)
        super().tearDown()

    def login(self, username):
        self.browser.get(f"{self.live_server_url}/login/")
        self.browser.find_element(By.ID, "login-username").send_keys(username)
        self.browser.find_element(By.ID, "login-password").send_keys(self.password)
        self.browser.find_element(By.CSS_SELECTOR, "#login-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_to_be(f"{self.live_server_url}/"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "profile-form")))
        self.wait.until(
            expected_conditions.text_to_be_present_in_element_value(
                (By.ID, "profile-username"),
                username,
            )
        )

    def modules(self):
        return {
            item.get_attribute("data-module")
            for item in self.browser.find_elements(By.CSS_SELECTOR, "#app-sidebar [data-module]")
        }

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

    def test_platform_admin_persona(self):
        self.browser.set_window_size(1440, 1000)
        self.login("uat_platform_admin")
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "dashboard-title"), "پنل مدیر پلتفرم"))
        self.assertTrue({"customers", "sales", "after-sales", "users", "audit"}.issubset(self.modules()))
        self.assert_browser_clean()

    def test_store_manager_persona(self):
        self.browser.set_window_size(1440, 1000)
        self.login("uat_sales_manager")
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "dashboard-title"), "پنل مدیر فروشگاه"))
        self.assertTrue({"customers", "sales", "after-sales", "users", "performance"}.issubset(self.modules()))
        self.assertNotIn("audit", self.modules())
        self.browser.get(f"{self.live_server_url}/users/")
        self.wait.until(expected_conditions.invisibility_of_element_located((By.ID, "users-loading")))
        rows = self.browser.find_element(By.ID, "users-table-body").text
        self.assertIn("uat_sales_agent", rows)
        self.assertIn("uat_after_sales_operator", rows)
        self.assertNotIn("uat_platform_admin", rows)
        self.assert_browser_clean()

    def test_call_center_agent_persona(self):
        self.browser.set_window_size(1440, 1000)
        self.login("uat_sales_agent")
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "dashboard-title"), "میز کار بازاریاب"))
        self.assertTrue({"customers", "leads", "interactions", "products", "sales", "performance"}.issubset(self.modules()))
        self.assertTrue({"after-sales", "users", "audit"}.isdisjoint(self.modules()))
        self.wait.until(expected_conditions.invisibility_of_element_located((By.ID, "agent-work-queue-loading")))
        self.assertIn("مشتری ساختگی آزمون پذیرش", self.browser.find_element(By.ID, "agent-work-queue-body").text)
        self.assert_browser_clean()

    def test_after_sales_operator_persona(self):
        self.browser.set_window_size(1440, 1000)
        self.login("uat_after_sales_operator")
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "dashboard-title"), "میز کار خدمات پس از فروش"))
        self.assertIn("after-sales", self.modules())
        self.assertTrue(
            {"customers", "leads", "interactions", "products", "sales", "performance", "users", "audit"}.isdisjoint(self.modules())
        )
        self.browser.get(f"{self.live_server_url}/after-sales/")
        self.wait.until(expected_conditions.invisibility_of_element_located((By.ID, "after-sales-loading")))
        self.assertIn("پرونده ساختگی خدمات پس از فروش", self.browser.find_element(By.ID, "after-sales-table-body").text)
        self.assert_browser_clean()
