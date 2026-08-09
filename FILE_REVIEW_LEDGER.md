# File review ledger

Classification: `ACTIVE`, `DOC`, `DEPLOY`, `SOURCE`, `DEMO`, `GENERATED`, `DEAD`, `UNCERTAIN`, or `PENDING`.

| Path | Owner | Purpose / entry | Dependencies and side effects | Security / tests | Language / brand | Class | Follow-up |
|---|---|---|---|---|---|---|---|
| `AGENTS.md` | root policy | Workspace scope and work rules | Governs all work | Safety rules | Kariz policy added | SOURCE | Keep continuous rule current |
| `BACKEND_SPEC.md` | product/backend | Provisional authority | Drives schema, access, reports | Must reconcile code/tests | Persian-only/Kariz required | SOURCE | Track unresolved decisions |
| durable goal file | root policy | Completion gates and phases | Drives roadmap | No runtime side effect | Defines language/brand | SOURCE | Keep tracked |
| continuous patch file | root policy | Merge source for work loop | No runtime side effect | Safe deletion policy | Defines language/brand | SOURCE | Keep as evidence |
| `.gitignore` | repository | Prevent local/secret/generated tracking | Git only | Secret/artifact safety | none | SOURCE | Recheck staged paths before commit |
| `.dockerignore` | deployment | Backend-only image context | Excludes static archive | Reduces leak/build size | Means archive not active in image | DEPLOY | Review active UI strategy |
| `requirements.txt` | backend | Runtime dependency ranges | Django stack/PostgreSQL/Gunicorn | Dependency scan due | none | ACTIVE | Consider reproducible lock/hash path later |
| `docs/backend/DISCOVERY.md` | docs | Current source/runtime/migration facts | Roadmap inputs | Records proof limits | Notes inactive archive | DOC | Update each topology change |
| `docs/backend/ENTITY_CATALOG.md` | docs | Entity definitions | Models/migrations | Server fields/deletion | none | DOC | Reconcile global phone rule |
| `docs/backend/RELATIONSHIPS.md` | docs | Relation/visibility map | Models/selectors | Object scope | none | DOC | Reconcile current spec |
| `docs/backend/ERD.mmd` | docs | Relationship diagram | Catalog | No runtime | none | DOC | Update only with schema relation change |
| `docs/backend/API_CONTRACT.md` | docs | Routes/auth/error contract | URLs/views/schema | Permission/error claims | Product title elsewhere | DOC | Add reports and stable codes |
| `docs/backend/POSTGRES_TESTING.md` | docs | Isolated DB proof path | guard settings/script | Protects live data | none | DOC | Run when native tools exist |
| `PROJECT_ROADMAP.md` | root docs | Live phase execution | All work | Proof, risk, rollback | Includes language/brand phases | DOC | Update every batch |
| `PRODUCTION_READINESS_CHECKLIST.md` | root docs | Release gates | All evidence | Prevents false readiness | Language/brand gates | DOC | Update at gates |
| `CODEBASE_MAP.md` | root docs | Durable architecture map | Ledger and code | Request/data trust flow | Active UI state | DOC | Expand after each review batch |
| `FILE_REVIEW_LEDGER.md` | root docs | Bounded file memory | All active first-party files | Tracks gaps/tests | Tracks language/brand | DOC | Add 10-25 files per batch |
| `WORKLOG.md` | root docs | Resume checkpoints | Roadmap | Exact evidence | none | DOC | Append meaningful batches |
| `BLOCKERS.md` | root docs | External/business blocks | Roadmap/checklist | Stops false claims | UI inputs tracked | DOC | Close only with evidence |
| `ASSUMPTIONS.md` | root docs | Safe working choices | Spec and implementation | No hidden business invention | Persian/Kariz baseline | DOC | Keep distinct from blockers |

## Pending review batches

1. `config`, `common`, `auditlog` request/runtime/security files and their tests.
2. `accounts` model/services/serializers/views/permissions/URLs/migrations/tests.
3. `sales` models/selectors/services/serializers/views/URLs/migrations/tests.
4. `reports` current shell, then Phase 5 implementation.
5. Dockerfile, Compose, Nginx, environment, scripts, and operations docs.
6. Exact active auth/customer/user-management/dashboard frontend allowlist only.
7. Active locale/brand reference manifests; do not review excluded vendor/media/minified trees.
