"""`manage.py sync_cdr [--integration <id>] [--since 2026-09-01T00:00] [--until …]`

Without a range, resumes from each connection's cursor — what the worker does
every five minutes. With `--since`, re-reads that range and leaves the cursor
alone; running it again changes nothing.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from integrations.models import Integration
from telephony.cdr import CdrUnavailable, configured, pbx_zone, sync


class Command(BaseCommand):
    help = "Synchronise calls from the PBX's CDR table."

    def add_arguments(self, parser):
        parser.add_argument("--integration", type=int)
        parser.add_argument("--since")
        parser.add_argument("--until")

    def handle(self, *args, **options):
        rows = Integration.objects.filter(provider_key="asterisk", enabled=True)
        if options["integration"]:
            rows = rows.filter(pk=options["integration"])
        for integration in rows:
            config = integration.config or {}
            if not configured(config):
                self.stdout.write(f"{integration.name}: no CDR settings; skipped")
                continue
            since = until = None
            zone = pbx_zone(config)
            for name in ("since", "until"):
                raw = options[name]
                if raw:
                    value = parse_datetime(raw)
                    if value is None:
                        raise CommandError(f"--{name} is not a date-time: {raw}")
                    if value.tzinfo is None:
                        value = value.replace(tzinfo=zone)
                    if name == "since":
                        since = value
                    else:
                        until = value
            try:
                result = sync(integration, since=since, until=until)
            except CdrUnavailable as error:
                self.stderr.write(f"{integration.name}: {error}")
                continue
            self.stdout.write(
                f"{integration.name}: {result['rows']} row(s), {result['calls']} call(s), "
                f"{result['created']} created, {result['changed']} changed"
            )
