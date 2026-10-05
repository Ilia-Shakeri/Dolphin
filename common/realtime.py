"""Live updates for the panel (2.38.0): «something of this kind changed».

An event is tiny — a kind (`customer`, `invoice`, `chat`…), optionally an id and
optionally the users it concerns. It carries **no data**: the page that receives
it asks the ordinary API again, so every permission and object scope applies to
what it then reads, exactly as for any other request.

How it travels, with no extra service beyond what a deployment already runs:

* a change publishes with `pg_notify` *inside the transaction that made it*, so
  PostgreSQL delivers the event only if that transaction commits;
* one process per deployment (the `realtime` service, `DOLPHIN_REALTIME_LISTENER`)
  holds a `LISTEN` connection and hands each event to the browsers connected to
  it over Server-Sent Events (`common.realtime_views`);
* on SQLite (development) there is no database to relay through, so the event
  goes straight to this process' own subscribers after commit.

It is optional at every level. The feature `realtime` is off by default,
`DOLPHIN_REALTIME_ENABLED` is a hard off switch, and a browser that cannot reach
the stream just keeps refreshing the way it always did.
"""

import json
import logging
import queue
import threading
import time

from django.conf import settings
from django.db import connection, transaction

from common.deployment.profile import feature_enabled

logger = logging.getLogger("dolphin.realtime")

CHANNEL = "dolphin_events"
#: PostgreSQL refuses a NOTIFY payload over 8000 bytes; stay well under it.
MAX_PAYLOAD_BYTES = 6000
#: Kinds whose id is never sent to anyone: they name a person's record, and the
#: page re-reads the list itself.
KINDS_WITHOUT_ID = frozenset({"customer", "payment", "lead", "interaction", "invoice", "order", "campaign", "sale", "after_sales"})


#: Who may hear that a kind of record changed (2.39.23): the read capabilities of
#: the module that lists it. A kind not named here (chat, call — always sent to
#: named users only — and resync) is not filtered this way.
KIND_CAPABILITIES = {
    "customer": {"customers.scoped", "customers.company"},
    "lead": {"leads.scoped", "leads.company"},
    "interaction": {"interactions.scoped", "interactions.company"},
    "sale": {"sales.own", "sales.company"},
    "campaign": {"campaigns.scoped", "campaigns.company"},
    "invoice": {"invoices.scoped", "invoices.company"},
    "order": {"orders.scoped", "orders.company"},
    "payment": {"payments.company"},
    "after_sales": {"after_sales.company", "after_sales.assigned"},
    "inventory": {"inventory.read", "inventory.manage"},
}


def kinds_for_capabilities(capabilities):
    """The record kinds a holder of `capabilities` may be told about."""
    return frozenset(kind for kind, needed in KIND_CAPABILITIES.items() if needed & set(capabilities))


def available():
    """Publishing is worth doing only when the feature is on and not switched off."""
    return bool(getattr(settings, "REALTIME_ENABLED", False)) and feature_enabled("realtime")


class Subscriber:
    def __init__(self, user_id, kinds=None):
        self.user_id = user_id
        #: `None` = every kind (internal use and tests); otherwise only these.
        self.kinds = kinds
        self.created = time.monotonic()
        self.queue = queue.Queue(maxsize=256)
        self.overflowed = False
        #: Set when a newer connection of the same user pushed this one out; the
        #: stream then ends with a terminal `bye` the browser must not retry.
        self.evicted = False

    def offer(self, event):
        try:
            self.queue.put_nowait(event)
        except queue.Full:
            # A browser that cannot keep up is told to re-read everything once
            # rather than being sent a backlog.
            self.overflowed = True


class Broker:
    """The browsers connected to this process."""

    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers = set()

    def subscribe(self, user_id, kinds=None):
        subscriber = Subscriber(user_id, kinds)
        limit = int(getattr(settings, "REALTIME_MAX_PER_USER", 3))
        with self._lock:
            mine = sorted((s for s in self._subscribers if s.user_id == user_id), key=lambda s: s.created)
            # One user (many tabs, a runaway script) may not take every slot:
            # beyond the per-user ceiling the oldest connections are told to end.
            for old in mine[: max(len(mine) - limit + 1, 0)]:
                old.evicted = True
                self._subscribers.discard(old)
            self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber):
        with self._lock:
            self._subscribers.discard(subscriber)

    def count(self):
        with self._lock:
            return len(self._subscribers)

    def deliver(self, event):
        users = event.get("u")
        with self._lock:
            kind = event.get("k")
            targets = [
                s for s in self._subscribers
                if (users is None or s.user_id in users)
                and (s.kinds is None or kind not in KIND_CAPABILITIES or kind in s.kinds)
            ]
        for subscriber in targets:
            subscriber.offer(event)


BROKER = Broker()


def public_event(event):
    """What a browser is told: the kind, and an id only where one is harmless."""
    kind = event["k"]
    return {"k": kind, "i": None if kind in KINDS_WITHOUT_ID else event.get("i"), "t": event["t"]}


def _already_announced(event):
    """True when the same announcement was already made in this transaction
    (2.40.0): an import of 5000 rows is one «customers changed», not 5000.

    The set lives on the connection beside a marker callback queued with
    `on_commit`; when the marker is no longer queued (the transaction committed
    or rolled back) the set belongs to a finished transaction and starts over.
    Outside a transaction nothing is coalesced.
    """
    if not getattr(connection, "in_atomic_block", False) or not hasattr(connection, "run_on_commit"):
        return False
    state = getattr(connection, "_dolphin_realtime_state", None)
    queued = {entry[1] for entry in connection.run_on_commit}
    if state is None or state["marker"] not in queued:
        def marker():
            return None

        state = {"marker": marker, "seen": set()}
        connection._dolphin_realtime_state = state
        transaction.on_commit(marker)
    key = (event["k"], tuple(event["u"]) if event["u"] is not None else None,
           None if event["k"] in KINDS_WITHOUT_ID else event["i"])
    if key in state["seen"]:
        return True
    state["seen"].add(key)
    return False


def publish(kind, *, object_id=None, users=None):
    """Announce a change. A no-op unless live updates are on; never raises."""
    if not available():
        return
    event = {"k": kind, "i": object_id, "u": sorted(set(users)) if users is not None else None, "t": int(time.time() * 1000)}
    try:
        if _already_announced(event):
            return
        if connection.vendor == "postgresql":
            payload = json.dumps(event, separators=(",", ":"))
            if len(payload.encode("utf-8")) > MAX_PAYLOAD_BYTES:
                payload = json.dumps({"k": kind, "i": None, "u": None, "t": event["t"]}, separators=(",", ":"))
            # A savepoint: a failing NOTIFY must not abort the business write
            # it is announcing.
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_notify(%s, %s)", [CHANNEL, payload])
        else:
            transaction.on_commit(lambda: BROKER.deliver(event))
    except Exception:  # noqa: BLE001 - live updates are auxiliary and never break a write
        logger.exception("publishing a live update failed (kind=%s)", kind)


# --- the process that serves streams ---------------------------------------

_listener_lock = threading.Lock()
_listener_started = False


def _connection_parameters():
    database = settings.DATABASES["default"]
    options = dict(database.get("OPTIONS") or {})
    parameters = {
        "dbname": database["NAME"], "user": database["USER"], "password": database["PASSWORD"],
        "host": database["HOST"], "port": database["PORT"],
    }
    for name in ("sslmode", "sslrootcert", "connect_timeout"):
        if options.get(name):
            parameters[name] = options[name]
    return {key: value for key, value in parameters.items() if value not in ("", None)}


#: When the LISTEN connection last proved alive (monotonic seconds), or None.
_listener_alive_at = None
#: Whether the listener has connected at least once (a reconnect then resyncs).
_listener_connected_before = False


def _listen_forever():
    import psycopg

    global _listener_alive_at, _listener_connected_before
    delay = 1
    while True:
        try:
            with psycopg.connect(**_connection_parameters(), autocommit=True) as listener:
                listener.execute(f"LISTEN {CHANNEL}")
                logger.info("realtime listener connected")
                delay = 1
                _listener_alive_at = time.monotonic()
                if _listener_connected_before:
                    # Events published while the connection was down are lost:
                    # every browser re-reads what it shows (2.40.0).
                    BROKER.deliver({"k": "resync", "i": None, "u": None, "t": int(time.time() * 1000)})
                _listener_connected_before = True
                while True:
                    _listener_alive_at = time.monotonic()
                    for notice in listener.notifies(timeout=30):
                        try:
                            BROKER.deliver(json.loads(notice.payload))
                        except ValueError:
                            logger.warning("ignored a malformed live update")
        except Exception:  # noqa: BLE001 - reconnect with backoff; browsers keep their fallback meanwhile
            _listener_alive_at = None
            logger.exception("realtime listener lost its connection; retrying in %ss", delay)
            time.sleep(delay)
            delay = min(delay * 2, 30)


def ensure_listener():
    """Start the one `LISTEN` thread of this process (PostgreSQL only)."""
    global _listener_started
    if connection.vendor != "postgresql":
        return False
    with _listener_lock:
        if not _listener_started:
            threading.Thread(target=_listen_forever, name="dolphin-realtime-listener", daemon=True).start()
            _listener_started = True
    return True


def listener_running():
    return _listener_started


def listener_healthy():
    """The LISTEN connection answered within the last minute (2.40.0) — not
    merely «a thread was started». The notifies loop wakes every 30 s."""
    return _listener_alive_at is not None and time.monotonic() - _listener_alive_at < 75


def serves_streams():
    """Whether *this* process may hold event streams open.

    Streams hold a thread each, so only the dedicated `realtime` service (a
    threaded worker) does it; the ordinary web workers answer 404 and a
    misrouted proxy cannot tie them up. In development (DEBUG, SQLite) the
    development server is threaded, so it serves them too.
    """
    return bool(getattr(settings, "REALTIME_SERVE_STREAMS", False))
