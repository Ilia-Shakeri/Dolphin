"""`manage.py run_integrations_worker` — the long-running integrations process.

Hosted by the `integrations-worker` Compose service (restart:
unless-stopped). Every `--interval` seconds it handles pending domain events
and sends due outbound webhooks; worker hooks registered by providers (the
Asterisk listener and CDR sync from 2.22.0) run alongside. It never exits
on an error — each failure is logged and the loop continues — and stops
cleanly on SIGTERM/SIGINT. With `--once` it runs one pass and returns.
"""

import logging
import signal
import threading

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from common.deployment.profile import feature_enabled
from integrations.events import process_pending
from integrations.webhooks import deliver_due
from integrations.worker import periodic_jobs, start_background_services

logger = logging.getLogger("dolphin.integrations.worker")


class Command(BaseCommand):
    help = "Run the integrations worker: outbox, outbound webhooks and provider listeners."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=float, default=5.0)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        stop = threading.Event()

        def request_stop(signum, frame):
            logger.info("integrations worker stopping (signal %s)", signum)
            stop.set()

        if not options["once"]:
            signal.signal(signal.SIGTERM, request_stop)
            signal.signal(signal.SIGINT, request_stop)
            if feature_enabled("integrations"):
                start_background_services(stop)
        once = options["once"]
        while not stop.is_set():
            if not once:
                # A long-lived process must drop a connection the database
                # side closed (restart, idle timeout) before using it again.
                close_old_connections()
            if feature_enabled("integrations"):
                for name, job in [("outbox", process_pending), *periodic_jobs()]:
                    try:
                        job()
                    except Exception:  # noqa: BLE001 — logged; the worker keeps running
                        logger.exception("integrations worker job %s failed", name)
                if feature_enabled("outbound_webhooks"):
                    try:
                        deliver_due()
                    except Exception:  # noqa: BLE001
                        logger.exception("webhook delivery sweep failed")
            if once:
                break
            stop.wait(options["interval"])
        if not once:
            close_old_connections()
