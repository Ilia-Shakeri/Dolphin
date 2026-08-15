import os

from config.postgres_restore_guard import build_postgres_restore_database
from config.settings import *


SECRET_KEY = "isolated-postgresql-restore-key-not-for-deployment"
DEBUG = False
DATABASES = {"default": build_postgres_restore_database(os.environ)}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
