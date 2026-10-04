from django.core.management.base import BaseCommand

from sales.campaign_migration import run_migration


class Command(BaseCommand):
    help = (
        "Group existing leads by their campaign label into Campaign rows and move "
        "every audience member onto its campaign (2.36.0). Idempotent and "
        "expand-only; --dry-run reports counts and spellings needing review "
        "without writing anything."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--report", help="write a CSV with one row per migrated person")

    def handle(self, *args, dry_run=False, report=None, **options):
        path = report
        report = run_migration(apply=not dry_run)
        if path:
            report.write_csv(path)
            self.stdout.write(f"report written to {path}")
        self.stdout.write("DRY RUN - no changes written:" if dry_run else "Applied:")
        for line in report.lines():
            self.stdout.write(line)
