"""`manage.py prune_integration_logs [--days 90]` — drop old integration log
rows, processed events and settled deliveries. Receipts of inbound webhooks
are kept as long as the events they produced."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from integrations.models import DomainEvent, IntegrationLog, WebhookDelivery


class Command(BaseCommand):
    help = "Delete integration log rows and settled events older than --days (default 90)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90)

    def handle(self, *args, **options):
        days = max(7, options["days"])
        cutoff = timezone.now() - timedelta(days=days)
        logs = IntegrationLog.objects.filter(created_at__lt=cutoff).delete()[0]
        deliveries = WebhookDelivery.objects.filter(
            created_at__lt=cutoff, status__in=[WebhookDelivery.Status.DELIVERED, WebhookDelivery.Status.FAILED]
        ).delete()[0]
        events = DomainEvent.objects.filter(
            created_at__lt=cutoff, status=DomainEvent.Status.PROCESSED, deliveries__isnull=True
        ).delete()[0]
        self.stdout.write(f"removed {logs} log row(s), {deliveries} delivery row(s), {events} event(s) older than {days} days")
