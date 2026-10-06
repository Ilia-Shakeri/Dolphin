"""A marketer imports a customer list once an admin allows it (2.40.32)."""

from django.test import TestCase

from accounts.access import has_any_capability
from accounts.models import User
from accounts.module_permissions import effective_matrix_for_user
from accounts.services import set_user_permission_overrides


class ImportPermissionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="ip.admin", password="Strong-pass-274!", role=User.Role.PLATFORM_ADMIN)
        self.agent = User.objects.create_user(username="ip.agent", password="Strong-pass-274!", role=User.Role.SALES_AGENT)

    def test_a_marketer_starts_without_it_and_an_admin_grants_it(self):
        self.assertFalse(has_any_capability(self.agent, "customers.import"))
        matrix = {key: {"read": row["read"], "write": row["write"], "delete": row["delete"]}
                  for key, row in effective_matrix_for_user(self.agent).items()}
        self.assertFalse(matrix["customers_import"]["read"])
        matrix["customers_import"]["read"] = True
        set_user_permission_overrides(actor=self.admin, target=self.agent, matrix=matrix)
        self.agent = User.objects.get(pk=self.agent.pk)
        self.assertTrue(has_any_capability(self.agent, "customers.import"))
        # Nothing else widened with it.
        self.assertFalse(has_any_capability(self.agent, "customers.company"))
