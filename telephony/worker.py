"""What the telephony module runs inside `integrations-worker` (2.22.0).

* A **listener service**: one asyncio loop in its own thread, holding one AMI
  session per enabled Asterisk connection (`telephony.ami.run_forever`). Every
  `RESCAN` seconds it re-reads the connections, so enabling, disabling or
  editing one starts, stops or restarts its session without restarting the
  worker. Events go to that connection's `CallTracker`, which writes through
  the ORM in a worker thread (the ORM is synchronous).
* A **CDR sync job** every `CDR_EVERY` seconds per connection with CDR
  settings.

Health — connected, refused, unreachable — is written to the connection row,
where the integrations page shows it.
"""

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections

from common.deployment.profile import feature_enabled

logger = logging.getLogger("dolphin.telephony.worker")

RESCAN = 30
CDR_EVERY = 300

#: integration id -> live AMI connection, for placing calls (2.23.0).
LIVE_CONNECTIONS = {}
_LIVE_LOCK = threading.Lock()


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


async def _listen_on(integration, stop, executor):
    from integrations.services import record_health, secrets_of
    from telephony.ami import run_forever
    from telephony.tracker import CallTracker

    loop = asyncio.get_running_loop()
    tracker = await loop.run_in_executor(executor, _fresh, CallTracker, integration)

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
        with _LIVE_LOCK:
            if connection is None:
                LIVE_CONNECTIONS.pop(integration.pk, None)
            else:
                LIVE_CONNECTIONS[integration.pk] = (loop, connection)

    await run_forever(settings_loader, on_event, stop=stop, on_status=on_status, on_connected=on_connected)


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
