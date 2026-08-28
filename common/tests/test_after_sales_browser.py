import importlib.util
import json
import unittest
from pathlib import Path

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache

from accounts.models import User
from sales.services import create_customer_with_phone


SELENIUM_AVAILABLE = importlib.util.find_spec("selenium") is not None

if SELENIUM_AVAILABLE:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions
    from selenium.webdriver.support.ui import Select, WebDriverWait


@unittest.skipUnless(SELENIUM_AVAILABLE, "Selenium is not installed.")
class AfterSalesRealBrowserTests(StaticLiveServerTestCase):
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
            username="after.browser.manager", password=self.password, role=User.Role.SALES_MANAGER,
        )
        self.operator = User.objects.create_user(
            username="after.browser.operator", password=self.password, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES, first_name="اپراتور", last_name="خدمات",
        )
        create_customer_with_phone(actor=self.manager, full_name="مشتری مرورگر خدمات")

    def tearDown(self):
        self.browser.get("about:blank")
        self.wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")
        self.browser.delete_all_cookies()
        for key in ("browser", "performance"):
            self.browser.get_log(key)
        super().tearDown()

    def login(self, user):
        self.browser.get(f"{self.live_server_url}/login/")
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

    def logout(self):
        # Signing out lives in the header user menu now, so it has to be opened
        # first — which is exactly what a user does.
        self.browser.find_element(By.ID, "user-menu-toggle").click()
        self.wait.until(
            expected_conditions.element_to_be_clickable(
                (By.CSS_SELECTOR, "#logout-form button[type='submit']")
            )
        ).click()
        self.wait.until(expected_conditions.url_to_be(f"{self.live_server_url}/login/"))

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

    def test_manager_assigns_operator_updates_assigned_case_and_sees_result(self):
        self.browser.set_window_size(1440, 1000)
        self.login(self.manager)
        self.browser.get(f"{self.live_server_url}/after-sales/")
        # The button is server-rendered, but its click handler is only attached
        # after the page's initial API loads resolve, so a click that lands
        # earlier is silently discarded. Real database latency makes that easy
        # to hit, so click until the dialog is genuinely open.
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "open-create-after-sales")))

        def _click_until_open(driver):
            dialog = driver.find_element(By.ID, "create-after-sales-dialog")
            if dialog.get_property("open"):
                return True
            driver.find_element(By.ID, "open-create-after-sales").click()
            return driver.find_element(By.ID, "create-after-sales-dialog").get_property("open")

        self.wait.until(_click_until_open)
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "create-after-sales-customer")))
        # The dialog now opens as soon as the page renders rather than only
        # after its lookup loads resolve, so wait for the options themselves.
        for select_id in ("create-after-sales-customer", "create-after-sales-assigned"):
            self.wait.until(
                lambda driver, node=select_id: len(Select(driver.find_element(By.ID, node)).options) > 1
            )
        Select(self.browser.find_element(By.ID, "create-after-sales-customer")).select_by_visible_text("مشتری مرورگر خدمات")
        Select(self.browser.find_element(By.ID, "create-after-sales-assigned")).select_by_visible_text("اپراتور خدمات")
        self.browser.find_element(By.ID, "create-after-sales-subject").send_keys("پیگیری مرورگر")
        self.browser.find_element(By.ID, "create-after-sales-status").send_keys("جدید")
        self.browser.find_element(By.ID, "create-after-sales-description").send_keys("شرح ثبت واقعی پرونده")
        self.browser.find_element(By.CSS_SELECTOR, "#create-after-sales-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/after-sales/\d+/$"))
        case_url = self.browser.current_url
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "after-sales-detail-content")))
        self.assertEqual(self.browser.find_element(By.ID, "after-sales-assigned-detail").get_attribute("value"), "اپراتور خدمات")

        self.logout()
        self.login(self.operator)
        self.assertIn("میز کار خدمات پس از فروش", self.browser.find_element(By.TAG_NAME, "h1").text)
        self.assertEqual(len(self.browser.find_elements(By.CSS_SELECTOR, '[data-module="after-sales"]')), 1)
        for module in ("customers", "leads", "interactions", "products", "sales", "sales-documents", "users", "audit"):
            self.assertEqual(len(self.browser.find_elements(By.CSS_SELECTOR, f'[data-module="{module}"]')), 0)
        self.browser.get(case_url)
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "after-sales-detail-content")))
        self.assertEqual(len(self.browser.find_elements(By.ID, "after-sales-assign-form")), 0)
        self.browser.find_element(By.ID, "after-sales-to-status").send_keys("در حال پیگیری")
        self.browser.find_element(By.ID, "after-sales-status-reason").send_keys("تماس دستی")
        self.browser.find_element(By.CSS_SELECTOR, "#after-sales-status-form button[type='submit']").click()
        self.wait.until(expected_conditions.text_to_be_present_in_element_value((By.ID, "after-sales-status-detail"), "در حال پیگیری"))
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "after-sales-history-body"), "تغییر وضعیت"))

        self.logout()
        self.login(self.manager)
        self.browser.get(case_url)
        self.wait.until(expected_conditions.text_to_be_present_in_element_value((By.ID, "after-sales-status-detail"), "در حال پیگیری"))
        self.assertEqual(len(self.browser.find_elements(By.ID, "after-sales-assign-form")), 1)
        self.assertEqual(len(self.browser.find_elements(By.ID, "close-after-sales")), 1)
        self.assert_browser_clean()
