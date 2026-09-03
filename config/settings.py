import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

# One source of truth for the product version, read from the `VERSION` file at
# the repository root. A file rather than a constant here so a build, a release
# script and the running application all read the same three numbers, and so
# bumping a version is a one-line change that shows up plainly in a diff.
# CHANGELOG.md records what each number contains.
#
# The fallback covers a container built without the file: the application must
# still start, and an unknown version is better than a wrong one.
try:
    DOLPHIN_VERSION = (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
except OSError:
    DOLPHIN_VERSION = "unknown"
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
    # `common` is listed before `django.contrib.staticfiles` on purpose:
    # Django resolves a management command to the *first* app in this list that
    # provides it, so this ordering is what lets
    # common/management/commands/collectstatic.py apply the deployment's own
    # ignore list. Without it the override is silently never used.
    "common",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "accounts",
    "auditlog",
    "sales",
    "aftersales",
    "communications",
    "inventory",
    "billing",
    "reports",
    "attachments",
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
        "common.context_processors.product_version",
        "common.context_processors.sidebar_state",
        "common.context_processors.brand",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("POSTGRES_DB", "dolphin"),
    "USER": os.environ.get("POSTGRES_USER", "dolphin_app"),
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
# The purchased Metronic build is the visual system for the served UI, so its
# tree is the static root. It is mapped *without* a prefix on purpose: Django's
# FileSystemFinder joins a prefix using os.sep, so a prefixed entry silently
# fails to resolve forward-slash URLs on Windows, which is where this is
# developed. Metronic's own CSS also resolves its fonts relatively
# (`../fonts/IRANSansWeb.woff`, `fonts/keenicons/...`), so the directory shape
# has to survive intact anyway.
#
# The favicon is a Dolphin brand asset and lives with the application, so
# the theme's demo media directory is not needed at runtime at all.
STATICFILES_DIRS = [BASE_DIR / "assets"]
#: Applied by common/management/commands/collectstatic.py on every invocation.
#: Patterns match a file name or a directory name while walking, so these are
#: names rather than paths. Everything here is unreachable from a served page:
#: theme demo imagery, icon families the UI never uses, the LTR builds of the
#: RTL bundles, and bundles nothing loads.
#:
#: `plugins.bundle.js` was on this list until 1.3.12 and is deliberately not any
#: more. It carries ApexCharts, which is what the purchased theme draws its
#: charts with and what this panel's charts now use. It is 3.6 MB and brings
#: jQuery, select2 and dropzone that nothing here calls — the product owner was
#: told the size and asked for the theme's own charts regardless. Re-adding it
#: here does not fail any build: collectstatic still reports success and every
#: chart silently 404s at runtime, which is why it is also pinned in
#: scripts/validate_image_content.py and common/tests/test_static_assets.py.
#:
#: `plugins/custom/*` was a single bare `"custom"` entry — matched by basename
#: while walking, so it pruned the whole directory — until 1.7.5. That was
#: correct when the comment said "none loaded"; it silently broke the day the
#: lead calendar started loading `plugins/custom/fullcalendar/fullcalendar.
#: bundle.js`. `collectstatic` still reported success (an ignored file is not
#: a missing one), so the failure only ever showed up as the calendar page's
#: own "در حال دریافت سرنخ‌ها…" never resolving in a deployment that actually
#: runs `collectstatic` — `runserver` serves straight from `STATICFILES_DIRS`
#: without it, which is why this did not reproduce locally. Listed below by
#: name instead, one entry per still-unused bundle under `plugins/custom/`,
#: so a future one gets the same silent-404 fate only on purpose.
STATICFILES_COLLECT_IGNORE = [
    "media",              # ~46MB of theme stock photography and illustrations
    "ckeditor",           # plugins/custom/* demo bundles, none loaded —
    "cookiealert",        # `fullcalendar` is the one exception (see above),
    "cropper",            # so it is not in this list.
    "datatables",
    "draggable",
    "flotcharts",
    "formrepeater",
    "fslightbox",
    "jkanban",
    "jstree",
    "leaflet",
    "prismjs",
    "tinymce",
    "typedjs",
    "vis-timeline",
    # `assets/js/custom/*` — per-demo page scripts, also nothing loads any of
    # these. A bare `"custom"` would prune `plugins/custom` again too (see
    # above): a directory is matched by name alone while walking, with no way
    # to say "custom, but only under js/" — so this is every subdirectory and
    # top-level file `js/custom` actually holds, named individually instead.
    "account",
    "apps",
    "authentication",
    "pages",
    "utilities",
    "landing.js",
    "widgets.js",          # assets/js/custom/widgets.js — distinct from
                            # assets/js/widgets.bundle.js, excluded below too
    "@fortawesome",       # icon families the UI does not use; it uses keenicons
    "bootstrap-icons",
    "line-awesome",
    "style.bundle.css",   # LTR builds; this deployment is RTL only
    "plugins.bundle.css",
    "widgets.bundle.js",  # theme demo widgets, not loaded
    "*.map",
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# Sized from the largest document the application itself permits, not picked as
# a round number: BILLING_MAX_DOCUMENT_ITEMS lines, each carrying a
# LINE_DESCRIPTION_MAX_LENGTH description in Persian (two UTF-8 bytes per
# character) plus its JSON field names, comes to roughly 220 KB. At 64 KB the
# limit contradicted the rule the API advertises — a document the service layer
# accepts was rejected as too large before it ever reached validation.
#
# `client_max_body_size` in nginx/default.conf must stay at or above this, or
# the edge refuses what the application would have accepted.
DATA_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024

# Attachments (Customer/Lead/Invoice/SalesDocument/AfterSalesRequest).
# Product-owner decision 2026-09-03: image (jpeg/png/webp) and PDF only, 10 MB
# per file — see attachments/models.py for the full record and for why this is
# a setting AND a fixed database CheckConstraint at the same value: the
# constraint is the hard ceiling migrations move deliberately, this setting
# may only ever tighten it further, never raise it past that ceiling.
ATTACHMENT_MAX_BYTES = int(os.environ.get("KARIZ_ATTACHMENT_MAX_BYTES", str(10 * 1024 * 1024)))

# Routes that accept a real file rather than a JSON document, and the bound that
# applies to them. Kept explicit and still bounded: a file larger than this is a
# data-migration task (for the spreadsheet routes) or simply refused (for
# attachments — ATTACHMENT_MAX_BYTES above is the real, tighter limit; this is
# only what reaches Django's request-body middleware at all).
FILE_UPLOAD_PATHS = (
    "/api/v1/products/import-xlsx/",
    "/api/v1/customers/import-xlsx/",
    "/api/v1/attachments/",
)
# The larger of what any FILE_UPLOAD_PATHS route needs, plus a fixed margin for
# multipart boundaries/headers around the attachment bytes themselves — a flat
# per-path allowance was not built into RequestBodyLimitMiddleware, so this one
# number has to cover every route above without narrowing the xlsx import's own
# real behaviour, which nginx/default.conf still bounds at 5 MB for those two
# routes specifically regardless of this being raised for attachments.
FILE_UPLOAD_MAX_MEMORY_SIZE = max(5 * 1024 * 1024, ATTACHMENT_MAX_BYTES + 64 * 1024)

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
        "dolphin.request": {
            "handlers": ["request_console"],
            "level": "INFO",
            "propagate": False,
        },
        "dolphin.server_fault": {
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
    "TITLE": "Dolphin API",
    "VERSION": DOLPHIN_VERSION,
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
# the "Inventory semantics" and "Billing semantics" sections of `BACKEND_SPEC.md`
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

# Whether issuing an invoice moves stock.
#
# Off by default. In Client-1's flow the invoice comes first and the order
# follows, and it is the *order* that owns the inventory lifecycle: stock leaves
# on approval and comes back on cancellation, exactly once each. If an invoice
# also deducted, the same goods would leave twice for one sale.
#
# The behaviour is kept rather than deleted because a deployment that invoices
# straight out of stock, with no order step, is a legitimate configuration — it
# just is not this one.
BILLING_INVOICE_AFFECTS_STOCK = (
    os.environ.get("KARIZ_BILLING_INVOICE_AFFECTS_STOCK", "false").lower() == "true"
)

# When a cheque payment credits the customer account: on clearing (default) or
# at registration. Clearing is the safe default because an uncleared cheque is
# not money received.
#: Whether a cheque credits the customer on arrival (`registration`) or
#: only once the bank pays it (`cleared`). The product owner chose arrival
#: in 1.3.0; a bounce then reverses the credit. See
#: `billing.payments.cheque_credits_on_registration`.
BILLING_CHEQUE_CREDITS_ON = os.environ.get("KARIZ_BILLING_CHEQUE_CREDITS_ON", "registration")

# Default spacing between installments, in days, and the hard ceiling on how
# many lines or installments one document may carry.
BILLING_INSTALLMENT_INTERVAL_DAYS = int(
    os.environ.get("KARIZ_BILLING_INSTALLMENT_INTERVAL_DAYS", "30")
)
BILLING_MAX_DOCUMENT_ITEMS = int(os.environ.get("KARIZ_BILLING_MAX_DOCUMENT_ITEMS", "200"))

# The seller's own legal identity, as it must appear on an official invoice.
#
# Deployment-level rather than per-invoice: this is one company per deployment,
# and it is the same on every document it ever issues. It is configuration, not
# data an operator edits between invoices.
#
# All three default to empty, and empty is meaningful: a deployment that has not
# supplied them cannot mark an invoice official, and `billing.services` refuses
# the transition rather than issuing a tax document with a blank seller. A
# deployment issuing only unofficial invoices needs none of this and is not
# nagged for it.
#
# Nothing here is a tax rule. These are three identifiers printed on a document;
# what tax applies to it, and how it is computed, stays open (D.3-D.6).
SELLER_LEGAL_NAME = os.environ.get("KARIZ_SELLER_LEGAL_NAME", "").strip()
SELLER_NATIONAL_ID = os.environ.get("KARIZ_SELLER_NATIONAL_ID", "").strip()
SELLER_ECONOMIC_CODE = os.environ.get("KARIZ_SELLER_ECONOMIC_CODE", "").strip()
#: The rest of مشخصات فروشنده as the printed document sets it out. These are
#: deployment identity, not business data, which is why they are environment and
#: not a model: one deployment is one seller, and a second seller would be a
#: second deployment with its own database.
#:
#: Only name, national id and economic code are required to issue — those three
#: identify the seller for tax. The address block is printed when present and
#: does not block issuing, because a deployment that has not filled it in should
#: still be able to invoice.
SELLER_REGISTRATION_NUMBER = os.environ.get("KARIZ_SELLER_REGISTRATION_NUMBER", "").strip()
SELLER_ADDRESS = os.environ.get("KARIZ_SELLER_ADDRESS", "").strip()
SELLER_POSTAL_CODE = os.environ.get("KARIZ_SELLER_POSTAL_CODE", "").strip()
SELLER_CITY = os.environ.get("KARIZ_SELLER_CITY", "").strip()
SELLER_PHONE = os.environ.get("KARIZ_SELLER_PHONE", "").strip()

# Server-generated PDF. Off unless a deployment sets a renderer, because the
# only supported renderer needs a browser binary on the host and a control that
# cannot act is never shown. Browser print / save-as-PDF works regardless.
# Supported value: "chromium". See common/pdf.py for why no PDF library is used.
PDF_RENDERER = os.environ.get("KARIZ_PDF_RENDERER", "")
# Optional explicit path. When empty, a browser already on PATH is accepted,
# which is the normal case inside an image that installed one.
PDF_CHROMIUM_BINARY = os.environ.get("KARIZ_PDF_CHROMIUM_BINARY", "")
PDF_RENDER_TIMEOUT_SECONDS = int(os.environ.get("KARIZ_PDF_RENDER_TIMEOUT_SECONDS", "20"))

# Outbound SMS. Off unless a deployment sets a provider, for the same reason
# the PDF renderer is off unless configured: a control that cannot act is
# never shown. Supported value: "http" — a generic HTTP request built
# entirely from these settings. See communications/sms.py for why no specific
# vendor (Kavenegar, Melipayamak, Ghasedak, ...) is integrated in shared
# source, and for the exact placeholder tokens KARIZ_SMS_API_BODY_TEMPLATE
# uses. Each deployment's own .env supplies its own gateway's real values —
# never a name or a request shape hardcoded here.
SMS_PROVIDER = os.environ.get("KARIZ_SMS_PROVIDER", "").strip().lower()
SMS_API_URL = os.environ.get("KARIZ_SMS_API_URL", "").strip()
# A JSON object, e.g. {"receptor": "__SMS_TO__", "message": "__SMS_BODY__",
# "sender": "__SMS_SENDER__"} — adapted per gateway; the three placeholder
# tokens are substituted after the JSON is parsed, never into raw text.
SMS_API_BODY_TEMPLATE = os.environ.get("KARIZ_SMS_API_BODY_TEMPLATE", "").strip()
# A JSON object of extra HTTP headers (the gateway's API key/token usually
# goes here). Content-Type: application/json is always sent and cannot be
# overridden by this.
SMS_API_HEADERS = os.environ.get("KARIZ_SMS_API_HEADERS", "").strip()
SMS_SENDER_ID = os.environ.get("KARIZ_SMS_SENDER_ID", "").strip()
SMS_API_TIMEOUT_SECONDS = int(os.environ.get("KARIZ_SMS_API_TIMEOUT_SECONDS", "10"))

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
