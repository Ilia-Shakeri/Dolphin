from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from common.throttles import SensitiveRateThrottle


class SensitiveReadThrottleTests(TestCase):
    @mock.patch.object(SensitiveRateThrottle, "get_rate", lambda self: "1/min")
    def test_audit_json_report_and_xlsx_export_are_throttled(self):
        actor = User.objects.create_user(
            username="sensitive-read-admin",
            password="Long-Safe-Pass-741!",
            role=User.Role.PLATFORM_ADMIN,
        )
        period = "period_start=2026-01-01T00%3A00%3A00Z&period_end=2026-02-01T00%3A00%3A00Z"
        urls = (
            "/api/v1/activity-logs/",
            f"/api/v1/reports/user-performance/?{period}",
            f"/api/v1/exports/user-performance.xlsx?{period}",
        )

        for url in urls:
            with self.subTest(url=url):
                cache.clear()
                client = APIClient()
                client.force_authenticate(actor)
                self.assertEqual(client.get(url).status_code, 200)
                throttled = client.get(url)
                self.assertEqual(throttled.status_code, 429)
                self.assertEqual(throttled.data["error"]["code"], "throttled")
        cache.clear()
