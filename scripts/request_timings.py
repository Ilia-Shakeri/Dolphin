"""How fast the server answers, from its own request log (2.40.42).

Every request the application serves writes one JSON line —
`{"event":"http_request","method":…,"path":…,"status":…,"duration_ms":…}`
(`common/request_logging.py`). This reads those lines from standard input and
prints, per route, how many requests there were and their median, 95th
percentile and slowest time. Numbers in a path are folded into `{id}` so a
record's page is one route, not one per record. It sends nothing anywhere and
reads nothing but its input.

On the server, for the last day of traffic:

    docker logs --since 24h dolphin-web-1 2>&1 | python3 scripts/request_timings.py

Options: `--top N` (routes shown, default 25), `--min N` (fewest requests a
route needs to be shown, default 5), `--api-only`, `--pages-only`.
"""

import argparse
import json
import re
import sys
from statistics import median

ID = re.compile(r"/\d+(?=/|$)")


def percentile(values, share):
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(share * (len(ordered) - 1))))
    return ordered[index]


def read(stream, *, api_only=False, pages_only=False):
    routes = {}
    for line in stream:
        start = line.find('{"event":"http_request"')
        if start < 0:
            continue
        try:
            entry = json.loads(line[start:])
        except ValueError:
            continue
        path = entry.get("path") or ""
        if path.startswith("/static/") or path.startswith("/api/v1/realtime/events"):
            continue
        is_api = path.startswith("/api/")
        if (api_only and not is_api) or (pages_only and is_api):
            continue
        route = f'{entry.get("method", "")} {ID.sub("/{id}", path)}'
        routes.setdefault(route, []).append(float(entry.get("duration_ms") or 0.0))
    return routes


def report(routes, *, top=25, least=5):
    rows = [
        (route, len(times), median(times), percentile(times, 0.95), max(times))
        for route, times in routes.items()
        if len(times) >= least
    ]
    rows.sort(key=lambda row: row[3], reverse=True)
    lines = [f'{"route":60} {"n":>6} {"p50 ms":>8} {"p95 ms":>8} {"max ms":>8}']
    for route, count, middle, p95, slowest in rows[:top]:
        lines.append(f"{route[:60]:60} {count:6d} {middle:8.1f} {p95:8.1f} {slowest:8.1f}")
    every = [time for times in routes.values() for time in times]
    if every:
        lines.append(f'{"all requests":60} {len(every):6d} {median(every):8.1f} {percentile(every, 0.95):8.1f} {max(every):8.1f}')
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--min", type=int, default=5, dest="least")
    parser.add_argument("--api-only", action="store_true")
    parser.add_argument("--pages-only", action="store_true")
    options = parser.parse_args(argv)
    routes = read(sys.stdin, api_only=options.api_only, pages_only=options.pages_only)
    if not routes:
        print("No request log lines on standard input.", file=sys.stderr)
        return 1
    print(report(routes, top=options.top, least=options.least))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
