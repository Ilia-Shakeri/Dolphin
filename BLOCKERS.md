# Blockers

Only the affected work is blocked. Independent roadmap work continues.

## Business decisions

| ID | State | Missing decision | Impact | Safe work that continues | Close evidence |
|---|---|---|---|---|---|
| BIZ-001 | BLOCKED_DECISION | Initial Lead assignment method | No automatic assignment/self-pick rule | Manual create plus dedicated elevated assignment/reassignment | Approved assignment rule and tests |
| BIZ-002 | BLOCKED_DECISION | Final Lead statuses/transitions | No status-transition action or enum claim | Lead storage, scope, assignment, reports not needing status | Approved codes and transition matrix |
| BIZ-003 | BLOCKED_DECISION | Final Interaction outcomes/directions and qualifying calls | No answered/call KPI | Manual free text entry and sale/customer metrics | Approved code sets and metric grouping |
| BIZ-004 | BLOCKED_DECISION | Generic customer KPI, conversion denominator, reassignment history semantics | Those metrics stay absent | Exact created-customer and confirmed-sale metrics | Approved formulas with date/ownership rules |
| BIZ-005 | BLOCKED_DECISION | Team model and manager team-admin scope | Sales Manager cannot administer users | Company IT/Platform Admin user management | Approved Team schema and boundaries |
| BIZ-006 | BLOCKED_DECISION | Sale correction fields and accounting meaning | Correction stays rejected; cancellation works | Sale creation/cancellation/audit | Approved correction transition and audit fields |
| BIZ-007 | BLOCKED_DECISION | XLSX final columns/style and Jalali display | No claimed final Persian presentation | Machine-readable dates and exact metric workbook foundation | Approved columns/display rules |
| BIZ-008 | BLOCKED_DECISION | Optional after-sales scope | No support entity/API | Core CRM work | Explicit inclusion and workflow/status rules |
| BIZ-009 | BLOCKED_DECISION | Backup destination and retention | Cannot claim live backup policy | Fail-closed scripts/config/runbook with placeholders | Owner-approved path, access, daily/weekly retention |
| BIZ-010 | BLOCKED_DECISION | Concurrent-user/capacity target | No final sizing/load claim | Query review and documented local smoke | Approved target and production-shaped load result |

## External environment

| ID | State | Missing input/tool | Impact | Close evidence |
|---|---|---|---|---|
| EXT-001 | BLOCKED_EXTERNAL | Native PostgreSQL `initdb` and `pg_ctl` or approved binary path | Cannot run isolated live-engine migration/constraint proof | Successful `scripts/test-postgres.ps1` evidence |
| EXT-002 | BLOCKED_EXTERNAL | Docker runtime | Cannot build/boot Compose stack | Build/up/health/static/API logs |
| EXT-003 | BLOCKED_EXTERNAL | Nginx runtime | Cannot execute proxy config/error/rate/static smoke | Config test and HTTP evidence through edge |
| EXT-004 | BLOCKED_EXTERNAL | Production server, hostname, certificate, and trusted TLS edge path | Cannot prove HTTPS, HSTS, certificate, live capacity | Approved deploy and TLS smoke/scanner evidence |
| EXT-005 | BLOCKED_EXTERNAL | Disposable PostgreSQL runtime after backup tools exist | Cannot prove real backup/restore | Backup plus restore into exact disposable database and data check |

## Missing historical evidence

- The older named backend prompt and frontend context files are absent under canonical or obvious suffixed root names. Current `BACKEND_SPEC.md` and durable goal cover independent work. If those files arrive later, reconcile conflicts without overwriting current evidence.
