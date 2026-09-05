import re
from ipaddress import ip_network
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


_PLACEHOLDER_PREFIX = "replace-with-"
_POSTGRES_IDENTIFIER = re.compile(r"\A[a-z_][a-z0-9_]{0,62}\Z")
_PUBLIC_HOST = re.compile(
    r"\A(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)


def _fail(message):
    raise ImproperlyConfigured(message)


def _required(environment, name):
    value = environment.get(name, "").strip()
    if not value or value.lower().startswith(_PLACEHOLDER_PREFIX):
        _fail(f"{name} must be set to a private production value.")
    return value


def _csv(environment, name, *, required=False):
    raw = environment.get(name, "")
    values = [value.strip() for value in raw.split(",") if value.strip()]
    if required and not values:
        _fail(f"{name} must contain at least one value.")
    return values


def _strict_bool(environment, name, *, default):
    raw = environment.get(name, "true" if default else "false").strip().lower()
    if raw not in {"true", "false"}:
        _fail(f"{name} must be true or false.")
    return raw == "true"


def _bounded_int(environment, name, *, default, minimum, maximum):
    raw = environment.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        _fail(f"{name} must be an integer.")
    if not minimum <= value <= maximum:
        _fail(f"{name} must be between {minimum} and {maximum}.")
    return value


def _postgres_identifier(environment, name):
    value = _required(environment, name)
    if value.startswith("pg_") or not _POSTGRES_IDENTIFIER.fullmatch(value):
        _fail(f"{name} must be a safe lowercase PostgreSQL identifier.")
    return value


def _validate_database_identity(environment, name, *, role):
    """Check a database or role name is a safe identifier — nothing more.

    What the name *says* is a deployment's own choice. This used to demand a
    brand prefix and refuse to start without one, which protected nothing and
    stopped a working staging deployment whose roles were already created under
    their existing names. The checks that do protect something are all still
    here and all still unconditional: the value must be a lowercase PostgreSQL
    identifier, must not claim the reserved `pg_` prefix, the three roles must
    be distinct from each other, and their passwords must be long.

    `role` is kept in the signature because callers read better for it, and so a
    future rule can distinguish the two without changing every call site.
    """
    return _postgres_identifier(environment, name)


def _validate_allowed_hosts(hosts):
    for host in hosts:
        if (
            "*" in host
            or host.startswith(".")
            or "://" in host
            or "/" in host
            or any(character.isspace() for character in host)
        ):
            _fail("DJANGO_ALLOWED_HOSTS contains an unsafe host value.")


def _validate_csrf_origins(origins):
    for origin in origins:
        parsed = urlsplit(origin)
        try:
            parsed.port
        except ValueError as exc:
            raise ImproperlyConfigured(
                "DJANGO_CSRF_TRUSTED_ORIGINS contains an invalid port."
            ) from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or "*" in parsed.hostname
            or parsed.hostname.startswith(".")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            _fail("DJANGO_CSRF_TRUSTED_ORIGINS must contain HTTPS origins only.")


SUPPORTED_SSLMODES = frozenset(
    {"", "disable", "allow", "prefer", "require", "verify-ca", "verify-full"}
)


def _database_sslmode(environment):
    """Validate POSTGRES_SSLMODE rather than passing an unknown value to libpq.

    An unrecognised mode is refused here instead of at connection time, so a
    typo fails the process at startup rather than silently behaving like
    something the operator did not intend.
    """
    value = (environment.get("POSTGRES_SSLMODE") or "").strip().lower()
    if value not in SUPPORTED_SSLMODES:
        _fail(f"POSTGRES_SSLMODE must be one of {sorted(SUPPORTED_SSLMODES - {''})}.")
    return value


def _validate_proxy_networks(networks):
    try:
        parsed = [ip_network(value, strict=False) for value in networks]
    except ValueError as exc:
        raise ImproperlyConfigured("AUDIT_TRUSTED_PROXY_CIDRS contains an invalid network.") from exc
    if any(network.prefixlen == 0 for network in parsed):
        _fail("AUDIT_TRUSTED_PROXY_CIDRS cannot trust every address.")
    return [str(network) for network in parsed]


def validate_production_environment(environment):
    secret_key = _required(environment, "DJANGO_SECRET_KEY")
    if len(secret_key) < 50:
        _fail("DJANGO_SECRET_KEY must be at least 50 characters.")

    allowed_hosts = _csv(environment, "DJANGO_ALLOWED_HOSTS", required=True)
    _validate_allowed_hosts(allowed_hosts)

    csrf_origins = _csv(environment, "DJANGO_CSRF_TRUSTED_ORIGINS", required=True)
    _validate_csrf_origins(csrf_origins)

    raw_public_host = _required(environment, "DOLPHIN_PUBLIC_HOST")
    public_host = raw_public_host.lower()
    if (
        raw_public_host != public_host
        or public_host in {"*", "_"}
        or ":" in public_host
        or "/" in public_host
        or any(character.isspace() for character in public_host)
        or not _PUBLIC_HOST.fullmatch(public_host)
    ):
        _fail("DOLPHIN_PUBLIC_HOST must be one safe lowercase hostname.")
    if allowed_hosts != [public_host]:
        _fail("DJANGO_ALLOWED_HOSTS must contain only the exact DOLPHIN_PUBLIC_HOST value.")
    expected_csrf_origin = f"https://{public_host}"
    if csrf_origins != [expected_csrf_origin]:
        _fail(
            "DJANGO_CSRF_TRUSTED_ORIGINS must contain only the exact HTTPS "
            "DOLPHIN_PUBLIC_HOST origin."
        )

    database_role = environment.get("DOLPHIN_DATABASE_ROLE", "").strip()
    if database_role not in {"app", "migration"}:
        _fail("DOLPHIN_DATABASE_ROLE must be app or migration.")

    role_names = {
        "init": _validate_database_identity(environment, "POSTGRES_INIT_USER", role=True),
        "migration": _validate_database_identity(environment, "POSTGRES_MIGRATION_USER", role=True),
        "app": _validate_database_identity(environment, "POSTGRES_APP_USER", role=True),
    }
    if len(set(role_names.values())) != len(role_names):
        _fail("PostgreSQL role names must be distinct.")

    password_name = (
        "POSTGRES_APP_PASSWORD"
        if database_role == "app"
        else "POSTGRES_MIGRATION_PASSWORD"
    )
    database = {
        "NAME": _validate_database_identity(environment, "POSTGRES_DB", role=False),
        "USER": role_names[database_role],
        "PASSWORD": _required(environment, password_name),
        "HOST": _required(environment, "POSTGRES_HOST"),
        "PORT": str(_bounded_int(environment, "POSTGRES_PORT", default=5432, minimum=1, maximum=65535)),
        "CONNECT_TIMEOUT": _bounded_int(
            environment,
            "POSTGRES_CONNECT_TIMEOUT",
            default=3,
            minimum=1,
            maximum=30,
        ),
        # Transport security to the database. Empty keeps libpq's own default,
        # which is what a single-host deployment wants: the database is only
        # reachable on an internal Docker network that never leaves the host.
        # A split app/database deployment carries the connection over a real
        # network and must set "verify-full" with a CA, or the credentials and
        # every row cross that network in the clear.
        "SSLMODE": _database_sslmode(environment),
        "SSLROOTCERT": (environment.get("POSTGRES_SSLROOTCERT") or "").strip(),
    }
    if len(database["PASSWORD"]) < 16:
        _fail(f"{password_name} must be at least 16 characters.")
    if database["SSLMODE"] in {"verify-ca", "verify-full"} and not database["SSLROOTCERT"]:
        _fail("POSTGRES_SSLROOTCERT must name the CA bundle when POSTGRES_SSLMODE verifies the server.")

    # HSTS is one year or more when it is on, and the only other accepted value
    # is exactly 0, meaning off. A value in between would be a weak pin that
    # looks like protection, so it stays refused.
    #
    # 0 exists for one real case: a staging or IP-only deployment presenting a
    # self-signed certificate. HSTS is inert for a bare IP by specification, but
    # on a hostname a one-year pin makes the browser refuse to let anyone click
    # through the certificate warning for a year — on the operator's own machine,
    # with no easy undo. Production keeps the default.
    hsts_raw = environment.get("DJANGO_SECURE_HSTS_SECONDS", "31536000").strip()
    if hsts_raw == "0":
        hsts_seconds = 0
    else:
        hsts_seconds = _bounded_int(
            environment,
            "DJANGO_SECURE_HSTS_SECONDS",
            default=31_536_000,
            minimum=31_536_000,
            maximum=63_072_000,
        )
    hsts_include_subdomains = _strict_bool(
        environment,
        "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
        default=False,
    )
    hsts_preload = _strict_bool(environment, "DJANGO_SECURE_HSTS_PRELOAD", default=False)
    if hsts_preload and not hsts_include_subdomains:
        _fail("DJANGO_SECURE_HSTS_PRELOAD requires HSTS on subdomains.")
    if hsts_seconds == 0:
        # Off means off at both layers: no subdomain or preload modifier may be
        # claimed, and the edge must send no header at all.
        if hsts_include_subdomains or hsts_preload:
            _fail("DJANGO_SECURE_HSTS_SECONDS=0 cannot be combined with subdomain or preload HSTS.")
        expected_hsts_header = ""
    else:
        expected_hsts_header = f"max-age={hsts_seconds}"
        if hsts_include_subdomains:
            expected_hsts_header += "; includeSubDomains"
        if hsts_preload:
            expected_hsts_header += "; preload"
    # When HSTS is off the edge header must be empty, and nginx omits a header
    # whose value is an empty string — so the two layers stay in agreement
    # instead of Django saying "off" while the proxy still pins the browser.
    supplied_hsts_header = (environment.get("DOLPHIN_HSTS_HEADER") or "").strip()
    if supplied_hsts_header != expected_hsts_header:
        _fail("DOLPHIN_HSTS_HEADER must exactly match the approved HSTS settings.")

    secure_ssl_redirect = _strict_bool(
        environment,
        "DJANGO_SECURE_SSL_REDIRECT",
        default=True,
    )
    if not secure_ssl_redirect:
        _fail("DJANGO_SECURE_SSL_REDIRECT must be true in production.")

    return {
        "SECRET_KEY": secret_key,
        "ALLOWED_HOSTS": allowed_hosts,
        "CSRF_TRUSTED_ORIGINS": csrf_origins,
        "PUBLIC_HOST": public_host,
        "AUDIT_TRUSTED_PROXY_CIDRS": _validate_proxy_networks(
            _csv(environment, "AUDIT_TRUSTED_PROXY_CIDRS")
        ),
        "DATABASE": database,
        "DATABASE_ROLE": database_role,
        "SECURE_SSL_REDIRECT": secure_ssl_redirect,
        "SECURE_HSTS_SECONDS": hsts_seconds,
        "SECURE_HSTS_INCLUDE_SUBDOMAINS": hsts_include_subdomains,
        "SECURE_HSTS_PRELOAD": hsts_preload,
    }
