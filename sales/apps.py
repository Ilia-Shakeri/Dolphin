from django.apps import AppConfig


class SalesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sales"

    def ready(self):
        from accounts.signals import user_deactivated
        from sales import shipping

        shipping.register()
        user_deactivated.connect(_return_work_of_deactivated, dispatch_uid="sales.returned_work")


def _return_work_of_deactivated(sender, *, actor, user, **kwargs):
    from sales.returned_work import return_work_of

    return_work_of(actor=actor, user=user)
