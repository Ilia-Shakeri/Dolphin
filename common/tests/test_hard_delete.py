"""`HardDeleteMixin` (common/viewsets.py) — the 2026-09-02 Platform-Admin-only
real DELETE, single and bulk, added on top of the previously delete-free
`AdminHardDeleteModelViewSet` (formerly `NoDestroyModelViewSet`).

Exercised through two very different resources on purpose: `Warehouse` (a
simple standalone record) and `Customer` (one with several `PROTECT`ed
dependents readily at hand) — the mixin is shared code, so a bug in it would
show up the same way on any of the dozen viewsets that use it.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from inventory.models import StockMovement, Warehouse
from inventory.services import create_warehouse, record_stock_movement
from sales.models import Customer
from sales.services import create_customer_with_phone, create_product


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class WarehouseHardDeleteTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="hd.admin", password="Strong-pass-937!", role=User.Role.PLATFORM_ADMIN
        )
        self.manager = User.objects.create_user(
            username="hd.manager", password="Strong-pass-937!", role=User.Role.SALES_MANAGER
        )
        self.warehouse = create_warehouse(actor=self.admin, code="hd-main", name="انبار تست حذف")

    def test_non_admin_cannot_delete_a_single_row(self):
        response = _client(self.manager).delete(f"/api/v1/warehouses/{self.warehouse.pk}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Warehouse.objects.filter(pk=self.warehouse.pk).exists())

    def test_platform_admin_deletes_an_unused_row_and_it_is_logged(self):
        response = _client(self.admin).delete(f"/api/v1/warehouses/{self.warehouse.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Warehouse.objects.filter(pk=self.warehouse.pk).exists())
        log = ActivityLog.objects.get(operation="warehouse.deleted", object_id=str(self.warehouse.pk))
        self.assertEqual(log.actor_id, self.admin.pk)

    def test_a_row_with_dependents_is_protected_not_orphaned(self):
        product = create_product(actor=self.admin, sku="HD-1", name="کالای تست حذف", current_price=Decimal("10.00"))
        record_stock_movement(
            actor=self.admin,
            warehouse=self.warehouse,
            product=product,
            movement_type=StockMovement.MovementType.PURCHASE,
            quantity=5,
            unit_cost=Decimal("10.00"),
        )
        response = _client(self.admin).delete(f"/api/v1/warehouses/{self.warehouse.pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Warehouse.objects.filter(pk=self.warehouse.pk).exists())

    def test_bulk_delete_reports_deleted_and_not_found_separately(self):
        other = create_warehouse(actor=self.admin, code="hd-second", name="انبار دوم تست")
        response = _client(self.admin).post(
            "/api/v1/warehouses/bulk-delete/",
            {"ids": [self.warehouse.pk, other.pk, 999999]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertCountEqual(data["deleted"], [self.warehouse.pk, other.pk])
        self.assertEqual(data["not_found"], [999999])
        self.assertEqual(data["protected"], [])
        self.assertFalse(Warehouse.objects.filter(pk__in=[self.warehouse.pk, other.pk]).exists())

    def test_bulk_delete_is_refused_wholesale_for_a_non_admin(self):
        response = _client(self.manager).post(
            "/api/v1/warehouses/bulk-delete/", {"ids": [self.warehouse.pk]}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Warehouse.objects.filter(pk=self.warehouse.pk).exists())

    def test_bulk_delete_rejects_a_malformed_id_list(self):
        for bad in ([], ["not-an-id"], list(range(1, 202)), "1,2,3"):
            with self.subTest(bad=bad):
                response = _client(self.admin).post(
                    "/api/v1/warehouses/bulk-delete/", {"ids": bad}, format="json"
                )
                self.assertEqual(response.status_code, 400)


class CustomerHardDeleteTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="hd.cadmin", password="Strong-pass-937!", role=User.Role.PLATFORM_ADMIN
        )
        self.customer = create_customer_with_phone(
            actor=self.admin, full_name="مشتری تستِ حذف", phone={"raw_phone": "09120000001", "is_primary": True}
        )

    def test_a_customer_with_a_phone_is_protected(self):
        response = _client(self.admin).delete(f"/api/v1/customers/{self.customer.pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())

    def test_a_bare_customer_deletes_cleanly(self):
        bare = create_customer_with_phone(actor=self.admin, full_name="مشتری بدون سابقه")
        response = _client(self.admin).delete(f"/api/v1/customers/{bare.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Customer.objects.filter(pk=bare.pk).exists())
