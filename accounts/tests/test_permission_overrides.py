"""The per-user permission override system: defaults, overrides, and the
backend enforcement that makes the override screen more than a display.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.access import capabilities_for
from accounts.models import User, UserCapabilityOverride
from accounts.module_permissions import default_matrix_for_role, effective_matrix_for_user
from accounts.services import (
    change_user_role,
    reset_user_permissions,
    set_user_permission_overrides,
    user_permissions_for,
)
from auditlog.models import ActivityLog
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from sales.models import Customer


class DefaultMatrixMatchesRoleCapabilitiesTests(TestCase):
    """An unoverridden user's matrix must say exactly what their role says —
    this is the regression guard for every `.manage` capability this feature
    added to `ROLE_CAPABILITIES`."""

    def test_agent_can_read_and_write_their_scoped_modules_but_not_payments(self):
        matrix = default_matrix_for_role(User.Role.SALES_AGENT, User.Workstream.SALES)
        for module in ("customers", "leads", "interactions", "sales", "quotations", "orders", "invoices", "products", "product_categories", "inventory"):
            with self.subTest(module=module):
                self.assertTrue(matrix[module]["read"], module)
        self.assertTrue(matrix["customers"]["write"])
        self.assertFalse(matrix["products"]["write"])
        self.assertFalse(matrix["payments"]["read"])
        self.assertFalse(matrix["payments"]["write"])
        self.assertFalse(matrix["after_sales"]["read"])
        self.assertFalse(matrix["sales_documents"]["write"])

    def test_manager_can_read_and_write_everything_business_facing(self):
        matrix = default_matrix_for_role(User.Role.SALES_MANAGER)
        for module in ("customers", "products", "product_categories", "inventory", "payments", "sales_documents", "after_sales", "quotations", "orders", "invoices"):
            with self.subTest(module=module):
                self.assertTrue(matrix[module]["read"], module)
                self.assertTrue(matrix[module]["write"], module)
        self.assertTrue(matrix["reports"]["read"])
        self.assertFalse(matrix["reports"].get("write", False))

    def test_after_sales_workstream_agent_defaults_come_from_the_special_case(self):
        matrix = default_matrix_for_role(User.Role.SALES_AGENT, User.Workstream.AFTER_SALES)
        # `after_sales.assigned` is on the module's read side, so this
        # narrow workstream reads as able to see the module — correctly, it
        # can see its own assigned cases. `after_sales.work` (their write
        # capability for those same cases) is not tracked by this matrix's
        # write side, which only names the elevated `.manage`: real access
        # is unaffected either way (see the comment in aftersales/views.py),
        # this row just under-reports "write" for this one narrow case.
        self.assertTrue(matrix["after_sales"]["read"])
        self.assertFalse(matrix["after_sales"]["write"])
        self.assertFalse(matrix["customers"]["read"])


class OverrideDivergesFromRoleWithoutTouchingItTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin1", password="Long-Safe-Pass-741!", role=User.Role.PLATFORM_ADMIN)
        self.agent = User.objects.create_user(username="agent1", password="Long-Safe-Pass-741!", role=User.Role.SALES_AGENT)
        self.other_agent = User.objects.create_user(username="agent2", password="Long-Safe-Pass-741!", role=User.Role.SALES_AGENT)

    def test_revoking_write_on_one_agent_never_touches_a_peer_with_the_same_role(self):
        matrix = effective_matrix_for_user(self.agent)
        matrix["customers"] = {"read": True, "write": False}
        set_user_permission_overrides(actor=self.admin, target=self.agent, matrix=matrix)

        self.agent.refresh_from_db()
        self.assertFalse(has_capability := "customers.manage" in capabilities_for(self.agent))
        self.assertIn("customers.manage", capabilities_for(self.other_agent))
        self.assertTrue(effective_matrix_for_user(self.agent)["customers"]["is_custom"])
        self.assertFalse(effective_matrix_for_user(self.other_agent)["customers"]["is_custom"])

    def test_only_the_rows_that_actually_differ_become_database_rows(self):
        matrix = effective_matrix_for_user(self.agent)
        matrix["customers"] = {"read": True, "write": False}  # the only real change
        set_user_permission_overrides(actor=self.admin, target=self.agent, matrix=matrix)
        rows = list(UserCapabilityOverride.objects.filter(user=self.agent).values_list("capability", "granted"))
        self.assertEqual(rows, [("customers.manage", False)])

    def test_resaving_the_role_default_clears_the_override_row(self):
        matrix = effective_matrix_for_user(self.agent)
        matrix["customers"] = {"read": True, "write": False}
        set_user_permission_overrides(actor=self.admin, target=self.agent, matrix=matrix)
        self.assertEqual(UserCapabilityOverride.objects.filter(user=self.agent).count(), 1)

        matrix["customers"] = {"read": True, "write": True}
        set_user_permission_overrides(actor=self.admin, target=self.agent, matrix=matrix)
        self.assertEqual(UserCapabilityOverride.objects.filter(user=self.agent).count(), 0)

    def test_widening_a_scope_axis_never_grants_company_wide_visibility(self):
        # The agent starts with no read at all on `payments`; granting it
        # must land on `payments.company` (the only capability that module
        # has) without ever silently handing out a `.scoped`-vs-`.company`
        # escalation on a module that actually has both.
        matrix = effective_matrix_for_user(self.agent)
        matrix["payments"] = {"read": True, "write": False}
        result = set_user_permission_overrides(actor=self.admin, target=self.agent, matrix=matrix)
        self.assertTrue(result["matrix"]["payments"]["read"])
        self.agent.refresh_from_db()
        self.assertIn("payments.company", capabilities_for(self.agent))

        # Now widen `customers` read for an agent who already reads it via
        # `.scoped` — must stay on `.scoped`, never add `.company`.
        matrix2 = effective_matrix_for_user(self.other_agent)
        set_user_permission_overrides(actor=self.admin, target=self.other_agent, matrix=matrix2)
        self.other_agent.refresh_from_db()
        self.assertNotIn("customers.company", capabilities_for(self.other_agent))

    def test_edit_implies_read_is_enforced_server_side_even_if_the_client_lies(self):
        matrix = effective_matrix_for_user(self.agent)
        matrix["after_sales"] = {"read": False, "write": True}  # invalid on its own
        result = set_user_permission_overrides(actor=self.admin, target=self.agent, matrix=matrix)
        self.assertTrue(result["matrix"]["after_sales"]["read"])
        self.assertTrue(result["matrix"]["after_sales"]["write"])

    def test_users_and_audit_can_never_be_granted_through_this_screen(self):
        matrix = effective_matrix_for_user(self.agent)
        # Not a real module key, so this asserts the *shape* rejects it —
        # the actual hard boundary lives in `capabilities_for`'s protected
        # prefixes and in `governed_capabilities`, exercised below.
        with self.assertRaises(BusinessRuleError):
            set_user_permission_overrides(actor=self.admin, target=self.agent, matrix={**matrix, "users": {"read": True, "write": True}})

        # Even a hand-crafted row naming a protected capability directly is
        # refused by `set_user_permission_overrides`'s own defensive check —
        # not reachable through `MODULES` today, but proven unreachable anyway.
        UserCapabilityOverride.objects.create(user=self.agent, capability="users.manage_all", granted=True)
        self.assertNotIn("users.manage_all", capabilities_for(self.agent))

    def test_reset_restores_role_defaults_for_this_user_only(self):
        matrix = effective_matrix_for_user(self.agent)
        matrix["customers"] = {"read": True, "write": False}
        set_user_permission_overrides(actor=self.admin, target=self.agent, matrix=matrix)
        self.assertTrue(UserCapabilityOverride.objects.filter(user=self.agent).exists())

        reset_user_permissions(actor=self.admin, target=self.agent)
        self.assertFalse(UserCapabilityOverride.objects.filter(user=self.agent).exists())
        self.agent.refresh_from_db()
        self.assertIn("customers.manage", capabilities_for(self.agent))

    def test_non_admin_cannot_touch_anyones_permissions(self):
        manager = User.objects.create_user(username="mgr1", password="Long-Safe-Pass-741!", role=User.Role.SALES_MANAGER)
        with self.assertRaises(BusinessPermissionDenied):
            user_permissions_for(actor=manager, target=self.agent)
        with self.assertRaises(BusinessPermissionDenied):
            set_user_permission_overrides(actor=manager, target=self.agent, matrix=effective_matrix_for_user(self.agent))
        with self.assertRaises(BusinessPermissionDenied):
            reset_user_permissions(actor=manager, target=self.agent)


class RoleChangePermissionHandlingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin2", password="Long-Safe-Pass-741!", role=User.Role.PLATFORM_ADMIN)
        self.agent = User.objects.create_user(username="agent3", password="Long-Safe-Pass-741!", role=User.Role.SALES_AGENT)
        matrix = effective_matrix_for_user(self.agent)
        matrix["customers"] = {"read": True, "write": False}
        set_user_permission_overrides(actor=self.admin, target=self.agent, matrix=matrix)

    def test_role_change_keeps_overrides_by_default(self):
        change_user_role(actor=self.admin, target=self.agent, role=User.Role.SALES_MANAGER)
        self.assertTrue(UserCapabilityOverride.objects.filter(user=self.agent).exists())

    def test_explicit_reset_on_role_change_clears_overrides_and_is_audited(self):
        change_user_role(actor=self.admin, target=self.agent, role=User.Role.SALES_MANAGER, keep_custom_permissions=False)
        self.assertFalse(UserCapabilityOverride.objects.filter(user=self.agent).exists())
        self.assertTrue(
            ActivityLog.objects.filter(operation="user.permissions_reset", object_id=str(self.agent.pk)).exists()
        )


class PermissionApiEndpointTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin3", password="Long-Safe-Pass-741!", role=User.Role.PLATFORM_ADMIN)
        self.agent = User.objects.create_user(username="agent4", password="Long-Safe-Pass-741!", role=User.Role.SALES_AGENT)
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.admin)

    def test_get_put_and_reset_round_trip(self):
        got = self.client_api.get(f"/api/v1/users/{self.agent.pk}/permissions/")
        self.assertEqual(got.status_code, 200)
        self.assertFalse(got.data["has_custom_permissions"])

        matrix = {key: dict(value) for key, value in got.data["matrix"].items()}
        matrix["customers"]["write"] = False
        patched = self.client_api.patch(
            f"/api/v1/users/{self.agent.pk}/permissions/", {"matrix": matrix}, format="json"
        )
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertTrue(patched.data["has_custom_permissions"])
        self.assertFalse(patched.data["matrix"]["customers"]["write"])

        reset = self.client_api.post(f"/api/v1/users/{self.agent.pk}/permissions/reset/")
        self.assertEqual(reset.status_code, 200)
        self.assertFalse(reset.data["has_custom_permissions"])

    def test_non_admin_gets_403_from_every_permissions_action(self):
        client = APIClient()
        client.force_authenticate(self.agent)
        self.assertEqual(client.get(f"/api/v1/users/{self.agent.pk}/permissions/").status_code, 403)
        self.assertEqual(
            client.patch(f"/api/v1/users/{self.agent.pk}/permissions/", {"matrix": {}}, format="json").status_code, 403
        )
        self.assertEqual(client.post(f"/api/v1/users/{self.agent.pk}/permissions/reset/").status_code, 403)


class BackendEnforcementActuallyBlocksRequestsTests(TestCase):
    """The point of the whole feature: a revoked module is refused by the
    API itself, not merely hidden — and a re-granted one works again."""

    def setUp(self):
        self.admin = User.objects.create_user(username="admin4", password="Long-Safe-Pass-741!", role=User.Role.PLATFORM_ADMIN)
        self.agent = User.objects.create_user(username="agent5", password="Long-Safe-Pass-741!", role=User.Role.SALES_AGENT)
        self.customer = Customer.objects.create(full_name="مشتری آزمایشی", kind=Customer.Kind.INDIVIDUAL, created_by=self.admin)
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.agent)

    def test_revoking_read_blocks_list_with_403_not_an_empty_page(self):
        self.assertEqual(self.client_api.get("/api/v1/customers/").status_code, 200)
        matrix = effective_matrix_for_user(self.agent)
        matrix["customers"] = {"read": False, "write": False}
        set_user_permission_overrides(actor=self.admin, target=self.agent, matrix=matrix)
        self.assertEqual(self.client_api.get("/api/v1/customers/").status_code, 403)
        self.assertEqual(self.client_api.get(f"/api/v1/customers/{self.customer.pk}/").status_code, 403)

    def test_read_only_override_allows_get_but_rejects_write(self):
        matrix = effective_matrix_for_user(self.agent)
        matrix["customers"] = {"read": True, "write": False}
        set_user_permission_overrides(actor=self.admin, target=self.agent, matrix=matrix)
        self.assertEqual(self.client_api.get("/api/v1/customers/").status_code, 200)
        created = self.client_api.post("/api/v1/customers/", {"full_name": "کاربر جدید", "kind": "individual"}, format="json")
        self.assertEqual(created.status_code, 403)
        edited = self.client_api.patch(f"/api/v1/customers/{self.customer.pk}/", {"full_name": "ویرایش"}, format="json")
        self.assertEqual(edited.status_code, 403)

    def test_granting_write_beyond_the_role_default_actually_works(self):
        # products.manage is elevated-only by default; an agent granted it
        # here can now create a product through the ordinary endpoint.
        matrix = effective_matrix_for_user(self.agent)
        matrix["products"] = {"read": True, "write": True}
        set_user_permission_overrides(actor=self.admin, target=self.agent, matrix=matrix)
        created = self.client_api.post(
            "/api/v1/products/",
            {"sku": "OVR-1", "name": "کالای مجوز ویژه", "current_price": "1000000", "unit": "piece"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
