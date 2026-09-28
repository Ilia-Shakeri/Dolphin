"""Who may delete (2.18.8).

Product owner, 2026-09-27: «مدیر اصلی پنل باید بتواند هر چیزی را که می‌خواهد
حذف کند، ولی کاربران دیگر باید مجوز بگیرند». The Platform Admin deletes
anything; anyone else only with a `<module>.delete` granted to them on the
permission matrix — and still only inside their own object scope.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.access import can_delete, capabilities_for
from accounts.models import User, UserCapabilityOverride
from accounts.module_permissions import MODULES, effective_matrix_for_user, validate_matrix
from accounts.services import set_user_permission_overrides
from sales.models import Customer
from sales.services import create_customer_with_phone

PASSWORD = "Strong-pass-937!"


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class Fixtures(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="del.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="del.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="del.agent", password=PASSWORD, role=User.Role.SALES_AGENT)

    def grant(self, user, capability):
        UserCapabilityOverride.objects.create(user=user, capability=capability, granted=True)


class CanDeleteRuleTests(Fixtures):
    def test_the_platform_admin_deletes_anything(self):
        for module in MODULES:
            for capability in module.delete:
                self.assertTrue(can_delete(self.admin, capability))
        # Even a surface no matrix governs (user administration).
        self.assertTrue(can_delete(self.admin, None))

    def test_no_other_role_deletes_by_default(self):
        for user in (self.manager, self.agent):
            for module in MODULES:
                for capability in module.delete:
                    with self.subTest(role=user.role, capability=capability):
                        self.assertFalse(can_delete(user, capability))

    def test_a_granted_capability_is_exactly_what_it_says(self):
        self.grant(self.manager, "customers.delete")
        self.assertTrue(can_delete(self.manager, "customers.delete"))
        self.assertFalse(can_delete(self.manager, "leads.delete"))
        self.assertFalse(can_delete(self.manager, None))


class MatrixTests(Fixtures):
    def test_delete_implies_edit_implies_read(self):
        normalised = validate_matrix({"customers": {"read": False, "write": False, "delete": True}})
        self.assertEqual(normalised["customers"], {"read": True, "write": True, "delete": True})

    def test_a_module_with_nothing_to_delete_never_carries_it(self):
        normalised = validate_matrix({"ledger": {"read": True, "delete": True}})
        self.assertFalse(normalised["ledger"]["delete"])

    def test_granting_delete_through_the_matrix_writes_one_override(self):
        matrix = {key: {"read": entry["read"], "write": entry["write"], "delete": entry["delete"]}
                  for key, entry in effective_matrix_for_user(self.manager).items()}
        matrix["customers"]["delete"] = True
        set_user_permission_overrides(actor=self.admin, target=self.manager, matrix=matrix)
        self.assertEqual(
            list(UserCapabilityOverride.objects.filter(user=self.manager).values_list("capability", "granted")),
            [("customers.delete", True)],
        )
        row = effective_matrix_for_user(self.manager)["customers"]
        self.assertTrue(row["delete"])
        self.assertTrue(row["is_custom"])

    def test_the_platform_admins_own_delete_column_is_locked_on(self):
        matrix = effective_matrix_for_user(self.admin)
        self.assertTrue(all(entry["delete"] and entry["delete_locked"]
                            for entry in matrix.values() if entry["supports_delete"]))
        # And no save through the matrix can take it away.
        request = {key: {"read": entry["read"], "write": entry["write"], "delete": False}
                   for key, entry in matrix.items()}
        set_user_permission_overrides(actor=self.admin, target=self.admin, matrix=request)
        self.assertIn("customers.delete", capabilities_for(self.admin))
        self.assertTrue(can_delete(self.admin, "customers.delete"))


class ApiTests(Fixtures):
    def test_a_manager_without_the_permission_is_refused(self):
        bare = create_customer_with_phone(actor=self.admin, full_name="مشتری بی‌سابقه")
        response = client_for(self.manager).delete(f"/api/v1/customers/{bare.pk}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Customer.objects.filter(pk=bare.pk).exists())

    def test_a_granted_manager_deletes_single_and_bulk(self):
        self.grant(self.manager, "customers.delete")
        first = create_customer_with_phone(actor=self.admin, full_name="مشتری اول")
        second = create_customer_with_phone(actor=self.admin, full_name="مشتری دوم")
        self.assertEqual(client_for(self.manager).delete(f"/api/v1/customers/{first.pk}/").status_code, 204)
        response = client_for(self.manager).post("/api/v1/customers/bulk-delete/", {"ids": [second.pk]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"], [second.pk])

    def test_a_grant_on_one_module_does_not_reach_another(self):
        self.grant(self.manager, "customers.delete")
        response = client_for(self.manager).post("/api/v1/warehouses/bulk-delete/", {"ids": [1]}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_a_granted_agent_still_only_reaches_their_own_scope(self):
        self.grant(self.agent, "customers.delete")
        theirs = create_customer_with_phone(actor=self.agent, full_name="مشتری خود بازاریاب")
        not_theirs = create_customer_with_phone(actor=self.manager, full_name="مشتری دیگری")
        client = client_for(self.agent)
        self.assertEqual(client.delete(f"/api/v1/customers/{not_theirs.pk}/").status_code, 404)
        self.assertTrue(Customer.objects.filter(pk=not_theirs.pk).exists())
        self.assertEqual(client.delete(f"/api/v1/customers/{theirs.pk}/").status_code, 204)

    def test_user_administration_stays_platform_admin_only(self):
        """No `users.*` capability is ever grantable (`PROTECTED_CAPABILITY_PREFIXES`)."""
        UserCapabilityOverride.objects.create(user=self.manager, capability="users.delete", granted=True)
        response = client_for(self.manager).delete(f"/api/v1/users/{self.agent.pk}/")
        self.assertIn(response.status_code, {403, 404})
        self.assertTrue(User.objects.filter(pk=self.agent.pk).exists())


class PermissionApiTests(Fixtures):
    """The permission screen reads and writes the matrix through the API; the
    delete column has to survive the serializer both ways — on the first
    cut it did not, and the screen drew «—» on every row."""

    def test_the_api_carries_the_delete_column_and_accepts_it(self):
        client = client_for(self.admin)
        matrix = client.get(f"/api/v1/users/{self.manager.pk}/permissions/").json()["matrix"]
        self.assertTrue(matrix["customers"]["supports_delete"])
        self.assertFalse(matrix["customers"]["delete"])
        self.assertFalse(matrix["ledger"]["supports_delete"])
        request = {key: {"read": entry["read"], "write": entry["write"], "delete": entry["delete"]}
                   for key, entry in matrix.items()}
        request["customers"]["delete"] = True
        response = client.patch(f"/api/v1/users/{self.manager.pk}/permissions/", {"matrix": request}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["matrix"]["customers"]["delete"])
        self.assertTrue(can_delete(User.objects.get(pk=self.manager.pk), "customers.delete"))

    def test_the_admins_own_row_comes_back_locked(self):
        matrix = client_for(self.admin).get(f"/api/v1/users/{self.admin.pk}/permissions/").json()["matrix"]
        self.assertTrue(matrix["customers"]["delete"])
        self.assertTrue(matrix["customers"]["delete_locked"])


class PageTests(Fixtures):
    def page(self, user, path="/customers/"):
        self.client.force_login(user)
        return self.client.get(path)

    def test_the_list_page_offers_deletion_only_where_it_would_work(self):
        self.assertFalse(self.page(self.manager).context["can_hard_delete"])
        self.grant(self.manager, "customers.delete")
        self.assertTrue(self.page(self.manager).context["can_hard_delete"])
        # …and only on the module granted.
        self.assertFalse(self.page(self.manager, "/leads/").context["can_hard_delete"])
        self.assertTrue(self.page(self.admin, "/leads/").context["can_hard_delete"])

    def test_financial_documents_are_never_offered_for_deletion(self):
        """Product owner, 2026-09-28: non-financial records are deletable,
        money documents are not — the Platform Admin included. A wrong
        invoice or payment is cancelled or reversed instead."""
        for path in ("/invoices/", "/orders/", "/payments/", "/sales/"):
            with self.subTest(path=path):
                self.assertFalse(self.page(self.admin, path).context["can_hard_delete"])

    def test_financial_documents_refuse_deletion_through_the_api(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(self.admin)
        for endpoint in ("invoices", "orders", "quotations", "payments", "sales"):
            with self.subTest(endpoint=endpoint):
                response = client.post(f"/api/v1/{endpoint}/bulk-delete/", {"ids": [1]}, format="json")
                self.assertEqual(response.status_code, 403)
                self.assertIn("اسناد مالی حذف نمی‌شوند", str(response.data["detail"]))

    def test_the_permission_dialog_has_a_delete_column(self):
        page = self.page(self.admin, "/users/").content.decode("utf-8")
        self.assertIn('<th class="text-center">حذف</th>', page)
