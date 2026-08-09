import os

from config.settings import *
from config.postgres_test_guard import build_postgres_test_database


SECRET_KEY = "isolated-postgresql-test-key-not-for-deployment"
DEBUG = False
DATABASES = {"default": build_postgres_test_database(os.environ)}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

