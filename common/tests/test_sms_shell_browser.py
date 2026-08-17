import importlib.util
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache

from accounts.models import User
from communications.services import NormalizedInboundSMSEvent, store_normalized_inbound_sms


SELENIUM_AVAILABLE = importlib.util.find_spec("selenium") is not None

if SELENIUM_AVAILABLE:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions
    from selenium.webdriver.support.ui import WebDriverWait


@unittest.skipUnless(SELENIUM_AVAILABLE, "Selenium is not installed.")
class InboundSMSShellBrowserTests(StaticLiveServerTestCase):
    password = "Strong-pass-983!"

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
        self.manager = User.objects.create_user(
            username="sms.browser.manager",
            password=self.password,
            role=User.Role.SALES_MANAGER,
        )
        self.agent = User.objects.create_user(
            username="sms.browser.agent",
            password=self.password,
            role=User.Role.SALES_AGENT,
        )
        store_normalized_inbound_sms(
            event=NormalizedInboundSMSEvent(
                provider_code="future_provider",
                external_message_id="browser-1",
                sender_normalized="+989121110000",
                recipient_normalized="+989999990000",
                provider_received_at=datetime.now(tz=UTC),
                metadata={"route": "primary"},
            ),
            actor=self.manager,
        )

    def login(self, user):
        self.browser.get(f"{self.live_server_url}/login/")
        self.browser.find_element(By.ID, "login-username").send_keys(user.username)
        self.browser.find_element(By.ID, "login-password").send_keys(self.password)
        self.browser.find_element(By.CSS_SELECTOR, "#login-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_to_be(f"{self.live_server_url}/"))

    def assert_browser_clean(self):
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

    def test_manager_sees_real_report_chart_and_authorized_drilldown(self):
        self.browser.set_window_size(1440, 1000)
        self.login(self.manager)
        self.assertEqual(
            len(self.browser.find_elements(By.CSS_SELECTOR, '#app-sidebar [data-module="inbound-sms-report"]')),
            1,
        )
        self.browser.get(f"{self.live_server_url}/reports/inbound-sms/")
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "inbound-sms-total"), "1"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "inbound-sms-chart")))
        aggregate_button = self.wait.until(
            expected_conditions.element_to_be_clickable((By.CSS_SELECTOR, "#inbound-sms-table-body button"))
        )
        self.browser.execute_script("arguments[0].scrollIntoView({block:'center'});", aggregate_button)
        aggregate_button.click()
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "inbound-sms-drilldown-wrap")))
        detail_button = self.wait.until(
            expected_conditions.element_to_be_clickable((By.CSS_SELECTOR, "#inbound-sms-drilldown-body button"))
        )
        self.browser.execute_script("arguments[0].scrollIntoView({block:'center'});", detail_button)
        detail_button.click()
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "inbound-sms-message-detail")))
        self.assertEqual(self.browser.find_element(By.ID, "inbound-sms-detail-external").text, "browser-1")
        self.assertIn("primary", self.browser.find_element(By.ID, "inbound-sms-detail-metadata").text)
        self.assert_browser_clean()

    def test_agent_menu_hides_report_and_direct_page_is_denied(self):
        self.login(self.agent)
        self.assertEqual(
            self.browser.find_elements(By.CSS_SELECTOR, '#app-sidebar [data-module="inbound-sms-report"]'),
            [],
        )
        self.browser.get(f"{self.live_server_url}/reports/inbound-sms/")
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "app-error-status"), "403"))
        self.assertIn("اجازه مشاهده گزارش پیامک", self.browser.find_element(By.ID, "main-content").text)
