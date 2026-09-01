import argparse
from dataclasses import dataclass
from ipaddress import ip_address
import json
import math
from queue import Empty, Queue
import re
import ssl
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)


READ_ONLY_SENTINEL = "DOLPHIN_READ_ONLY_LOAD_V1"
ALLOWED_PATHS = frozenset(
    {
        "/health/live/",
        "/api/v1/health/live/",
        "/api/v1/health/ready/",
    }
)
MAX_REQUESTS = 2_000
MAX_CONCURRENCY = 32
MAX_TIMEOUT_SECONDS = 10.0
MAX_WALL_SECONDS = 300.0
MAX_P95_MILLISECONDS = 10_000.0
MAX_MINIMUM_REQUESTS_PER_SECOND = 100_000.0
_DNS_HOST = re.compile(
    r"\A(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)
_THREAD_STATE = threading.local()


class LoadInputError(ValueError):
    pass


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(2, "Load readiness arguments are invalid.\n")


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


@dataclass(frozen=True)
class LoadConfig:
    origin: str
    confirmed_host: str
    path: str
    requests: int
    concurrency: int
    timeout_seconds: float
    max_wall_seconds: float
    max_p95_ms: float
    min_requests_per_second: float


@dataclass(frozen=True)
class ProbeResult:
    elapsed_ms: float
    status: int | None
    success: bool


def build_parser():
    parser = SafeArgumentParser(
        description="Run a bounded, GET-only Dolphin health readiness load check."
    )
    parser.add_argument("--sentinel", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--confirm-host", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--requests", required=True)
    parser.add_argument("--concurrency", required=True)
    parser.add_argument("--timeout-seconds", required=True)
    parser.add_argument("--max-wall-seconds", required=True)
    parser.add_argument("--max-p95-ms", required=True)
    parser.add_argument("--min-requests-per-second", required=True)
    return parser


def _bounded_integer(raw_value, *, name, minimum, maximum):
    if len(raw_value or "") > 10 or not re.fullmatch(r"[0-9]+", raw_value or ""):
        raise LoadInputError(f"{name} must be a whole number.")
    value = int(raw_value)
    if not minimum <= value <= maximum:
        raise LoadInputError(f"{name} is outside the safe bound.")
    return value


def _bounded_number(raw_value, *, name, minimum, maximum):
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise LoadInputError(f"{name} must be a number.") from exc
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise LoadInputError(f"{name} is outside the safe bound.")
    return value


def _canonical_host(raw_host):
    if "%" in raw_host:
        raise LoadInputError("confirm-host must be one safe lowercase host.")
    try:
        return str(ip_address(raw_host))
    except ValueError:
        if len(raw_host) > 253 or not _DNS_HOST.fullmatch(raw_host):
            raise LoadInputError("confirm-host must be one safe lowercase host.")
        return raw_host


def _is_loopback(host):
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def validate_arguments(arguments):
    if arguments.sentinel != READ_ONLY_SENTINEL:
        raise LoadInputError("sentinel does not confirm the read-only run.")
    if arguments.path not in ALLOWED_PATHS:
        raise LoadInputError("path is not an allowed health endpoint.")

    try:
        parsed = urlsplit(arguments.base_url)
        port = parsed.port
    except ValueError as exc:
        raise LoadInputError("base-url is invalid.") from exc
    if parsed.scheme not in {"http", "https"}:
        raise LoadInputError("base-url must use HTTPS or loopback HTTP.")
    if port == 0:
        raise LoadInputError("base-url port is outside the safe bound.")
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise LoadInputError("base-url must be one credential-free origin.")

    confirmed_host = _canonical_host(arguments.confirm_host)
    parsed_host = _canonical_host(parsed.hostname)
    if confirmed_host != parsed_host or arguments.confirm_host != confirmed_host:
        raise LoadInputError("confirm-host must exactly match base-url.")
    if parsed.scheme == "http" and not _is_loopback(parsed_host):
        raise LoadInputError("plain HTTP is allowed only for a loopback host.")

    rendered_host = f"[{parsed_host}]" if ":" in parsed_host else parsed_host
    rendered_port = f":{port}" if port is not None else ""
    origin = f"{parsed.scheme}://{rendered_host}{rendered_port}"
    if arguments.base_url not in {origin, f"{origin}/"}:
        raise LoadInputError("base-url must exactly match its canonical origin.")

    request_count = _bounded_integer(
        arguments.requests,
        name="requests",
        minimum=1,
        maximum=MAX_REQUESTS,
    )
    concurrency = _bounded_integer(
        arguments.concurrency,
        name="concurrency",
        minimum=1,
        maximum=MAX_CONCURRENCY,
    )
    if concurrency > request_count:
        raise LoadInputError("concurrency cannot exceed requests.")

    return LoadConfig(
        origin=origin,
        confirmed_host=confirmed_host,
        path=arguments.path,
        requests=request_count,
        concurrency=concurrency,
        timeout_seconds=_bounded_number(
            arguments.timeout_seconds,
            name="timeout-seconds",
            minimum=0.1,
            maximum=MAX_TIMEOUT_SECONDS,
        ),
        max_wall_seconds=_bounded_number(
            arguments.max_wall_seconds,
            name="max-wall-seconds",
            minimum=1.0,
            maximum=MAX_WALL_SECONDS,
        ),
        max_p95_ms=_bounded_number(
            arguments.max_p95_ms,
            name="max-p95-ms",
            minimum=1.0,
            maximum=MAX_P95_MILLISECONDS,
        ),
        min_requests_per_second=_bounded_number(
            arguments.min_requests_per_second,
            name="min-requests-per-second",
            minimum=0.01,
            maximum=MAX_MINIMUM_REQUESTS_PER_SECOND,
        ),
    )


def _get_opener():
    opener = getattr(_THREAD_STATE, "opener", None)
    if opener is None:
        opener = build_opener(
            ProxyHandler({}),
            HTTPSHandler(context=ssl.create_default_context()),
            RejectRedirects(),
        )
        _THREAD_STATE.opener = opener
    return opener


def _probe(target_url, timeout_seconds):
    started = time.perf_counter()
    status = None
    try:
        request = Request(target_url, data=None, method="GET")
        with _get_opener().open(request, timeout=timeout_seconds) as response:
            status = int(response.status)
            response.read(4096)
    except HTTPError as exc:
        status = int(exc.code)
        exc.close()
    except Exception:
        status = None
    elapsed_ms = (time.perf_counter() - started) * 1000
    return ProbeResult(elapsed_ms=elapsed_ms, status=status, success=status == 200)


def _nearest_rank(values, percentile):
    ordered = sorted(values)
    rank = max(1, math.ceil((percentile / 100) * len(ordered)))
    return ordered[rank - 1]


def _rounded(value):
    return round(value, 3)


def execute_load(config, *, probe=_probe):
    target_url = f"{config.origin}{config.path}"
    started = time.perf_counter()
    deadline = started + config.max_wall_seconds
    results = []
    result_queue = Queue()
    request_lock = threading.Lock()
    stop_event = threading.Event()
    next_request = 0

    def claim_request():
        nonlocal next_request
        with request_lock:
            if (
                stop_event.is_set()
                or next_request >= config.requests
                or time.perf_counter() >= deadline
            ):
                return False
            next_request += 1
            return True

    def worker():
        while claim_request():
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return
            timeout = min(config.timeout_seconds, max(0.1, remaining))
            try:
                result = probe(target_url, timeout)
            except Exception:
                result = ProbeResult(elapsed_ms=0.0, status=None, success=False)
            if time.perf_counter() <= deadline:
                result_queue.put(result)

    workers = [
        threading.Thread(
            target=worker,
            name=f"dolphin-readiness-{index}",
            daemon=True,
        )
        for index in range(config.concurrency)
    ]
    for thread in workers:
        thread.start()

    while len(results) < config.requests:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            break
        try:
            results.append(result_queue.get(timeout=remaining))
        except Empty:
            break
    stop_event.set()

    wall_seconds = max(time.perf_counter() - started, 0.000001)
    successful = [result for result in results if result.success]
    successful_latencies = [result.elapsed_ms for result in successful]
    status_counts = {}
    for result in results:
        if result.status is not None:
            key = str(result.status)
            status_counts[key] = status_counts.get(key, 0) + 1

    completed = len(results)
    succeeded = len(successful)
    transport_errors = sum(result.status is None for result in results)
    not_completed = config.requests - completed
    errors = config.requests - succeeded
    successful_rate = succeeded / wall_seconds
    latency = None
    p95_ms = None
    if successful_latencies:
        p95_ms = _nearest_rank(successful_latencies, 95)
        latency = {
            "min": _rounded(min(successful_latencies)),
            "average": _rounded(sum(successful_latencies) / succeeded),
            "p50": _rounded(_nearest_rank(successful_latencies, 50)),
            "p95": _rounded(p95_ms),
            "max": _rounded(max(successful_latencies)),
        }

    passed = (
        errors == 0
        and p95_ms is not None
        and p95_ms <= config.max_p95_ms
        and successful_rate >= config.min_requests_per_second
        and wall_seconds <= config.max_wall_seconds
    )
    return {
        "event": "load_readiness_result",
        "passed": passed,
        "endpoint": config.path,
        "requested": config.requests,
        "completed": completed,
        "succeeded": succeeded,
        "errors": errors,
        "error_rate_percent": _rounded((errors / config.requests) * 100),
        "transport_errors": transport_errors,
        "not_completed": not_completed,
        "status_counts": dict(sorted(status_counts.items())),
        "wall_seconds": _rounded(wall_seconds),
        "successful_requests_per_second": _rounded(successful_rate),
        "latency_ms": latency,
        "thresholds": {
            "max_wall_seconds": config.max_wall_seconds,
            "max_p95_ms": config.max_p95_ms,
            "min_requests_per_second": config.min_requests_per_second,
            "zero_errors_required": True,
        },
    }


def main(argv=None):
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        config = validate_arguments(arguments)
        result = execute_load(config)
    except LoadInputError as exc:
        print(f"Load readiness input is invalid: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Load readiness run stopped.", file=sys.stderr)
        return 130
    except Exception:
        print("Load readiness run failed safely.", file=sys.stderr)
        return 3
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
