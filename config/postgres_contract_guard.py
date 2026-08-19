import re

from django.core.exceptions import ImproperlyConfigured


TOKEN_PATTERN = re.compile(r"^[a-f0-9]{32}$")


def build_postgres_contract_database(environment):
    if environment.get("KARIZ_PG_CONTRACT") != "1":
        raise ImproperlyConfigured(
            "KARIZ_PG_CONTRACT=1 is required for the isolated PostgreSQL contract settings."
        )

    token = environment.get("KARIZ_PG_CONTRACT_TOKEN", "")
    if not TOKEN_PATTERN.fullmatch(token):
        raise ImproperlyConfigured(
            "KARIZ_PG_CONTRACT_TOKEN must be a random 32-character lowercase hex value."
        )

    host = environment.get("KARIZ_PG_CONTRACT_HOST", "")
    if host != "127.0.0.1":
        raise ImproperlyConfigured("PostgreSQL contract proof must use the IPv4 loopback host.")

    try:
        port = int(environment.get("KARIZ_PG_CONTRACT_PORT", ""))
    except ValueError as exc:
        raise ImproperlyConfigured(
            "KARIZ_PG_CONTRACT_PORT must be a high local port."
        ) from exc
    if port <= 1024 or port >= 65536 or port == 5432:
        raise ImproperlyConfigured(
            "PostgreSQL contract proof must use a high port other than 5432."
        )

    expected_name = f"contract_frooshbin_{token}"
    if environment.get("KARIZ_PG_CONTRACT_NAME") != expected_name:
        raise ImproperlyConfigured(
            "PostgreSQL contract database name does not match the random run token."
        )

    expected_user = f"frooshbin_migration_{token}"
    if environment.get("KARIZ_PG_CONTRACT_USER") != expected_user:
        raise ImproperlyConfigured(
            "PostgreSQL contract user does not match the random run token."
        )
    password = environment.get("KARIZ_PG_CONTRACT_PASSWORD", "")
    if len(password) < 16:
        raise ImproperlyConfigured(
            "KARIZ_PG_CONTRACT_PASSWORD must be an isolated non-empty proof secret."
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
