import json
import logging
from contextlib import contextmanager
from io import StringIO
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from common.request_context import bind_request_context, current_request_context, reset_request_context
from common.request_logging import (
    REQUEST_LOGGER_NAME,
    SERVER_FAULT_LOGGER_NAME,
    RequestJsonFormatter,
    ServerFaultJsonFormatter,
    write_request_log,
    write_server_fault_log,
)


class RequestLoggingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="request-log-user",
            password="Long-Safe-Pass-741!",
            role=User.Role.PLATFORM_ADMIN,
        )

    @contextmanager
    def capture_request_logs(self):
        logger = logging.getLogger(REQUEST_LOGGER_NAME)
        old_handlers = list(logger.handlers)
        old_level = logger.level
        old_propagate = logger.propagate
        old_disabled = logger.disabled
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(RequestJsonFormatter())
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.disabled = False
        try:
            yield stream
        finally:
            logger.handlers = old_handlers
            logger.setLevel(old_level)
            logger.propagate = old_propagate
            logger.disabled = old_disabled

    def parsed_lines(self, stream):
        return [json.loads(line) for line in stream.getvalue().splitlines() if line]

    def test_success_log_has_safe_fields_same_id_and_no_query_or_headers(self):
        client = APIClient()
        with self.capture_request_logs() as stream:
            response = client.get(
                "/api/v1/health/live/?token=query-marker&password=query-pass-marker",
                HTTP_X_REQUEST_ID="request-log-123",
                HTTP_AUTHORIZATION="Bearer header-marker",
                HTTP_USER_AGENT="agent-marker",
            )

        self.assertEqual(response.status_code, 200)
        logs = self.parsed_lines(stream)
        self.assertEqual(len(logs), 1)
        payload = logs[0]
        self.assertEqual(
            set(payload),
            {"event", "request_id", "method", "path", "status", "duration_ms"},
        )
        self.assertEqual(payload["event"], "http_request")
        self.assertEqual(payload["request_id"], response["X-Request-ID"])
        self.assertEqual(payload["request_id"], "request-log-123")
        self.assertEqual(payload["method"], "GET")
        self.assertEqual(payload["path"], "/api/v1/health/live/")
        self.assertEqual(payload["status"], 200)
        self.assertGreaterEqual(payload["duration_ms"], 0)
        rendered = stream.getvalue()
        for marker in ("query-marker", "query-pass-marker", "header-marker", "agent-marker"):
            self.assertNotIn(marker, rendered)
        self.assertEqual(current_request_context().request_id, "")
        self.assertIsNone(current_request_context().ip_address)

    def test_validation_error_logs_once_without_body(self):
        client = APIClient()
        client.force_authenticate(self.user)
        with self.capture_request_logs() as stream:
            response = client.post(
                "/api/v1/customers/",
                {"password": "body-marker"},
                format="json",
                HTTP_X_REQUEST_ID="request-log-error",
            )

        self.assertEqual(response.status_code, 400)
        logs = self.parsed_lines(stream)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["status"], 400)
        self.assertEqual(logs[0]["request_id"], response["X-Request-ID"])
        self.assertNotIn("body-marker", stream.getvalue())

    def test_formatter_escapes_method_and_path_as_valid_json(self):
        token = bind_request_context(request_id="escape-log-1")
        try:
            with self.capture_request_logs() as stream:
                write_request_log(
                    method='G"ET',
                    path='/odd/"line\n',
                    status=202,
                    duration_ms=1.25,
                )
        finally:
            reset_request_context(token)

        lines = self.parsed_lines(stream)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["method"], 'G"ET')
        self.assertEqual(lines[0]["path"], '/odd/"line\n')
        self.assertEqual(lines[0]["request_id"], "escape-log-1")
        self.assertEqual(len(stream.getvalue().splitlines()), 1)
        self.assertEqual(current_request_context().request_id, "")

    def test_logging_failure_never_breaks_response_or_context_reset(self):
        client = APIClient()
        with mock.patch(
            "common.middleware.write_request_log",
            side_effect=RuntimeError("log sink failed"),
        ):
            response = client.get(
                "/api/v1/health/live/",
                HTTP_X_REQUEST_ID="request-log-failure",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Request-ID"], "request-log-failure")
        self.assertEqual(current_request_context().request_id, "")
        self.assertIsNone(current_request_context().ip_address)

    def test_server_fault_log_has_safe_type_and_frames_without_fault_text(self):
        logger = logging.getLogger(SERVER_FAULT_LOGGER_NAME)
        old_handlers = list(logger.handlers)
        old_level = logger.level
        old_propagate = logger.propagate
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(ServerFaultJsonFormatter())
        logger.handlers = [handler]
        logger.setLevel(logging.ERROR)
        logger.propagate = False
        token = bind_request_context(request_id="server-fault-1")
        request = mock.Mock(method="POST", path="/api/v1/fault/")
        try:
            try:
                raise RuntimeError("private-fault-marker")
            except RuntimeError as exc:
                write_server_fault_log(exc=exc, request=request)
        finally:
            reset_request_context(token)
            logger.handlers = old_handlers
            logger.setLevel(old_level)
            logger.propagate = old_propagate

        rendered = stream.getvalue()
        payload = json.loads(rendered)
        self.assertEqual(
            set(payload),
            {"event", "request_id", "method", "path", "exception_type", "frames"},
        )
        self.assertEqual(payload["event"], "server_fault")
        self.assertEqual(payload["request_id"], "server-fault-1")
        self.assertEqual(payload["exception_type"], "RuntimeError")
        self.assertTrue(payload["frames"])
        self.assertNotIn("private-fault-marker", rendered)
