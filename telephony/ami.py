"""A small, dependency-free Asterisk Manager Interface client (decision D10).

AMI is a line protocol over TCP: the server greets with one banner line, then
both sides exchange *messages* — `Key: Value` lines ended by a blank line. A
message with `Response:` answers an action (matched by `ActionID`); one with
`Event:` is unsolicited. This module speaks exactly that, on asyncio:

* `parse_message` — never raises on a malformed line; it skips it.
* `AMIConnection` — one logged-in session: send an action and await its
  response, receive events, `Ping` as a heartbeat.
* `run_forever` — keep a session alive: connect, log in, read events, ping
  every `heartbeat` seconds, and on any failure reconnect after an
  exponentially growing, jittered delay (1 s … 60 s). It returns only when
  `stop` is set.

The password is sent in the `Login` action and nowhere else; nothing here
logs a message that carries it.
"""

import asyncio
import itertools
import logging
import random

logger = logging.getLogger("dolphin.telephony.ami")

CONNECT_TIMEOUT = 10
RESPONSE_TIMEOUT = 10
#: A message larger than this is not AMI; the connection is dropped.
MAX_MESSAGE_LINES = 400


class AMIError(Exception):
    pass


class AuthenticationFailed(AMIError):
    pass


def parse_message(lines):
    """`["Key: Value", …]` → `{"Key": "Value"}`. A line with no colon is
    skipped; a repeated key keeps its first value but `Variable`-style
    repeats are joined with a newline so nothing is silently lost."""
    message = {}
    for line in lines:
        key, sep, value = line.partition(":")
        if not sep or not key.strip():
            continue
        key, value = key.strip(), value.strip()
        if key in message:
            message[key] = f"{message[key]}\n{value}"
        else:
            message[key] = value
    return message


def format_action(action, fields, action_id):
    lines = [f"Action: {action}", f"ActionID: {action_id}"]
    for key, value in fields.items():
        if value is None:
            continue
        for item in value if isinstance(value, (list, tuple)) else [value]:
            text = str(item).replace("\r", " ").replace("\n", " ")
            lines.append(f"{key}: {text}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")


class AMIConnection:
    """One TCP session to one Asterisk."""

    def __init__(self, reader, writer, banner=""):
        self.reader = reader
        self.writer = writer
        self.banner = banner
        self._ids = itertools.count(1)
        self._pending = {}
        self.events = asyncio.Queue()
        self._reader_task = None
        self.closed = asyncio.Event()

    @classmethod
    async def open(cls, host, port, *, timeout=CONNECT_TIMEOUT):
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        banner = (await asyncio.wait_for(reader.readline(), timeout)).decode("utf-8", "replace").strip()
        if not banner.lower().startswith("asterisk call manager"):
            writer.close()
            raise AMIError(f"Not an Asterisk Manager banner: {banner[:60]!r}")
        connection = cls(reader, writer, banner)
        connection._reader_task = asyncio.create_task(connection._read_loop())
        return connection

    async def _read_loop(self):
        try:
            while True:
                lines = []
                while True:
                    raw = await self.reader.readline()
                    if not raw:
                        raise ConnectionError("AMI connection closed by the server")
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if line == "":
                        if lines:
                            break
                        continue
                    lines.append(line)
                    if len(lines) > MAX_MESSAGE_LINES:
                        raise AMIError("AMI message too long")
                message = parse_message(lines)
                action_id = message.get("ActionID")
                if "Response" in message and action_id in self._pending:
                    future = self._pending.pop(action_id)
                    if not future.done():
                        future.set_result(message)
                elif "Event" in message:
                    await self.events.put(message)
        except (ConnectionError, AMIError, OSError) as error:
            logger.info("AMI read loop ended: %s", error)
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(ConnectionError("AMI connection closed"))
            self._pending.clear()
            self.closed.set()
            await self.events.put(None)

    async def action(self, action, *, timeout=RESPONSE_TIMEOUT, **fields):
        if self.closed.is_set():
            raise ConnectionError("AMI connection closed")
        action_id = f"dolphin-{next(self._ids)}"
        future = asyncio.get_running_loop().create_future()
        self._pending[action_id] = future
        self.writer.write(format_action(action, fields, action_id))
        await self.writer.drain()
        return await asyncio.wait_for(future, timeout)

    async def login(self, username, secret):
        response = await self.action("Login", Username=username, Secret=secret, Events="on")
        if response.get("Response", "").lower() != "success":
            # The server's own words, which never contain the password.
            raise AuthenticationFailed(response.get("Message") or "Authentication failed")
        return response

    async def ping(self):
        response = await self.action("Ping")
        if response.get("Response", "").lower() != "success":
            raise AMIError("Ping failed")
        return response

    async def close(self):
        try:
            if not self.closed.is_set():
                try:
                    await asyncio.wait_for(self.action("Logoff"), 2)
                except Exception:  # noqa: BLE001 — closing anyway
                    pass
        finally:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
            if self._reader_task:
                self._reader_task.cancel()


def backoff_delays(base=1.0, cap=60.0):
    """1, 2, 4 … `cap` seconds, each with ±20 % jitter so a PBX restart does
    not get every client reconnecting in the same instant."""
    delay = base
    while True:
        yield delay * random.uniform(0.8, 1.2)
        delay = min(cap, delay * 2)


async def run_forever(
    settings_loader,
    on_event,
    *,
    stop,
    on_status=None,
    heartbeat=20.0,
    backoff=None,
    on_connected=None,
):
    """Keep one AMI session alive until `stop` (an `asyncio.Event`) is set.

    `settings_loader()` returns `(host, port, username, secret)` — called on
    every connect, so a changed configuration takes effect at the next
    reconnect. `on_event(message)` is awaited for every event, in order.
    `on_status(ok, message)` reports health; `on_connected(connection)` gets
    the live connection (for originating calls).
    """
    delays = backoff or backoff_delays()
    while not stop.is_set():
        connection = None
        try:
            host, port, username, secret = await settings_loader()
            connection = await AMIConnection.open(host, port)
            await connection.login(username, secret)
            delays = backoff or backoff_delays()
            if on_status:
                await on_status(True, f"متصل به {connection.banner}")
            if on_connected:
                await on_connected(connection)
            last_ping = asyncio.get_running_loop().time()
            while not stop.is_set():
                try:
                    event = await asyncio.wait_for(connection.events.get(), timeout=min(1.0, heartbeat))
                except asyncio.TimeoutError:
                    event = False
                if event is None:
                    raise ConnectionError("AMI connection closed")
                if event:
                    try:
                        await on_event(event)
                    except Exception:  # noqa: BLE001 — one bad event never ends the session
                        logger.exception("AMI event handler failed for %s", event.get("Event"))
                now = asyncio.get_running_loop().time()
                if now - last_ping >= heartbeat:
                    await connection.ping()
                    last_ping = now
        except AuthenticationFailed as error:
            if on_status:
                await on_status(False, f"ورود به AMI رد شد: {error}")
        except Exception as error:  # noqa: BLE001 — reconnect on anything
            logger.info("AMI session ended: %s: %s", type(error).__name__, error)
            if on_status:
                await on_status(False, f"اتصال به AMI برقرار نیست: {type(error).__name__}")
        finally:
            if on_connected:
                try:
                    await on_connected(None)
                except Exception:  # noqa: BLE001
                    pass
            if connection is not None:
                await connection.close()
        if stop.is_set():
            break
        try:
            await asyncio.wait_for(stop.wait(), timeout=next(delays))
        except asyncio.TimeoutError:
            pass
