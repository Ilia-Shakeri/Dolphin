from django.apps import AppConfig


class TelephonyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "telephony"

    def ready(self):
        # The Asterisk provider registers itself on import; the listener and
        # the CDR sync join the integrations worker.
        from telephony import provider, worker  # noqa: F401

        worker.register()
