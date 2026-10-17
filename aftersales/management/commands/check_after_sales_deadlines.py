"""Act on the after-sales deadlines due now (2.40.61, BIZ-008).

Run from cron every 15 minutes, like the other scheduled commands — the
deployment has no task queue. Safe to run as often as wanted: each warning is
written once per case, deadline and level, and what it sets off (a text, an
escalation) happens once with it. Panel warnings need no run at all; they are
read live from the deadlines.
"""

from django.core.management.base import BaseCommand

from aftersales.alerts import check_deadlines
from common.deployment.profile import feature_enabled


class Command(BaseCommand):
    help = "Write the after-sales deadline warnings due now; text and escalate as the company set."

    def handle(self, *args, **options):
        if not feature_enabled("after_sales"):
            self.stdout.write("after-sales deadlines: feature off, nothing to do")
            return
        counts = check_deadlines()
        self.stdout.write(
            f"after-sales deadlines: alerts={counts['alerts']} texts={counts['texts']} escalated={counts['escalated']}"
        )
