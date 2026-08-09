from config.settings import *


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
ENABLE_API_DOCS = True
LOGGING["loggers"]["kariz.request"]["level"] = "WARNING"
