from dataclasses import replace
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unittest

from django.test import SimpleTestCase

from scripts import load_readiness


REPO_ROOT = Path(__file__).resolve().parents[2]
LOAD_SCRIPT = REPO_ROOT / "scripts" / "load_readiness.py"
LOAD_RUNBOOK = REPO_ROOT / "docs" / "ops" / "LOAD_TEST.md"


class _HealthHandler(BaseHTTPRequestHandler):
    response_status = 200
    redirect_location = ""
    seen = []
    seen_lock = threading.Lock()

    def do_GET(self):
        with self.seen_lock:
            self.seen.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "proxy_authorization": self.headers.get("Proxy-Authorization"),
                    "cookie": self.headers.get("Cookie"),
                    "content_length": self.headers.get("Content-Length"),
                }
            )
        self.send_response(self.response_status)
        if self.redirect_location:
            self.send_header("Location", self.redirect_location)
        body = b"ok" if self.response_status == 200 else b"response-marker"
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string, *arguments):
        return


class LoadReadinessTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        _HealthHandler.response_status = 200
        _HealthHandler.redirect_location = ""
        _HealthHandler.seen = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
        self.server.daemon_threads = True
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=3)
        super().tearDown()

    def _arguments(self, **overrides):
        values = {
            "sentinel": load_readiness.READ_ONLY_SENTINEL,
            "base_url": f"http://127.0.0.1:{self.server.server_port}",
            "confirm_host": "127.0.0.1",
            "path": "/health/live/",
            "requests": "6",
            "concurrency": "2",
            "timeout_seconds": "1",
            "max_wall_seconds": "5",
            "max_p95_ms": "5000",
            "min_requests_per_second": "0.01",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_loopback_run_is_get_only_aggregate_and_secret_free(self):
        config = load_readiness.validate_arguments(self._arguments())
        result = load_readiness.execute_load(config)

        self.assertTrue(result["passed"])
        self.assertEqual(result["requested"], 6)
        self.assertEqual(result["completed"], 6)
        self.assertEqual(result["succeeded"], 6)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["error_rate_percent"], 0.0)
        self.assertEqual(result["status_counts"], {"200": 6})
        self.assertEqual(len(_HealthHandler.seen), 6)
        for request in _HealthHandler.seen:
            with self.subTest(request=request):
                self.assertEqual(request["method"], "GET")
                self.assertEqual(request["path"], "/health/live/")
                self.assertIsNone(request["authorization"])
                self.assertIsNone(request["proxy_authorization"])
                self.assertIsNone(request["cookie"])
                self.assertIsNone(request["content_length"])

        rendered = json.dumps(result, sort_keys=True)
        self.assertNotIn("127.0.0.1", rendered)
        self.assertNotIn(str(self.server.server_port), rendered)
        self.assertNotIn("response-marker", rendered)

    def test_redirect_is_not_followed_and_fails_the_run(self):
        _HealthHandler.response_status = 302
        _HealthHandler.redirect_location = (
            f"http://127.0.0.1:{self.server.server_port}/api/v1/health/live/"
        )
        config = load_readiness.validate_arguments(
            self._arguments(requests="1", concurrency="1")
        )
        result = load_readiness.execute_load(config)

        self.assertFalse(result["passed"])
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["status_counts"], {"302": 1})
        self.assertEqual(len(_HealthHandler.seen), 1)

    def test_non_200_response_fails_without_exposing_response_body(self):
        _HealthHandler.response_status = 503
        config = load_readiness.validate_arguments(
            self._arguments(requests="2", concurrency="1")
        )
        result = load_readiness.execute_load(config)

        self.assertFalse(result["passed"])
        self.assertEqual(result["errors"], 2)
        self.assertEqual(result["status_counts"], {"503": 2})
        self.assertNotIn("response-marker", json.dumps(result))

    def test_latency_and_rate_thresholds_are_exact_and_required(self):
        config = load_readiness.validate_arguments(
            self._arguments(requests="4", concurrency="2")
        )

        def fixed_probe(target_url, timeout_seconds):
            return load_readiness.ProbeResult(
                elapsed_ms=50.0,
                status=200,
                success=True,
            )

        latency_failure = load_readiness.execute_load(
            replace(config, max_p95_ms=49.0),
            probe=fixed_probe,
        )
        rate_failure = load_readiness.execute_load(
            replace(config, min_requests_per_second=100_000.0),
            probe=fixed_probe,
        )
        passing = load_readiness.execute_load(
            replace(config, max_p95_ms=50.0, min_requests_per_second=0.01),
            probe=fixed_probe,
        )

        self.assertFalse(latency_failure["passed"])
        self.assertFalse(rate_failure["passed"])
        self.assertTrue(passing["passed"])
        self.assertEqual(passing["latency_ms"]["p95"], 50.0)
        self.assertTrue(passing["thresholds"]["zero_errors_required"])

    def test_only_exact_safe_origin_and_health_paths_are_accepted(self):
        accepted_https = load_readiness.validate_arguments(
            self._arguments(
                base_url="https://crm.example.test",
                confirm_host="crm.example.test",
                path="/api/v1/health/ready/",
            )
        )
        self.assertEqual(accepted_https.origin, "https://crm.example.test")

        unsafe = (
            {"sentinel": "wrong"},
            {
                "base_url": "http://crm.example.test",
                "confirm_host": "crm.example.test",
            },
            {"base_url": "https://crm.example.test/?token=marker"},
            {"base_url": "https://user:password@crm.example.test"},
            {
                "base_url": "https://crm.example.test",
                "confirm_host": "other.example.test",
            },
            {"path": "/api/v1/customers/"},
            {"path": "/health/live/?token=marker"},
            {"base_url": "HTTPS://crm.example.test", "confirm_host": "crm.example.test"},
            {"base_url": "http://127.0.0.1:0"},
            {"base_url": "http://localhost:8080", "confirm_host": "localhost"},
        )
        for values in unsafe:
            with self.subTest(values=values):
                with self.assertRaises(load_readiness.LoadInputError):
                    load_readiness.validate_arguments(self._arguments(**values))

    def test_wall_deadline_returns_without_waiting_for_a_stuck_probe(self):
        config = replace(
            load_readiness.validate_arguments(
                self._arguments(requests="1", concurrency="1")
            ),
            max_wall_seconds=1.0,
        )

        def stuck_probe(target_url, timeout_seconds):
            time.sleep(2.0)
            return load_readiness.ProbeResult(
                elapsed_ms=2_000.0,
                status=200,
                success=True,
            )

        started = time.perf_counter()
        result = load_readiness.execute_load(config, probe=stuck_probe)
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 1.5)
        self.assertFalse(result["passed"])
        self.assertEqual(result["completed"], 0)
        self.assertEqual(result["not_completed"], 1)

    def test_workload_and_timeout_bounds_fail_closed(self):
        unsafe = (
            {"requests": "0"},
            {"requests": "9" * 20},
            {"requests": str(load_readiness.MAX_REQUESTS + 1)},
            {"concurrency": "0"},
            {"concurrency": str(load_readiness.MAX_CONCURRENCY + 1)},
            {"requests": "2", "concurrency": "3"},
            {"timeout_seconds": "0"},
            {"timeout_seconds": str(load_readiness.MAX_TIMEOUT_SECONDS + 1)},
            {"max_wall_seconds": "0"},
            {"max_wall_seconds": str(load_readiness.MAX_WALL_SECONDS + 1)},
            {"max_p95_ms": "nan"},
            {"max_p95_ms": str(load_readiness.MAX_P95_MILLISECONDS + 1)},
            {"min_requests_per_second": "0"},
            {
                "min_requests_per_second": str(
                    load_readiness.MAX_MINIMUM_REQUESTS_PER_SECOND + 1
                )
            },
        )
        for values in unsafe:
            with self.subTest(values=values):
                with self.assertRaises(load_readiness.LoadInputError):
                    load_readiness.validate_arguments(self._arguments(**values))

    def test_cli_parse_error_does_not_echo_untrusted_value(self):
        marker = "credential-marker-must-not-print"
        result = subprocess.run(
            [sys.executable, str(LOAD_SCRIPT), "--unknown", marker],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(marker, result.stdout + result.stderr)
        self.assertIn("arguments are invalid", result.stderr)

        arguments = self._arguments(
            base_url=f"https://{marker}.example/?token={marker}",
            confirm_host=f"{marker}.example",
        )
        argv = []
        for name, value in vars(arguments).items():
            argv.extend([f"--{name.replace('_', '-')}", value])
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = load_readiness.main(argv)
        self.assertEqual(exit_code, 2)
        self.assertNotIn(marker, stdout.getvalue() + stderr.getvalue())

    def test_cli_prints_one_safe_json_result_and_uses_exit_status(self):
        arguments = self._arguments(requests="2", concurrency="1")
        argv = []
        for name, value in vars(arguments).items():
            argv.extend([f"--{name.replace('_', '-')}", value])
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = load_readiness.main(argv)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        lines = stdout.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        payload = json.loads(lines[0])
        self.assertTrue(payload["passed"])
        self.assertNotIn("127.0.0.1", lines[0])
        self.assertNotIn(str(self.server.server_port), lines[0])

    def test_runbook_keeps_the_read_only_contract_and_proof_boundary(self):
        runbook = LOAD_RUNBOOK.read_text(encoding="utf-8")
        script = LOAD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("KARIZ_READ_ONLY_LOAD_V1", runbook)
        for path in load_readiness.ALLOWED_PATHS:
            self.assertIn(path, runbook)
        self.assertIn("follows no redirect", runbook)
        self.assertIn("uses no environment proxy", runbook)
        self.assertIn('"zero_errors_required": True', script)
        self.assertNotIn('add_argument("--method"', script)
        self.assertNotIn('add_argument("--header"', script)
        self.assertNotIn('add_argument("--data"', script)
        self.assertIn("not prove public tls", runbook.lower())


if __name__ == "__main__":
    unittest.main()
