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


class UserCapabilityOverride(models.Model):
    """One capability, force-granted or force-revoked for one user.

    `accounts.access.ROLE_CAPABILITIES` still decides what a role gets by
    default — this table only records where one specific user's effective set
    diverges from that default, so two people with the same role can end up
    with different access without a second role ever existing for either of
    them. Absence of a row means "inherit whatever the role says today", which
    is what makes a role's own permissions still take effect for an
    unoverridden user, and what makes `reset_user_permissions` a plain delete.

    `accounts.access.capabilities_for` is the only reader that matters: it
    layers `granted=True` rows on top of the role default and removes
    `granted=False` rows from it, refusing to honour any row naming a
    `users.*` or `audit.*` capability — see `PROTECTED_CAPABILITY_PREFIXES`.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="capability_overrides")
    capability = models.CharField(max_length=64)
    granted = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "user capability override"
        verbose_name_plural = "user capability overrides"
        constraints = [
            models.UniqueConstraint(fields=["user", "capability"], name="accounts_capability_override_unique"),
        ]
