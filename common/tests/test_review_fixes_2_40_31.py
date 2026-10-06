"""Findings of the panel-wide review fixed in 2.40.31.

* A postal status stored as its vocabulary key showed the key — «returned» —
  in a customer's timeline, the global search and the list chart's filter.
* Reads of `SensitiveRateThrottle` endpoints shared the writes' 30/min
  budget: moving between reports was refused (429) inside a minute.
"""

from pathlib import Path

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from accounts.models import User
from common.customer_timeline import _sales_document_events
from common.search import _sales_document_results
from common.throttles import SensitiveRateThrottle
from reports.list_charts import _postal_label, _text_options
from sales import postal
from sales.models import SalesDocument
from sales.services import create_customer_with_phone, register_sales_document

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")


class PostalWordsTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="rv.manager", password="Strong-pass-661!", role=User.Role.SALES_MANAGER)
        self.customer = create_customer_with_phone(actor=self.manager, full_name="گیرنده", phone={"raw_phone": "09125550199", "is_primary": True})
        register_sales_document(actor=self.manager, customer=self.customer, document_number="RV-1", postal_status="returned")

    def test_the_timeline_shows_the_label(self):
        (event,) = _sales_document_events(self.manager, self.customer)
        self.assertEqual(event["subtitle"], "برگشتی نهایی")

    def test_search_finds_a_key_by_its_words(self):
        self.assertEqual(postal.keys_matching("برگشتی"), ["pre_return", "returned", "return_confirmed"])
        group = _sales_document_results(self.manager, text="برگشتی", latin="برگشتی", digits="")
        self.assertTrue(group)

    def test_the_chart_filter_offers_the_label(self):
        options = _text_options("postal_status", _postal_label)(SalesDocument.objects.all())
        self.assertEqual(options, [{"value": "returned", "label": "برگشتی نهایی"}])


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class ReadBudgetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="rv.reader", password="Strong-pass-661!", role=User.Role.SALES_MANAGER)

    def requests(self, method, count):
        allowed = 0
        for _ in range(count):
            request = getattr(RequestFactory(), method)("/x/")
            request.user = self.user
            allowed += SensitiveRateThrottle().allow_request(request, None)
        return allowed

    def test_reads_have_their_own_larger_budget(self):
        self.assertEqual(self.requests("get", 60), 60)
        # The reads did not spend the writes' budget.
        self.assertEqual(self.requests("post", 30), 30)
        self.assertEqual(self.requests("post", 1), 0)


class LayoutTests(SimpleTestCase):
    def test_the_kpi_header_wraps_on_a_narrow_card(self):
        head = CSS[CSS.index(".kpi-card-head {"):]
        self.assertIn("flex-wrap: wrap;", head[: head.index("}")])

    def test_phone_tables_scroll_instead_of_wrapping_word_by_word(self):
        self.assertIn(".table-responsive > .table { min-width: 40rem; }", CSS)
