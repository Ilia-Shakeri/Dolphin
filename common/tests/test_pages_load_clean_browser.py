"""Every served page loads its script without a single browser error.

The panel's script is a tree of ES modules resolved through an import map, so a
wrong import path, a missing export or a name that did not survive a move
surfaces only in a real browser, on the one page that needs it. This opens each
page that needs no record id, waits for its own loading placeholders to clear,
and fails on any error the browser logged — an uncaught exception, a module that
did not resolve, or a static file that answered 404.
"""

import importlib.util
import time
import unittest
from pathlib import Path

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from accounts.models import User
from sales.models import Customer, Lead, Product

SELENIUM_AVAILABLE = importlib.util.find_spec("selenium") is not None

if SELENIUM_AVAILABLE:
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException

#: Pages that take no record id, by URL name.
PAGES = (
    "home", "users", "my-profile", "customers", "leads", "lead-calendar", "lead-board",
    "interactions", "products", "product-categories", "warehouses", "stock-levels",
    "stock-movements", "sales", "orders", "order-board", "invoices", "payments",
    "disbursements", "cheques", "installments", "sales-documents", "after-sales",
    "after-sales-calendar", "user-performance", "sales-document-report", "inbound-sms-report",
    "outbound-sms", "chat", "integrations", "sms-provider-settings", "post-provider-settings",
    "receivables-report", "profit-report", "stock-valuation-report", "customer-ledger",
    "activity-logs", "branding-settings", "settings",
)

#: Pages that belong to an ordinary CRM user rather than to the platform administrator:
#: the profile page asks for that person's own performance figures, which a platform
#: administrator has none of.
PAGES_FOR_A_MANAGER = {"my-profile"}

#: The placeholders a page shows while its script is still fetching (the chat drawer keeps
#: its own off-screen one, which says nothing about the page).
BUSY_SCRIPT = """
return Array.from(document.querySelectorAll('[id$="-loading"], .placeholder-glow, [aria-busy="true"]'))
    .filter(node => !node.hidden && node.offsetParent !== null && !node.closest('[data-dolphin-drawer]')).length;
"""


@unittest.skipUnless(SELENIUM_AVAILABLE, "Selenium is not installed.")
@override_settings(DEPLOYMENT_PROFILE_ENABLES_ALL_FEATURES=True)
class EveryPageLoadsCleanTests(StaticLiveServerTestCase):
    password = "Strong-pass-451!"

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
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
        try:
            cls.browser = webdriver.Chrome(options=options)
        except WebDriverException as exc:
            super().tearDownClass()
            raise unittest.SkipTest(f"Chrome WebDriver unavailable: {exc.msg}") from exc

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.quit()
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            username="pages.admin", password=self.password, role=User.Role.PLATFORM_ADMIN
        )
        customer = Customer.objects.create(full_name="مشتری آزمون صفحه‌ها", created_by=self.admin)
        Lead.objects.create(customer=customer, created_by=self.admin)
        Product.objects.create(
            sku="PAGES-1", name="محصول آزمون", current_price="100.00",
            created_by=self.admin, updated_by=self.admin,
        )
        self.manager = User.objects.create_user(
            username="pages.manager", password=self.password, role=User.Role.SALES_MANAGER
        )
        self.sign_in(self.admin)

    def sign_in(self, user):
        from django.test import Client

        client = Client()
        client.force_login(user)
        self.browser.delete_all_cookies()
        self.browser.get(f"{self.live_server_url}/login/")
        self.browser.add_cookie({"name": "sessionid", "value": client.cookies["sessionid"].value, "path": "/"})

    def settle(self):
        deadline = time.time() + 12
        while time.time() < deadline:
            done = self.browser.execute_script("return document.readyState") == "complete"
            if done and self.browser.execute_script(BUSY_SCRIPT) == 0:
                break
            time.sleep(0.2)
        time.sleep(0.4)

    def test_no_page_logs_a_browser_error(self):
        offenders = []
        for name in PAGES:
            with self.subTest(page=name):
                self.sign_in(self.manager if name in PAGES_FOR_A_MANAGER else self.admin)
                self.browser.get_log("browser")
                self.browser.get(f"{self.live_server_url}{reverse(f'common_ui:{name}')}")
                self.settle()
                errors = [
                    f'{entry["message"][:300]}'
                    for entry in self.browser.get_log("browser")
                    if entry["level"] == "SEVERE"
                ]
                if errors:
                    offenders.append((name, errors))
                self.assertEqual(errors, [], name)
        self.assertEqual(offenders, [])
