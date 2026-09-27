from django.apps import AppConfig


class ProfilesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "profiles"

    def ready(self):
        from profiles.adapters import CustomerAdapter, UserAdapter
        from profiles.registry import register

        register(CustomerAdapter())
        register(UserAdapter())
