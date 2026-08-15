import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "unsafe-development-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [value.strip() for value in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if value.strip()]
CSRF_TRUSTED_ORIGINS = [value.strip() for value in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if value.strip()]
CSRF_FAILURE_VIEW = "common.error_views.csrf_failure"
AUDIT_TRUSTED_PROXY_CIDRS = [value.strip() for value in os.environ.get("AUDIT_TRUSTED_PROXY_CIDRS", "").split(",") if value.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "common",
    "accounts",
    "auditlog",
    "sales",
    "aftersales",
    "communications",
    "inventory",
    "billing",
    "reports",
]

MIDDLEWARE = [
    "common.middleware.RequestContextMiddleware",
    "common.middleware.RequestBodyLimitMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("POSTGRES_DB", "kariz"),
    "USER": os.environ.get("POSTGRES_USER", "kariz"),
    "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
    "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    "CONN_MAX_AGE": 60,
    "OPTIONS": {"connect_timeout": int(os.environ.get("POSTGRES_CONNECT_TIMEOUT", "3"))},
}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
AUTH_USER_MODEL = "accounts.User"
LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [("kariz-brand", BASE_DIR / "assets" / "media" / "logos")]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATA_UPLOAD_MAX_MEMORY_SIZE = 64 * 1024

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "request_json": {
            "()": "common.request_logging.RequestJsonFormatter",
        },
        "server_fault_json": {
            "()": "common.request_logging.ServerFaultJsonFormatter",
        },
    },
    "handlers": {
        "request_console": {
            "class": "logging.StreamHandler",
            "formatter": "request_json",
            "stream": "ext://sys.stdout",
        },
        "server_fault_console": {
            "class": "logging.StreamHandler",
            "formatter": "server_fault_json",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        "kariz.request": {
            "handlers": ["request_console"],
            "level": "INFO",
            "propagate": False,
        },
        "kariz.server_fault": {
            "handlers": ["server_fault_console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["common.permissions.IsActiveAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["common.parsers.BoundedJSONParser"],
    "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "sensitive": "30/min",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Kariz CRM API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Several modules own a field called `status` or `to_status` over different
    # vocabularies. Naming each enum after its module keeps the generated
    # schema readable instead of letting the generator invent a hashed name.
    "ENUM_NAME_OVERRIDES": {
        "ChequeStatusEnum": "billing.models.Cheque.Status",
        "InvoiceStatusEnum": "billing.models.Invoice.Status",
        "OrderStatusEnum": "billing.models.Order.Status",
        "QuotationStatusEnum": "billing.models.Quotation.Status",
        "PaymentStatusEnum": "billing.models.Payment.Status",
        "PaymentMethodEnum": "billing.models.Payment.Method",
        "InstallmentStatusEnum": "billing.models.Installment.Status",
        "InstallmentPlanStatusEnum": "billing.models.InstallmentPlan.Status",
        "LedgerEntryTypeEnum": "billing.models.CustomerLedgerEntry.EntryType",
        "StockMovementTypeEnum": "inventory.models.StockMovement.MovementType",
        "SaleStatusEnum": "sales.models.Sale.Status",
    },
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "common.openapi.add_common_api_contract",
    ],
}
ENABLE_API_DOCS = DEBUG
# Django Admin is a server-administration plane, not a customer application
# surface. It stays unregistered unless explicitly enabled, independently of
# DEBUG, so that a debug-enabled environment never exposes it by accident and a
# production misconfiguration cannot enable it implicitly. CRM roles are never
# Django staff, so enabling this does not grant any CRM user access.
ENABLE_DJANGO_ADMIN = os.environ.get("ENABLE_DJANGO_ADMIN", "false").lower() == "true"


def _manifest_public_keys(raw):
    """Parse `key_id:base64,key_id:base64` into the trusted signer mapping.

    Only public keys are ever configured. The matching private key stays with
    the platform owner and never reaches a deployment, so a customer cannot
    issue a manifest that verifies here.
    """
    keys = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        key_id, separator, value = entry.partition(":")
        if not separator or not key_id.strip() or not value.strip():
            raise ValueError(
                "KARIZ_DEPLOYMENT_MANIFEST_KEYS entries must be key_id:base64_public_key."
            )
        keys[key_id.strip()] = value.strip()
    return keys


# --- Inventory and billing semantics -----------------------------------------
# None of these encode a legal, tax, or accounting requirement. They are the
# conservative bounded defaults this codebase applies where no approved external
# contract fixed the rule, and every one is per-deployment configurable.
# `docs/backend/INVENTORY_SEMANTICS.md` and `docs/backend/BILLING_SEMANTICS.md`
# state each choice and what would change it.

# Refuse an issue that would drive a warehouse level below zero. A deployment
# that genuinely sells before receipting sets this to true deliberately.
INVENTORY_ALLOW_NEGATIVE_STOCK = (
    os.environ.get("KARIZ_INVENTORY_ALLOW_NEGATIVE_STOCK", "false").lower() == "true"
)

# Document numbering. `{sequence}` is a gap-free per-kind counter. The format is
# validated at use, so a deployment cannot configure a format that drops the
# counter and produces duplicates.
BILLING_NUMBER_FORMATS = {
    "quotation": os.environ.get("KARIZ_NUMBER_FORMAT_QUOTATION", "QT-{sequence:06d}"),
    "order": os.environ.get("KARIZ_NUMBER_FORMAT_ORDER", "SO-{sequence:06d}"),
    "invoice": os.environ.get("KARIZ_NUMBER_FORMAT_INVOICE", "INV-{sequence:06d}"),
    "payment": os.environ.get("KARIZ_NUMBER_FORMAT_PAYMENT", "PY-{sequence:06d}"),
}

# Tax is OFF by default and this code claims no tax compliance for any
# jurisdiction. It applies the configured percentage to one taxable base
# (subtotal minus header discount) and nothing more.
BILLING_DEFAULT_TAX_RATE = os.environ.get("KARIZ_BILLING_DEFAULT_TAX_RATE", "0.00")

# Upper bound on a single line discount, as a percentage.
BILLING_MAX_DISCOUNT_PERCENT = os.environ.get("KARIZ_BILLING_MAX_DISCOUNT_PERCENT", "100.00")

# Default validity window of a quotation, and default payment term of an
# invoice, both in days. Zero due days means the invoice is due on issue.
BILLING_QUOTATION_VALID_DAYS = int(os.environ.get("KARIZ_BILLING_QUOTATION_VALID_DAYS", "30"))
BILLING_INVOICE_DUE_DAYS = int(os.environ.get("KARIZ_BILLING_INVOICE_DUE_DAYS", "0"))

# Issuing an invoice that names a warehouse deducts its lines from that
# warehouse and snapshots the unit cost. An invoice without a warehouse has no
# stock effect and reports no profit.
BILLING_INVOICE_AFFECTS_STOCK = (
    os.environ.get("KARIZ_BILLING_INVOICE_AFFECTS_STOCK", "true").lower() == "true"
)

# When a cheque payment credits the customer account: on clearing (default) or
# at registration. Clearing is the safe default because an uncleared cheque is
# not money received.
BILLING_CHEQUE_CREDITS_ON = os.environ.get("KARIZ_BILLING_CHEQUE_CREDITS_ON", "cleared")

# Default spacing between installments, in days, and the hard ceiling on how
# many lines or installments one document may carry.
BILLING_INSTALLMENT_INTERVAL_DAYS = int(
    os.environ.get("KARIZ_BILLING_INSTALLMENT_INTERVAL_DAYS", "30")
)
BILLING_MAX_DOCUMENT_ITEMS = int(os.environ.get("KARIZ_BILLING_MAX_DOCUMENT_ITEMS", "200"))

# Deployment profile (PROFILE-001, Option C). The signed external manifest is
# the source of truth for feature availability; the database table of the same
# name is a derived cache that never authorises anything. Feature availability,
# role permission, and object scope stay three separate controls.
DEPLOYMENT_MANIFEST_PATH = os.environ.get("KARIZ_DEPLOYMENT_MANIFEST", "")
DEPLOYMENT_MANIFEST_PUBLIC_KEYS = _manifest_public_keys(
    os.environ.get("KARIZ_DEPLOYMENT_MANIFEST_KEYS", "")
)
# Development and the test suite may run without a manifest. Production sets
# this to True, so a customer deployment refuses to start without one.
DEPLOYMENT_MANIFEST_REQUIRED = False
