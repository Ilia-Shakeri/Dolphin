import importlib
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import Resolver404, resolve
from rest_framework.throttling import BaseThrottle
import yaml

from config.production_env import validate_production_environment
from config.urls import build_urlpatterns


VALID_PRODUCTION_ENVIRONMENT = {
    "DJANGO_SECRET_KEY": "test-only-long-private-value-for-production-settings-check-1234567890",
    "DJANGO_ALLOWED_HOSTS": "crm.example.test",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://crm.example.test",
    "KARIZ_PUBLIC_HOST": "crm.example.test",
    "AUDIT_TRUSTED_PROXY_CIDRS": "10.20.0.0/24",
    "DJANGO_SECURE_SSL_REDIRECT": "true",
    "DJANGO_SECURE_HSTS_SECONDS": "31536000",
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS": "false",
    "DJANGO_SECURE_HSTS_PRELOAD": "false",
    "KARIZ_HSTS_HEADER": "max-age=31536000",
    "POSTGRES_DB": "kariz",
    "POSTGRES_INIT_USER": "kariz_init",
    "POSTGRES_MIGRATION_USER": "kariz_migration",
    "POSTGRES_APP_USER": "kariz_app",
    "POSTGRES_APP_PASSWORD": "test-only-app-password-741",
    "KARIZ_DATABASE_ROLE": "app",
    "POSTGRES_HOST": "db",
    "POSTGRES_PORT": "5432",
    "POSTGRES_CONNECT_TIMEOUT": "3",
}


class ProductionSettingsTests(SimpleTestCase):
    def test_secure_cookies_do_not_follow_debug_environment(self):
        environment = {**VALID_PRODUCTION_ENVIRONMENT, "DJANGO_DEBUG": "true"}
        with mock.patch.dict(os.environ, environment, clear=False):
            settings_module = importlib.import_module("config.production_settings")
            settings_module = importlib.reload(settings_module)
        self.assertFalse(settings_module.DEBUG)
        self.assertTrue(settings_module.SESSION_COOKIE_SECURE)
        self.assertTrue(settings_module.CSRF_COOKIE_SECURE)
        self.assertTrue(settings_module.SECURE_SSL_REDIRECT)
        self.assertEqual(settings_module.SECURE_HSTS_SECONDS, 31_536_000)
        self.assertFalse(settings_module.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertFalse(settings_module.ENABLE_API_DOCS)
        self.assertEqual(settings_module.REST_FRAMEWORK["NUM_PROXIES"], 1)
        self.assertEqual(settings_module.ALLOWED_HOSTS, ["crm.example.test"])
        self.assertEqual(settings_module.DATABASES["default"]["HOST"], "db")
        self.assertEqual(settings_module.DATABASES["default"]["USER"], "kariz_app")
        self.assertEqual(settings_module.DATABASES["default"]["CONN_MAX_AGE"], 60)
        self.assertEqual(
            settings_module.CACHES["default"]["BACKEND"],
            "django.core.cache.backends.filebased.FileBasedCache",
        )
        self.assertEqual(
            settings_module.CACHES["default"]["LOCATION"],
            str(Path(tempfile.gettempdir()) / "kariz-throttle-cache"),
        )
        self.assertLessEqual(
            settings_module.CACHES["default"]["OPTIONS"]["MAX_ENTRIES"],
            10_000,
        )

    @override_settings(ENABLE_API_DOCS=False)
    def test_production_url_map_excludes_schema_and_rendered_docs(self):
        production_patterns = tuple(build_urlpatterns())
        for route in ("/api/v1/schema/", "/api/v1/docs/"):
            with self.subTest(route=route):
                with self.assertRaises(Resolver404):
                    resolve(route, urlconf=production_patterns)
        self.assertNotIn(
            "schema",
            {getattr(pattern, "name", None) for pattern in production_patterns},
        )
        self.assertNotIn(
            "docs",
            {getattr(pattern, "name", None) for pattern in production_patterns},
        )

    def test_production_environment_rejects_missing_or_unsafe_values(self):
        bad_values = (
            ("DJANGO_ALLOWED_HOSTS", "*"),
            ("DJANGO_CSRF_TRUSTED_ORIGINS", "http://crm.example.test"),
            ("DJANGO_CSRF_TRUSTED_ORIGINS", "https://crm.example.test:bad"),
            ("KARIZ_PUBLIC_HOST", "Bad Host"),
            ("POSTGRES_APP_PASSWORD", "short"),
            ("POSTGRES_PORT", "not-a-port"),
            ("POSTGRES_APP_USER", "Unsafe-Role"),
            ("POSTGRES_APP_USER", "pg_reserved"),
            ("AUDIT_TRUSTED_PROXY_CIDRS", "not-a-network"),
            ("DJANGO_SECURE_SSL_REDIRECT", "yes"),
        )
        for field, value in bad_values:
            with self.subTest(field=field):
                environment = {**VALID_PRODUCTION_ENVIRONMENT, field: value}
                with self.assertRaisesMessage(ImproperlyConfigured, field):
                    validate_production_environment(environment)

        environment = dict(VALID_PRODUCTION_ENVIRONMENT)
        environment.pop("POSTGRES_HOST")
        with self.assertRaisesMessage(ImproperlyConfigured, "POSTGRES_HOST"):
            validate_production_environment(environment)

    def test_production_environment_rejects_world_proxy_networks(self):
        for value in ("0.0.0.0/0", "::/0"):
            with self.subTest(value=value):
                environment = {
                    **VALID_PRODUCTION_ENVIRONMENT,
                    "AUDIT_TRUSTED_PROXY_CIDRS": value,
                }
                with self.assertRaisesMessage(
                    ImproperlyConfigured,
                    "AUDIT_TRUSTED_PROXY_CIDRS",
                ):
                    validate_production_environment(environment)

    def test_production_environment_requires_only_exact_public_host(self):
        for value in (
            ".example.test",
            "*.example.test",
            "crm.example.test,sibling.example.test",
        ):
            with self.subTest(value=value):
                environment = {
                    **VALID_PRODUCTION_ENVIRONMENT,
                    "DJANGO_ALLOWED_HOSTS": value,
                }
                with self.assertRaisesMessage(
                    ImproperlyConfigured,
                    "DJANGO_ALLOWED_HOSTS",
                ):
                    validate_production_environment(environment)

    def test_production_environment_requires_only_exact_https_csrf_origin(self):
        for value in (
            "https://.example.test",
            "https://*.example.test",
            "https://crm.example.test,https://sibling.example.test",
            "https://crm.example.test:443",
            "https://crm.example.test/",
        ):
            with self.subTest(value=value):
                environment = {
                    **VALID_PRODUCTION_ENVIRONMENT,
                    "DJANGO_CSRF_TRUSTED_ORIGINS": value,
                }
                with self.assertRaisesMessage(
                    ImproperlyConfigured,
                    "DJANGO_CSRF_TRUSTED_ORIGINS",
                ):
                    validate_production_environment(environment)

    def test_database_roles_are_distinct_and_access_mode_is_closed(self):
        duplicate = {
            **VALID_PRODUCTION_ENVIRONMENT,
            "POSTGRES_APP_USER": "kariz_migration",
        }
        with self.assertRaisesMessage(ImproperlyConfigured, "must be distinct"):
            validate_production_environment(duplicate)

        invalid_mode = {
            **VALID_PRODUCTION_ENVIRONMENT,
            "KARIZ_DATABASE_ROLE": "owner",
        }
        with self.assertRaisesMessage(ImproperlyConfigured, "KARIZ_DATABASE_ROLE"):
            validate_production_environment(invalid_mode)

    def test_migration_mode_uses_only_migration_login(self):
        environment = {
            **VALID_PRODUCTION_ENVIRONMENT,
            "KARIZ_DATABASE_ROLE": "migration",
            "POSTGRES_MIGRATION_PASSWORD": "test-only-migration-password-852",
        }
        environment.pop("POSTGRES_APP_PASSWORD")
        validated = validate_production_environment(environment)
        self.assertEqual(validated["DATABASE"]["USER"], "kariz_migration")
        self.assertEqual(
            validated["DATABASE"]["PASSWORD"],
            "test-only-migration-password-852",
        )
        self.assertEqual(validated["DATABASE_ROLE"], "migration")

    def test_hsts_preload_needs_subdomains(self):
        environment = {
            **VALID_PRODUCTION_ENVIRONMENT,
            "DJANGO_SECURE_HSTS_PRELOAD": "true",
        }
        with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_SECURE_HSTS_PRELOAD"):
            validate_production_environment(environment)

    def test_production_tls_controls_fail_closed(self):
        for field, value in (
            ("DJANGO_SECURE_SSL_REDIRECT", "false"),
            ("DJANGO_SECURE_HSTS_SECONDS", "86400"),
        ):
            with self.subTest(field=field):
                environment = {**VALID_PRODUCTION_ENVIRONMENT, field: value}
                with self.assertRaisesMessage(ImproperlyConfigured, field):
                    validate_production_environment(environment)

        mismatch = {
            **VALID_PRODUCTION_ENVIRONMENT,
            "KARIZ_PUBLIC_HOST": "other.example.test",
        }
        with self.assertRaisesMessage(ImproperlyConfigured, "KARIZ_PUBLIC_HOST"):
            validate_production_environment(mismatch)

        bad_hsts_header = {
            **VALID_PRODUCTION_ENVIRONMENT,
            "KARIZ_HSTS_HEADER": "max-age=0",
        }
        with self.assertRaisesMessage(ImproperlyConfigured, "KARIZ_HSTS_HEADER"):
            validate_production_environment(bad_hsts_header)

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

    def test_production_default_logs_are_bounded_safe_json(self):
        with mock.patch.dict(os.environ, VALID_PRODUCTION_ENVIRONMENT, clear=False):
            settings_module = importlib.import_module("config.production_settings")
            settings_module = importlib.reload(settings_module)

        formatter = settings_module.SafeRuntimeJsonFormatter()
        request = RequestFactory().get(
            "/admin/fault/?token=query-marker",
            HTTP_AUTHORIZATION="header-marker",
        )
        request.request_id = "runtime-log-1"
        try:
            raise RuntimeError("exception-marker")
        except RuntimeError:
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="django.request",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="message-marker %s",
            args=("argument-marker",),
            exc_info=exc_info,
        )
        record.request = request

        rendered = formatter.format(record)
        payload = json.loads(rendered)
        self.assertEqual(
            set(payload),
            {
                "time",
                "event",
                "logger",
                "level",
                "request_id",
                "method",
                "path",
                "exception_type",
            },
        )
        self.assertEqual(payload["event"], "runtime_log")
        self.assertEqual(payload["request_id"], "runtime-log-1")
        self.assertEqual(payload["method"], "GET")
        self.assertEqual(payload["path"], "/admin/fault/")
        self.assertEqual(payload["exception_type"], "RuntimeError")
        for marker in (
            "query-marker",
            "header-marker",
            "message-marker",
            "argument-marker",
            "exception-marker",
        ):
            self.assertNotIn(marker, rendered)

        record.name = "n" * 300
        request.request_id = "r" * 200
        request.method = "M" * 50
        request.path = "/" + ("p" * 3000)
        bounded_payload = json.loads(formatter.format(record))
        self.assertEqual(len(bounded_payload["logger"]), 128)
        self.assertEqual(len(bounded_payload["request_id"]), 64)
        self.assertEqual(len(bounded_payload["method"]), 16)
        self.assertEqual(len(bounded_payload["path"]), 2048)

        logging_config = settings_module.LOGGING
        self.assertEqual(
            logging_config["root"],
            {"handlers": ["runtime_safe_console"], "level": "WARNING"},
        )
        self.assertEqual(
            logging_config["handlers"]["runtime_safe_console"]["stream"],
            "ext://sys.stderr",
        )
        self.assertTrue(
            {
                "django",
                "django.request",
                "django.server",
                "django.security",
                "django.db.backends",
                "gunicorn.error",
                "gunicorn.access",
            }.issubset(logging_config["loggers"])
        )
        for logger_name in settings_module._SAFE_RUNTIME_LOGGERS:
            with self.subTest(logger=logger_name):
                self.assertEqual(
                    logging_config["loggers"][logger_name]["handlers"],
                    ["runtime_safe_console"],
                )
                self.assertFalse(
                    logging_config["loggers"][logger_name]["propagate"]
                )

    def test_edge_owns_request_id_for_all_responses(self):
        config = (Path(__file__).resolve().parents[2] / "nginx" / "default.conf").read_text(encoding="utf-8")
        self.assertIn("add_header X-Request-ID $request_id always;", config)
        self.assertEqual(config.count("proxy_set_header X-Request-ID $request_id;"), 3)
        self.assertEqual(config.count("proxy_hide_header X-Request-ID;"), 3)

    def test_admin_login_is_rate_limited_and_still_proxied(self):
        config = (Path(__file__).resolve().parents[2] / "nginx" / "default.conf").read_text(encoding="utf-8")
        marker = "location = /admin/login/ {"
        self.assertEqual(config.count(marker), 1)
        block = config.split(marker, maxsplit=1)[1].split("\n    }", maxsplit=1)[0]
        self.assertIn("limit_req zone=login_limit burst=5 nodelay;", block)
        self.assertIn("limit_req_status 429;", block)
        self.assertIn("proxy_pass http://web:8000;", block)
        self.assertIn("proxy_set_header Host $host;", block)
        self.assertIn("proxy_set_header X-Real-IP $remote_addr;", block)
        self.assertIn("proxy_set_header X-Forwarded-For $remote_addr;", block)
        self.assertIn("proxy_set_header X-Forwarded-Proto https;", block)
        self.assertIn("proxy_set_header X-Request-ID $request_id;", block)
        self.assertIn("proxy_hide_header X-Request-ID;", block)
        self.assertNotIn("return ", block)

    def test_edge_requires_direct_tls_and_redirects_plain_http_to_fixed_host(self):
        root = Path(__file__).resolve().parents[2]
        config = (root / "nginx" / "default.conf").read_text(encoding="utf-8")
        compose = (root / "compose.yml").read_text(encoding="utf-8")
        self.assertIn("listen 80 default_server;", config)
        self.assertIn("return 308 https://${KARIZ_PUBLIC_HOST}$request_uri;", config)
        self.assertIn("listen 443 ssl default_server;", config)
        self.assertIn("server_name ${KARIZ_PUBLIC_HOST};", config)
        self.assertIn("ssl_certificate /etc/nginx/tls/fullchain.pem;", config)
        self.assertIn("ssl_certificate_key /etc/nginx/tls/privkey.pem;", config)
        self.assertIn("ssl_protocols TLSv1.2 TLSv1.3;", config)
        self.assertIn("ssl_session_tickets off;", config)
        self.assertIn(
            'add_header Strict-Transport-Security "${KARIZ_HSTS_HEADER}" always;',
            config,
        )
        self.assertEqual(config.count("proxy_hide_header Strict-Transport-Security;"), 3)
        self.assertEqual(config.count("proxy_set_header X-Forwarded-Proto https;"), 3)
        self.assertNotIn("proxy_set_header X-Forwarded-Proto $scheme;", config)
        self.assertIn('- "443:443"', compose)
        self.assertIn("KARIZ_TLS_CERT_PATH must name the approved certificate chain file", compose)
        self.assertIn("KARIZ_TLS_KEY_PATH must name the approved private key file", compose)
        self.assertIn("/etc/nginx/templates/default.conf.template", compose)
        self.assertIn("NGINX_ENVSUBST_FILTER: KARIZ_PUBLIC_HOST|KARIZ_HSTS_HEADER", compose)

    def test_edge_log_is_structured_bounded_and_query_free(self):
        config = (Path(__file__).resolve().parents[2] / "nginx" / "default.conf").read_text(encoding="utf-8")
        log_format = next(
            line.strip()
            for line in config.splitlines()
            if line.strip().startswith("log_format kariz_json ")
        )
        self.assertIn("escape=json", log_format)
        self.assertIn('"request_id":"$request_id"', log_format)
        self.assertIn('"uri":"$uri"', log_format)
        for unsafe_variable in (
            "$args",
            "$query_string",
            "$request_uri",
            "$http_referer",
            "$http_user_agent",
        ):
            with self.subTest(variable=unsafe_variable):
                self.assertNotIn(unsafe_variable, log_format)
        self.assertIn("access_log /dev/stdout kariz_json;", config)
        self.assertIn("error_log /dev/stderr alert;", config)
        self.assertNotIn("/var/log/nginx/", config)
        self.assertIn("proxy_connect_timeout 5s;", config)
        self.assertIn("proxy_send_timeout 30s;", config)
        self.assertIn("proxy_read_timeout 30s;", config)
        self.assertIn("send_timeout 30s;", config)

    def test_static_cache_revalidates_unversioned_paths(self):
        config = (
            Path(__file__).resolve().parents[2] / "nginx" / "default.conf"
        ).read_text(encoding="utf-8")
        marker = "location /static/ {"
        block = config.split(marker, maxsplit=1)[1].split("\n    }", maxsplit=1)[0]
        self.assertIn("expires -1;", block)
        self.assertNotIn("expires 7d;", block)
        self.assertNotIn("add_header", block)

    def test_compose_has_stable_identity_and_safe_postgres_logs(self):
        root = Path(__file__).resolve().parents[2]
        compose = yaml.safe_load((root / "compose.yml").read_text(encoding="utf-8"))
        restore = yaml.safe_load(
            (root / "compose.restore-verify.yml").read_text(encoding="utf-8")
        )
        self.assertIn("${KARIZ_COMPOSE_PROJECT_NAME:?", compose["name"])
        self.assertEqual(
            restore["name"],
            compose["name"] + "-restore-verify",
        )
        self.assertEqual(
            compose["services"]["db"]["command"],
            [
                "postgres",
                "-c",
                "log_statement=none",
                "-c",
                "log_min_duration_statement=-1",
                "-c",
                "log_min_duration_sample=-1",
                "-c",
                "log_transaction_sample_rate=0",
                "-c",
                "log_parameter_max_length=0",
                "-c",
                "log_min_error_statement=panic",
                "-c",
                "log_parameter_max_length_on_error=0",
                "-c",
                "log_error_verbosity=terse",
                "-c",
                "log_connections=off",
                "-c",
                "log_disconnections=off",
                "-c",
                "log_duration=off",
            ],
        )
        env_example = (root / ".env.example").read_text(encoding="utf-8")
        self.assertIn("KARIZ_COMPOSE_PROJECT_NAME=replace-with-", env_example)

    def test_edge_short_circuit_errors_use_stable_json_and_request_id(self):
        config = (Path(__file__).resolve().parents[2] / "nginx" / "default.conf").read_text(encoding="utf-8")
        self.assertIn("error_page 429 = @throttled;", config)
        self.assertIn("error_page 418 =503 @write_stopped;", config)
        self.assertIn("error_page 502 503 504 = @upstream_unavailable;", config)
        self.assertIn('"code":"throttled"', config)
        self.assertIn('"code":"server_error"', config)
        error_returns = [
            line.strip()
            for line in config.splitlines()
            if line.strip().startswith(("return 429 ", "return 503 "))
        ]
        self.assertEqual(len(error_returns), 4)
        self.assertTrue(
            all('"request_id":"$request_id"' in line for line in error_returns)
        )
        self.assertNotIn("proxy_intercept_errors on;", config)

    def test_edge_write_stop_is_explicit_reversible_and_read_safe(self):
        root = Path(__file__).resolve().parents[2]
        config = (root / "nginx" / "default.conf").read_text(encoding="utf-8")
        off = (root / "nginx" / "write-stop-off.conf").read_text(encoding="utf-8")
        on = (root / "nginx" / "write-stop-on.conf").read_text(encoding="utf-8")
        compose = (root / "compose.yml").read_text(encoding="utf-8")
        override = (root / "compose.write-stop.yml").read_text(encoding="utf-8")

        self.assertIn("include /etc/nginx/write-stop.conf;", config)
        self.assertEqual(config.count("if ($kariz_write_stop) {"), 2)
        self.assertEqual(config.count("return 418;"), 2)
        self.assertIn("location @write_stopped_http {", config)
        self.assertIn("location @write_stopped {", config)
        self.assertIn('"code":"server_error"', config)
        self.assertIn('"request_id":"$request_id"', config)

        self.assertIn("# kariz-write-stop: off", off)
        self.assertIn("default 0;", off)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                self.assertNotIn(f"{method} 1;", off)
                self.assertIn(f"{method} 1;", on)
        self.assertIn("# kariz-write-stop: on", on)
        self.assertIn("default 0;", on)
        self.assertNotIn("GET 1;", on)
        self.assertNotIn("HEAD 1;", on)

        self.assertIn("source: ./nginx/write-stop-off.conf", compose)
        self.assertIn("source: ./nginx/write-stop-on.conf", override)
        for source in (compose, override):
            self.assertIn("target: /etc/nginx/write-stop.conf", source)
            self.assertIn("read_only: true", source)

    def test_compose_uses_process_and_edge_liveness_with_log_limits(self):
        compose = (Path(__file__).resolve().parents[2] / "compose.yml").read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:8000/api/v1/health/live/", compose)
        self.assertNotIn("http://127.0.0.1:8000/api/v1/health/ready/", compose)
        self.assertIn("'X-Forwarded-Proto': 'https'", compose)
        self.assertIn("location = /health/live/", (Path(__file__).resolve().parents[2] / "nginx" / "default.conf").read_text(encoding="utf-8"))
        self.assertIn("http://127.0.0.1/health/live/", compose)
        self.assertEqual(compose.count("driver: json-file"), 7)
        self.assertEqual(compose.count('max-size: "10m"'), 7)
        self.assertEqual(compose.count('max-file: "5"'), 7)

    def test_docker_context_excludes_private_and_generated_data(self):
        dockerignore = (
            Path(__file__).resolve().parents[2] / ".dockerignore"
        ).read_text(encoding="utf-8").splitlines()
        required_patterns = {
            ".env*",
            "backups",
            "logs",
            "media",
            "uploads",
            "exports",
            "*.dump",
            "*.xlsx",
            "credentials.json",
            "service-account.json",
            ".pgpass",
            "*.pem",
            "*.key",
            "secrets",
        }
        self.assertTrue(required_patterns.issubset(set(dockerignore)))
