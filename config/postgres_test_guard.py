import re

from django.core.exceptions import ImproperlyConfigured


TOKEN_PATTERN = re.compile(r"^[a-f0-9]{32}$")


def build_postgres_test_database(environment):
    if environment.get("KARIZ_PG_TEST") != "1":
        raise ImproperlyConfigured("KARIZ_PG_TEST=1 is required for the isolated PostgreSQL test settings.")

    token = environment.get("KARIZ_PG_TEST_TOKEN", "")
    if not TOKEN_PATTERN.fullmatch(token):
        raise ImproperlyConfigured("KARIZ_PG_TEST_TOKEN must be a random 32-character lowercase hex value.")

    host = environment.get("KARIZ_PG_TEST_HOST", "")
    if host != "127.0.0.1":
        raise ImproperlyConfigured("PostgreSQL tests must use the IPv4 loopback host.")

    try:
        port = int(environment.get("KARIZ_PG_TEST_PORT", ""))
    except ValueError as exc:
        raise ImproperlyConfigured("KARIZ_PG_TEST_PORT must be a high local port.") from exc
    if port <= 1024 or port >= 65536 or port == 5432:
        raise ImproperlyConfigured("PostgreSQL tests must use a high port other than 5432.")

    expected_name = f"test_kariz_{token}"
    if environment.get("KARIZ_PG_TEST_NAME") != expected_name:
        raise ImproperlyConfigured("PostgreSQL test database name does not match the random run token.")

    user = environment.get("KARIZ_PG_TEST_USER", "")
    if not user.startswith("kariz_test_"):
        raise ImproperlyConfigured("PostgreSQL test user must use the kariz_test_ prefix.")

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "postgres",
        "USER": user,
        "PASSWORD": "",
        "HOST": host,
        "PORT": str(port),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 3},
        "TEST": {"NAME": expected_name},
    }

