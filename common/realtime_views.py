"""`/api/v1/realtime/events/` (Server-Sent Events) and its health probe (2.38.0)."""

import json
import queue
import time

from django.conf import settings
from django.db import connections
from django.http import Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.views import View

from accounts.access import is_crm_identity
from common import realtime

HEARTBEAT_SECONDS = 15


class EventStreamView(View):
    """One browser's stream of «something changed» events.

    Authenticated like every page (the session cookie), restricted to CRM
    identities, and bounded: it ends after `REALTIME_STREAM_SECONDS` so a
    signed-out or deactivated user stops receiving within minutes, and the
    browser simply reconnects. Nothing here reads the database per event.
    """

    def get(self, request):
        if not realtime.available() or not realtime.serves_streams():
            raise Http404
        if not is_crm_identity(request.user):
            return HttpResponse(status=401)
        # Same-site only (2.40.0): a page on another site may not hold a stream
        # with this user's cookie.
        if request.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "same-site", "none"):
            return HttpResponse(status=403)
        origin = request.headers.get("Origin")
        if origin and origin.split("://", 1)[-1] != request.get_host():
            return HttpResponse(status=403)
        limit = int(getattr(settings, "REALTIME_MAX_CONNECTIONS", 200))
        if realtime.BROKER.count() >= limit:
            return HttpResponse(status=503, headers={"Retry-After": "30"})
        from accounts.access import capabilities_for

        # Read once, before the connection is released: a stream lasts minutes
        # and ends (REALTIME_STREAM_SECONDS), so a changed role takes effect on
        # the next reconnect.
        kinds = realtime.kinds_for_capabilities(capabilities_for(request.user))
        subscriber = realtime.BROKER.subscribe(request.user.pk, kinds)
        # The stream reads nothing from the database from here on, so this
        # thread must not sit on a connection for the minutes it stays open: a
        # few hundred browsers would otherwise hold a few hundred database
        # connections idle. Anything that needs one later reopens it.
        connections.close_all()
        deadline = time.monotonic() + int(getattr(settings, "REALTIME_STREAM_SECONDS", 300))

        def stream():
            try:
                # First message of every connection: a resync, so whatever changed while
                # the browser was away (or reconnecting) is re-read.
                yield f"retry: 5000\n\ndata: {json.dumps({'k': 'resync', 'i': None, 't': int(time.time() * 1000)})}\n\n"
                while time.monotonic() < deadline and not subscriber.evicted:
                    if subscriber.overflowed:
                        subscriber.overflowed = False
                        yield f"data: {json.dumps({'k': 'resync', 'i': None, 't': int(time.time() * 1000)})}\n\n"
                    try:
                        event = subscriber.queue.get(timeout=HEARTBEAT_SECONDS)
                    except queue.Empty:
                        yield ": ping\n\n"
                        continue
                    yield f"data: {json.dumps(realtime.public_event(event), separators=(',', ':'))}\n\n"
            finally:
                realtime.BROKER.unsubscribe(subscriber)

        def stream_with_goodbye():
            yield from stream()
            if subscriber.evicted:
                # Terminal: a newer tab of the same user took this slot.
                yield f"event: bye\ndata: {json.dumps({'k': 'bye'})}\n\n"

        response = StreamingHttpResponse(stream_with_goodbye(), content_type="text/event-stream")
        # Freed on close even if the generator never started (a client that left
        # before the first byte would otherwise keep its slot).
        response._resource_closers.append(lambda: realtime.BROKER.unsubscribe(subscriber))
        response["Cache-Control"] = "no-cache, no-transform"
        # nginx: never buffer this response.
        response["X-Accel-Buffering"] = "no"
        return response


class RealtimeHealthView(View):
    """For the compose healthcheck and the operator: no data, no auth."""

    def get(self, request):
        if not getattr(settings, "REALTIME_SERVE_STREAMS", False):
            raise Http404
        # Nothing about users or events; the listener's real state (2.40.0).
        healthy = realtime.listener_healthy() or not realtime.listener_running()
        return JsonResponse(
            {"status": "ok" if healthy else "degraded", "listener": realtime.listener_healthy(), "connections": realtime.BROKER.count()},
            status=200 if healthy else 503,
        )
