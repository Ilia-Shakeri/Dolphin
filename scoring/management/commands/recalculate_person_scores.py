"""`manage.py recalculate_person_scores` — the nightly score run.

Run as the one-shot `score-recalculation` Compose service from the host's
crontab (docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md §4.4). Safe to run any number
of times: a score that has not moved within a day stores nothing new.
"""

from django.core.management.base import BaseCommand

from common.deployment.profile import feature_enabled
from scoring.services import recalculate_all


class Command(BaseCommand):
    help = "Recompute every active customer's and user's score and store the ones that moved."

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            choices=("customer", "user"),
            action="append",
            dest="types",
            help="Only this person type (repeatable). Default: both.",
        )

    def handle(self, *args, **options):
        if not feature_enabled("person_scoring"):
            self.stdout.write("person_scoring is not enabled on this deployment; nothing to do.")
            return
        summary = recalculate_all(tuple(options["types"] or ("customer", "user")))
        for person_type, (computed, stored) in summary.items():
            self.stdout.write(f"{person_type}: {computed} scored, {stored} new snapshot(s)")
