from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from sales.models import Product, ProductCategory
from sales.services import create_product, create_product_category, deactivate_product


class ProductCategoryContractTests(TestCase):
    password = "Strong-pass-548!"

    def setUp(self):
        cache.clear()
        self.manager = User.objects.create_user(
            username="category-manager",
            password=self.password,
            role=User.Role.SALES_MANAGER,
        )
        self.agent = User.objects.create_user(
            username="category-agent",
            password=self.password,
            role=User.Role.SALES_AGENT,
        )
        self.manager_client = APIClient()
        self.manager_client.force_authenticate(self.manager)
        self.agent_client = APIClient()
        self.agent_client.force_authenticate(self.agent)

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def create_category(self, **overrides):
        data = {"code": "general", "name": "کالای عمومی", "display_order": 2}
        data.update(overrides)
        return create_product_category(actor=self.manager, **data)

    def test_normalized_name_code_and_barcode_contract(self):
        category = self.create_category(name="  کالای   ویژه  ")
        self.assertEqual(category.name, "کالای ویژه")
        self.assertEqual(category.normalized_name, "کالای ویژه")

        duplicate_name = self.manager_client.post(
            "/api/v1/product-categories/",
            {"code": "other", "name": "  كالاي ویژه "},
            format="json",
        )
        self.assertEqual(duplicate_name.status_code, 409)

        invalid_code = self.manager_client.post(
            "/api/v1/product-categories/",
            {"code": "Bad Code", "name": "دسته دیگر"},
            format="json",
        )
        self.assertEqual(invalid_code.status_code, 400)
        self.assertIn("code", invalid_code.data)
        duplicate_code = self.manager_client.post(
            "/api/v1/product-categories/",
            {"code": "general", "name": "نام یکتای دیگر"},
            format="json",
        )
        self.assertEqual(duplicate_code.status_code, 409)
        self.assertIn("code", duplicate_code.data)

        product = self.manager_client.post(
            "/api/v1/products/",
            {
                "sku": "CAT-1",
                "name": "محصول دسته‌دار",
                "category": category.pk,
                "brand": "برند یک",
                "barcode": "abc-1",
                "current_price": "15.00",
            },
            format="json",
        )
        self.assertEqual(product.status_code, 201)
        self.assertEqual(product.data["barcode"], "ABC-1")
        self.assertEqual(product.data["category_name"], category.name)

        duplicate_barcode = self.manager_client.post(
            "/api/v1/products/",
            {
                "sku": "CAT-2",
                "name": "محصول دوم",
                "barcode": "abc-1",
                "current_price": "10.00",
            },
            format="json",
        )
        self.assertEqual(duplicate_barcode.status_code, 409)
        self.assertIn("barcode", duplicate_barcode.data)

    def test_category_code_is_immutable_and_server_fields_are_rejected(self):
        category = self.create_category()
        for payload in (
            {"code": "changed"},
            {"is_active": False},
            {"created_by": self.agent.pk},
            {"normalized_name": "fake"},
        ):
            with self.subTest(payload=payload):
                response = self.manager_client.patch(
                    f"/api/v1/product-categories/{category.pk}/",
                    payload,
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(next(iter(payload)), response.data)
        category.refresh_from_db()
        self.assertEqual(category.code, "general")
        self.assertTrue(category.is_active)

    def test_non_destructive_lifecycle_blocks_active_product(self):
        category = self.create_category()
        product = create_product(
            actor=self.manager,
            sku="ACTIVE-CAT",
            name="محصول فعال",
            category=category,
            current_price=Decimal("12.00"),
        )
        endpoint = f"/api/v1/product-categories/{category.pk}/"
        self.assertEqual(self.manager_client.delete(endpoint).status_code, 405)
        blocked = self.manager_client.post(f"{endpoint}deactivate/")
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("category", blocked.data)

        deactivate_product(actor=self.manager, product=product)
        deactivated = self.manager_client.post(f"{endpoint}deactivate/")
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.data["is_active"])
        self.assertEqual(self.agent_client.get(endpoint).status_code, 404)

        invalid_assignment = self.manager_client.post(
            "/api/v1/products/",
            {
                "sku": "INACTIVE-CAT",
                "name": "محصول نامعتبر",
                "category": category.pk,
                "current_price": "10.00",
            },
            format="json",
        )
        self.assertEqual(invalid_assignment.status_code, 400)
        self.assertIn("category", invalid_assignment.data)

        reactivated = self.manager_client.post(f"{endpoint}reactivate/")
        self.assertEqual(reactivated.status_code, 200)
        self.assertTrue(reactivated.data["is_active"])
        operations = set(
            ActivityLog.objects.filter(object_type="sales.productcategory").values_list(
                "operation", flat=True
            )
        )
        self.assertTrue(
            {
                "product_category.created",
                "product_category.deactivated",
                "product_category.reactivated",
            }.issubset(operations)
        )

    def test_agent_scope_and_privilege_escalation_fail_closed(self):
        active = self.create_category()
        inactive = self.create_category(code="old", name="قدیمی")
        ProductCategory.objects.filter(pk=inactive.pk).update(is_active=False)

        listing = self.agent_client.get("/api/v1/product-categories/?is_active=false")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 0)
        self.assertEqual(
            self.agent_client.get(f"/api/v1/product-categories/{inactive.pk}/").status_code,
            404,
        )
        self.assertEqual(
            self.agent_client.get(f"/api/v1/product-categories/{active.pk}/").status_code,
            200,
        )
        self.client.force_login(self.agent)
        browser_list = self.client.get("/product-categories/")
        self.assertEqual(browser_list.status_code, 200)
        self.assertNotContains(browser_list, 'id="open-create-product-category"')
        self.assertEqual(
            self.client.get(f"/product-categories/{inactive.pk}/").status_code,
            404,
        )
        active_detail = self.client.get(f"/product-categories/{active.pk}/")
        self.assertEqual(active_detail.status_code, 200)
        self.assertNotContains(active_detail, 'id="toggle-product-category"')
        self.client.force_login(self.manager)
        self.assertContains(
            self.client.get("/product-categories/"),
            'id="open-create-product-category"',
        )
        self.assertContains(
            self.client.get(f"/product-categories/{inactive.pk}/"),
            'id="toggle-product-category"',
        )
        rejected = self.agent_client.post(
            "/api/v1/product-categories/",
            {
                "code": "escalate",
                "name": "",
                "created_by": self.manager.pk,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(rejected.status_code, 403)
        self.assertFalse(ProductCategory.objects.filter(code="escalate").exists())
        product_rejected = self.agent_client.post(
            "/api/v1/products/",
            {"sku": "ESC-1", "name": "", "current_price": "0"},
            format="json",
        )
        self.assertEqual(product_rejected.status_code, 403)
        self.assertFalse(Product.objects.filter(sku="ESC-1").exists())

    def test_product_category_filter_stays_inside_product_scope(self):
        visible = self.create_category()
        product = create_product(
            actor=self.manager,
            sku="FILTER-1",
            name="محصول فیلتر",
            category=visible,
            current_price=Decimal("5.00"),
        )
        result = self.agent_client.get(f"/api/v1/products/?category={visible.pk}")
        self.assertEqual(result.status_code, 200)
        self.assertEqual([row["id"] for row in result.data["results"]], [product.pk])
        unknown = self.agent_client.get("/api/v1/products/?category=999999")
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.data["count"], 0)
        malformed = self.agent_client.get("/api/v1/products/?category=01")
        self.assertEqual(malformed.status_code, 400)
