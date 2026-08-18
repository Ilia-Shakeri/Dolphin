import json
from decimal import Decimal
from pathlib import Path

from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from reports.xlsx import safe_spreadsheet_text
from sales.models import Sale
from sales.services import assign_lead, create_customer_with_phone, create_lead, create_product, mark_sale


ROOT = Path(__file__).resolve().parents[2]


class CommercialShellContractTests(SimpleTestCase):
    def test_real_pages_states_and_identical_report_query_are_wired(self):
        script = (ROOT / "common" / "static" / "common" / "kariz-app.js").read_text(encoding="utf-8")
        for page in ("products", "product-detail", "product-categories", "product-category-detail", "sales", "sale-detail", "user-performance", "activity-logs", "activity-log-detail"):
            self.assertIn(f'page === "{page}"', script)
        self.assertIn("function reportQuery(form)", script)
        self.assertIn("/api/v1/reports/user-performance/?${query}", script)
        self.assertIn("/api/v1/exports/user-performance.xlsx?${query}", script)
        for status in (403, 404, 409, 429):
            self.assertIn(f'{status}: "', script)

    def test_sale_browser_sends_only_user_owned_inputs(self):
        template = (ROOT / "common" / "templates" / "common" / "sales" / "list.html").read_text(encoding="utf-8")
        form = template.split('id="create-sale-form"', 1)[1].split("</form>", 1)[0]
        for field in ("customer", "sold_by", "unit_price_snapshot", "total_amount", "status", "sold_at", "created_at", "updated_at"):
            self.assertNotIn(f'name="{field}"', form)
        script = (ROOT / "common" / "static" / "common" / "kariz-app.js").read_text(encoding="utf-8")
        self.assertIn('formPayload(createForm, ["lead", "product", "quantity", "notes"])', script)
        self.assertNotIn("correction", template.lower())
        self.assertNotIn('method: "DELETE"', script)

    def test_product_agent_template_has_no_write_controls(self):
        list_template = (ROOT / "common" / "templates" / "common" / "products" / "list.html").read_text(encoding="utf-8")
        detail_template = (ROOT / "common" / "templates" / "common" / "products" / "detail.html").read_text(encoding="utf-8")
        self.assertIn("{% if can_manage_products %}", list_template)
        self.assertIn("{% if can_manage_products %}", detail_template)
        self.assertNotIn("inventory", (list_template + detail_template).lower())
        self.assertIn('id="product-status-filter" name="is_active"', list_template)
        self.assertIn('name="sku" required maxlength="80"', list_template)
        self.assertIn('name="sku" required maxlength="80"', detail_template)
        self.assertIn('id="product-category-filter" name="category"', list_template)
        self.assertIn('name="brand" maxlength="120"', list_template)
        self.assertIn('name="barcode" maxlength="64"', list_template)
        script = (ROOT / "common" / "static" / "common" / "kariz-app.js").read_text(encoding="utf-8")
        self.assertIn('query.set("is_active", isActive)', script)
        self.assertIn('query.set("category", category)', script)
        self.assertNotIn('method: "DELETE"', script)

    def test_category_templates_have_real_states_and_no_hard_delete(self):
        list_template = (ROOT / "common" / "templates" / "common" / "product_categories" / "list.html").read_text(encoding="utf-8")
        detail_template = (ROOT / "common" / "templates" / "common" / "product_categories" / "detail.html").read_text(encoding="utf-8")
        self.assertIn('id="product-categories-loading"', list_template)
        self.assertIn('id="product-categories-empty"', list_template)
        self.assertIn("{% if can_manage_products %}", list_template)
        self.assertIn("{% if can_manage_products %}", detail_template)
        self.assertIn('id="toggle-product-category"', detail_template)
        self.assertNotIn('type="submit">حذف', list_template + detail_template)
        self.assertNotIn('/delete/', list_template + detail_template)

    def test_formula_injection_protection_stays_active(self):
        self.assertEqual(safe_spreadsheet_text("=2+2"), "'=2+2")
        self.assertEqual(safe_spreadsheet_text(" +SUM(A1)"), "' +SUM(A1)")


class CommercialShellScopeTests(TestCase):
    password = "Strong-pass-548!"

    def setUp(self):
        # Throttle history is keyed by user id and lives in the process cache,
        # which the test database rollback does not touch. A user id reused
        # from an earlier test would arrive already throttled and fail this
        # test on a 429 that has nothing to do with scope or server fields.
        cache.clear()
        self.roles = {
            role: User.objects.create_user(username=f"commercial-{role}", password=self.password, role=role)
            for role in User.Role.values
        }
        self.agent = self.roles[User.Role.SALES_AGENT]
        self.other_agent = User.objects.create_user(username="commercial-other", password=self.password, role=User.Role.SALES_AGENT)
        self.manager = self.roles[User.Role.SALES_MANAGER]
        self.customer = create_customer_with_phone(actor=self.agent, full_name="مشتری مجاز")
        self.lead = create_lead(actor=self.agent, customer=self.customer, source="manual")
        assign_lead(actor=self.manager, lead=self.lead, to_user=self.agent, reason="scope")
        self.other_customer = create_customer_with_phone(actor=self.other_agent, full_name="مشتری پنهان")
        self.other_lead = create_lead(actor=self.other_agent, customer=self.other_customer, source="manual")
        assign_lead(actor=self.manager, lead=self.other_lead, to_user=self.other_agent, reason="scope")
        self.product = create_product(actor=self.manager, sku="CRM-1", name="محصول یک", current_price=Decimal("125.50"))
        self.inactive_product = create_product(actor=self.manager, sku="CRM-2", name="محصول قدیمی", current_price=Decimal("10.00"))
        self.inactive_product.is_active = False
        self.inactive_product.save(update_fields=["is_active"])
        self.sale = mark_sale(actor=self.agent, lead=self.lead, product=self.product, quantity=2, sold_at=timezone.now())
        self.other_sale = mark_sale(actor=self.other_agent, lead=self.other_lead, product=self.product, quantity=1, sold_at=timezone.now())
        self.platform_log = ActivityLog.objects.create(
            actor=self.roles[User.Role.PLATFORM_ADMIN],
            actor_role_snapshot=User.Role.PLATFORM_ADMIN,
            operation="user.role_changed",
            object_type="accounts.user",
            object_id=str(self.roles[User.Role.PLATFORM_ADMIN].pk),
            object_role_snapshot=User.Role.PLATFORM_ADMIN,
            safe_changes={"to": User.Role.PLATFORM_ADMIN},
        )

    def test_browser_product_and_sale_direct_ids_apply_all_four_scopes(self):
        api = APIClient()
        for role, actor in self.roles.items():
            self.client.force_login(actor)
            api.force_authenticate(actor)
            with self.subTest(role=role, item="inactive-product"):
                expected = 404 if role == User.Role.SALES_AGENT else 200
                self.assertEqual(self.client.get(f"/products/{self.inactive_product.pk}/").status_code, expected)
                self.assertEqual(api.get(f"/api/v1/products/{self.inactive_product.pk}/").status_code, expected)
            with self.subTest(role=role, item="other-sale"):
                expected = 404 if role == User.Role.SALES_AGENT else 200
                self.assertEqual(self.client.get(f"/sales/{self.other_sale.pk}/").status_code, expected)
                self.assertEqual(api.get(f"/api/v1/sales/{self.other_sale.pk}/").status_code, expected)

    def test_agent_product_browser_is_read_only(self):
        self.client.force_login(self.agent)
        listing = self.client.get("/products/")
        detail = self.client.get(f"/products/{self.product.pk}/")
        self.assertNotContains(listing, 'id="open-create-product"')
        self.assertNotContains(detail, 'id="product-active-select"')
        self.assertNotContains(detail, 'type="submit">ذخیره تغییرات')
        # A store manager runs the shop, so activation is theirs as well as the
        # platform admin's — what stays Platform-Admin-only is the security
        # plane, not business workflow. It is a reversible select either way.
        for role in (User.Role.SALES_MANAGER, User.Role.PLATFORM_ADMIN):
            with self.subTest(role=role):
                self.client.force_login(self.roles[role])
                detail_page = self.client.get(f"/products/{self.product.pk}/")
                self.assertContains(detail_page, 'id="product-active-select"')
                self.assertNotContains(detail_page, 'id="deactivate-product"')
        self.client.force_login(self.manager)
        self.assertContains(self.client.get("/products/"), 'id="open-create-product"')

    def test_activity_log_browser_and_api_scope_are_enforced(self):
        for role in (User.Role.SALES_AGENT, User.Role.SALES_MANAGER):
            self.client.force_login(self.roles[role])
            self.assertEqual(self.client.get("/activity-logs/").status_code, 403)
        self.client.force_login(self.roles[User.Role.COMPANY_IT])
        self.assertEqual(self.client.get("/activity-logs/").status_code, 200)
        self.assertEqual(self.client.get(f"/activity-logs/{self.platform_log.pk}/").status_code, 404)
        self.client.force_login(self.roles[User.Role.PLATFORM_ADMIN])
        self.assertEqual(self.client.get(f"/activity-logs/{self.platform_log.pk}/").status_code, 200)

        api = APIClient()
        for role, expected in ((User.Role.SALES_AGENT, 403), (User.Role.SALES_MANAGER, 403), (User.Role.COMPANY_IT, 200), (User.Role.PLATFORM_ADMIN, 200)):
            api.force_authenticate(self.roles[role])
            with self.subTest(role=role):
                self.assertEqual(api.get("/api/v1/activity-logs/").status_code, expected)
        api.force_authenticate(self.roles[User.Role.COMPANY_IT])
        self.assertEqual(api.get(f"/api/v1/activity-logs/{self.platform_log.pk}/").status_code, 404)

    def test_api_scope_server_fields_and_controlled_cancel(self):
        api = APIClient()
        api.force_authenticate(self.agent)
        self.assertEqual(api.get(f"/api/v1/sales/{self.other_sale.pk}/").status_code, 404)
        rejected = api.post("/api/v1/sales/", {"lead": self.other_lead.pk, "product": self.product.pk, "quantity": 1}, format="json")
        self.assertEqual(rejected.status_code, 400)
        for field, value in (("customer", self.customer.pk), ("sold_by", self.manager.pk), ("unit_price_snapshot", "1.00"), ("status", "cancelled"), ("sold_by_display", "fake")):
            response = api.post("/api/v1/sales/", {"lead": self.lead.pk, "product": self.product.pk, "quantity": 1, field: value}, format="json")
            with self.subTest(field=field):
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
        derived = api.post("/api/v1/sales/", {"lead": self.lead.pk, "product": self.product.pk, "quantity": 3, "total_amount": "0.01"}, format="json")
        self.assertEqual(derived.status_code, 201)
        self.assertEqual(Decimal(derived.data["total_amount"]), Decimal("376.50"))
        self.assertEqual(derived.data["sold_by"], self.agent.pk)
        self.assertEqual(derived.data["customer"], self.customer.pk)
        self.assertEqual(api.post(f"/api/v1/sales/{derived.data['id']}/cancel/", {}, format="json").status_code, 403)
        api.force_authenticate(self.manager)
        cancelled = api.post(f"/api/v1/sales/{derived.data['id']}/cancel/", {"reason": "approved"}, format="json")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.data["status"], Sale.Status.CANCELLED)
        self.assertEqual(api.post(f"/api/v1/sales/{derived.data['id']}/cancel/", {}, format="json").status_code, 409)

    def test_product_search_pagination_and_deactivation_conflict(self):
        for index in range(25):
            create_product(actor=self.manager, sku=f"PAGE-{index:02d}", name=f"محصول {index:02d}", current_price=Decimal("1.00"))
        api = APIClient()
        api.force_authenticate(self.manager)
        page = api.get("/api/v1/products/?search=محصول&ordering=sku&page=1")
        self.assertEqual(page.status_code, 200)
        self.assertGreaterEqual(page.data["count"], 26)
        self.assertIsNotNone(page.data["next"])
        active = api.get("/api/v1/products/?is_active=true&ordering=sku")
        inactive = api.get("/api/v1/products/?is_active=false&ordering=sku")
        self.assertTrue(all(row["is_active"] for row in active.data["results"]))
        self.assertEqual([row["id"] for row in inactive.data["results"]], [self.inactive_product.pk])
        invalid = api.get("/api/v1/products/?is_active=yes")
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("is_active", invalid.data)

        api.force_authenticate(self.agent)
        hidden_inactive = api.get("/api/v1/products/?is_active=false")
        self.assertEqual(hidden_inactive.status_code, 200)
        self.assertEqual(hidden_inactive.data["count"], 0)
        api.force_authenticate(self.roles[User.Role.PLATFORM_ADMIN])
        deactivated = api.post(f"/api/v1/products/{self.product.pk}/deactivate/")
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.data["is_active"])
        self.assertEqual(api.post(f"/api/v1/products/{self.product.pk}/deactivate/").status_code, 409)

    def test_session_csrf_required_for_product_sale_and_cancel(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)
        self.assertEqual(client.get("/products/").status_code, 200)
        token = client.cookies["csrftoken"].value
        product_data = {"sku": "CSRF-1", "name": "محصول سی اس آر اف", "current_price": "25.00"}
        self.assertEqual(client.post("/api/v1/products/", data=json.dumps(product_data), content_type="application/json").status_code, 403)
        created_product = client.post("/api/v1/products/", data=json.dumps(product_data), content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(created_product.status_code, 201)
        sale_data = {"lead": self.lead.pk, "product": created_product.json()["id"], "quantity": 1}
        self.assertEqual(client.post("/api/v1/sales/", data=json.dumps(sale_data), content_type="application/json").status_code, 403)
        created_sale = client.post("/api/v1/sales/", data=json.dumps(sale_data), content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(created_sale.status_code, 201)
        cancel_path = f"/api/v1/sales/{created_sale.json()['id']}/cancel/"
        self.assertEqual(client.post(cancel_path, data="{}", content_type="application/json").status_code, 403)
        self.assertEqual(client.post(cancel_path, data="{}", content_type="application/json", HTTP_X_CSRFTOKEN=token).status_code, 200)
