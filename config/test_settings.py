import os
import tempfile
from pathlib import Path

from config.settings import *


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {
            "NAME": str(Path(tempfile.gettempdir()) / f"test_kariz_{os.getpid()}.sqlite3"),
        },
    }
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
ENABLE_API_DOCS = True
LOGGING["loggers"]["kariz.request"]["level"] = "WARNING"
