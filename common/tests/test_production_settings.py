import importlib
import os
from pathlib import Path
from unittest import mock

from django.test import RequestFactory, SimpleTestCase, override_settings
from rest_framework.throttling import BaseThrottle


class ProductionSettingsTests(SimpleTestCase):
    def test_secure_cookies_do_not_follow_debug_environment(self):
        environment = {
            "DJANGO_SECRET_KEY": "test-only-long-private-value-for-production-settings-check-1234567890",
            "DJANGO_DEBUG": "true",
        }
        with mock.patch.dict(os.environ, environment, clear=False):
            settings_module = importlib.import_module("config.production_settings")
            settings_module = importlib.reload(settings_module)
        self.assertFalse(settings_module.DEBUG)
        self.assertTrue(settings_module.SESSION_COOKIE_SECURE)
        self.assertTrue(settings_module.CSRF_COOKIE_SECURE)
        self.assertEqual(settings_module.REST_FRAMEWORK["NUM_PROXIES"], 1)

    def test_one_proxy_identity_ignores_spoofed_prefix(self):
        rest_settings = {
            "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
            "NUM_PROXIES": 1,
        }
        request_factory = RequestFactory()
        with override_settings(REST_FRAMEWORK=rest_settings):
            first = request_factory.get("/", HTTP_X_FORWARDED_FOR="spoof-a, 203.0.113.4")
            second = request_factory.get("/", HTTP_X_FORWARDED_FOR="spoof-b, 203.0.113.4")
            other = request_factory.get("/", HTTP_X_FORWARDED_FOR="spoof-a, 203.0.113.5")
            throttle = BaseThrottle()
            self.assertEqual(throttle.get_ident(first), "203.0.113.4")
            self.assertEqual(throttle.get_ident(second), "203.0.113.4")
            self.assertEqual(throttle.get_ident(other), "203.0.113.5")

    def test_edge_owns_request_id_for_all_responses(self):
        config = (Path(__file__).resolve().parents[2] / "nginx" / "default.conf").read_text(encoding="utf-8")
        self.assertIn("add_header X-Request-ID $request_id always;", config)
        self.assertEqual(config.count("proxy_set_header X-Request-ID $request_id;"), 2)
        self.assertEqual(config.count("proxy_hide_header X-Request-ID;"), 2)
