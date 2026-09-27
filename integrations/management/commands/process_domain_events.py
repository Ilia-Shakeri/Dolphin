"""`manage.py process_domain_events` — one sweep of the outbox and of due
outbound webhook deliveries. The worker does this continuously; this is for
cron or a manual retry."""

from django.core.management.base import BaseCommand

from common.deployment.profile import feature_enabled
from integrations.events import process_pending
from integrations.webhooks import deliver_due


class Command(BaseCommand):
    help = "Handle pending domain events and send due outbound webhooks once."

    def handle(self, *args, **options):
        if not feature_enabled("integrations"):
            self.stdout.write("integrations is not enabled on this deployment; nothing to do.")
            return
        events = process_pending()
        deliveries = deliver_due() if feature_enabled("outbound_webhooks") else 0
        self.stdout.write(f"{events} event(s) handled, {deliveries} delivery attempt(s)")
