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
