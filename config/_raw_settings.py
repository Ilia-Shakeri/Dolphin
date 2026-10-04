# Temporary: a fresh database for the raw-data walk-through (removed afterwards).
from config.devcheck_settings import *  # noqa: F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": r"C:/Users/DEAR-O~1/AppData/Local/Temp/claude/C--Users-Dear-OTCamp-User-Desktop-Dolphin/a0bd6fa2-90d2-4df8-a8ce-2c5432a9ee69/scratchpad/raw.sqlite3"}}
REALTIME_ENABLED = False
