import getpass
import secrets

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from accounts.platform_admin_guard import lock_platform_admin_guard
from auditlog.services import log_activity


class Command(BaseCommand):
    help = "Create the first active CRM Platform Admin through a server terminal."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)

    def handle(self, *args, **options):
        username = User.normalize_username(options["username"])
        self._assert_available(username)

        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Password (again): ")
        if not secrets.compare_digest(password, confirmation):
            raise CommandError("Passwords do not match.")

        user = User(
            username=username,
            role=User.Role.PLATFORM_ADMIN,
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
        try:
            user.full_clean(
                exclude=("password",),
                validate_unique=False,
                validate_constraints=False,
            )
            validate_password(password, user=user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc

        with transaction.atomic():
            lock_platform_admin_guard()
            self._assert_available(username)
            user.set_password(password)
            user.save(force_insert=True)
            log_activity(
                actor=None,
                operation="user.platform_admin_bootstrapped",
                instance=user,
                changes={
                    "fields": ["username", "role", "is_active"],
                    "password_set": True,
                },
                request_id="",
                ip_address=None,
            )

        self.stdout.write(self.style.SUCCESS("Platform Admin created."))

    @staticmethod
    def _assert_available(username):
        if User.objects.filter(role=User.Role.PLATFORM_ADMIN).exists():
            raise CommandError("A Platform Admin account already exists.")
        if User.objects.filter(username=username).exists():
            raise CommandError("Username already exists.")
