import os
import tempfile
from pathlib import Path

from config.settings import *


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {
            "NAME": str(Path(tempfile.gettempdir()) / f"test_forooshbin_{os.getpid()}.sqlite3"),
        },
    }
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
ENABLE_API_DOCS = True
LOGGING["loggers"]["forooshbin.request"]["level"] = "WARNING"

# The suite covers every shipped module, including those a real deployment does
# not serve unless its manifest asks for them. Without this the tests would stop
# exercising code that is still in the release and still reusable.
DEPLOYMENT_PROFILE_ENABLES_ALL_FEATURES = True
