"""What the integrations worker runs besides the outbox (2.21.0).

Providers add long-running services (a PBX event listener) with
`register_service(start)` and periodic jobs (a CDR sync, a health check) with
`register_job(name, fn, every_seconds)`. The worker starts the services once
in their own threads and calls each job when it is due.
"""

import time

_SERVICES = []
_JOBS = []


def register_service(start):
    """`start(stop_event)` runs in its own daemon thread until `stop_event` is set."""
    _SERVICES.append(start)
    return start


def register_job(name, fn, every_seconds):
    _JOBS.append({"name": name, "fn": fn, "every": every_seconds, "last": 0.0})
    return fn


def start_background_services(stop_event):
    import threading

    threads = []
    for start in _SERVICES:
        thread = threading.Thread(target=start, args=(stop_event,), daemon=True, name=getattr(start, "__name__", "service"))
        thread.start()
        threads.append(thread)
    return threads


def periodic_jobs(now=None):
    """`[(name, fn)]` of the registered jobs that are due now."""
    now = now if now is not None else time.monotonic()
    due = []
    for job in _JOBS:
        if now - job["last"] >= job["every"]:
            job["last"] = now
            due.append((job["name"], job["fn"]))
    return due
