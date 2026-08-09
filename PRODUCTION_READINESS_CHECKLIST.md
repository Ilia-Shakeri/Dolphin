# Production readiness checklist

Status: `PASS`, `PARTIAL`, `PENDING`, `BLOCKED_EXTERNAL`, or `BLOCKED_DECISION`. A status needs direct evidence.

## Application and schema

| Gate | Status | Evidence / next proof |
|---|---|---|
| Test-settings system check | PARTIAL | Prior clean claim; rerun after source reconciliation |
| Production deploy check | PARTIAL | Prior clean safe-environment check; rerun at phase gate |
| Migration drift | PARTIAL | Prior no-drift claim; rerun after next migration |
| Zero migrations on PostgreSQL | BLOCKED_EXTERNAL | Native tools absent; run `scripts/test-postgres.ps1` |
| Upgrade migrations on PostgreSQL | BLOCKED_EXTERNAL | Need disposable PostgreSQL upgrade fixture/path |
| Critical DB constraints | PARTIAL | Role, assignment, money, Sale guards exist; global active phone rule needs migration |
| Database readiness | PASS | Public readiness executes `SELECT 1`; fast test exists |
| OpenAPI validation | PARTIAL | Prior clean claim; rerun after API/report changes |

## Security

| Gate | Status | Evidence / next proof |
|---|---|---|
| Production DEBUG off | PASS | `config/production_settings.py` plus test |
| Secrets from environment | PASS | Production secret guard; `.env.example` has placeholders |
| Ignore secret/key/database artifacts | PASS | Expanded `.gitignore`; staged-path scan still due before commit |
| Allowed hosts/origins explicit | PASS | Environment-backed settings |
| Secure cookies and headers | PARTIAL | Secure cookies forced; real HTTPS/HSTS proof external |
| CSRF/session behavior | PARTIAL | Existing tests; rerun full suite |
| Inactive-user denial | PARTIAL | Existing tests; endpoint matrix recheck due |
| Role/object isolation | PARTIAL | Broad tests exist; Company IT matrix changed under current spec |
| Privilege fields blocked | PARTIAL | Existing account tests; rerun after reconciliation |
| Request IDs and audit binding | PASS | Middleware/audit tests and edge config tests |
| Forwarded-header trust | PASS | One proxy in production; Nginx overwrites chain; CIDR-gated audit IP |
| Login throttling | PASS | Application and edge limits with tests/config proof |
| Audit secret scrubbing | PASS | Safe key/value allowlist and no-leak tests |
| Dependency/source scans | PARTIAL | Package consistency and high-confidence secret scan; security advisory scan pending |

## API and behavior

| Gate | Status | Evidence / next proof |
|---|---|---|
| Versioned API and pagination | PASS | `/api/v1/`, page-number default |
| Strict unknown/server fields | PASS | Shared mixin and tests |
| Transactional reassignment/history/audit | PASS | Locked service and rollback tests |
| Product/Sale transition security | PARTIAL | Agent blocks proven; Company IT rights need spec reconciliation |
| Stable machine error codes | PENDING | Current field errors lack complete stable code contract |
| Reports exact formulas | PENDING | Phase 5 |
| Report role scope and filters | PENDING | Phase 5 |
| XLSX parity and workbook validity | PENDING | Phase 5 |

## Runtime and operations

| Gate | Status | Evidence / next proof |
|---|---|---|
| Non-root production server image | PASS | Dockerfile uses non-root Gunicorn |
| Compose parses | PARTIAL | Prior host YAML parse; Docker config proof unavailable |
| One-shot migration/static job | PASS | Compose topology review |
| Stack boots and health passes | BLOCKED_EXTERNAL | Docker absent |
| Nginx routing/static/errors | BLOCKED_EXTERNAL | Nginx binary/runtime absent |
| Restart policies | PASS | Database, web, and edge policies present |
| Log rotation/bounds | PENDING | Add Compose/proxy/application bounds |
| Automated backup | PENDING | Phase 9 repo script/config |
| Disposable restore proof | BLOCKED_EXTERNAL | Repo tool first, then PostgreSQL runtime |
| Deployment/rollback/runbooks | PENDING | Phase 9/11 |
| TLS proof | BLOCKED_EXTERNAL | Need hostname and certificate path |

## Product quality and release

| Gate | Status | Evidence / next proof |
|---|---|---|
| Full tests pass | PARTIAL | Prior 61-pass claim; fresh gate in progress |
| Critical path tests pass alone | PARTIAL | Existing targeted tests; report/UI paths missing |
| No schema drift | PARTIAL | Fresh proof due after phone/report work |
| No forbidden tracked/shipped artifact | PARTIAL | Initial targeted scan clean; full reviewed staged/deployment manifests pending |
| Active UI is Persian/RTL only | PENDING | Phase 6 active-path proof |
| Active UI uses Kariz brand | PENDING | Phase 7 active-path proof |
| No open repository P0/P1 | PENDING | Final security/reliability audit |
| Known limitations explicit | PARTIAL | `ASSUMPTIONS.md` and `BLOCKERS.md` created; keep live |
| Production candidate evidence | PENDING | Phase 11 |
| Full production proof | BLOCKED_EXTERNAL | Phase 12 |

Current allowed claim: backend work in progress. Do not claim production candidate or production ready yet.
