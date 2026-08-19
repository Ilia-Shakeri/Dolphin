import re

from django.core.exceptions import ImproperlyConfigured


TOKEN_PATTERN = re.compile(r"^[a-f0-9]{32}$")
RESTORE_NAME_PATTERN = re.compile(r"^restore_frooshbin_[a-f0-9]{32}$")


def is_ephemeral_restore_database(name):
    """True only for the disposable restore database of one harness run.

    The harness drops the database this names, so the pattern is deliberately
    strict: an exact prefix plus the 32-character run token, nothing else.
    """
    return bool(RESTORE_NAME_PATTERN.fullmatch(name or ""))


def build_postgres_restore_database(environment):
    """Connect to the restored database as the ordinary application role.

    The restore proof exists to show that a real `pg_restore` archive yields a
    database the normal runtime login can use. It therefore refuses any elevated
    login, and refuses any database name that is not the run's disposable
    restore database.
    """
    if environment.get("KARIZ_PG_RESTORE") != "1":
        raise ImproperlyConfigured(
            "KARIZ_PG_RESTORE=1 is required for the isolated PostgreSQL restore settings."
        )

    token = environment.get("KARIZ_PG_RESTORE_TOKEN", "")
    if not TOKEN_PATTERN.fullmatch(token):
        raise ImproperlyConfigured(
            "KARIZ_PG_RESTORE_TOKEN must be a random 32-character lowercase hex value."
        )

    host = environment.get("KARIZ_PG_RESTORE_HOST", "")
    if host != "127.0.0.1":
        raise ImproperlyConfigured("PostgreSQL restore proof must use the IPv4 loopback host.")

    try:
        port = int(environment.get("KARIZ_PG_RESTORE_PORT", ""))
    except ValueError as exc:
        raise ImproperlyConfigured(
            "KARIZ_PG_RESTORE_PORT must be a high local port."
        ) from exc
    if port <= 1024 or port >= 65536 or port == 5432:
        raise ImproperlyConfigured(
            "PostgreSQL restore proof must use a high port other than 5432."
        )

    expected_name = f"restore_frooshbin_{token}"
    name = environment.get("KARIZ_PG_RESTORE_NAME")
    if name != expected_name or not is_ephemeral_restore_database(name):
        raise ImproperlyConfigured(
            "PostgreSQL restore database name does not match the random run token."
        )

    # The point of this settings module is to exercise the runtime role, so the
    # migration and initialisation logins are rejected outright.
    expected_user = f"frooshbin_app_{token}"
    if environment.get("KARIZ_PG_RESTORE_USER") != expected_user:
        raise ImproperlyConfigured(
            "PostgreSQL restore proof must use the ordinary application login."
        )

    password = environment.get("KARIZ_PG_RESTORE_PASSWORD", "")
    if len(password) < 16:
        raise ImproperlyConfigured(
            "KARIZ_PG_RESTORE_PASSWORD must be an isolated non-empty proof secret."
        )

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": expected_name,
        "USER": expected_user,
        "PASSWORD": password,
        "HOST": host,
        "PORT": str(port),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 3},
    }
