"""`manage.py run_telephony_listener --integration <id>` — one AMI listener in
the foreground, for debugging a PBX connection. In production the listener
runs inside `integrations-worker`; do not run both against the same PBX."""

import asyncio
import signal

from django.core.management.base import BaseCommand, CommandError

from integrations.models import Integration


class Command(BaseCommand):
    help = "Run the Asterisk AMI listener for one connection in the foreground."

    def add_arguments(self, parser):
        parser.add_argument("--integration", type=int, required=True)

    def handle(self, *args, **options):
        from telephony.worker import _listen

        integration = Integration.objects.filter(pk=options["integration"], provider_key="asterisk").first()
        if integration is None:
            raise CommandError("No Asterisk connection with that id.")

        async def main():
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for signum in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(signum, stop.set)
                except (NotImplementedError, RuntimeError):
                    signal.signal(signum, lambda *_: loop.call_soon_threadsafe(stop.set))
            await _listen(integration, stop)

        self.stdout.write(f"listening to Asterisk connection {integration.pk} (Ctrl+C to stop)")
        asyncio.run(main())
