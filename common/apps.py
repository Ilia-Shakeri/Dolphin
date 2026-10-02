from django.apps import AppConfig
from django.conf import settings


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "common"

    def ready(self):
        # Resolve and verify the signed deployment manifest before the first
        # request is served. An unacceptable manifest raises here, so the
        # process refuses to start instead of serving with an assumed feature
        # set. No database access happens at this point: the cache table in
        # common/models.py is derived later and is never authoritative.
        from common.deployment.profile import configure_from_settings

        configure_from_settings(settings)

        # Live updates (2.38.0): announce saves, and — only in the dedicated
        # `realtime` process — listen for them. Both are no-ops unless the
        # `realtime` feature and DOLPHIN_REALTIME_ENABLED are on.
        from common import realtime, realtime_signals

        realtime_signals.connect()
        if getattr(settings, "REALTIME_SERVE_STREAMS", False) and realtime.available():
            realtime.ensure_listener()
