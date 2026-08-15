import re
from unittest import mock

from django.conf import settings
from django.db import connection
from django.db.utils import OperationalError
from django.test import TestCase, override_settings
from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient
from rest_framework.views import APIView

from accounts.models import User
from auditlog.models import ActivityLog


class FaultProbeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        raise RuntimeError("private-fault-marker")


urlpatterns = [
    path("api/v1/fault-probe/", FaultProbeView.as_view()),
]


class SystemApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="schema-user",
            password="Long-Safe-Pass-741!",
            role=User.Role.PLATFORM_ADMIN,
        )

    def test_health_splits_liveness_and_readiness(self):
        client = APIClient()
        self.assertEqual(client.get("/api/v1/health/live/").status_code, 200)
        ready = client.get("/api/v1/health/ready/")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.data["database"], "up")

    def test_readiness_reports_unavailable_when_the_database_cannot_answer(self):
        """Readiness must fail closed, and liveness must stay independent of it.

        Proven by making the connection raise rather than by stopping a server,
        so the gate runs on every vendor and on every suite run instead of being
        a one-off manual observation.
        """
        client = APIClient()
        with mock.patch.object(
            connection, "cursor", side_effect=OperationalError("connection refused")
        ):
            ready = client.get("/api/v1/health/ready/")
            self.assertEqual(ready.status_code, 503)
            self.assertEqual(ready.data["status"], "unavailable")
            self.assertEqual(ready.data["database"], "down")
            # A dead database must not take the process out of rotation.
            self.assertEqual(client.get("/api/v1/health/live/").status_code, 200)
            # Nothing about the failure may leak connection detail.
            body = ready.content.decode("utf-8")
            for leaked in ("connection refused", "password", "host", "port", "user"):
                with self.subTest(leaked=leaked):
                    self.assertNotIn(leaked, body.lower())

        self.assertEqual(client.get("/api/v1/health/ready/").status_code, 200)

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_security_redirect_has_request_id(self):
        response = APIClient().get("/api/v1/health/live/")
        self.assertEqual(response.status_code, 301)
        self.assertRegex(response["X-Request-ID"], re.compile(r"^[0-9a-f]{32}$"))

    def test_schema_and_docs_require_active_login(self):
        client = APIClient()
        self.assertEqual(client.get("/api/v1/schema/").status_code, 403)
        self.assertEqual(client.get("/api/v1/docs/").status_code, 403)
        client.force_authenticate(self.user)
        self.assertEqual(client.get("/api/v1/schema/").status_code, 200)
        docs_response = client.get("/api/v1/docs/")
        self.assertEqual(docs_response.status_code, 200)
        self.assertContains(
            docs_response,
            "https://cdn.jsdelivr.net/npm/swagger-ui-dist",
        )

    def test_schema_documents_status_filters(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/v1/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
        self.assertEqual(response.status_code, 200)
        lead_parameters = response.data["paths"]["/api/v1/leads/"]["get"]["parameters"]
        sale_parameters = response.data["paths"]["/api/v1/sales/"]["get"]["parameters"]
        product_parameters = response.data["paths"]["/api/v1/products/"]["get"]["parameters"]
        self.assertIn("status", {parameter["name"] for parameter in lead_parameters})
        self.assertIn("status", {parameter["name"] for parameter in sale_parameters})
        self.assertIn("is_active", {parameter["name"] for parameter in product_parameters})

    def test_schema_documents_phone_filter_and_assignment_reads(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/v1/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
        self.assertEqual(response.status_code, 200)

        phone_parameters = response.data["paths"]["/api/v1/customer-phones/"]["get"]["parameters"]
        self.assertIn("customer", {parameter["name"] for parameter in phone_parameters})
        self.assertIn("post", response.data["paths"]["/api/v1/customer-phones/{id}/deactivate/"])
        self.assertIn("get", response.data["paths"]["/api/v1/leads/assignees/"])
        history = response.data["paths"]["/api/v1/leads/{id}/assignment-history/"]["get"]
        self.assertIn("page", {parameter["name"] for parameter in history["parameters"]})
        for relation in ("leads", "interactions", "sales"):
            related = response.data["paths"][f"/api/v1/customers/{{id}}/{relation}/"]["get"]
            self.assertIn("page", {parameter["name"] for parameter in related["parameters"]})

    def test_schema_documents_exact_custom_action_contracts(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/v1/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
        self.assertEqual(response.status_code, 200)

        contracts = {
            "/api/v1/users/{id}/change-role/": (
                "RoleChange",
                {"200", "400", "403", "404", "409"},
            ),
            "/api/v1/customers/{id}/deactivate/": (
                None,
                {"200", "403", "404", "409"},
            ),
            "/api/v1/leads/{id}/reassign/": (
                "Reassign",
                {"200", "400", "403", "404", "409"},
            ),
            "/api/v1/products/{id}/deactivate/": (
                None,
                {"200", "403", "404", "409"},
            ),
            "/api/v1/sales/{id}/cancel/": (
                "CancelSale",
                {"200", "400", "403", "404", "409"},
            ),
        }
        for route, (request_component, response_codes) in contracts.items():
            with self.subTest(route=route):
                operation = response.data["paths"][route]["post"]
                self.assertTrue(response_codes.issubset(operation["responses"]))
                if request_component is None:
                    self.assertNotIn("requestBody", operation)
                else:
                    request_media = operation["requestBody"]["content"]["application/json"]
                    self.assertEqual(
                        request_media["schema"]["$ref"],
                        f"#/components/schemas/{request_component}",
                    )
                    self.assertTrue(request_media.get("examples"))
                for code in response_codes - {"200"}:
                    error_media = operation["responses"][code]["content"]["application/json"]
                    self.assertEqual(
                        error_media["schema"]["$ref"],
                        "#/components/schemas/ApiErrorEnvelope",
                    )
                    self.assertTrue(error_media.get("examples"))

    def test_schema_uses_shared_error_envelope_for_declared_errors(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/v1/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
        self.assertEqual(response.status_code, 200)

        declared_errors = {
            ("/api/v1/auth/login/", "post"): {"400", "403", "429"},
            ("/api/v1/auth/logout/", "post"): {"403"},
            ("/api/v1/auth/me/", "patch"): {"400", "403"},
            ("/api/v1/reports/user-performance/", "get"): {"400", "403"},
            ("/api/v1/reports/user-performance/details/", "get"): {"400", "403"},
            ("/api/v1/exports/user-performance.xlsx", "get"): {"400", "403"},
        }
        for (route, method), codes in declared_errors.items():
            operation = response.data["paths"][route][method]
            for code in codes:
                with self.subTest(route=route, method=method, code=code):
                    error_media = operation["responses"][code]["content"]["application/json"]
                    self.assertEqual(
                        error_media["schema"]["$ref"],
                        "#/components/schemas/ApiErrorEnvelope",
                    )
                    self.assertTrue(error_media.get("examples"))

        components = response.data["components"]["schemas"]
        self.assertIn("error", components["ApiErrorEnvelope"]["required"])
        self.assertNotIn("detail", components["ApiErrorEnvelope"]["required"])
        self.assertEqual(
            set(components["ApiErrorReference"]["required"]),
            {"code", "request_id"},
        )

    def test_schema_documents_common_errors_and_request_id_header(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/v1/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
        self.assertEqual(response.status_code, 200)

        operations = {
            ("/api/v1/customers/", "get"): {"400", "403", "406", "429", "500"},
            ("/api/v1/customers/", "post"): {"400", "403", "406", "409", "413", "415", "429", "500"},
            ("/api/v1/customers/{id}/", "get"): {"400", "403", "404", "406", "429", "500"},
            ("/api/v1/customers/{id}/", "patch"): {
                "400",
                "403",
                "404",
                "406",
                "409",
                "413",
                "415",
                "429",
                "500",
            },
        }
        for (route, method), error_codes in operations.items():
            with self.subTest(route=route, method=method):
                operation = response.data["paths"][route][method]
                self.assertTrue(error_codes.issubset(operation["responses"]))
                for code, documented in operation["responses"].items():
                    self.assertIn("X-Request-ID", documented["headers"])
                    if code in error_codes:
                        error_media = documented["content"]["application/json"]
                        self.assertEqual(
                            error_media["schema"]["$ref"],
                            "#/components/schemas/ApiErrorEnvelope",
                        )
                        self.assertTrue(error_media["examples"])

    def test_normal_api_is_json_only_for_request_and_response_media(self):
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"],
            ["rest_framework.renderers.JSONRenderer"],
        )
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_PARSER_CLASSES"],
            ["common.parsers.BoundedJSONParser"],
        )

        client = APIClient()
        client.force_authenticate(self.user)
        html = client.get("/api/v1/customers/", HTTP_ACCEPT="text/html")
        self.assertEqual(html.status_code, 406)
        self.assertEqual(html["Content-Type"], "application/json")
        self.assertEqual(html.data["error"]["code"], "not_acceptable")

        browsable_format = client.get("/api/v1/customers/?format=api")
        self.assertEqual(browsable_format.status_code, 404)
        self.assertEqual(browsable_format["Content-Type"], "application/json")
        self.assertEqual(browsable_format.data["error"]["code"], "not_found")

        for content_type in (
            "application/x-www-form-urlencoded",
            "multipart/form-data; boundary=kariz-boundary",
        ):
            with self.subTest(content_type=content_type):
                response = client.post(
                    "/api/v1/customers/",
                    "full_name=WrongMedia",
                    content_type=content_type,
                )
                self.assertEqual(response.status_code, 415)
                self.assertEqual(response["Content-Type"], "application/json")
                self.assertEqual(
                    response.data["error"]["code"],
                    "unsupported_media_type",
                )

    def test_viewset_query_parameters_reject_unknown_and_repeated_keys(self):
        client = APIClient()
        client.force_authenticate(self.user)

        unknown = client.get("/api/v1/customers/?typo=value")
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual([str(item) for item in unknown.data["typo"]], ["Unknown query parameter."])
        self.assertEqual(unknown.data["error"]["code"], "validation_error")

        repeated = client.get("/api/v1/customers/?search=one&search=two")
        self.assertEqual(repeated.status_code, 400)
        self.assertEqual(
            [str(item) for item in repeated.data["search"]],
            ["Query parameter must appear once."],
        )

        detail_query = client.get("/api/v1/customers/999999/?search=value")
        self.assertEqual(detail_query.status_code, 400)
        self.assertIn("search", detail_query.data)

        self.assertEqual(client.get("/api/v1/leads/?status=new").status_code, 200)
        self.assertEqual(client.get("/api/v1/sales/?status=confirmed").status_code, 200)
        self.assertEqual(client.get("/api/v1/products/?is_active=true").status_code, 200)

    def test_api_errors_have_stable_code_and_matching_request_id(self):
        client = APIClient()
        client.force_authenticate(self.user)
        invalid = client.post(
            "/api/v1/customers/",
            {},
            format="json",
            HTTP_X_REQUEST_ID="error-validation-1",
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("full_name", invalid.data)
        self.assertEqual(
            invalid.data["error"],
            {"code": "validation_error", "request_id": "error-validation-1"},
        )
        self.assertEqual(invalid["X-Request-ID"], "error-validation-1")

        missing = client.get(
            "/api/v1/customers/999999/",
            HTTP_X_REQUEST_ID="error-missing-1",
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(
            missing.data["error"],
            {"code": "not_found", "request_id": "error-missing-1"},
        )

        agent = User.objects.create_user(
            username="blocked-product-user",
            password="Long-Safe-Pass-741!",
            role=User.Role.SALES_AGENT,
        )
        client.force_authenticate(agent)
        denied = client.post(
            "/api/v1/products/",
            {"sku": "NO", "name": "No", "current_price": "1.00"},
            format="json",
            HTTP_X_REQUEST_ID="error-denied-1",
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(
            denied.data["error"],
            {"code": "permission_denied", "request_id": "error-denied-1"},
        )

    @override_settings(ROOT_URLCONF="common.tests.test_system_api")
    def test_unhandled_api_error_is_safe_json_with_request_id(self):
        with mock.patch("common.exceptions.write_server_fault_log") as fault_log:
            response = APIClient().get(
                "/api/v1/fault-probe/",
                HTTP_X_REQUEST_ID="error-server-1",
            )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response["X-Request-ID"], "error-server-1")
        self.assertEqual(
            response.data,
            {
                "detail": "Internal server error.",
                "error": {
                    "code": "server_error",
                    "request_id": "error-server-1",
                },
            },
        )
        self.assertNotIn("private-fault-marker", str(response.data))
        fault_log.assert_called_once()
        self.assertEqual(fault_log.call_args.kwargs["request"].path, "/api/v1/fault-probe/")

    def test_unknown_api_route_uses_safe_json_but_unknown_ui_route_stays_html(self):
        api_response = APIClient().get(
            "/api/v1/not-a-real-route/",
            HTTP_X_REQUEST_ID="error-route-1",
        )
        self.assertEqual(api_response.status_code, 404)
        self.assertEqual(api_response["Content-Type"], "application/json")
        self.assertEqual(api_response["X-Request-ID"], "error-route-1")
        self.assertEqual(
            api_response.json(),
            {
                "detail": "Not found.",
                "error": {
                    "code": "not_found",
                    "request_id": "error-route-1",
                },
            },
        )

        ui_response = APIClient().get("/not-a-real-page/")
        self.assertEqual(ui_response.status_code, 404)
        self.assertTrue(ui_response["Content-Type"].startswith("text/html"))

    def test_request_id_is_returned_and_bound_to_audit(self):
        client = APIClient()
        client.force_authenticate(self.user)
        first = client.patch(
            "/api/v1/auth/me/",
            {"first_name": "Trace"},
            format="json",
            HTTP_X_REQUEST_ID="crm.test-123",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first["X-Request-ID"], "crm.test-123")
        first_log = ActivityLog.objects.get(operation="user.profile_updated", object_id=str(self.user.pk))
        self.assertEqual(first_log.request_id, "crm.test-123")
        self.assertEqual(str(first_log.ip_address), "127.0.0.1")

        second = client.patch(
            "/api/v1/auth/me/",
            {"last_name": "Fresh"},
            format="json",
            HTTP_X_REQUEST_ID="bad request id",
        )
        self.assertEqual(second.status_code, 200)
        self.assertRegex(second["X-Request-ID"], re.compile(r"^[0-9a-f]{32}$"))
        self.assertNotEqual(second["X-Request-ID"], first["X-Request-ID"])
        second_log = ActivityLog.objects.filter(
            operation="user.profile_updated",
            object_id=str(self.user.pk),
        ).latest("id")
        self.assertEqual(second_log.request_id, second["X-Request-ID"])

    @override_settings(AUDIT_TRUSTED_PROXY_CIDRS=["10.20.0.0/24"])
    def test_audit_ip_trusts_only_configured_proxy_peer(self):
        client = APIClient()
        client.force_authenticate(self.user)
        trusted = client.patch(
            "/api/v1/auth/me/",
            {"first_name": "Trusted"},
            format="json",
            REMOTE_ADDR="10.20.0.4",
            HTTP_X_REAL_IP="203.0.113.8",
        )
        self.assertEqual(trusted.status_code, 200)
        trusted_log = ActivityLog.objects.get(operation="user.profile_updated", object_id=str(self.user.pk))
        self.assertEqual(str(trusted_log.ip_address), "203.0.113.8")

        untrusted = client.patch(
            "/api/v1/auth/me/",
            {"last_name": "Peer"},
            format="json",
            REMOTE_ADDR="198.51.100.7",
            HTTP_X_REAL_IP="203.0.113.9",
        )
        self.assertEqual(untrusted.status_code, 200)
        untrusted_log = ActivityLog.objects.filter(
            operation="user.profile_updated",
            object_id=str(self.user.pk),
        ).latest("id")
        self.assertEqual(str(untrusted_log.ip_address), "198.51.100.7")
