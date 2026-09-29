from django.apps import AppConfig


class TelephonyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "telephony"

    def ready(self):
        # The Asterisk and webhook providers register themselves on import; the listener and
        # the CDR sync join the integrations worker; the hooks (popup,
        # missed-call task, score refresh) listen for call events (2.23.0).
        from telephony import hooks, pbx_webhook, provider, worker  # noqa: F401

        worker.register()
