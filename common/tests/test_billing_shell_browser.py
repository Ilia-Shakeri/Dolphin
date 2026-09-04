"""The commercial chain driven through a real browser.

This is the proof that the pages a Client-1 operator actually uses work: a
manager receipts stock, builds an order and then an
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
from billing.models import Cheque, Invoice, Payment
from billing.payments import register_payment
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
        # The account button is the proof the shell rendered signed in. It is
        # the button and not the name beside it: the name carries `d-none
        # d-md-flex`, so a visibility wait on it can never pass on mobile.
        #
        # The profile form used to stand in for all of this and no longer can —
        # it lives in a dialog now, and is not visible until it is opened.
        self.wait.until(
            expected_conditions.visibility_of_element_located((By.ID, "user-menu-toggle"))
        )

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

    def set_hidden_select(self, element, value):
        """Choose a value on a `<select>` the searchable wrapper has hidden.

        `choose_searchable` below is the right tool where the control has ids to
        find it by. Rows built at runtime — an allocation line, an invoice line —
        have no ids, and once the wrapper binds it hides the native control, so
        Selenium will not click its options. Setting the value and firing the
        `change` a click would have fired is the same end state.
        """
        self.wait.until(
            lambda driver: any(
                option.get_attribute("value") == str(value)
                for option in Select(element).options
            )
        )
        self.browser.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
            element,
            str(value),
        )

    def choose_searchable(self, element_id, value):
        """Pick from a search-box-over-select the way an operator does.

        `Select.select_by_value` cannot be used once the script has swapped the
        native control for the search box: Selenium refuses to drive an element
        that is not visible, and rightly — nobody can click what nobody can see.
        Typing and clicking a suggestion is the path a person actually takes, so
        it is the one worth testing.
        """
        self.wait.until(
            lambda driver: any(
                option.get_attribute("value") == str(value)
                for option in Select(
                    driver.find_element(By.ID, element_id)
                ).options
            )
        )
        label = next(
            option.text
            for option in Select(self.browser.find_element(By.ID, element_id)).options
            if option.get_attribute("value") == str(value)
        )
        search = self.browser.find_element(By.ID, f"{element_id}-search")
        search.clear()
        search.send_keys(label)
        option = self.wait.until(
            expected_conditions.element_to_be_clickable(
                (By.CSS_SELECTOR, f"#{element_id}-options li")
            )
        )
        option.click()
        self.wait.until(
            lambda driver: driver.find_element(By.ID, element_id).get_attribute("value")
            == str(value)
        )

    def value_of(self, element_id):
        return self.browser.find_element(By.ID, element_id).get_attribute("value")

    def advance_wizard(self, dialog_id):
        """Click a create dialog's own "بعدی" past the step currently shown.

        The invoice and order dialogs became real `KTStepper` wizards in
        1.11.0: a later step's fields are not visible — and Selenium refuses
        to click what is not visible — until that step becomes current. A
        click that `KTStepper` itself refused (an invalid required field on
        the step being left) leaves the same content div "current", which is
        exactly what this waits past.
        """
        current = self.browser.find_element(
            By.CSS_SELECTOR, f"#{dialog_id} [data-kt-stepper-element='content'].current"
        )
        self.browser.find_element(
            By.CSS_SELECTOR, f"#{dialog_id} [data-kt-stepper-action='next']"
        ).click()
        self.wait.until(
            lambda driver: "current" not in current.get_attribute("class").split()
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

    # --- the flow ----------------------------------------------------------

    def test_manager_receipts_stock_then_orders_invoices_and_takes_payment(self):
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

        # 3. Build the order directly from the catalogue.
        # The dialog became a 3-step wizard in 1.11.0: customer/warehouse/
        # shipping first, the (now multi-capable) item rows second, a review
        # step last — `advance_wizard` is what moves between them.
        self.browser.get(f"{self.live_server_url}/orders/")
        self.open_create_dialog("open-create-order", "create-order-dialog")
        self.choose_searchable("create-order-customer", self.customer.pk)
        self.select_when_populated("create-order-warehouse", warehouse_id)
        self.advance_wizard("create-order-dialog")
        order_line = self.wait.until(
            lambda driver: driver.find_element(
                By.CSS_SELECTOR, "#create-order-lines [data-line-row]"
            )
        )
        self.set_hidden_select(
            order_line.find_element(By.CSS_SELECTOR, "[data-line-product]"), self.product.pk
        )
        order_quantity = order_line.find_element(By.CSS_SELECTOR, "[data-line-quantity]")
        order_quantity.clear()
        order_quantity.send_keys("3")
        self.advance_wizard("create-order-dialog")
        self.browser.find_element(By.CSS_SELECTOR, "#create-order-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/orders/\d+/$"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "order-detail-content")))
        # 3 × 200 with tax off by default.
        # Every amount on a served page now reads as grouped rial with no
        # fraction — the same string a person sees.
        self.assertEqual(self.value_of("order-total"), "۶۰۰ ریال")
        order_id = int(self.browser.current_url.rstrip("/").rsplit("/", 1)[-1])
        # Approving the warehouse-backed order moves stock once.
        Select(self.browser.find_element(By.ID, "order-status-select")).select_by_value("confirmed")
        self.browser.switch_to.alert.accept()
        self.wait.until(
            lambda driver: Select(
                driver.find_element(By.ID, "order-status-select")
            ).first_selected_option.get_attribute("value") == "confirmed"
        )

        # 5. Raise an invoice on its own — Client-1 invoices first — then issue
        # it and attach it to the order afterwards.
        self.browser.get(f"{self.live_server_url}/invoices/")
        self.open_create_dialog("open-create-invoice", "create-invoice-dialog")
        self.choose_searchable("create-invoice-customer", self.customer.pk)
        # The dialog became a 3-step wizard in 1.11.0: customer/type/date
        # first, the item rows and discount second, a review step last.
        self.advance_wizard("create-invoice-dialog")
        # One line row is offered as soon as the products arrive; «افزودن کالا»
        # adds more. An invoice can carry several products since 1.4.0, where it
        # used to take exactly one.
        line = self.wait.until(
            lambda driver: driver.find_element(
                By.CSS_SELECTOR, "#create-invoice-lines [data-line-row]"
            )
        )
        self.set_hidden_select(line.find_element(By.CSS_SELECTOR, "[data-line-product]"), self.product.pk)
        quantity = line.find_element(By.CSS_SELECTOR, "[data-line-quantity]")
        quantity.clear()
        quantity.send_keys("3")
        self.advance_wizard("create-invoice-dialog")
        self.browser.find_element(By.CSS_SELECTOR, "#create-invoice-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/invoices/\d+/$"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "invoice-detail-content")))
        invoice_id = int(self.browser.current_url.rstrip("/").rsplit("/", 1)[-1])
        # Issuing runs from the status select; the issue/cancel box is gone.
        Select(self.browser.find_element(By.ID, "invoice-status-select")).select_by_value("issued")
        self.browser.switch_to.alert.accept()
        self.wait.until(
            lambda driver: Select(
                driver.find_element(By.ID, "invoice-status-select")
            ).first_selected_option.get_attribute("value") == "issued"
        )

        # Issuing moved no stock: the order owns the inventory lifecycle, and
        # deducting here as well would take the same goods out twice.
        self.assertEqual(
            StockItem.objects.get(warehouse_id=warehouse_id, product=self.product).quantity, 37
        )

        # The invoice can be attached to the order after both already exist.
        Invoice.objects.filter(pk=invoice_id).update(order_id=order_id)
        self.browser.get(f"{self.live_server_url}/orders/{order_id}/")
        self.wait.until(
            expected_conditions.text_to_be_present_in_element(
                (By.ID, "order-invoices-table-body"), "INV-"
            )
        )

        # 6. Take a payment and allocate it to the invoice.
        self.browser.get(f"{self.live_server_url}/payments/")
        self.open_create_dialog("open-create-payment", "create-payment-dialog")
        self.choose_searchable("create-payment-customer", self.customer.pk)
        # The method is a mode now, not a dropdown: each one shows only the
        # fields it collects. Cash is selected by default.
        self.assertEqual(
            self.browser.find_element(By.ID, "create-payment-method").get_attribute("value"),
            "cash",
        )
        self.assertFalse(self.browser.find_element(By.ID, "create-payment-bank-fields").is_displayed())
        self.assertFalse(self.browser.find_element(By.ID, "create-payment-cheque-fields").is_displayed())

        # Switching to the transfer mode reveals its fields and only its fields.
        self.browser.find_element(By.CSS_SELECTOR, '[data-payment-mode="bank_transfer"]').click()
        self.assertEqual(
            self.browser.find_element(By.ID, "create-payment-method").get_attribute("value"),
            "bank_transfer",
        )
        self.assertTrue(self.browser.find_element(By.ID, "create-payment-bank-fields").is_displayed())
        self.assertFalse(self.browser.find_element(By.ID, "create-payment-cheque-fields").is_displayed())

        # And the cheque mode swaps them over, and shows its own warning.
        self.browser.find_element(By.CSS_SELECTOR, '[data-payment-mode="cheque"]').click()
        self.assertTrue(self.browser.find_element(By.ID, "create-payment-cheque-fields").is_displayed())
        self.assertFalse(self.browser.find_element(By.ID, "create-payment-bank-fields").is_displayed())
        self.assertTrue(self.browser.find_element(By.ID, "create-payment-cheque-note").is_displayed())

        # Back to cash to record the receipt this test is actually about.
        self.browser.find_element(By.CSS_SELECTOR, '[data-payment-mode="cash"]').click()
        self.browser.find_element(By.ID, "create-payment-amount").send_keys("250")
        self.browser.find_element(By.CSS_SELECTOR, "#create-payment-form button[type='submit']").click()
        self.wait.until(expected_conditions.url_matches(r"/payments/\d+/$"))
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "payment-detail-content")))
        # The status is a two-value select since 1.3.7, so its `value` is the
        # stored word and its selected option is what the reader sees. Both are
        # checked: the wrong one passing would mean the page showed a Persian
        # label over an English value or the reverse.
        self.assertEqual(self.value_of("payment-status"), "confirmed")
        self.assertEqual(
            Select(self.browser.find_element(By.ID, "payment-status"))
            .first_selected_option.text,
            "تأییدشده",
        )

        # One allocation form since 1.3.14, and it opens with a row already in
        # it — settling a receipt against one invoice is the common case, so it
        # should not start by asking the reader to press «افزودن فاکتور». The
        # invoice picker is searchable now, but the real `<select>` underneath is
        # still the value that submits, which is what this drives.
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "payment-allocate-form")))
        picker = self.wait.until(
            lambda driver: driver.find_element(By.CSS_SELECTOR, "#payment-split-rows [data-split-invoice]")
        )
        self.set_hidden_select(picker, invoice_id)
        self.browser.find_element(By.CSS_SELECTOR, "#payment-allocate-form button[type='submit']").click()
        # «تخصیص‌یافته» left the detail card in 1.3.7 — allocation has its own
        # section with the invoices named, so the allocation row is the evidence.
        self.wait.until(
            expected_conditions.text_to_be_present_in_element(
                (By.ID, "payment-allocations-table-body"), "۲۵۰"
            )
        )

        # 7. The invoice now shows the payment, and prints the stored snapshot.
        self.browser.get(f"{self.live_server_url}/invoices/{invoice_id}/")
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "invoice-detail-content")))
        # «پرداخت شده» is read-only since 1.3.14 and is the sum of what the
        # receipts desk allocated, so it carries the currency word like every
        # other derived display on this card.
        self.wait.until(lambda driver: self.value_of("invoice-paid") == "۲۵۰ ریال")
        self.assertFalse(self.browser.find_element(By.ID, "invoice-paid").is_enabled())
        self.assertEqual(self.value_of("invoice-balance"), "۳۵۰ ریال")
        self.assertEqual(self.value_of("invoice-settlement"), "تسویه جزئی")  # canonical, not manual

        self.browser.get(f"{self.live_server_url}/invoices/{invoice_id}/print/")
        self.wait.until(expected_conditions.visibility_of_element_located((By.CSS_SELECTOR, ".print-sheet")))
        printed = self.browser.find_element(By.CSS_SELECTOR, ".print-sheet").text
        self.assertIn("مشتری بازرگانی", printed)
        self.assertIn("BR-1", printed)
        self.assertIn("۶۰۰ ریال", printed)
        # The printed page carries no navigation to click away from.
        self.assertEqual(self.browser.find_elements(By.ID, "app-sidebar"), [])

        # 8. The receivables report reflects the same numbers.
        self.browser.get(f"{self.live_server_url}/reports/receivables/")
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "receivables-table-wrap")))
        self.assertEqual(self.browser.find_element(By.ID, "receivables-total").text, "۳۵۰ ریال")

        # The ageing chart draws the same money the cards above it show. All
        # five buckets are present even where a bucket is empty, because the
        # sequence is the point and a missing bucket is the reader's good news.
        chart = self.browser.find_element(By.ID, "receivables-aging-chart")
        self.wait.until(lambda driver: chart.is_displayed())
        # ApexCharts draws asynchronously, so the container is displayed before
        # the bars exist. Waiting on the bars is waiting on the actual thing
        # being asserted.
        self.wait.until(
            lambda driver: len(chart.find_elements(By.CSS_SELECTOR, ".apexcharts-bar-area")) == 5
        )
        bars = chart.find_elements(By.CSS_SELECTOR, ".apexcharts-bar-area")

        # The bucket's own name and its figure are one combined label now,
        # drawn past the bar's own tip rather than the name sitting in a
        # separate y-axis column — Apex's own gutter-width calculation for
        # that column measured badly for this panel's Persian labels (see
        # `common/tests/test_chart_labels.py`), so the column was dropped
        # and the name joined the value it used to sit beside instead.
        figures = [
            node.get_attribute("textContent").strip()
            for node in chart.find_elements(By.CSS_SELECTOR, ".apexcharts-datalabels text")
        ]
        self.assertEqual(len(figures), 5)
        names = [figure.split(" — ")[0] for figure in figures]
        self.assertEqual(
            names,
            ["سررسید نشده", "۱ تا ۳۰ روز", "۳۱ تا ۶۰ روز", "۶۱ تا ۹۰ روز", "بیش از ۹۰ روز"],
        )

        # Every figure is formatted rial, never a raw decimal - the defect the
        # shared renderer was written to make impossible.
        for figure in figures:
            with self.subTest(figure=figure):
                self.assertRegex(figure, r"ریال$")

        # The same string the summary card above shows, character for character:
        # `money()` groups with the Arabic comma and Persian digits, and a
        # chart that formatted them differently from the card beside it would
        # be its own kind of wrong. The chart's own label carries the bucket
        # name in front of it now, so this checks the figure ends with the
        # card's own text rather than equalling it outright.
        self.assertTrue(any(figure.endswith("۳۵۰ ریال") for figure in figures))
        self.assertTrue(
            figures[1].endswith(self.browser.find_element(By.ID, "receivables-1-30").text)
        )

        # The five buckets escalate, so their colours have to as well - and each
        # has to differ from the one before it, which is what went wrong when
        # two of them shared the theme's single warning yellow.
        fills = [bar.get_attribute("fill") for bar in bars]
        self.assertEqual(len(set(fills)), 5, fills)

        self.assertTrue(chart.get_attribute("aria-label"))

        self.assert_browser_clean()

    def test_agent_sees_documents_and_no_money_navigation_at_all(self):
        self.browser.set_window_size(1440, 1000)
        self.login(self.agent)
        sidebar = self.browser.find_element(By.ID, "app-sidebar").text
        self.assertIn("اسناد فروش", sidebar)
        self.assertIn("انبار و موجودی", sidebar)
        self.assertNotIn("اسناد مالی", sidebar)
        self.assertNotIn("پیش‌فاکتور", sidebar)

        for path in (
            "/quotations/",
            "/quotations/1/",
            "/quotations/1/print/",
            "/quotations/1/print.pdf",
        ):
            status = self.browser.execute_async_script(
                "const done = arguments[arguments.length - 1]; "
                "fetch(arguments[0], {credentials: 'same-origin'})"
                ".then(response => done(response.status)).catch(() => done(0));",
                path,
            )
            self.assertEqual(status, 404, path)

        self.browser.get(f"{self.live_server_url}/payments/")
        # Pinned by id, not by a styling class: the denial has to keep working
        # whatever the theme calls its card.
        self.wait.until(expected_conditions.visibility_of_element_located((By.ID, "app-error")))
        self.assertIn(
            "۴۰۳",
            self.browser.find_element(By.ID, "app-error-status").text.replace("403", "۴۰۳"),
        )

        # The stock page is readable and offers the agent no way to change it.
        # `presence`, not `visibility`: the filter form now lives collapsed
        # inside its own popover (`setupListFilterPopovers()`) until someone
        # opens it, so this only needs to know the page finished rendering.
        self.browser.get(f"{self.live_server_url}/stock/")
        self.wait.until(expected_conditions.presence_of_element_located((By.ID, "stock-search-form")))
        self.assertEqual(self.browser.find_elements(By.ID, "open-create-movement"), [])
        self.assertEqual(self.browser.find_elements(By.ID, "open-transfer-stock"), [])

    def test_the_disbursement_cheque_form_asks_its_questions_in_order(self):
        """«ثبت پرداخت» on the cheque method, which was reordered in 1.4.0.

        نوع چک decides the shape of everything under it, so it comes first with
        شماره چک beside it, and who receives the cheque sits under its own
        heading. Which facts belong to that side differs by kind, and neither
        omission is cosmetic — an endorsed cheque carries its own amount, and a
        cheque we write has not been paid yet.
        """
        received = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CHEQUE,
            amount=Decimal("500.00"),
            cheque={
                "bank_name": "بانک ملی",
                "bank_account": "0201234567001",
                "serial_number": "SPEND-1",
                "due_date": "2026-12-01",
            },
        )
        self.login(self.manager)
        self.browser.get(f"{self.live_server_url}/disbursements/")
        self.open_create_dialog("open-create-payment", "create-payment-dialog")
        self.browser.find_element(By.CSS_SELECTOR, "[data-payment-mode='cheque']").click()

        source = self.browser.find_element(By.ID, "create-cheque-source")
        serial = self.browser.find_element(By.ID, "create-cheque-existing")
        payee_block = self.browser.find_element(By.ID, "create-cheque-payee-block")
        amount = self.browser.find_element(By.CSS_SELECTOR, "[data-payment-field='amount']")
        date = self.browser.find_element(By.CSS_SELECTOR, "[data-payment-field='received-at']")

        # چک مشتری: the instrument is chosen, not described, and its amount is
        # its own.
        self.assertTrue(source.is_displayed())
        self.wait.until(lambda driver: serial.is_displayed())
        self.assertTrue(payee_block.is_displayed())
        self.assertFalse(amount.is_displayed())
        self.assertTrue(date.is_displayed())
        # The party moved under the heading rather than being duplicated.
        self.assertIn(
            "اطلاعات گیرنده",
            self.browser.find_element(By.ID, "create-cheque-payee-block").text,
        )

        # چک تازه: an amount is needed, a payment date is not.
        Select(source).select_by_value("own")
        self.wait.until(lambda driver: amount.is_displayed())
        self.assertFalse(date.is_displayed())
        self.assertFalse(serial.is_displayed())

        # Back to چک مشتری, and the instrument can be chosen by its number.
        Select(source).select_by_value("customer_endorsed")
        self.wait.until(lambda driver: serial.is_displayed())
        self.set_hidden_select(
            self.browser.find_element(By.ID, "create-cheque-existing-id"),
            received.cheque.pk,
        )
        self.assertEqual(
            self.browser.find_element(By.ID, "create-cheque-existing-id").get_attribute("value"),
            str(received.cheque.pk),
        )
        # What happens on submit — the cheque is spent, filed, and appears on
        # this desk reading «خرج شده» — is covered where it can be asserted
        # deterministically, in billing/tests/test_bidirectional_payments.py.
        self.assert_browser_clean()
