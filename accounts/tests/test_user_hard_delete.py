"""`UserViewSet`'s own `_extra_delete_guard` on top of `HardDeleteMixin`'s
blanket Platform-Admin-only gate: nobody deletes their own signed-in account
through this endpoint, and the Platform Admin account is never removable
through it at all — see [[PlatformAdminSingletonTests]] in
test_user_administration_policy.py for the matching "never a *second* one"
half of the same invariant.
"""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog


class ThrottleIsolatedTestCase(TestCase):
    def tearDown(self):
        cache.clear()
        super().tearDown()


def _client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class UserHardDeleteTests(ThrottleIsolatedTestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="hd.admin2", password="Strong-pass-937!", role=User.Role.PLATFORM_ADMIN
        )
        self.mistaken = User.objects.create_user(
            username="hd.mistaken", password="Strong-pass-937!", role=User.Role.SALES_AGENT
        )

    def test_admin_deletes_an_unused_account(self):
        response = _client(self.admin).delete(f"/api/v1/users/{self.mistaken.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.mistaken.pk).exists())
        log = ActivityLog.objects.get(operation="user.deleted", object_id=str(self.mistaken.pk))
        self.assertEqual(log.actor_id, self.admin.pk)

    def test_admin_cannot_delete_their_own_account(self):
        response = _client(self.admin).delete(f"/api/v1/users/{self.admin.pk}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_platform_admin_account_is_never_deletable_here(self):
        second_admin = User.objects.create_user(
            username="hd.admin3", password="Strong-pass-937!", role=User.Role.PLATFORM_ADMIN
        )
        response = _client(self.admin).delete(f"/api/v1/users/{second_admin.pk}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=second_admin.pk).exists())

    def test_a_user_with_history_is_protected_not_orphaned(self):
        from sales.services import create_customer_with_phone

        create_customer_with_phone(actor=self.mistaken, full_name="مشتری ثبت‌شده توسط این کاربر")
        response = _client(self.admin).delete(f"/api/v1/users/{self.mistaken.pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(User.objects.filter(pk=self.mistaken.pk).exists())

    def test_non_admin_cannot_delete_anyone(self):
        agent = User.objects.create_user(
            username="hd.agent", password="Strong-pass-937!", role=User.Role.SALES_AGENT
        )
        response = _client(agent).delete(f"/api/v1/users/{self.mistaken.pk}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.mistaken.pk).exists())

    def test_bulk_delete_skips_self_and_the_admin_but_deletes_the_rest(self):
        other_mistaken = User.objects.create_user(
            username="hd.mistaken2", password="Strong-pass-937!", role=User.Role.SALES_AGENT
        )
        response = _client(self.admin).post(
            "/api/v1/users/bulk-delete/",
            {"ids": [self.mistaken.pk, other_mistaken.pk, self.admin.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertCountEqual(data["deleted"], [self.mistaken.pk, other_mistaken.pk])
        self.assertEqual(data["denied"], [self.admin.pk])
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())
