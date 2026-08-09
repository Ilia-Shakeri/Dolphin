import json
import logging
import traceback
from pathlib import Path

from common.request_context import current_request_context


REQUEST_LOGGER_NAME = "kariz.request"
SERVER_FAULT_LOGGER_NAME = "kariz.server_fault"
request_logger = logging.getLogger(REQUEST_LOGGER_NAME)
server_fault_logger = logging.getLogger(SERVER_FAULT_LOGGER_NAME)


class RequestJsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "event": "http_request",
            "request_id": str(getattr(record, "request_id", "")),
            "method": str(getattr(record, "request_method", "")),
            "path": str(getattr(record, "request_path", "")),
            "status": int(getattr(record, "response_status", 0)),
            "duration_ms": float(getattr(record, "duration_ms", 0.0)),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class ServerFaultJsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "event": "server_fault",
            "request_id": str(getattr(record, "request_id", "")),
            "method": str(getattr(record, "request_method", "")),
            "path": str(getattr(record, "request_path", "")),
            "exception_type": str(getattr(record, "exception_type", "")),
            "frames": list(getattr(record, "fault_frames", ())),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def write_request_log(*, method, path, status, duration_ms):
    context = current_request_context()
    request_logger.info(
        "http_request",
        extra={
            "request_id": context.request_id,
            "request_method": method,
            "request_path": path,
            "response_status": status,
            "duration_ms": duration_ms,
        },
    )


def write_server_fault_log(*, exc, request):
    context = current_request_context()
    frames = [
        {
            "file": Path(frame.filename).name,
            "line": frame.lineno,
            "function": frame.name,
        }
        for frame in traceback.extract_tb(exc.__traceback__)[-20:]
    ]
    server_fault_logger.error(
        "server_fault",
        extra={
            "request_id": context.request_id,
            "request_method": request.method,
            "request_path": request.path,
            "exception_type": type(exc).__name__,
            "fault_frames": frames,
        },
    )
