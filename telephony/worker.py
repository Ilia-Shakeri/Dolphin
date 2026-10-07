"""What the telephony module runs inside `integrations-worker` (2.22.0).

* A **listener service**: one asyncio loop in its own thread, holding one AMI
  session per enabled Asterisk connection (`telephony.ami.run_forever`). Every
  `RESCAN` seconds it re-reads the connections, so enabling, disabling or
  editing one starts, stops or restarts its session without restarting the
  worker. Events go to that connection's `CallTracker`, which writes through
  the ORM in a worker thread (the ORM is synchronous).
* A **CDR sync job** every `CDR_EVERY` seconds per connection with CDR
  settings.
* **Click-to-call** (2.23.0): while a session is up, it claims that
  connection's queued `OriginateRequest`s every `ORIGINATE_POLL` seconds,
  creates each `Call` and sends `Originate` on the same session.

Health — connected, refused, unreachable — is written to the connection row,
where the integrations page shows it.
"""

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections, transaction
from django.utils import timezone

from common.deployment.profile import feature_enabled
from common.persian_errors import ami_reason

logger = logging.getLogger("dolphin.telephony.worker")

RESCAN = 30
CDR_EVERY = 300
ORIGINATE_POLL = 1.0


def _enabled_integrations():
    from integrations.models import Integration

    return list(Integration.objects.filter(provider_key="asterisk", enabled=True))


def _fresh(function, *args):
    """Run ORM work on one of the listener's long-lived threads, first
    dropping a connection the database closed (restart, idle timeout) —
    what the worker's main loop does between its jobs."""
    close_old_connections()
    return function(*args)


def _signature(integration):
    """What, if changed, means the session must be restarted."""
    return (integration.pk, repr(sorted(integration.config.items())), integration.secrets_token, integration.updated_at)


def _close_connections():
    from django.db import connections

    connections.close_all()


async def _listen(integration, stop):
    """One connection's session. Its database work runs on one dedicated
    thread — which also keeps a call's events in the order they came —
    and that thread's database connection is closed when the session ends."""
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"telephony-{integration.pk}")
    try:
        await _listen_on(integration, stop, executor)
    finally:
        await asyncio.get_running_loop().run_in_executor(executor, _close_connections)
        executor.shutdown(wait=True)


def _claim_originates(integration_id):
    """This connection's queued requests, each now `sending` and paired with
    a new outbound `Call` whose `Linkedid` is the `ChannelId` it will be
    given. Claimed one by one with a conditional update, so two workers
    never send the same call."""
    from telephony.models import Call, OriginateRequest
    from telephony.services import expire_stale_originates

    now = timezone.now()
    expire_stale_originates(now=now)
    claimed = []
    for request in OriginateRequest.objects.filter(
        integration_id=integration_id, status=OriginateRequest.Status.PENDING,
        created_at__gte=now - OriginateRequest.TTL,
    ).order_by("created_at")[:10]:
        with transaction.atomic():
            taken = OriginateRequest.objects.filter(pk=request.pk, status=OriginateRequest.Status.PENDING).update(
                status=OriginateRequest.Status.SENDING
            )
            if not taken:
                continue
            call = Call.objects.create(
                integration_id=integration_id,
                linkedid=f"dolphin-{uuid.uuid4().hex}",
                direction=Call.Direction.OUTBOUND,
                caller_raw=request.extension,
                callee_raw=request.dial,
                external_number=request.external_number,
                extension=request.extension,
                user_id=request.user_id,
                person_type=request.person_type,
                person_id=request.person_id,
                started_at=now,
                raw={"events": [{"Event": "DolphinOriginate"}]},
            )
            OriginateRequest.objects.filter(pk=request.pk).update(call=call)
            request.call = call
        claimed.append(request)
    return claimed


def _settle_originate(request, ok, message):
    from integrations.events import emit
    from telephony.models import Call, OriginateRequest
    from telephony.tracker import CallTracker

    now = timezone.now()
    if ok:
        OriginateRequest.objects.filter(pk=request.pk).update(status=OriginateRequest.Status.SENT, sent_at=now)
        return
    OriginateRequest.objects.filter(pk=request.pk).update(status=OriginateRequest.Status.FAILED, error=message[:300])
    call = Call.objects.filter(pk=request.call_id, status=Call.Status.RINGING).first()
    if call is not None:
        call.status, call.ended_at, call.hangup_cause = Call.Status.FAILED, now, "originate refused"
        call.save(update_fields=["status", "ended_at", "hangup_cause", "updated_at"])
        emit("call.ended", CallTracker.payload(call), person_type=call.person_type, person_id=call.person_id,
             dedupe_key=f"call:{call.pk}:ended")


def originate_fields(config, request):
    """The `Originate` action for one request: ring the user's extension,
    and when they pick up, dial the number in the originate context."""
    timeout = int(config.get("originate_timeout") or 30)
    caller_id = config.get("originate_caller_id") or f"{request.dial} <{request.dial}>"
    return {
        "Channel": (config.get("originate_channel") or "Local/{extension}@from-internal").replace(
            "{extension}", request.extension
        ),
        "Context": config.get("originate_context") or "from-internal",
        "Exten": request.dial,
        "Priority": "1",
        "CallerID": caller_id,
        "Timeout": str(timeout * 1000),
        "Async": "true",
        "ChannelId": request.call.linkedid,
        "OtherChannelId": f"{request.call.linkedid}-2",
    }


async def _originate_loop(integration, executor, live, stop):
    loop = asyncio.get_running_loop()
    config = integration.config or {}
    while not stop.is_set():
        connection = live.get("connection")
        if connection is not None:
            try:
                requests = await loop.run_in_executor(executor, _fresh, _claim_originates, integration.pk)
            except Exception:  # noqa: BLE001 — logged; the next tick tries again
                logger.exception("claiming originate requests failed")
                requests = []
            for request in requests:
                try:
                    response = await connection.action("Originate", **originate_fields(config, request))
                    ok = (response.get("Response") or "").lower() == "success"
                    message = "" if ok else f"مرکز تلفن تماس را نپذیرفت: {response.get('Message') or ''}".strip()
                except Exception as error:  # noqa: BLE001 — reported on the request
                    ok, message = False, f"ارسال به مرکز تلفن ناموفق بود: {ami_reason(error)}"
                await loop.run_in_executor(executor, _fresh, _settle_originate, request, ok, message)
        try:
            await asyncio.wait_for(stop.wait(), timeout=ORIGINATE_POLL)
        except asyncio.TimeoutError:
            pass


async def _listen_on(integration, stop, executor):
    from integrations.services import record_health, secrets_of
    from telephony.ami import run_forever
    from telephony.tracker import CallTracker

    loop = asyncio.get_running_loop()
    tracker = await loop.run_in_executor(executor, _fresh, CallTracker, integration)
    live = {}

    async def settings_loader():
        secret = await loop.run_in_executor(executor, _fresh, lambda: secrets_of(integration).get("ami_password", ""))
        config = integration.config
        return config["ami_host"], int(config.get("ami_port") or 5038), config["ami_username"], secret

    async def on_event(event):
        if event.get("Event") in ("ExtensionStatus", "FullyBooted"):
            return
        await loop.run_in_executor(executor, _fresh, tracker.handle, event)

    async def on_status(ok, message):
        await loop.run_in_executor(executor, _fresh, record_health, integration, ok, message)
        if ok:
            await loop.run_in_executor(executor, tracker.refresh_extensions)

    async def on_connected(connection):
        live["connection"] = connection

    originating = asyncio.create_task(_originate_loop(integration, executor, live, stop))
    try:
        await run_forever(settings_loader, on_event, stop=stop, on_status=on_status, on_connected=on_connected)
    finally:
        originating.cancel()
        try:
            await originating
        except asyncio.CancelledError:
            pass


async def _supervise(thread_stop):
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="telephony-supervisor")
    loop = asyncio.get_running_loop()
    running = {}  # integration id -> (signature, stop event, task)
    try:
        while not thread_stop.is_set():
            wanted = {}
            if feature_enabled("telephony"):
                for integration in await loop.run_in_executor(executor, _fresh, _enabled_integrations):
                    wanted[integration.pk] = integration
            for pk, (signature, stop, task) in list(running.items()):
                integration = wanted.get(pk)
                if integration is None or _signature(integration) != signature or task.done():
                    stop.set()
                    try:
                        await asyncio.wait_for(task, 10)
                    except Exception:  # noqa: BLE001
                        task.cancel()
                    running.pop(pk)
            for pk, integration in wanted.items():
                if pk not in running:
                    stop = asyncio.Event()
                    task = asyncio.create_task(_listen(integration, stop))
                    running[pk] = (_signature(integration), stop, task)
                    logger.info("telephony listener started for integration %s", pk)
            for _ in range(RESCAN):
                if thread_stop.is_set():
                    break
                await asyncio.sleep(1)
    finally:
        for _signature_value, stop, task in running.values():
            stop.set()
        for _signature_value, _stop, task in running.values():
            try:
                await asyncio.wait_for(task, 5)
            except Exception:  # noqa: BLE001
                task.cancel()
        await loop.run_in_executor(executor, _close_connections)
        executor.shutdown(wait=False)


def listener_service(thread_stop):
    """Entry point for `integrations.worker.register_service`."""
    try:
        asyncio.run(_supervise(thread_stop))
    except Exception:  # noqa: BLE001 — logged; the worker's other jobs carry on
        logger.exception("telephony listener service stopped")


def cdr_job():
    """Sync every connection that has CDR settings; errors are recorded, not raised."""
    from integrations.models import IntegrationLog
    from integrations.services import log, record_health
    from telephony.cdr import CdrUnavailable, configured, sync
    from telephony.models import CdrSyncState

    if not feature_enabled("telephony"):
        return
    for integration in _enabled_integrations():
        if not configured(integration.config or {}):
            continue
        try:
            result = sync(integration)
        except CdrUnavailable as error:
            CdrSyncState.objects.update_or_create(integration=integration, defaults={"last_error": str(error)[:500]})
            log(integration, direction=IntegrationLog.Direction.INBOUND, event_type="cdr.sync",
                status=IntegrationLog.Status.ERROR, message=str(error))
            record_health(integration, False, str(error))
            continue
        if result["created"] or result["changed"]:
            log(integration, direction=IntegrationLog.Direction.INBOUND, event_type="cdr.sync",
                status=IntegrationLog.Status.OK,
                message=f"{result['rows']} ردیف، {result['created']} تماس تازه، {result['changed']} اصلاح")


def register():
    from integrations.worker import register_job, register_service

    register_service(listener_service)
    register_job("telephony.cdr", cdr_job, CDR_EVERY)
