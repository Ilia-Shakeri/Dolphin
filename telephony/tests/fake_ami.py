"""A fake Asterisk Manager Interface server for tests — no PBX needed.

Speaks enough AMI for Dolphin: the banner, `Login` (checked against the
configured user and secret), `Ping`, `Logoff` and `Originate` (answered, and
remembered so a test can see what Dolphin asked for). A test pushes recorded
events to every connected client with `push(...)`, and can `drop_clients()` to
exercise reconnection. It runs its own event loop in a background thread, so
both synchronous and asyncio tests can use it.
"""

import asyncio
import json
import threading
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def encode(message):
    return ("".join(f"{key}: {value}\r\n" for key, value in message.items()) + "\r\n").encode("utf-8")


class FakeAMIServer:
    def __init__(self, username="dolphin", secret="amipass"):
        self.username, self.secret = username, secret
        self.loop = asyncio.new_event_loop()
        self.clients = []
        self.logins = []
        self.actions = []
        self.originates = []
        self.connections = 0
        self.ready = threading.Event()
        self.logged_in = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.port = None
        self._server = None

    # --- lifecycle ------------------------------------------------------------

    def start(self):
        self.thread.start()
        self.ready.wait(5)
        return self

    def stop(self):
        async def shutdown():
            for writer in list(self.clients):
                writer.close()
            self._server.close()
            await self._server.wait_closed()

        asyncio.run_coroutine_threadsafe(shutdown(), self.loop).result(5)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)

    def _run(self):
        asyncio.set_event_loop(self.loop)

        async def serve():
            self._server = await asyncio.start_server(self._client, "127.0.0.1", 0)
            self.port = self._server.sockets[0].getsockname()[1]
            self.ready.set()

        self.loop.run_until_complete(serve())
        self.loop.run_forever()

    # --- protocol ----------------------------------------------------------------

    async def _client(self, reader, writer):
        self.connections += 1
        writer.write(b"Asterisk Call Manager/9.0.0\r\n")
        await writer.drain()
        authenticated = False
        try:
            while True:
                lines = []
                while True:
                    raw = await reader.readline()
                    if not raw:
                        return
                    line = raw.decode("utf-8").rstrip("\r\n")
                    if not line:
                        if lines:
                            break
                        continue
                    lines.append(line)
                message = {}
                for line in lines:
                    key, _, value = line.partition(":")
                    message.setdefault(key.strip(), value.strip())
                action = message.get("Action", "")
                action_id = message.get("ActionID", "")
                self.actions.append(action)
                if action == "Login":
                    ok = message.get("Username") == self.username and message.get("Secret") == self.secret
                    self.logins.append(ok)
                    writer.write(encode({
                        "Response": "Success" if ok else "Error",
                        "ActionID": action_id,
                        "Message": "Authentication accepted" if ok else "Authentication failed",
                    }))
                    await writer.drain()
                    if not ok:
                        writer.close()
                        return
                    authenticated = True
                    self.clients.append(writer)
                    self.logged_in.set()
                elif not authenticated:
                    writer.write(encode({"Response": "Error", "ActionID": action_id, "Message": "Permission denied"}))
                elif action == "Ping":
                    writer.write(encode({"Response": "Success", "ActionID": action_id, "Ping": "Pong"}))
                elif action == "Originate":
                    self.originates.append(message)
                    writer.write(encode({"Response": "Success", "ActionID": action_id, "Message": "Originate successfully queued"}))
                elif action == "Logoff":
                    writer.write(encode({"Response": "Goodbye", "ActionID": action_id}))
                    await writer.drain()
                    writer.close()
                    return
                else:
                    writer.write(encode({"Response": "Error", "ActionID": action_id, "Message": "Invalid/unknown command"}))
                await writer.drain()
        except (ConnectionError, OSError):
            return
        finally:
            if writer in self.clients:
                self.clients.remove(writer)

    # --- test controls --------------------------------------------------------------

    def push(self, events, *, garbage=False):
        """Send events (dicts) to every logged-in client, in order."""

        async def send():
            for writer in list(self.clients):
                if garbage:
                    writer.write(b"this line has no colon\r\n: nor this\r\nEvent: Unknown\r\n\r\n")
                for event in events:
                    writer.write(encode(event))
                await writer.drain()

        asyncio.run_coroutine_threadsafe(send(), self.loop).result(5)

    def drop_clients(self):
        async def drop():
            for writer in list(self.clients):
                writer.close()
            self.clients.clear()

        self.logged_in.clear()
        asyncio.run_coroutine_threadsafe(drop(), self.loop).result(5)
