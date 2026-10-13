"""`manage.py reset_two_factor --username <name>` — take two-factor sign-in off
one account from the server (2.40.42).

The way back for whoever cannot reach the panel's own reset: the Platform
Admin, whose phone and recovery codes are both gone (the panel never lets an
account reset itself — `accounts.two_factor.reset_two_factor`). Like
`bootstrap_platform_admin`, it is a host operation: only someone with a shell
on the server can run it, and the activity log records it.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import TwoFactorDevice, User
from auditlog.services import log_activity


class Command(BaseCommand):
    help = "Take two-factor sign-in off one account (a lost phone and no recovery code)."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        user = User.objects.filter(username=User.normalize_username(options["username"])).first()
        if user is None:
            raise CommandError("No such account.")
        deleted, _ = TwoFactorDevice.objects.filter(user=user).delete()
        user.two_factor_recovery_codes.all().delete()
        if not deleted:
            raise CommandError("Two-factor sign-in is not on for this account.")
        log_activity(actor=None, operation="two_factor.reset", instance=user)
        self.stdout.write(self.style.SUCCESS(f"Two-factor sign-in is off for {user.username}; they sign in with the password alone."))
