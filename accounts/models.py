from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        SALES_AGENT = "sales_agent", "Sales Agent"
        SALES_MANAGER = "sales_manager", "Sales Manager"
        COMPANY_IT = "company_it", "Company IT"
        PLATFORM_ADMIN = "platform_admin", "Platform Admin"

    class Workstream(models.TextChoices):
        SALES = "sales", "Sales"
        AFTER_SALES = "after_sales", "After Sales"

    phone = models.CharField(max_length=32, blank=True)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.SALES_AGENT, db_index=True)
    workstream = models.CharField(max_length=32, choices=Workstream.choices, default=Workstream.SALES, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=["sales_agent", "sales_manager", "company_it", "platform_admin"]),
                name="accounts_user_role_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(workstream__in=["sales", "after_sales"]),
                name="accounts_user_workstream_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(role="sales_agent") | models.Q(workstream="sales"),
                name="accounts_user_elevated_workstream_sales",
            ),
        ]
