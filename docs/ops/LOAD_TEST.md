# Read-only readiness load check

This procedure measures only the edge, application-liveness, or database-readiness health path. It never sends a business request and does not prove Customer, Lead, Sale, report, browser, or full production capacity.

The harness is fail-closed. It sends only `GET`, follows no redirect, uses no environment proxy, and accepts no query, request body, cookie, authorization value, caller header, or credential-bearing URL. It prints one aggregate JSON object and no target host, response body, per-request value, or exception text.

## Required approval and target

Before a non-loopback run, record:

- exact release reference and application image digest;
- exact approved HTTPS origin and the same host entered again as confirmation;
- target environment, owner, UTC window, observer, and abort authority;
- one approved path from `/health/live/`, `/api/v1/health/live/`, or `/api/v1/health/ready/`;
- exact request count, concurrency, request timeout, wall limit, maximum p95 latency, and minimum successful requests per second;
- current error budget and infrastructure saturation limits observed outside this repository.

Do not aim the harness at production without the environment owner and capacity owner approving those exact values. The readiness path reaches PostgreSQL, so treat `/api/v1/health/ready/` as database load. Start with a separately approved low run and stop if host monitoring reaches its abort limit. The script itself cannot see CPU, memory, connection-pool, database-lock, or upstream saturation.

Plain HTTP is accepted only for a literal loopback host. Any other target must use HTTPS with normal certificate and hostname verification. The base URL must be only a canonical origin, with no path, query, fragment, user name, or password. `--confirm-host` must exactly repeat its lowercase host.

## Bounds and pass rule

Every workload and threshold value is required; the script has no guessed load target.

| Input | Accepted bound |
|---|---:|
| Requests | 1 through 2,000 |
| Concurrency | 1 through 32, and no more than requests |
| Per-request timeout | 0.1 through 10 seconds |
| Whole-run wall limit | 1 through 300 seconds |
| Maximum nearest-rank p95 | 1 through 10,000 milliseconds |
| Minimum successful rate | 0.01 through 100,000 requests/second |

A pass requires every requested response to finish with HTTP 200, successful nearest-rank p95 at or below the caller threshold, successful request rate at or above the caller threshold, and wall time within the caller limit. A redirect, non-200 response, transport failure, unfinished request, or threshold miss exits nonzero.

## Exact run

Run from the reviewed release root. Enter no secret in any prompt:

```powershell
$approvedBaseUrl = Read-Host 'Exact approved HTTPS origin, or loopback HTTP origin'
$confirmedHost = Read-Host 'Repeat the exact lowercase host only'
$approvedPath = Read-Host 'Exact allowed health path'
$approvedRequests = Read-Host 'Approved request count'
$approvedConcurrency = Read-Host 'Approved concurrency'
$approvedTimeout = Read-Host 'Approved per-request timeout seconds'
$approvedWall = Read-Host 'Approved whole-run wall limit seconds'
$approvedP95 = Read-Host 'Approved maximum p95 milliseconds'
$approvedRate = Read-Host 'Approved minimum successful requests per second'
python scripts/load_readiness.py `
  --sentinel KARIZ_READ_ONLY_LOAD_V1 `
  --base-url $approvedBaseUrl `
  --confirm-host $confirmedHost `
  --path $approvedPath `
  --requests $approvedRequests `
  --concurrency $approvedConcurrency `
  --timeout-seconds $approvedTimeout `
  --max-wall-seconds $approvedWall `
  --max-p95-ms $approvedP95 `
  --min-requests-per-second $approvedRate
if ($LASTEXITCODE -ne 0) { throw 'Read-only readiness load gate failed.' }
```

Run one path per command so the result stays attributable. Do not run the three paths concurrently. Do not add application paths, HTTP methods, headers, login state, CSRF tokens, query values, or request bodies to this tool.

## Safe result and evidence

The one-line result contains only:

- fixed event name and allowed endpoint path;
- requested, completed, successful, error, transport-error, and unfinished counts plus aggregate error rate;
- numeric HTTP status counts;
- wall time, successful request rate, and aggregate successful latency values;
- caller thresholds and final pass boolean.

It does not contain the origin, confirmed host, response content, raw error, timestamp, credential, or request sample. Capture stdout and the process exit code through the approved restricted evidence runner. Bind the evidence record to the release reference, image digest, environment, approved target record, external CPU/memory/database metrics, UTC start/end time, runner/tool version, and named reviewer. Apply the approved evidence access, integrity-hash, retention, and deletion policy. Do not paste raw host monitoring, customer data, environment output, or secrets into a ticket.

Repository tests exercise the bounds and a local loopback server only. They do not prove public TLS, the deployed edge, PostgreSQL capacity, a production-shaped host, or any approved service-level target.
