import os

from config.settings import *
from config.postgres_test_guard import build_postgres_test_database


SECRET_KEY = "isolated-postgresql-test-key-not-for-deployment"
DEBUG = False
DATABASES = {"default": build_postgres_test_database(os.environ)}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
# Match config/test_settings.py: the schema/docs routes are only registered when
# this is enabled, and the system-API tests assert against them. Without it the
# same tests that pass on SQLite return 404 here purely because of the settings
# module, not because of PostgreSQL.
ENABLE_API_DOCS = True

