from django.core.management.base import BaseCommand
from django.db import transaction

from sales.customer_backfill import run_backfill
from sales.models import Customer, CustomerCategory


class Command(BaseCommand):
    help = (
        "Fill Customer.owner (from created_by) and Customer.category_ref (from the "
        "category text), idempotently. --dry-run reports what would change and "
        "writes nothing; ambiguous category spellings are listed, never merged."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, dry_run=False, **options):
        with transaction.atomic():
            report = run_backfill(Customer, CustomerCategory, apply=not dry_run)
        self.stdout.write(("DRY RUN - no changes written" if dry_run else "Applied") + ":")
        for line in report.as_lines():
            self.stdout.write(line)
