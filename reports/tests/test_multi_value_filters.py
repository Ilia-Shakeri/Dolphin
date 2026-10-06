"""Step-by-step reports take several values per filter (2.40.21).

The dropdowns of the sales-documents and inbound-SMS reports are checklists:
a repeated parameter means "any of these", one value still works exactly as
before, and the filters that stay single still refuse a repeat.
"""

from datetime import timedelta

from django.utils import timezone
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from sales.services import create_customer_with_phone, register_sales_document

PASSWORD = "Strong-pass-661!"


class SalesDocumentReportFilterTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mv.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        for index, (province, state) in enumerate((("تهران", "in_store"), ("اصفهان", "with_post"), ("فارس", "with_post"))):
            customer = create_customer_with_phone(
                actor=self.manager, full_name=f"مشتری {index}", province=province, city="شهر",
                phone={"raw_phone": f"0912555000{index}", "is_primary": True},
            )
            register_sales_document(actor=self.manager, customer=customer, document_number=f"MV-{index}", postal_status=state)
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        now = timezone.now()
        self.window = {"period_start": (now - timedelta(days=1)).isoformat(), "period_end": (now + timedelta(days=1)).isoformat()}

    def total(self, **extra):
        response = self.client.get("/api/v1/reports/sales-documents/", {**self.window, **extra})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["total"]

    def test_several_provinces_and_states(self):
        self.assertEqual(self.total(province=["تهران", "اصفهان"]), 2)
        self.assertEqual(self.total(postal_status=["in_store", "with_post"]), 3)
        self.assertEqual(self.total(province=["فارس", "تهران"], postal_status=["with_post"]), 1)

    def test_one_value_works_as_before(self):
        self.assertEqual(self.total(province="تهران"), 1)
        self.assertEqual(self.total(), 3)

    def test_a_single_filter_still_refuses_a_repeat(self):
        response = self.client.get("/api/v1/reports/sales-documents/", {**self.window, "city": ["a", "b"]})
        self.assertEqual(response.status_code, 400)


class InboundSmsStateFilterTests(TestCase):
    def test_several_processing_states_are_accepted(self):
        from communications.serializers import InboundSMSReportQuerySerializer
        from django.http import QueryDict

        now = timezone.now()
        query = QueryDict(mutable=True)
        query.update({"period_start": (now - timedelta(days=1)).isoformat(), "period_end": now.isoformat()})
        query.setlist("processing_state", ["linked", "unmatched"])
        serializer = InboundSMSReportQuerySerializer(data=query)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["processing_state"], ["linked", "unmatched"])
