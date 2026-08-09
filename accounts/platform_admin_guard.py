from django.db import connection

from accounts.models import User


PLATFORM_ADMIN_LOCK_KEY = 5422700358370087233


def lock_platform_admin_guard():
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                [PLATFORM_ADMIN_LOCK_KEY],
            )
        return
    list(
        User.objects.select_for_update()
        .filter(role=User.Role.PLATFORM_ADMIN)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
