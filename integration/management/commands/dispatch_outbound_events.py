"""PRELIMINARY, UNCOMMITTED — see integration/apps.py.

The real-time sync transport: no new infrastructure dependency (this
codebase deliberately carries no Celery/Redis — see chat/'s own polling
instead of a channel layer for the established precedent), just a
management command a cron entry or a simple supervised loop can run.

    python manage.py dispatch_outbound_events            # one pass, then exit
    python manage.py dispatch_outbound_events --loop 5   # forever, every 5s

Idempotency is what makes retrying safe: every `OutboundEvent.
idempotency_key` is a fresh UUID assigned once, at enqueue time
(`integration.services.enqueue_event`), and Dolphin Accounting's own
webhook receiver treats a redelivery of the same key as a no-op success —
so a delivery that succeeded but whose response this command never saw
(a network drop after the fact) is retried safely rather than skipped or
double-counted.
"""

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request

from django.core.management.base import BaseCommand
from django.utils import timezone

from integration.models import OutboundEvent
from integration.services import get_pairing_settings
from common.deployment.profile import paired_accounting_base_url
from common.persian_errors import http_answer, network_reason

MAX_RESPONSE_DETAIL = 200
REQUEST_TIMEOUT_SECONDS = 10


def _dispatch_one(event, *, base_url, secret):
    body = json.dumps({
        "idempotency_key": event.idempotency_key,
        "event_type": event.event_type,
        "payload": event.payload,
        "occurred_at": event.occurred_at.isoformat(),
    }).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    request = urllib.request.Request(
        f"{base_url}/api/v1/integration/webhook/events/",
        data=body,
        headers={"Content-Type": "application/json", "X-Dolphin-Signature": signature},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return True, http_answer(response.status)
    except urllib.error.HTTPError as error:
        detail = error.read(MAX_RESPONSE_DETAIL).decode("utf-8", errors="replace") if error.fp else ""
        return False, http_answer(error.code, detail)
    except (urllib.error.URLError, OSError, ValueError) as error:
        return False, f"خطای اتصال: {network_reason(error)}"


class Command(BaseCommand):
    help = "Deliver pending OutboundEvent rows to the paired Dolphin Accounting deployment."

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop", type=int, default=0, metavar="SECONDS",
            help="run forever, sleeping SECONDS between passes, instead of one pass and exit",
        )

    def handle(self, *args, **options):
        interval = options["loop"]
        while True:
            self._run_one_pass()
            if interval <= 0:
                return
            time.sleep(interval)

    def _run_one_pass(self):
        base_url = paired_accounting_base_url()
        pairing = get_pairing_settings()
        if not base_url or not pairing.is_enabled or not pairing.shared_secret:
            self.stdout.write("pairing not configured/enabled — nothing to do.")
            return
        pending = list(OutboundEvent.objects.filter(dispatched_at__isnull=True).order_by("created_at"))
        delivered = 0
        for event in pending:
            success, detail = _dispatch_one(event, base_url=base_url, secret=pairing.shared_secret)
            if success:
                event.dispatched_at = timezone.now()
                event.save(update_fields=["dispatched_at", "updated_at"])
                delivered += 1
            else:
                event.attempts += 1
                event.last_error = detail[:500]
                event.save(update_fields=["attempts", "last_error", "updated_at"])
                self.stderr.write(f"{event.idempotency_key}: {detail}")
        self.stdout.write(f"delivered {delivered}/{len(pending)} pending event(s).")
