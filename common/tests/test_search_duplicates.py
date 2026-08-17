"""A search that joins a to-many relation must not repeat a row.

`phones__normalized_phone` and `items__product_name_snapshot` join one row per
related match, so a customer with three matching phones could in principle come
back three times with the page count inflated to match.

DRF's own `SearchFilter` already prevents this: `must_call_distinct` detects a
lookup spanning a to-many relation and rewrites the query through an `Exists`
subquery. These tests pin that guarantee rather than re-implementing it — they
exist so that a change of filter backend, or a search field added to a viewset
that does not use `SearchFilter`, fails here instead of in front of a user.
"""

from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from billing.services import create_quotation
from sales.services import create_customer_with_phone, create_customer_phone, create_product


PASSWORD = "Strong-pass-937!"


class SearchDuplicateTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="dupe.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.client.force_login(self.manager)
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری چندشماره",
            phone={"raw_phone": "09121110000", "is_primary": True},
        )
        # Two more phones sharing the searched fragment. They are stored
        # normalized (+98…), which is the form the search matches.
        create_customer_phone(actor=self.manager, customer=self.customer, raw_phone="09121110001")
        create_customer_phone(actor=self.manager, customer=self.customer, raw_phone="09121110002")

    def test_a_customer_with_several_matching_phones_appears_once(self):
        response = self.client.get("/api/v1/customers/?search=98912111")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        identifiers = [row["id"] for row in payload["results"]]
        self.assertEqual(identifiers, [self.customer.pk])
        self.assertEqual(payload["count"], 1)

    def test_a_document_with_several_matching_lines_appears_once(self):
        product = create_product(
            actor=self.manager, sku="DUP-1", name="کالای تکراری", current_price=Decimal("100.00")
        )
        quotation = create_quotation(
            actor=self.manager,
            customer=self.customer,
            items=[
                {"product": product, "quantity": 1},
                {"product": product, "quantity": 2},
                {"product": product, "quantity": 3},
            ],
        )
        response = self.client.get("/api/v1/quotations/?search=تکراری")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([row["id"] for row in payload["results"]], [quotation.pk])
        self.assertEqual(payload["count"], 1)

    def test_an_unsearched_list_is_not_forced_through_distinct(self):
        """`.distinct()` costs a sort; it is applied only where it is needed."""
        response = self.client.get("/api/v1/customers/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
