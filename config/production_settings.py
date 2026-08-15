from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import tempfile

from config.settings import *
from config.production_env import validate_production_environment
from common.request_context import current_request_context


class SafeRuntimeJsonFormatter(logging.Formatter):
    def format(self, record):
        request = getattr(record, "request", None)
        context = current_request_context()
        request_id = getattr(request, "request_id", "") or context.request_id
        exception_type = ""
        if record.exc_info and record.exc_info[0] is not None:
            exception_type = record.exc_info[0].__name__
        payload = {
            "time": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "event": "runtime_log",
            "logger": str(record.name)[:128],
            "level": str(record.levelname)[:16],
            "request_id": str(request_id)[:64],
            "method": str(getattr(request, "method", ""))[:16],
            "path": str(getattr(request, "path", ""))[:2048],
            "exception_type": str(exception_type)[:128],
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


PRODUCTION_ENV = validate_production_environment(os.environ)
SECRET_KEY = PRODUCTION_ENV["SECRET_KEY"]
ALLOWED_HOSTS = PRODUCTION_ENV["ALLOWED_HOSTS"]
CSRF_TRUSTED_ORIGINS = PRODUCTION_ENV["CSRF_TRUSTED_ORIGINS"]
AUDIT_TRUSTED_PROXY_CIDRS = PRODUCTION_ENV["AUDIT_TRUSTED_PROXY_CIDRS"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": PRODUCTION_ENV["DATABASE"]["NAME"],
        "USER": PRODUCTION_ENV["DATABASE"]["USER"],
        "PASSWORD": PRODUCTION_ENV["DATABASE"]["PASSWORD"],
        "HOST": PRODUCTION_ENV["DATABASE"]["HOST"],
        "PORT": PRODUCTION_ENV["DATABASE"]["PORT"],
        "CONN_MAX_AGE": 60 if PRODUCTION_ENV["DATABASE_ROLE"] == "app" else 0,
        "OPTIONS": {"connect_timeout": PRODUCTION_ENV["DATABASE"]["CONNECT_TIMEOUT"]},
    }
}

DEBUG = False
ENABLE_API_DOCS = False
# Never expose the server-administration plane on a customer deployment. The
# reverse proxy denies /admin/ as well; both layers must be changed, and the
# management-network allowlist configured (P14), before it can ever be reached.
ENABLE_DJANGO_ADMIN = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": 1}
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = PRODUCTION_ENV["SECURE_SSL_REDIRECT"]
SECURE_HSTS_SECONDS = PRODUCTION_ENV["SECURE_HSTS_SECONDS"]
SECURE_HSTS_INCLUDE_SUBDOMAINS = PRODUCTION_ENV["SECURE_HSTS_INCLUDE_SUBDOMAINS"]
SECURE_HSTS_PRELOAD = PRODUCTION_ENV["SECURE_HSTS_PRELOAD"]
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": str(Path(tempfile.gettempdir()) / "kariz-throttle-cache"),
        "TIMEOUT": 300,
        "OPTIONS": {
            "MAX_ENTRIES": 10_000,
            "CULL_FREQUENCY": 3,
        },
    }
}

_SAFE_RUNTIME_LOGGERS = (
    "django",
    "django.request",
    "django.server",
    "django.security",
    "django.db.backends",
    "gunicorn.error",
    "gunicorn.access",
)
LOGGING = {
    **LOGGING,
    "formatters": {
        **LOGGING["formatters"],
        "runtime_safe_json": {"()": SafeRuntimeJsonFormatter},
    },
    "handlers": {
        **LOGGING["handlers"],
        "runtime_safe_console": {
            "class": "logging.StreamHandler",
            "formatter": "runtime_safe_json",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        **LOGGING["loggers"],
        **{
            name: {
                "handlers": ["runtime_safe_console"],
                "level": "WARNING",
                "propagate": False,
            }
            for name in _SAFE_RUNTIME_LOGGERS
        },
    },
    "root": {
        "handlers": ["runtime_safe_console"],
        "level": "WARNING",
    },
}
