import os

from config.postgres_contract_guard import build_postgres_contract_database
from config.settings import *


SECRET_KEY = "isolated-postgresql-contract-key-not-for-deployment"
DEBUG = False
DATABASES = {"default": build_postgres_contract_database(os.environ)}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
