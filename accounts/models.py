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
    # An explicit pick from the Metronic cartoon set (`accounts.avatars`),
    # e.g. `"023-woman.svg"`. Blank is the common case and means "no explicit
    # choice" — `avatars.default_avatar_for` then falls back to the stable
    # hash it always used. Product-owner request 2026-09-21: «کاربران باید
    # بتوانند بین عکس‌های پیش‌فرض انتخاب کنند». A plain `CharField`, not a
    # `CheckConstraint` against the allowed set: which files exist is a
    # property of the deployed static build, not something the database
    # schema can know — `accounts.avatars.set_default_avatar_choice` is the
    # one place that validates a name before it is stored.
    chosen_default_avatar = models.CharField(max_length=64, blank=True, default="")
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


class UserAvatar(models.Model):
    """One person's own profile picture.

    A separate table rather than four columns on `User`, for one reason
    worth the join: `User` is read on every authenticated request — the
    session, the capability set, the sidebar — and a two-megabyte
    `BinaryField` on it would be loaded and discarded thousands of times a
    day. Here it is read only by the endpoint that serves the image.

    Keyed by the user, so the relationship is one-to-one by construction and
    "this person has a picture" is a row existing rather than a nullable
    column being non-null. `CASCADE`: a picture of a deleted account is not
    a record anybody needs kept, unlike the business rows that use `PROTECT`.

    Stored in the row rather than on disk for the same reasons
    `common.models.BrandSettings.logo_content` is — the container filesystem
    is read-only, there is no `MEDIA_ROOT`, and this way the picture is in
    the backup that `common/backups.py` already takes.
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, primary_key=True, related_name="avatar"
    )
    content = models.BinaryField()
    content_type = models.CharField(max_length=32)
    size_bytes = models.PositiveIntegerField()
    original_filename = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "user avatar"
        verbose_name_plural = "user avatars"
        constraints = [
            # The three facts about the stored bytes travel together or the
            # row is meaningless — the same all-or-nothing shape
            # `common_brandsettings_logo_all_or_nothing` already uses.
            models.CheckConstraint(
                condition=models.Q(size_bytes__gt=0),
                name="accounts_user_avatar_has_content",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    content_type__in=("image/jpeg", "image/png", "image/webp")
                ),
                name="accounts_user_avatar_content_type_allowed",
            ),
        ]

