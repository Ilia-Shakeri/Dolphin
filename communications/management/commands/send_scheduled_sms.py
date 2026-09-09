"""Dispatch SMS campaigns that are due.

Run from cron, exactly like `clearsessions` (compose.yml's `session-cleanup`
service) and `dispatch_outbound_events` — this deployment has no task queue,
and a periodically-run management command is the established pattern here for
periodic work rather than a new piece of infrastructure.

The SMS page also flushes a few due recipients on its own when it is opened
(`SMS_CAMPAIGN_REQUEST_FLUSH_BATCH`), so a deployment whose operator has not
wired cron yet still sends. That flush is a safety net, not a substitute: it
only runs when somebody happens to open the page, so a campaign scheduled for
03:00 on a quiet night waits for the first visitor unless cron exists.
"""

from django.core.management.base import BaseCommand

from communications.services import SMS_CAMPAIGN_DISPATCH_BATCH, dispatch_due_sms_campaigns


class Command(BaseCommand):
    help = "Send the recipients of any SMS campaign whose scheduled time has arrived."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=SMS_CAMPAIGN_DISPATCH_BATCH,
            help=(
                "Most recipients to send in this run "
                f"(default {SMS_CAMPAIGN_DISPATCH_BATCH}). Each is one provider "
                "request, so this bounds how long the run takes."
            ),
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit <= 0:
            raise SystemExit("--limit must be positive.")
        sent, failed = dispatch_due_sms_campaigns(limit=limit)
        # Written to stdout rather than the logger so a cron mail carries the
        # outcome; the individual sends are already in the activity log.
        self.stdout.write(f"outbound sms dispatched: sent={sent} failed={failed}")
