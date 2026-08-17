"""Only `platform_admin` may administer CRM users.

These tests pin the secure default of the shared codebase. `sales_manager`,
`company_it`, and `sales_agent` hold no user-administration capability, and no
combination of endpoint, direct ID, or payload may give them one.
"""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.access import assignable_roles, capabilities_for
from accounts.models import User
from accounts.services import change_user_role, create_crm_user, update_crm_user
from common.exceptions import BusinessPermissionDenied


NON_ADMIN_ROLES = (
    User.Role.SALES_MANAGER,
    User.Role.COMPANY_IT,
    User.Role.SALES_AGENT,
)


class ThrottleIsolatedTestCase(TestCase):
    """Throttle state is keyed by user id, and test user ids are reused across
    modules. Clearing the cache keeps this module from throttling later tests."""

    def tearDown(self):
        cache.clear()
        super().tearDown()


class UserAdministrationCapabilityTests(ThrottleIsolatedTestCase):
    def test_only_platform_admin_holds_a_user_management_capability(self):
        for role in User.Role.values:
            user = User.objects.create_user(
                username=f"cap-{role}", password="Long-Safe-Pass-741!", role=role
            )
            management = {
                capability
                for capability in capabilities_for(user)
                if capability.startswith("users.manage_")
            }
            with self.subTest(role=role):
                if role == User.Role.PLATFORM_ADMIN:
                    self.assertEqual(management, {"users.manage_all"})
                else:
                    self.assertEqual(management, set())


class NonAdminRolesAreDeniedThroughApiTests(ThrottleIsolatedTestCase):
    """Every mutating user-administration route is closed to non-admin roles."""

    def setUp(self):
        self.target = User.objects.create_user(
            username="target-agent", password="Long-Safe-Pass-741!", role=User.Role.SALES_AGENT
        )
        self.platform = User.objects.create_user(
            username="target-platform", password="Long-Safe-Pass-741!", role=User.Role.PLATFORM_ADMIN
        )

    def _client_for(self, role):
        actor = User.objects.create_user(
            username=f"actor-{role}", password="Long-Safe-Pass-741!", role=role
        )
        client = APIClient()
        client.force_authenticate(actor)
        return client, actor

    def test_cannot_list_or_retrieve_users(self):
        for role in NON_ADMIN_ROLES:
            client, _ = self._client_for(role)
            with self.subTest(role=role):
                self.assertEqual(client.get("/api/v1/users/").status_code, 403)
                self.assertEqual(
                    client.get(f"/api/v1/users/{self.target.pk}/").status_code, 403
                )

    def test_cannot_create_user(self):
        for role in NON_ADMIN_ROLES:
            client, _ = self._client_for(role)
            with self.subTest(role=role):
                response = client.post(
                    "/api/v1/users/",
                    {"username": f"new-by-{role}", "password": "Long-Safe-Pass-741!"},
                    format="json",
                )
                self.assertEqual(response.status_code, 403)
                self.assertFalse(User.objects.filter(username=f"new-by-{role}").exists())

    def test_cannot_edit_user_fields(self):
        for role in NON_ADMIN_ROLES:
            client, _ = self._client_for(role)
            with self.subTest(role=role):
                response = client.patch(
                    f"/api/v1/users/{self.target.pk}/",
                    {"first_name": "changed"},
                    format="json",
                )
                self.assertEqual(response.status_code, 403)
        self.target.refresh_from_db()
        self.assertNotEqual(self.target.first_name, "changed")

    def test_cannot_reset_password(self):
        original = self.target.password
        for role in NON_ADMIN_ROLES:
            client, _ = self._client_for(role)
            with self.subTest(role=role):
                response = client.patch(
                    f"/api/v1/users/{self.target.pk}/",
                    {"password": "Attacker-Chosen-Pass-1!"},
                    format="json",
                )
                self.assertEqual(response.status_code, 403)
        self.target.refresh_from_db()
        self.assertEqual(self.target.password, original)
        self.assertFalse(self.target.check_password("Attacker-Chosen-Pass-1!"))

    def test_cannot_change_workstream(self):
        for role in NON_ADMIN_ROLES:
            client, _ = self._client_for(role)
            with self.subTest(role=role):
                response = client.patch(
                    f"/api/v1/users/{self.target.pk}/",
                    {"workstream": User.Workstream.AFTER_SALES},
                    format="json",
                )
                self.assertEqual(response.status_code, 403)
        self.target.refresh_from_db()
        self.assertEqual(self.target.workstream, User.Workstream.SALES)

    def test_cannot_deactivate_or_reactivate(self):
        for role in NON_ADMIN_ROLES:
            client, _ = self._client_for(role)
            with self.subTest(role=role):
                self.assertEqual(
                    client.patch(
                        f"/api/v1/users/{self.target.pk}/",
                        {"is_active": False},
                        format="json",
                    ).status_code,
                    403,
                )
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_cannot_change_role(self):
        for role in NON_ADMIN_ROLES:
            client, _ = self._client_for(role)
            with self.subTest(role=role):
                response = client.post(
                    f"/api/v1/users/{self.target.pk}/change-role/",
                    {"role": User.Role.PLATFORM_ADMIN},
                    format="json",
                )
                self.assertEqual(response.status_code, 403)
        self.target.refresh_from_db()
        self.assertEqual(self.target.role, User.Role.SALES_AGENT)

    def test_cannot_reach_platform_admin_through_direct_id(self):
        for role in NON_ADMIN_ROLES:
            client, _ = self._client_for(role)
            with self.subTest(role=role):
                self.assertEqual(
                    client.get(f"/api/v1/users/{self.platform.pk}/").status_code, 403
                )
                self.assertEqual(
                    client.patch(
                        f"/api/v1/users/{self.platform.pk}/",
                        {"is_active": False},
                        format="json",
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    client.post(
                        f"/api/v1/users/{self.platform.pk}/change-role/",
                        {"role": User.Role.SALES_AGENT},
                        format="json",
                    ).status_code,
                    403,
                )
        self.platform.refresh_from_db()
        self.assertTrue(self.platform.is_active)
        self.assertEqual(self.platform.role, User.Role.PLATFORM_ADMIN)

    def test_cannot_escalate_self(self):
        for role in NON_ADMIN_ROLES:
            client, actor = self._client_for(role)
            with self.subTest(role=role):
                client.post(
                    f"/api/v1/users/{actor.pk}/change-role/",
                    {"role": User.Role.PLATFORM_ADMIN},
                    format="json",
                )
                actor.refresh_from_db()
                self.assertEqual(actor.role, role)


class ServiceLayerIsAuthoritativeTests(ThrottleIsolatedTestCase):
    """The gate must hold for callers that bypass the REST permission class."""

    def setUp(self):
        self.target = User.objects.create_user(
            username="svc-target", password="Long-Safe-Pass-741!", role=User.Role.SALES_AGENT
        )

    def test_services_reject_every_non_admin_role(self):
        for role in NON_ADMIN_ROLES:
            actor = User.objects.create_user(
                username=f"svc-{role}", password="Long-Safe-Pass-741!", role=role
            )
            with self.subTest(role=role):
                with self.assertRaises(BusinessPermissionDenied):
                    create_crm_user(
                        actor=actor, password="Long-Safe-Pass-741!", username=f"svc-new-{role}"
                    )
                with self.assertRaises(BusinessPermissionDenied):
                    update_crm_user(actor=actor, target=self.target, first_name="x")
                with self.assertRaises(BusinessPermissionDenied):
                    change_user_role(
                        actor=actor, target=self.target, role=User.Role.SALES_MANAGER
                    )


class PlatformAdminRetainsFullAdministrationTests(ThrottleIsolatedTestCase):
    """Hardening must not remove the legitimate administration path."""

    def setUp(self):
        self.platform = User.objects.create_user(
            username="admin", password="Long-Safe-Pass-741!", role=User.Role.PLATFORM_ADMIN
        )
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.platform)

    def test_can_list_create_edit_and_manage_lifecycle(self):
        self.assertEqual(self.client_api.get("/api/v1/users/").status_code, 200)

        created = self.client_api.post(
            "/api/v1/users/",
            {"username": "fresh-agent", "password": "Long-Safe-Pass-741!"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        target_id = created.data["id"]
        self.assertEqual(User.objects.get(pk=target_id).role, User.Role.SALES_AGENT)

        self.assertEqual(
            self.client_api.patch(
                f"/api/v1/users/{target_id}/", {"first_name": "Ali"}, format="json"
            ).status_code,
            200,
        )
        # Not even a Platform Admin changes a password through the API: no role
        # is offered the control anywhere, so the API declines it too.
        self.assertEqual(
            self.client_api.patch(
                f"/api/v1/users/{target_id}/",
                {"password": "Rotated-Safe-Pass-1!"},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client_api.patch(
                f"/api/v1/users/{target_id}/",
                {"workstream": User.Workstream.AFTER_SALES},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client_api.patch(
                f"/api/v1/users/{target_id}/", {"is_active": False}, format="json"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client_api.patch(
                f"/api/v1/users/{target_id}/", {"is_active": True}, format="json"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client_api.post(
                f"/api/v1/users/{target_id}/change-role/",
                {"role": User.Role.SALES_MANAGER},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            User.objects.get(pk=target_id).role, User.Role.SALES_MANAGER
        )


class MaintainedUiRespectsPolicyTests(ThrottleIsolatedTestCase):
    """Navigation and pages follow the capability, with no separate role check."""

    def _login(self, role):
        User.objects.create_user(
            username=f"ui-{role}", password="Long-Safe-Pass-741!", role=role
        )
        client = self.client_class()
        client.login(username=f"ui-{role}", password="Long-Safe-Pass-741!")
        return client

    def test_non_admin_roles_are_denied_the_user_pages(self):
        target = User.objects.create_user(
            username="ui-target", password="Long-Safe-Pass-741!", role=User.Role.SALES_AGENT
        )
        for role in NON_ADMIN_ROLES:
            client = self._login(role)
            with self.subTest(role=role):
                self.assertEqual(client.get("/users/").status_code, 403)
                self.assertEqual(client.get(f"/users/{target.pk}/").status_code, 403)

    def test_non_admin_home_hides_user_administration(self):
        for role in NON_ADMIN_ROLES:
            client = self._login(role)
            with self.subTest(role=role):
                response = client.get("/")
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.context["can_manage_users"])
                self.assertNotContains(response, 'href="/users/"')

    def test_platform_admin_home_still_offers_user_administration(self):
        client = self._login(User.Role.PLATFORM_ADMIN)
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_manage_users"])
        self.assertContains(response, 'href="/users/"')


class InternalItRoleGateTests(TestCase):
    """`company_it` is a deployment feature, not a fixed part of the product.

    Client-1 policy is that only a Platform Admin administers users, so that
    role is absent from its manifest. Another deployment may want an on-site
    technical account, so the role is gated rather than deleted — and the gate
    has to hold at the API, not only in the page.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            username="gate.admin", password="Strong-pass-937!", role=User.Role.PLATFORM_ADMIN
        )
        self.agent = User.objects.create_user(
            username="gate.agent", password="Strong-pass-937!", role=User.Role.SALES_AGENT
        )

    @staticmethod
    def without_internal_it():
        from common.deployment.profile import DeploymentProfile
        from common.deployment.registry import ALL_FEATURES

        return DeploymentProfile(
            profile_id="client-1",
            features=frozenset(ALL_FEATURES) - {"internal_it_role"},
            source="signed-manifest",
        )

    def test_the_service_refuses_the_role_even_for_a_platform_admin(self):
        from common.deployment.profile import override_active_profile

        with override_active_profile(self.without_internal_it()):
            with self.assertRaises(BusinessPermissionDenied):
                change_user_role(actor=self.admin, target=self.agent, role=User.Role.COMPANY_IT)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.role, User.Role.SALES_AGENT)

    def test_the_api_refuses_it_too(self):
        from common.deployment.profile import override_active_profile

        self.client.force_login(self.admin)
        with override_active_profile(self.without_internal_it()):
            response = self.client.post(
                f"/api/v1/users/{self.agent.pk}/change-role/",
                data={"role": "company_it"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 403)

    def test_the_page_does_not_offer_a_role_the_deployment_does_not_run(self):
        from common.deployment.profile import override_active_profile

        self.client.force_login(self.admin)
        with override_active_profile(self.without_internal_it()):
            content = self.client.get(f"/users/{self.agent.pk}/").content.decode("utf-8")
        self.assertNotIn('value="company_it"', content)
        self.assertIn('value="sales_agent"', content)
        self.assertIn('value="sales_manager"', content)
        self.assertIn('value="platform_admin"', content)

    def test_a_deployment_that_runs_the_role_still_offers_and_accepts_it(self):
        self.client.force_login(self.admin)
        content = self.client.get(f"/users/{self.agent.pk}/").content.decode("utf-8")
        self.assertIn('value="company_it"', content)
        change_user_role(actor=self.admin, target=self.agent, role=User.Role.COMPANY_IT)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.role, User.Role.COMPANY_IT)

    def test_a_sales_manager_is_never_offered_the_platform_admin_role(self):
        manager = User.objects.create_user(
            username="gate.manager", password="Strong-pass-937!", role=User.Role.SALES_MANAGER
        )
        self.assertNotIn(
            "platform_admin", [value for value, _ in assignable_roles(manager)]
        )
        self.assertIn("platform_admin", [value for value, _ in assignable_roles(self.admin)])
