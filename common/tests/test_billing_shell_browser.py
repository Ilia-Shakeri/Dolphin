"""The commercial chain driven through a real browser.

This is the proof that the pages a Client-1 operator actually uses work: a
manager receipts stock, builds a quotation, moves it to an order and then an
invoice, issues it, takes a payment, allocates it, and prints the result —
clicking the same controls a person would.

Every assertion checks a value the server produced, so a page that renders but
does not reach its API fails here rather than looking fine.
"""

import importlib.util
import json
import unittest
from decimal import Decimal
from pathlib import Path

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache

from accounts.models import User
from inventory.models import StockItem
from sales.services import create_customer_with_phone, create_product, create_product_category


SELENIUM_AVAILABLE = importlib.util.find_spec("selenium") is not None

if SELENIUM_AVAILABLE:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions
    from selenium.webdriver.support.ui import Select, WebDriverWait


@unittest.skipUnless(SELENIUM_AVAILABLE, "Selenium is not installed.")
class CommercialChainRealBrowserTests(StaticLiveServerTestCase):
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
        cls.wait = WebDriverWait(cls.browser, 20)

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
            username="manager.billing.browser",
            password=self.password,
            role=User.Role.SALES_MANAGER,
            first_name="مدیر",
            last_name="فروش",
        )
        self.agent = User.objects.create_user(
            username="agent.billing.browser",
            password=self.password,
            role=User.Role.SALES_AGENT,
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری بازرگانی",
            phone={"raw_phone": "09121234500", "is_primary": True},
        )
        category = create_product_category(actor=self.manager, code="browser", name="دسته مرورگر")
        self.product = create_product(
            actor=self.manager,
            sku="BR-1",
            name="کالای مرورگر",
            category=category,
            current_price=Decimal("200.00"),
        )

    def tearDown(self):
        self.browser.get("about:blank")
        self.wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")
        self.browser.delete_all_cookies()
        for key in ("browser", "performance"):
            self.browser.get_log(key)
        super().tearDown()

    # --- harness helpers ---------------------------------------------------

    def login(self, user):
        self.browser.get(f"{self.live_server_url}/login/")
        self.browser.find_element(By.ID, "login-username").send_keys(user.username)
        self.browser.find_element(By.ID, "login-password").send_keys(self.password)
        self.browser.find_element(By.CSS_SELECTOR, "#login-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_to_be(f"{self.live_server_url}/"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "profile-form")))

    def open_create_dialog(self, button_id, dialog_id):
        """Click until the dialog is really open.

        A page attaches its handlers before awaiting network loads, but the
        click can still land before the script has run at all; retrying makes
        the test insensitive to that without hiding a real failure, because it
        still has to open within the wait.
        """
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, button_id)))

        def _click_until_open(driver):
            if driver.find_element(By.ID, dialog_id).get_property("open"):
                return True
            driver.find_element(By.ID, button_id).click()
            return driver.find_element(By.ID, dialog_id).get_property("open")

        self.wait.until(_click_until_open)

    def select_when_populated(self, element_id, value):
        """Choose an option only once the API-driven list has arrived."""
        self.wait.until(
            lambda driver: any(
                option.get_attribute("value") == str(value)
                for option in Select(driver.find_element(By.ID, element_id)).options
            )
        )
        Select(self.browser.find_element(By.ID, element_id)).select_by_value(str(value))

    def value_of(self, element_id):
        return self.browser.find_element(By.ID, element_id).get_attribute("value")

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

    # --- the flow ----------------------------------------------------------

    def test_manager_receipts_stock_then_quotes_orders_invoices_and_takes_payment(self):
        self.browser.set_window_size(1440, 1000)
        self.login(self.manager)

        # 1. Create a warehouse.
        self.browser.get(f"{self.live_server_url}/warehouses/")
        self.open_create_dialog("open-create-warehouse", "create-warehouse-dialog")
        self.browser.find_element(By.ID, "create-warehouse-code").send_keys("browserwh")
        self.browser.find_element(By.ID, "create-warehouse-name").send_keys("انبار مرورگر")
        Select(self.browser.find_element(By.ID, "create-warehouse-default")).select_by_value("true")
        self.browser.find_element(By.CSS_SELECTOR, "#create-warehouse-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/warehouses/\d+/$"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "warehouse-detail-content")))
        self.assertEqual(self.value_of("edit-warehouse-code"), "browserwh")
        warehouse_id = int(self.browser.current_url.rstrip("/").rsplit("/", 1)[-1])

        # 2. Receipt opening stock, and see the level the server computed.
        self.browser.get(f"{self.live_server_url}/stock/")
        self.open_create_dialog("open-create-movement", "create-movement-dialog")
        self.select_when_populated("create-movement-warehouse", warehouse_id)
        self.select_when_populated("create-movement-product", self.product.pk)
        Select(self.browser.find_element(By.ID, "create-movement-type")).select_by_value("opening")
        quantity = self.browser.find_element(By.ID, "create-movement-quantity")
        quantity.clear()
        quantity.send_keys("40")
        self.browser.find_element(By.ID, "create-movement-cost").send_keys("120")
        self.browser.find_element(By.CSS_SELECTOR, "#create-movement-form button[type='submit']").click()
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "stock-items-table-wrap")))
        first_row = self.browser.find_element(By.CSS_SELECTOR, "#stock-items-table-body tr")
        self.assertIn("انبار مرورگر", first_row.text)
        self.assertIn("40", first_row.text)
        self.assertEqual(
            StockItem.objects.get(warehouse_id=warehouse_id, product=self.product).average_cost,
            Decimal("120.00"),
        )

        # 3. Quotation from the catalogue, then through its status graph.
        self.browser.get(f"{self.live_server_url}/quotations/")
        self.open_create_dialog("open-create-quotation", "create-quotation-dialog")
        self.select_when_populated("create-quotation-customer", self.customer.pk)
        self.select_when_populated("create-quotation-product", self.product.pk)
        quotation_quantity = self.browser.find_element(By.ID, "create-quotation-quantity")
        quotation_quantity.clear()
        quotation_quantity.send_keys("3")
        self.browser.find_element(By.CSS_SELECTOR, "#create-quotation-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/quotations/\d+/$"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "quotation-detail-content")))
        # 3 × 200 with tax off by default.
        self.wait.until(lambda driver: self.value_of("quotation-total") == "600.00")
        self.assertEqual(self.value_of("quotation-status"), "پیش‌نویس")

        self.browser.find_element(By.CSS_SELECTOR, "[data-quotation-transition='sent']").click()
        self.browser.switch_to.alert.accept()
        self.wait.until(lambda driver: self.value_of("quotation-status") == "ارسال‌شده")
        self.browser.find_element(By.CSS_SELECTOR, "[data-quotation-transition='accepted']").click()
        self.browser.switch_to.alert.accept()
        self.wait.until(lambda driver: self.value_of("quotation-status") == "پذیرفته‌شده")

        # 4. Convert to an order and confirm it.
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "convert-quotation")))
        self.browser.find_element(By.ID, "convert-quotation").click()
        self.browser.switch_to.alert.accept()
        self.wait.until(expected_conditions.url_matches(r"/orders/\d+/$"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "order-detail-content")))
        self.assertEqual(self.value_of("order-total"), "600.00")
        self.browser.find_element(By.CSS_SELECTOR, "[data-order-transition='confirmed']").click()
        self.browser.switch_to.alert.accept()
        self.wait.until(lambda driver: self.value_of("order-status") == "تأییدشده")

        # 5. Convert to an invoice against the warehouse, and issue it.
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "order-convert-form")))
        self.select_when_populated("order-convert-warehouse", warehouse_id)
        self.browser.find_element(By.CSS_SELECTOR, "#order-convert-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/invoices/\d+/$"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "invoice-detail-content")))
        invoice_id = int(self.browser.current_url.rstrip("/").rsplit("/", 1)[-1])
        self.browser.find_element(By.ID, "issue-invoice").click()
        self.browser.switch_to.alert.accept()
        self.wait.until(lambda driver: self.value_of("invoice-status") == "صادرشده")

        # Issuing really moved the stock: 40 received minus 3 sold.
        self.assertEqual(
            StockItem.objects.get(warehouse_id=warehouse_id, product=self.product).quantity, 37
        )

        # 6. Take a payment and allocate it to the invoice.
        self.browser.get(f"{self.live_server_url}/payments/")
        self.open_create_dialog("open-create-payment", "create-payment-dialog")
        self.select_when_populated("create-payment-customer", self.customer.pk)
        Select(self.browser.find_element(By.ID, "create-payment-method")).select_by_value("cash")
        self.browser.find_element(By.ID, "create-payment-amount").send_keys("250")
        self.browser.find_element(By.CSS_SELECTOR, "#create-payment-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/payments/\d+/$"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "payment-detail-content")))
        self.assertEqual(self.value_of("payment-status"), "تأییدشده")

        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "payment-allocate-form")))
        self.select_when_populated("payment-allocate-invoice", invoice_id)
        self.browser.find_element(By.CSS_SELECTOR, "#payment-allocate-form button[type='submit']").click()
        self.wait.until(lambda driver: self.value_of("payment-allocated") == "250.00")

        # 7. The invoice now shows the payment, and prints the stored snapshot.
        self.browser.get(f"{self.live_server_url}/invoices/{invoice_id}/")
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "invoice-detail-content")))
        self.wait.until(lambda driver: self.value_of("invoice-paid") == "250.00")
        self.assertEqual(self.value_of("invoice-balance"), "350.00")
        self.assertEqual(self.value_of("invoice-settlement"), "تسویه جزئی")

        self.browser.get(f"{self.live_server_url}/invoices/{invoice_id}/print/")
        self.wait.until(expected_conditions.visibility_of_element_located((By.CSS_SELECTOR, ".print-sheet")))
        printed = self.browser.find_element(By.CSS_SELECTOR, ".print-sheet").text
        self.assertIn("مشتری بازرگانی", printed)
        self.assertIn("BR-1", printed)
        self.assertIn("600.00", printed)
        # The printed page carries no navigation to click away from.
        self.assertEqual(self.browser.find_elements(By.ID, "app-sidebar"), [])

        # 8. The receivables report reflects the same numbers.
        self.browser.get(f"{self.live_server_url}/reports/receivables/")
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "receivables-table-wrap")))
        self.assertEqual(self.browser.find_element(By.ID, "receivables-total").text, "350.00")

        self.assert_browser_clean()

    def test_agent_sees_documents_and_no_money_navigation_at_all(self):
        self.browser.set_window_size(1440, 1000)
        self.login(self.agent)
        sidebar = self.browser.find_element(By.ID, "app-sidebar").text
        self.assertIn("اسناد بازرگانی", sidebar)
        self.assertIn("انبار و موجودی", sidebar)
        self.assertNotIn("صندوق و دریافت", sidebar)

        self.browser.get(f"{self.live_server_url}/payments/")
        self.wait.until(expected_conditions.visibility_of_element_located((By.CLASS_NAME, "error-card")))
        self.assertIn("۴۰۳", self.browser.find_element(By.CLASS_NAME, "status-code").text.replace("403", "۴۰۳"))

        # The stock page is readable and offers the agent no way to change it.
        self.browser.get(f"{self.live_server_url}/stock/")
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "stock-search-form")))
        self.assertEqual(self.browser.find_elements(By.ID, "open-create-movement"), [])
        self.assertEqual(self.browser.find_elements(By.ID, "open-transfer-stock"), [])
