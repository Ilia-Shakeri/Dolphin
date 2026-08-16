import importlib.util
import json
import unittest
from decimal import Decimal
from pathlib import Path

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.utils import timezone

from accounts.models import User
from sales.models import Customer
from sales.services import create_customer_with_phone, create_lead, create_product, mark_sale


SELENIUM_AVAILABLE = importlib.util.find_spec("selenium") is not None

if SELENIUM_AVAILABLE:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException, WebDriverException
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
        self.manager = User.objects.create_user(
            username="manager.daily.browser",
            password=self.password,
            role=User.Role.SALES_MANAGER,
            first_name="مدیر",
            last_name="روزانه",
        )

    def tearDown(self):
        self.browser.get("about:blank")
        self.wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")
        self.browser.delete_all_cookies()
        for key in ("browser", "performance"):
            self.browser.get_log(key)
        super().tearDown()

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

    def logout(self):
        self.browser.find_element(By.CSS_SELECTOR, "#logout-form button[type='submit']").click()
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

    def open_create_dialog(self, button_id, dialog_id):
        """Click a create button until its dialog is actually open.

        Each page attaches its open-dialog handler only after the initial API
        loads resolve, so a click that lands earlier is silently discarded. On
        SQLite the loads finish in microseconds and this is never observed; real
        PostgreSQL latency makes it reproducible.
        """
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, button_id)))

        def _click_until_open(driver):
            dialog = driver.find_element(By.ID, dialog_id)
            if dialog.get_property("open"):
                return True
            driver.find_element(By.ID, button_id).click()
            return driver.find_element(By.ID, dialog_id).get_property("open")

        self.wait.until(_click_until_open)

    def submit_performance_filter(self, prefix="report"):
        """Filter a performance report only once the panel is really ready.

        The panel renders once on load and again on submit. Clicking before the
        first render has finished proves nothing about filtering, so wait for
        the loaded panel first, then submit and wait for the re-render.
        """
        content = (By.ID, f"{prefix}-performance-content")
        self.wait.until(expected_conditions.visibility_of_element_located(content))
        self.browser.find_element(
            By.CSS_SELECTOR, f"#{prefix}-performance-filter-form button[type='submit']"
        ).click()
        self.wait.until(expected_conditions.visibility_of_element_located(content))

    def test_customer_lead_assignment_history_and_manual_call_flow(self):
        self.browser.set_window_size(1440, 1000)
        self.login()

        self.browser.get(f"{self.live_server_url}/customers/")
        self.open_create_dialog("open-create-customer", "create-customer-dialog")
        self.browser.find_element(By.ID, "create-customer-name").send_keys("مشتری مرورگر")
        self.browser.find_element(By.ID, "create-customer-phone").send_keys("09121110000")
        self.browser.find_element(By.ID, "create-customer-postal-code").send_keys("کد ۱۲۳")
        self.browser.find_element(By.ID, "create-customer-category").send_keys("ویژه")
        self.browser.find_element(By.CSS_SELECTOR, "#create-customer-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/customers/\d+/$"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "customer-detail-content")))
        self.assertEqual(self.browser.find_element(By.TAG_NAME, "h1").text, "جزئیات مشتری")
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
        self.open_create_dialog("open-create-lead", "create-lead-dialog")
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
        self.open_create_dialog("open-create-interaction", "create-interaction-dialog")
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
        inactive_product = create_product(
            actor=self.platform,
            sku="WEB-INACTIVE",
            name="محصول غیرفعال مرورگر",
            current_price=Decimal("5.00"),
        )
        inactive_product.is_active = False
        inactive_product.save(update_fields=["is_active", "updated_at"])
        self.browser.set_window_size(1440, 1000)
        self.login()

        self.browser.get(f"{self.live_server_url}/products/")
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "open-create-product")))
        Select(self.browser.find_element(By.ID, "product-status-filter")).select_by_value("false")
        self.browser.find_element(By.CSS_SELECTOR, "#product-search-form button[type='submit']").click()
        self.wait.until(
            expected_conditions.text_to_be_present_in_element(
                (By.ID, "products-table-body"),
                "محصول غیرفعال مرورگر",
            )
        )
        self.open_create_dialog("open-create-product", "create-product-dialog")
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
        self.open_create_dialog("open-create-sale", "create-sale-dialog")
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
        self.submit_performance_filter()
        self.assertIn(self.platform.username, self.browser.find_element(By.ID, "report-performance-table-body").text)
        export_url = self.browser.find_element(By.ID, "report-performance-xlsx").get_attribute("href")
        self.assertIn("period_start=", export_url)
        self.assertIn("period_end=", export_url)
        export = self.browser.execute_async_script(
            "const done=arguments[0]; fetch(document.getElementById('report-performance-xlsx').href, {credentials:'same-origin'}).then(async r => done([r.status,r.headers.get('content-type'),(await r.arrayBuffer()).byteLength])).catch(e => done([0,String(e),0]));"
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

    def test_manager_category_product_form_and_agent_read_only_browser_flow(self):
        self.browser.set_window_size(1440, 1000)
        self.login(self.manager)

        self.browser.get(f"{self.live_server_url}/product-categories/")
        self.wait.until(
            expected_conditions.visibility_of_element_located(
                (By.ID, "open-create-product-category")
            )
        ).click()
        self.browser.find_element(By.ID, "create-product-category-code").send_keys("browser-goods")
        self.browser.find_element(By.ID, "create-product-category-name").send_keys("کالای مرورگر")
        order = self.browser.find_element(By.ID, "create-product-category-order")
        order.clear()
        order.send_keys("3")
        self.browser.find_element(
            By.CSS_SELECTOR, "#create-product-category-form button[type='submit']"
        ).click()
        self.wait.until(expected_conditions.url_matches(r"/product-categories/\d+/$"))
        category_url = self.browser.current_url
        self.wait.until(
            expected_conditions.visibility_of_element_located(
                (By.ID, "product-category-detail-content")
            )
        )
        self.assertEqual(
            self.browser.find_element(By.ID, "edit-product-category-code").get_attribute("value"),
            "browser-goods",
        )
        self.browser.find_element(By.ID, "toggle-product-category").click()
        self.wait.until(expected_conditions.alert_is_present()).accept()
        self.wait.until(
            expected_conditions.text_to_be_present_in_element_value(
                (By.ID, "product-category-status"), "غیرفعال"
            )
        )
        self.browser.find_element(By.ID, "toggle-product-category").click()
        self.wait.until(expected_conditions.alert_is_present()).accept()
        self.wait.until(
            expected_conditions.text_to_be_present_in_element_value(
                (By.ID, "product-category-status"), "فعال"
            )
        )

        self.browser.get(f"{self.live_server_url}/products/")
        self.wait.until(
            lambda driver: len(Select(driver.find_element(By.ID, "product-category-filter")).options) > 1
        )
        self.open_create_dialog("open-create-product", "create-product-dialog")
        self.browser.find_element(By.ID, "create-product-sku").send_keys("CAT-WEB-1")
        self.browser.find_element(By.ID, "create-product-name").send_keys("محصول دسته‌دار مرورگر")
        Select(self.browser.find_element(By.ID, "create-product-category")).select_by_visible_text("کالای مرورگر")
        self.browser.find_element(By.ID, "create-product-brand").send_keys("برند مرورگر")
        self.browser.find_element(By.ID, "create-product-barcode").send_keys("web-bar-1")
        self.browser.find_element(By.ID, "create-product-price").send_keys("18.50")
        self.browser.find_element(By.CSS_SELECTOR, "#create-product-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/products/\d+/$"))
        product_url = self.browser.current_url
        self.wait.until(
            expected_conditions.visibility_of_element_located((By.ID, "product-detail-content"))
        )
        self.assertEqual(
            Select(self.browser.find_element(By.ID, "edit-product-category")).first_selected_option.text,
            "کالای مرورگر",
        )
        self.assertEqual(
            self.browser.find_element(By.ID, "edit-product-barcode").get_attribute("value"),
            "WEB-BAR-1",
        )

        self.logout()
        self.login(self.agent)
        self.browser.get(f"{self.live_server_url}/product-categories/")
        self.wait.until(expected_conditions.invisibility_of_element_located((By.ID, "product-categories-loading")))
        self.assertFalse(self.browser.find_elements(By.ID, "open-create-product-category"))
        self.assertIn("کالای مرورگر", self.browser.find_element(By.ID, "product-categories-table-body").text)
        self.browser.get(category_url)
        self.wait.until(
            expected_conditions.visibility_of_element_located(
                (By.ID, "product-category-detail-content")
            )
        )
        self.assertFalse(self.browser.find_elements(By.ID, "toggle-product-category"))
        self.assertFalse(
            self.browser.find_elements(
                By.CSS_SELECTOR, "#edit-product-category-form button[type='submit']"
            )
        )
        self.browser.get(product_url)
        self.wait.until(
            expected_conditions.visibility_of_element_located((By.ID, "product-detail-content"))
        )
        self.assertFalse(self.browser.find_elements(By.ID, "deactivate-product"))
        self.assertTrue(self.browser.find_element(By.ID, "edit-product-category").get_attribute("disabled"))
        self.assert_browser_clean()

    def test_manager_to_agent_daily_workflow_and_company_report(self):
        self.browser.set_window_size(1440, 1000)
        self.login(self.manager)

        # The daily operator is provisioned by the platform admin, not by the
        # Sales Manager: user administration is platform_admin only. The manager
        # workflow below still covers catalog, customer, lead, and reporting.
        User.objects.create_user(
            username="daily.agent.browser",
            password=self.password,
            role=User.Role.SALES_AGENT,
            first_name="بازاریاب",
            last_name="روزانه",
        )

        self.browser.get(f"{self.live_server_url}/products/")
        self.open_create_dialog("open-create-product", "create-product-dialog")
        self.browser.find_element(By.ID, "create-product-sku").send_keys("DAILY-1")
        self.browser.find_element(By.ID, "create-product-name").send_keys("محصول روزانه")
        self.browser.find_element(By.ID, "create-product-price").send_keys("20.00")
        self.browser.find_element(By.CSS_SELECTOR, "#create-product-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/products/\d+/$"))

        self.browser.get(f"{self.live_server_url}/customers/")
        self.open_create_dialog("open-create-customer", "create-customer-dialog")
        self.browser.find_element(By.ID, "create-customer-name").send_keys("مشتری مسیر روزانه")
        self.browser.find_element(By.ID, "create-customer-phone").send_keys("09121230001")
        self.browser.find_element(By.CSS_SELECTOR, "#create-customer-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/customers/\d+/$"))

        self.browser.get(f"{self.live_server_url}/leads/")
        self.open_create_dialog("open-create-lead", "create-lead-dialog")
        self.wait.until(lambda driver: len(Select(driver.find_element(By.ID, "create-lead-customer")).options) > 1)
        Select(self.browser.find_element(By.ID, "create-lead-customer")).select_by_visible_text("مشتری مسیر روزانه")
        self.browser.find_element(By.ID, "create-lead-source").send_keys("صف روزانه")
        self.browser.execute_script(
            "const e=document.getElementById('create-lead-follow-up'); e.value='2026-08-13T10:30'; e.dispatchEvent(new Event('change',{bubbles:true}));"
        )
        self.browser.find_element(By.CSS_SELECTOR, "#create-lead-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/leads/\d+/$"))
        lead_url = self.browser.current_url
        lead_id = lead_url.rstrip("/").rsplit("/", 1)[1]
        self.wait.until(lambda driver: len(Select(driver.find_element(By.ID, "reassign-to-user")).options) > 1)
        Select(self.browser.find_element(By.ID, "reassign-to-user")).select_by_visible_text("بازاریاب روزانه")
        self.browser.find_element(By.ID, "reassign-reason").send_keys("صف کار روزانه")
        self.browser.find_element(By.CSS_SELECTOR, "#reassign-lead-form button[type='submit']").click()
        self.wait.until(expected_conditions.text_to_be_present_in_element_value((By.ID, "lead-assigned-to"), "بازاریاب روزانه"))

        self.logout()
        agent = User.objects.get(username="daily.agent.browser")
        self.login(agent)
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "agent-work-queue-body"), "مشتری مسیر روزانه"))
        queue_row = self.browser.find_element(By.CSS_SELECTOR, "#agent-work-queue-body tr")
        self.assertNotEqual(queue_row.find_elements(By.TAG_NAME, "td")[2].text, "—")
        queue_row.find_element(By.LINK_TEXT, "مشتری").click()
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "customer-detail-content")))
        self.assertEqual(self.browser.find_element(By.ID, "edit-customer-name").get_attribute("value"), "مشتری مسیر روزانه")

        self.browser.get(f"{self.live_server_url}/interactions/?lead={lead_id}")
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "create-interaction-dialog")))
        self.assertEqual(Select(self.browser.find_element(By.ID, "create-interaction-lead")).first_selected_option.get_attribute("value"), lead_id)
        self.browser.find_element(By.ID, "create-interaction-phone").send_keys("09121230001")
        Select(self.browser.find_element(By.ID, "create-interaction-direction")).select_by_value("outbound")
        self.browser.find_element(By.ID, "create-interaction-outcome").send_keys("نیاز به پیگیری")
        self.browser.execute_script(
            "const e=document.getElementById('create-interaction-follow-up'); e.value='2026-08-14T11:00'; e.dispatchEvent(new Event('change',{bubbles:true}));"
        )
        self.browser.find_element(By.CSS_SELECTOR, "#create-interaction-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/interactions/\d+/$"))

        self.browser.get(f"{self.live_server_url}/sales/?lead={lead_id}")
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "create-sale-dialog")))
        self.assertEqual(Select(self.browser.find_element(By.ID, "create-sale-lead")).first_selected_option.get_attribute("value"), lead_id)
        Select(self.browser.find_element(By.ID, "create-sale-product")).select_by_visible_text("محصول روزانه — 20.00")
        self.browser.find_element(By.CSS_SELECTOR, "#create-sale-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/sales/\d+/$"))
        sale_url = self.browser.current_url
        # The URL changes on redirect, but the detail page then fetches its own
        # data. Reading the field at redirect time races that fetch: on SQLite
        # the gap is microseconds, on real PostgreSQL under load it is not.
        # Wait for the value, as the manager's pass over the same page below
        # already does.
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "sale-detail-content")))
        self.wait.until(
            expected_conditions.text_to_be_present_in_element_value(
                (By.ID, "sale-seller"), "بازاریاب روزانه"
            )
        )

        self.logout()
        self.login(self.manager)
        self.browser.get(sale_url)
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "sale-detail-content")))
        self.assertEqual(self.browser.find_element(By.ID, "sale-customer").get_attribute("value"), "مشتری مسیر روزانه")
        self.assertEqual(self.browser.find_element(By.ID, "sale-seller").get_attribute("value"), "بازاریاب روزانه")
        self.browser.get(f"{self.live_server_url}/reports/user-performance/")
        self.submit_performance_filter()
        report_text = self.browser.find_element(By.ID, "report-performance-table-body").text
        self.assertIn("daily.agent.browser", report_text)
        self.assertIn("20.00", report_text)
        self.assert_browser_clean()

    def test_sales_document_postal_manager_to_agent_journey(self):
        customer = create_customer_with_phone(
            actor=self.agent, full_name="مشتری سند مرورگر", province="تهران", city="تهران",
            postal_code="1234567890", address="نشانی ثابت مرورگر",
        )
        lead = create_lead(actor=self.agent, customer=customer, source="سند مرورگر")
        from sales.services import assign_lead
        assign_lead(actor=self.manager, lead=lead, to_user=self.agent, reason="document browser scope")
        product = create_product(
            actor=self.manager, sku="DOC-WEB-1", name="محصول سند مرورگر", current_price=Decimal("40.00"),
        )
        sale = mark_sale(actor=self.agent, lead=lead, product=product, quantity=1, sold_at=timezone.now())
        self.browser.set_window_size(1440, 1000)
        self.login(self.manager)
        self.browser.get(f"{self.live_server_url}/sales-documents/")
        try:
            self.wait.until(expected_conditions.element_to_be_clickable((By.ID, "open-create-sales-document")))
        except TimeoutException:
            self.browser.delete_all_cookies()
            self.login(self.manager)
            self.browser.get(f"{self.live_server_url}/sales-documents/")
        self.open_create_dialog("open-create-sales-document", "create-sales-document-dialog")
        self.wait.until(lambda driver: len(Select(driver.find_element(By.ID, "create-sales-document-customer")).options) > 1)
        customer_select = Select(self.browser.find_element(By.ID, "create-sales-document-customer"))
        customer_select.select_by_visible_text("مشتری سند مرورگر")
        self.wait.until(lambda driver: len(Select(driver.find_element(By.ID, "create-sales-document-sale")).options) > 1)
        Select(self.browser.find_element(By.ID, "create-sales-document-sale")).select_by_value(str(sale.pk))
        self.browser.find_element(By.ID, "create-sales-document-number").send_keys("DOC-WEB-100")
        self.browser.find_element(By.ID, "create-sales-document-status").send_keys("ثبت اولیه")
        self.browser.find_element(By.CSS_SELECTOR, "#create-sales-document-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/sales-documents/\d+/$"))
        document_url = self.browser.current_url
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "sales-document-detail-content")))
        self.assertEqual(self.browser.find_element(By.ID, "sales-document-address").get_attribute("value"), "نشانی ثابت مرورگر")
        self.browser.find_element(By.ID, "postal-to-status").send_keys("تحویل پست")
        self.browser.find_element(By.ID, "postal-reason").send_keys("تحویل دستی")
        self.browser.find_element(By.CSS_SELECTOR, "#postal-transition-form button[type='submit']").click()
        self.wait.until(expected_conditions.text_to_be_present_in_element((By.ID, "postal-history-table-body"), "تحویل پست"))

        self.browser.get(f"{self.live_server_url}/reports/sales-documents/")
        self.browser.find_element(By.CSS_SELECTOR, "#sales-document-report-form button[type='submit']").click()
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "sales-document-report-content")))
        self.assertEqual(self.browser.find_element(By.ID, "sales-document-report-total").text, "1")
        self.assertIn("تهران", self.browser.find_element(By.ID, "sales-document-geography-body").text)
        self.assertIn("تحویل پست", self.browser.find_element(By.ID, "sales-document-status-body").text)

        self.assert_browser_clean()

    def test_postal_reason_field_has_its_own_error_target_and_length_limit(self):
        """The reason field's error paragraph must be a real, separate element.

        A missing closing quote on `maxlength` previously swallowed the
        paragraph into the input tag, so `showError()` wrote the message onto an
        `<input>`, where textContent renders nothing.

        Chrome parses `maxlength="500><p class="` with the rules for parsing
        non-negative integers and still yields 500, so the limit itself was NOT
        lost in a real browser; the length assertion below is a guard, and the
        error-target assertions are what discriminate the defect.

        This test deliberately provokes a 400 from the real API, so it does not
        call assert_browser_clean(), which forbids any >=400 response.
        """
        from sales.services import register_sales_document

        customer = create_customer_with_phone(actor=self.manager, full_name="مشتری خطای دلیل")
        document = register_sales_document(
            actor=self.manager,
            customer=customer,
            document_number="DOC-REASON-1",
            postal_status="ثبت اولیه",
        )
        self.browser.set_window_size(1440, 1000)
        self.login(self.manager)
        self.browser.get(f"{self.live_server_url}/sales-documents/{document.pk}/")
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "postal-reason")))

        reason = self.browser.find_element(By.ID, "postal-reason")
        self.assertEqual(reason.get_property("maxLength"), 500)
        self.assertEqual(reason.get_attribute("maxlength"), "500")

        # The discriminating assertions: a distinct paragraph, and an input that
        # did not absorb the paragraph's attributes.
        self.assertEqual(
            len(self.browser.find_elements(By.CSS_SELECTOR, "p[data-error-for='reason']")), 1
        )
        self.assertIsNone(reason.get_attribute("data-error-for"))

        # maxlength bounds typing, not programmatic assignment, so the server
        # rule stays reachable and must surface in the intended element.
        self.browser.execute_script("arguments[0].value = 'x'.repeat(501);", reason)
        self.browser.find_element(By.ID, "postal-to-status").send_keys("تحویل پست")
        self.browser.find_element(
            By.CSS_SELECTOR, "#postal-transition-form button[type='submit']"
        ).click()

        error_node = self.browser.find_element(By.CSS_SELECTOR, "p[data-error-for='reason']")
        self.wait.until(lambda driver: error_node.text.strip() != "")
        self.assertIn("500", error_node.text)
        document.refresh_from_db()
        self.assertEqual(document.postal_status, "ثبت اولیه")

    def test_agent_reads_only_scoped_sales_document(self):
        customer = create_customer_with_phone(actor=self.agent, full_name="مشتری سند عامل")
        lead = create_lead(actor=self.agent, customer=customer)
        from sales.services import assign_lead, register_sales_document
        assign_lead(actor=self.manager, lead=lead, to_user=self.agent, reason="agent document browser scope")
        document = register_sales_document(
            actor=self.manager, customer=customer,
            document_number="DOC-AGENT-WEB", postal_status="ثبت اولیه",
        )
        self.browser.set_window_size(1440, 1000)
        self.login(self.agent)
        self.browser.get(f"{self.live_server_url}/sales-documents/{document.pk}/")
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "sales-document-detail-content")))
        self.assertEqual(self.browser.find_element(By.ID, "sales-document-number").get_attribute("value"), "DOC-AGENT-WEB")
        self.assertEqual(self.browser.find_elements(By.ID, "postal-transition-form"), [])
        self.assert_browser_clean()
