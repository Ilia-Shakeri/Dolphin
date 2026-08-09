from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from sales.models import Customer, CustomerPhone, Interaction, Lead, Product, Sale


class ListQueryGrowthTests(TestCase):
    paths = (
        "/api/v1/users/",
        "/api/v1/activity-logs/",
        "/api/v1/customers/",
        "/api/v1/customer-phones/",
        "/api/v1/leads/",
        "/api/v1/interactions/",
        "/api/v1/products/",
        "/api/v1/sales/",
    )

    def setUp(self):
        self.admin = User.objects.create_user(
            username="query-admin",
            password="Long-Safe-Pass-741!",
            role=User.Role.PLATFORM_ADMIN,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _add_graph(self, index):
        worker = User.objects.create(username=f"query-worker-{index}", role=User.Role.SALES_AGENT)
        customer = Customer.objects.create(full_name=f"Customer {index}", created_by=worker)
        CustomerPhone.objects.create(
            customer=customer,
            raw_phone=f"0912{index:07d}",
            normalized_phone=f"+98912{index:07d}",
            is_primary=True,
        )
        product = Product.objects.create(
            sku=f"QUERY-{index}",
            name=f"Product {index}",
            current_price=Decimal("10.00"),
            created_by=self.admin,
            updated_by=self.admin,
        )
        now = timezone.now()
        lead = Lead.objects.create(
            customer=customer,
            created_by=worker,
            assigned_to=worker,
            assigned_by=self.admin,
            assigned_at=now,
            interested_product=product,
        )
        Interaction.objects.create(
            lead=lead,
            customer=customer,
            agent=worker,
            phone=f"0912{index:07d}",
            direction="outbound",
            outcome="answered",
            occurred_at=now,
        )
        Sale.objects.create(
            lead=lead,
            customer=customer,
            sold_by=worker,
            quantity=1,
            total_amount=Decimal("10.00"),
            sold_at=now,
        )
        ActivityLog.objects.create(
            actor=worker,
            actor_role_snapshot=User.Role.SALES_AGENT,
            operation="query.probe",
            object_type="sales.customer",
            object_id=str(customer.pk),
        )

    def _query_count(self, path):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return len(captured)

    def test_list_query_count_does_not_grow_with_rows(self):
        self._add_graph(1)
        for path in self.paths:
            self.client.get(path)
        small_counts = {path: self._query_count(path) for path in self.paths}

        for index in range(2, 6):
            self._add_graph(index)
        large_counts = {path: self._query_count(path) for path in self.paths}

        for path in self.paths:
            with self.subTest(path=path):
                self.assertLessEqual(large_counts[path], small_counts[path])
