"""Post the instalment late fees now due (2.40.52, feature `installment_late_fees`).

Run once a day from cron. Each row is charged once; a row due before the day a
fee was first configured is never charged; without the feature, or with no
fee set, it does nothing.
"""

from django.core.management.base import BaseCommand

from billing.installment_charges import LATE_FEE_BATCH, post_late_fees


class Command(BaseCommand):
    help = "Charge the late fee on every instalment now past its grace period."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=LATE_FEE_BATCH, help=f"Most rows in this run (default {LATE_FEE_BATCH}).")

    def handle(self, *args, **options):
        if options["limit"] <= 0:
            raise SystemExit("--limit must be positive.")
        charged = post_late_fees(limit=options["limit"])
        self.stdout.write(f"installment late fees: charged={charged}")
