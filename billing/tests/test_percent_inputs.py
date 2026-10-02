"""A tax rate and a discount percentage are numbers, and the server says so.

The invoice wizard now sends them from text fields that accept digits only; this
is the other side — anything that is not a number between 0 and 100 with at most
two decimals is refused with a sentence, whatever sent it.
"""

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-939!"


class PercentInputTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="pct.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.product = create_product(actor=self.manager, sku="PCT-1", name="کالا", current_price=Decimal("100.00"))
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری", phone={"raw_phone": "09121274444", "is_primary": True}
        )
        self.api = APIClient()
        self.api.force_authenticate(self.manager)

    def create(self, **extra):
        body = {"customer": self.customer.pk, "items": [{"product": self.product.pk, "quantity": 1}], **extra}
        return self.api.post("/api/v1/invoices/", body, format="json")

    def test_a_valid_rate_and_discount_are_accepted_with_decimals(self):
        response = self.create(tax_rate="9.5", discount_percent="12.25")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Decimal(response.json()["tax_rate"]), Decimal("9.50"))

    def test_text_is_refused_with_a_persian_sentence(self):
        response = self.create(tax_rate="abc")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["tax_rate"], ["نرخ مالیات باید یک عدد باشد."])
        response = self.create(discount_percent="۱۲e")
        self.assertEqual(response.status_code, 400)
        self.assertIn("درصد تخفیف", response.json()["discount_percent"][0])

    def test_out_of_range_and_too_many_decimals_are_refused(self):
        self.assertEqual(self.create(tax_rate="-1").status_code, 400)
        self.assertEqual(self.create(tax_rate="101").status_code, 400)
        refused = self.create(tax_rate="5.555")
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(refused.json()["tax_rate"], ["نرخ مالیات حداکثر دو رقم اعشار دارد."])
