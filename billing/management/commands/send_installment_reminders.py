"""Send the instalment reminder SMS due now (2.40.51, feature `installment_reminders`).

Run from cron like `send_scheduled_sms` — the deployment has no task queue,
and a periodically-run management command is the established pattern here.
Safe to run as often as wanted: each reminder is claimed once per row, kind
and due date, and nothing goes out before the company's send hour.
"""

from django.core.management.base import BaseCommand

from billing.installment_reminders import DISPATCH_BATCH, dispatch_installment_reminders


class Command(BaseCommand):
    help = "Send the instalment reminder SMS (before, on and after the due date) that are due now."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=DISPATCH_BATCH, help=f"Most reminders in this run (default {DISPATCH_BATCH}).")

    def handle(self, *args, **options):
        if options["limit"] <= 0:
            raise SystemExit("--limit must be positive.")
        sent, failed, skipped = dispatch_installment_reminders(limit=options["limit"])
        self.stdout.write(f"installment reminders: sent={sent} failed={failed} skipped={skipped}")
