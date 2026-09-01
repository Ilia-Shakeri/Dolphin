"""Capture screenshots of the served UI for visual review.

Not an assertion suite: this drives the real browser against the real static
files so a human (or the agent) can compare the result with the Metronic
reference. It is skipped unless DOLPHIN_VISUAL_CAPTURE names an output directory,
so it never runs as part of the normal suite.
"""

import importlib.util
import os
import unittest
from decimal import Decimal
from pathlib import Path

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache

from accounts.models import User
from billing.services import create_invoice, create_quotation, issue_invoice
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.models import Customer
from sales.services import create_customer_with_phone, create_lead, create_product, create_product_category


SELENIUM_AVAILABLE = importlib.util.find_spec("selenium") is not None
CAPTURE_DIR = os.environ.get("DOLPHIN_VISUAL_CAPTURE", "")

if SELENIUM_AVAILABLE:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions
    from selenium.webdriver.support.ui import WebDriverWait


@unittest.skipUnless(SELENIUM_AVAILABLE and CAPTURE_DIR, "Set DOLPHIN_VISUAL_CAPTURE to a directory.")
class VisualCaptureTests(StaticLiveServerTestCase):
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
        options.add_argument("--hide-scrollbars")
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
        self.manager = User.objects.create_user(
            username="visual.manager", password=self.password, role=User.Role.SALES_MANAGER,
            first_name="مدیر", last_name="فروش",
        )
        category = create_product_category(actor=self.manager, code="visual", name="دسته نمونه")
        self.product = create_product(
            actor=self.manager, sku="UI-1001", name="دستگاه تصفیه آب خانگی",
            category=category, current_price=Decimal("12500000.00"),
        )
        self.warehouse = create_warehouse(
            actor=self.manager, code="visualwh", name="انبار مرکزی تهران", is_default=True
        )
        record_stock_movement(
            actor=self.manager, warehouse=self.warehouse, product=self.product,
            movement_type=StockMovement.MovementType.OPENING, quantity=40,
            unit_cost=Decimal("9000000.00"),
        )
        for index in range(1, 8):
            customer = create_customer_with_phone(
                actor=self.manager,
                full_name=f"شرکت بازرگانی نمونه {index}",
                phone={"raw_phone": f"0912111{index:04d}", "is_primary": True},
            )
            customer.city = "تهران"
            customer.province = "تهران"
            customer.category = "طلایی"
            customer.save()
            create_lead(actor=self.manager, customer=customer, source="manual")
        first = Customer.objects.order_by("id").first()
        create_quotation(actor=self.manager, customer=first, items=[{"product": self.product, "quantity": 2}])
        issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.manager, customer=first,
                items=[{"product": self.product, "quantity": 1}], warehouse=self.warehouse,
            ),
        )

    def login(self):
        self.browser.get(f"{self.live_server_url}/login/")
        self.browser.find_element(By.ID, "login-username").send_keys(self.manager.username)
        self.browser.find_element(By.ID, "login-password").send_keys(self.password)
        self.browser.find_element(By.CSS_SELECTOR, "#login-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_to_be(f"{self.live_server_url}/"))

    def capture(self, name, path, width=1440, height=1000, settle=None):
        self.browser.set_window_size(width, height)
        self.browser.get(f"{self.live_server_url}{path}")
        if settle:
            try:
                self.wait.until(expected_conditions.visibility_of_element_located((By.ID, settle)))
            except Exception:  # noqa: BLE001 - a capture must not fail the run
                pass
        self.browser.execute_script("return document.fonts ? document.fonts.ready : true")
        target = Path(CAPTURE_DIR) / f"{name}.png"
        self.browser.save_screenshot(str(target))

    def test_capture_pages(self):
        self.capture("01-login-desktop", "/login/")
        self.login()
        for name, path, settle in (
            ("02-dashboard", "/", "dashboard-title"),
            ("03-customers", "/customers/", "customers-table-wrap"),
            ("04-leads", "/leads/", "leads-table-wrap"),
            ("05-products", "/products/", "products-table-wrap"),
            ("06-stock", "/stock/", "stock-items-table-wrap"),
            ("07-orders", "/orders/", "orders-table-wrap"),
            ("08-invoices", "/invoices/", "invoices-table-wrap"),
            ("09-payments", "/payments/", "payments-table-wrap"),
            ("10-receivables", "/reports/receivables/", None),
            ("11-performance", "/reports/user-performance/", None),
        ):
            self.capture(name, path, settle=settle)
        customer = Customer.objects.order_by("id").first()
        self.capture("12-customer-detail", f"/customers/{customer.pk}/", settle="customer-detail-content")
        # Mobile, to prove the responsive grid rather than assume it.
        self.capture("20-dashboard-mobile", "/", width=390, height=900)
        self.capture("21-customers-mobile", "/customers/", width=390, height=900)

        severe = [entry for entry in self.browser.get_log("browser") if entry["level"] == "SEVERE"]
        print("SEVERE_CONSOLE:", severe[:5])
