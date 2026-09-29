from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations"

    def ready(self):
        # Providers register themselves on import; so do the core handlers
        # and the signal receivers that turn other modules' saves into events.
        from integrations import handlers, openapi, signals  # noqa: F401
        from integrations.providers import ebazar, generic  # noqa: F401
