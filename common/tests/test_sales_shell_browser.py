import importlib.util
import json
import unittest
from decimal import Decimal
from pathlib import Path

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.utils import timezone

from accounts.models import User
from sales.models import Customer
from sales.services import create_customer_with_phone, create_lead, mark_sale


SELENIUM_AVAILABLE = importlib.util.find_spec("selenium") is not None

if SELENIUM_AVAILABLE:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions
    from selenium.webdriver.support.ui import Select, WebDriverWait


@unittest.skipUnless(SELENIUM_AVAILABLE, "Selenium is not installed.")
class SalesShellRealBrowserTests(StaticLiveServerTestCase):
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
        cls.wait = WebDriverWait(cls.browser, 10)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.quit()
        super().tearDownClass()

    def setUp(self):
        self.platform = User.objects.create_user(
            username="platform.sales.browser",
            password=self.password,
            role=User.Role.PLATFORM_ADMIN,
        )
        self.agent = User.objects.create_user(
            username="agent.sales.browser",
            password=self.password,
            role=User.Role.SALES_AGENT,
            first_name="کارشناس",
            last_name="مرورگر",
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

    def test_customer_lead_assignment_history_and_manual_call_flow(self):
        self.browser.set_window_size(1440, 1000)
        self.login()

        self.browser.get(f"{self.live_server_url}/customers/")
        self.wait.until(expected_conditions.invisibility_of_element_located((By.ID, "customers-loading")))
        self.browser.find_element(By.ID, "open-create-customer").click()
        self.browser.find_element(By.ID, "create-customer-name").send_keys("مشتری مرورگر")
        self.browser.find_element(By.ID, "create-customer-phone").send_keys("09121110000")
        self.browser.find_element(By.ID, "create-customer-postal-code").send_keys("کد ۱۲۳")
        self.browser.find_element(By.ID, "create-customer-category").send_keys("ویژه")
        self.browser.find_element(By.CSS_SELECTOR, "#create-customer-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/customers/\d+/$"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "customer-detail-content")))
        customer_url = self.browser.current_url
        self.assertEqual(self.browser.find_element(By.ID, "edit-customer-name").get_attribute("value"), "مشتری مرورگر")
        self.assertEqual(self.browser.find_element(By.ID, "edit-customer-postal-code").get_attribute("value"), "کد ۱۲۳")
        self.assertEqual(self.browser.find_element(By.ID, "edit-customer-category").get_attribute("value"), "ویژه")

        self.browser.find_element(By.ID, "open-create-phone").click()
        self.browser.find_element(By.ID, "phone-raw").send_keys("۰۹۱۲۹۹۹۰۰۰۰")
        self.browser.find_element(By.ID, "phone-label").send_keys("همراه دوم")
        self.browser.find_element(By.CSS_SELECTOR, "#phone-form button[type='submit']").click()
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "phones-table-body"), "+989129990000"))

        self.browser.get(f"{self.live_server_url}/leads/")
        self.wait.until(expected_conditions.invisibility_of_element_located((By.ID, "leads-loading")))
        self.browser.find_element(By.ID, "open-create-lead").click()
        self.wait.until(lambda driver: len(Select(driver.find_element(By.ID, "create-lead-customer")).options) > 1)
        Select(self.browser.find_element(By.ID, "create-lead-customer")).select_by_visible_text("مشتری مرورگر")
        self.browser.find_element(By.ID, "create-lead-source").send_keys("ثبت دستی مرورگر")
        self.browser.find_element(By.CSS_SELECTOR, "#create-lead-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/leads/\d+/$"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "lead-detail-content")))
        self.wait.until(lambda driver: len(Select(driver.find_element(By.ID, "reassign-to-user")).options) > 1)
        Select(self.browser.find_element(By.ID, "reassign-to-user")).select_by_visible_text("کارشناس مرورگر")
        self.browser.find_element(By.ID, "reassign-reason").send_keys("تخصیص دستی")
        self.browser.find_element(By.CSS_SELECTOR, "#reassign-lead-form button[type='submit']").click()
        self.wait.until(expected_conditions.text_to_be_present_in_element_value((By.ID, "lead-assigned-to"), "کارشناس مرورگر"))
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "history-table-body"), "کارشناس مرورگر"))

        self.browser.get(f"{self.live_server_url}/interactions/")
        self.wait.until(expected_conditions.invisibility_of_element_located((By.ID, "interactions-loading")))
        self.browser.find_element(By.ID, "open-create-interaction").click()
        self.wait.until(lambda driver: len(Select(driver.find_element(By.ID, "create-interaction-lead")).options) > 1)
        Select(self.browser.find_element(By.ID, "create-interaction-lead")).select_by_index(1)
        self.browser.find_element(By.ID, "create-interaction-phone").send_keys("09121110000")
        self.browser.find_element(By.ID, "create-interaction-outcome").send_keys("پاسخ دستی")
        self.browser.find_element(By.CSS_SELECTOR, "#create-interaction-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/interactions/\d+/$"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "interaction-detail-content")))
        self.assertEqual(self.browser.find_element(By.ID, "interaction-agent").get_attribute("value"), self.platform.username)
        self.assertEqual(self.browser.find_element(By.ID, "interaction-outcome").get_attribute("value"), "پاسخ دستی")

        customer = Customer.objects.get(full_name="مشتری مرورگر")
        mark_sale(
            actor=self.platform,
            lead=customer.leads.get(),
            total_amount=Decimal("25.00"),
            sold_at=timezone.now(),
        )

        self.browser.get(customer_url)
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "customer-detail-content")))
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "customer-leads-table-body"), "ثبت دستی مرورگر"))
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "customer-interactions-table-body"), "پاسخ دستی"))
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "customer-sales-table-body"), "25.00"))
        self.browser.find_element(By.ID, "deactivate-customer").click()
        self.wait.until(expected_conditions.alert_is_present()).accept()
        self.wait.until(expected_conditions.text_to_be_present_in_element_value((By.ID, "customer-active"), "غیرفعال"))
        self.assert_browser_clean()

    def test_product_sale_report_export_and_activity_log_flow(self):
        customer = create_customer_with_phone(actor=self.platform, full_name="مشتری فروش مرورگر")
        create_lead(actor=self.platform, customer=customer, source="ثبت مستقیم مرورگر")
        self.browser.set_window_size(1440, 1000)
        self.login()

        self.browser.get(f"{self.live_server_url}/products/")
        self.wait.until(expected_conditions.invisibility_of_element_located((By.ID, "products-loading")))
        self.browser.find_element(By.ID, "open-create-product").click()
        self.browser.find_element(By.ID, "create-product-sku").send_keys("WEB-1")
        self.browser.find_element(By.ID, "create-product-name").send_keys("محصول مرورگر")
        self.browser.find_element(By.ID, "create-product-price").send_keys("12.50")
        self.browser.find_element(By.CSS_SELECTOR, "#create-product-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/products/\d+/$"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "product-detail-content")))
        price = self.browser.find_element(By.ID, "edit-product-price")
        price.clear()
        price.send_keys("15.00")
        self.browser.find_element(By.CSS_SELECTOR, "#edit-product-form button[type='submit']").click()
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "global-message"), "محصول ذخیره شد"))

        self.browser.get(f"{self.live_server_url}/sales/")
        self.wait.until(expected_conditions.invisibility_of_element_located((By.ID, "sales-loading")))
        self.browser.find_element(By.ID, "open-create-sale").click()
        self.wait.until(lambda driver: len(Select(driver.find_element(By.ID, "create-sale-lead")).options) > 1)
        Select(self.browser.find_element(By.ID, "create-sale-lead")).select_by_visible_text("مشتری فروش مرورگر — ثبت مستقیم مرورگر")
        Select(self.browser.find_element(By.ID, "create-sale-product")).select_by_visible_text("محصول مرورگر — 15.00")
        quantity = self.browser.find_element(By.ID, "create-sale-quantity")
        quantity.clear()
        quantity.send_keys("2")
        self.browser.find_element(By.CSS_SELECTOR, "#create-sale-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/sales/\d+/$"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "sale-detail-content")))
        self.assertEqual(Decimal(self.browser.find_element(By.ID, "sale-total").get_attribute("value")), Decimal("30.00"))
        self.assertEqual(self.browser.find_element(By.ID, "sale-seller").get_attribute("value"), self.platform.username)
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "sale-cancel-section")))
        self.browser.find_element(By.ID, "cancel-sale-reason").send_keys("لغو مجاز مرورگر")
        self.browser.find_element(By.CSS_SELECTOR, "#cancel-sale-form button[type='submit']").click()
        self.wait.until(expected_conditions.text_to_be_present_in_element_value((By.ID, "sale-detail-status"), "لغوشده"))

        self.browser.get(f"{self.live_server_url}/reports/user-performance/")
        self.browser.find_element(By.CSS_SELECTOR, "#performance-filter-form button[type='submit']").click()
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "performance-content")))
        self.assertIn(self.platform.username, self.browser.find_element(By.ID, "performance-table-body").text)
        export_url = self.browser.find_element(By.ID, "performance-xlsx").get_attribute("href")
        self.assertIn("period_start=", export_url)
        self.assertIn("period_end=", export_url)
        export = self.browser.execute_async_script(
            "const done=arguments[0]; fetch(document.getElementById('performance-xlsx').href, {credentials:'same-origin'}).then(async r => done([r.status,r.headers.get('content-type'),(await r.arrayBuffer()).byteLength])).catch(e => done([0,String(e),0]));"
        )
        self.assertEqual(export[0], 200)
        self.assertIn("spreadsheetml", export[1])
        self.assertGreater(export[2], 1000)

        self.browser.get(f"{self.live_server_url}/activity-logs/")
        self.wait.until(expected_conditions.invisibility_of_element_located((By.ID, "activity-logs-loading")))
        self.assertIn("sale.cancelled", self.browser.find_element(By.ID, "activity-logs-table-body").text)
        self.browser.find_element(By.CSS_SELECTOR, "#activity-logs-table-body a").click()
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "activity-log-detail-content")))
        self.assert_browser_clean()
