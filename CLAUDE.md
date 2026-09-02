# Dolphin — repository rules

Concise, stable rules only. This file replaces the former long `AGENTS.md` (deleted as intentional prior work, not restored). It does not gate what may be inspected — read any first-party code relevant to the task.

## Authority order

1. Direct, explicit product-owner decisions stated in the current conversation.
2. Actual current code and executed repository evidence (tests you ran, greps you did) — not remembered prose.
3. `BACKEND_SPEC.md` as the normative business/backend contract.
4. `DOLPHIN_PROJECT_HANDOFF.md` as the only live status/evidence register, and `DOLPHIN_CLIENT1_CODEX_ROADMAP.md` as the phased plan.
5. `docs/backend/*.md` (entity/relationship/API contracts) and `docs/ops/*.md` (runbooks).
6. Older Git history/commit prose.
7. Vendor/demo HTML under `assets/`, `src/`, `dashboards/`, `pages/`, `apps/`, `layouts/`, `toolbars/`, `widgets/`, `utilities/`, `account/`, `authentication/`, `index.html`, `landing.html` — visual reference only, **never** a source of business rules, permissions, statuses, or workflows.

**Current code overrides stale prose.** If a document and the actual code disagree, trust the code, then correct the document — do not silently rewrite code behavior as though a document's claim were already true.

## Product architecture

- One shared codebase for multiple customer deployments. No permanent customer-specific fork or branch.
- Each customer deployment uses a separate database, secrets, and runtime identity — never `if client_name == ...` scattered through code.
- Feature availability, role permission, and object/data scope are three separate controls. Disabling a feature must never delete historical data.
- The maintained first-party UI is `common/templates/common/**` + `common/static/common/dolphin-app.js` + `common/static/common/dolphin.css`, routed through `common/ui_urls.py`/`common/ui_views.py`. This is the only served application UI.
- Backend enforces feature, role, and object-scope checks (selectors/services/permissions). A hidden or disabled frontend control is never authorization.

## Git safety

- Preserve all existing user work. Never assume an unfamiliar file, branch, or uncommitted change is safe to discard.
- No destructive Git commands (`reset --hard`, `clean -f`, `checkout --` over changes, force-push, history rewrite) unless explicitly requested for that exact action.
- No automatic `git add`, `git commit`, or `git push` unless the current task explicitly asks for a commit. Leave a reviewable diff in the working tree by default.
- Run `git status --short` before anything that could discard uncommitted work.

## Secrets and evidence

- Never print secrets, tokens, passwords, connection strings, private keys, or `.env` values — not even to confirm they exist. Report file paths and variable names only.
- Never fabricate test results, command output, or coverage numbers. If a check wasn't run, say so; if a tool is unavailable (e.g. no Docker/PostgreSQL on this host), record that as the exact blocker, not as a passed or failed test.
- Distinguish `CURRENT CODE BEHAVIOR` from `CLIENT-1 TARGET BEHAVIOR` explicitly when they differ; label the gap rather than merging them into one claim.

## Branding

- Active first-party product branding is `Dolphin` / `دلفین` only (rebranded from `ForooshBin` / `فروش‌بین`, itself formerly internally codenamed `Kariz`). No customer name hardcoded into shared source, fixtures, tests, or default config.
- Do not blindly rename stable vendor runtime identifiers (`KTMenu`, `KTDrawer`, `KTUtil`, `data-kt-*`) or delete required third-party `LICENSE`/`NOTICE` attribution.
- As of 2026-09-01 the rename is complete everywhere, by explicit product-owner instruction, with **one deliberate, permanent exception** — `forooshbin`/`frooshbin`/`Kariz` no longer appear anywhere else in the codebase, including the previously-exempted internal identifiers — PostgreSQL database/role/user names and the ephemeral-database safety patterns in `config/postgres_*_guard.py` (each guard's already-deployed-role recognition now checks the new `Dolphin managed … role v1` comment first, with `FrooshBin managed … role v1` and `Kariz managed … role v1` kept as accepted legacy variants so an already-deployed role or backup root needs no manual fix-up — see `scripts/bootstrap-postgres.sh`, `scripts/backup-postgres.{sh,ps1}`, `scripts/verify-postgres-restore.{sh,ps1}`), the `DolphinXxxView` server-side view class names, the `dolphin.css`/`dolphin-app.js` static filenames and the `DOLPHIN_VERSION` settings constant, the `dolphin.*` logger names, and the internal engineering docs, renamed to match (`DOLPHIN_PROJECT_HANDOFF.md`, `DOLPHIN_CLIENT1_CODEX_ROADMAP.md`, `DOLPHIN_FEATURE_MAP_AND_ROADMAP.md`). `BACKEND_SPEC.md` body prose was updated in place; historical `CHANGELOG.md` entries were deliberately left as originally written — they are a record of what shipped under its name at the time, not live documentation, and rewriting them would misstate the history of the rename itself.
- **The exception**: the `KARIZ_*`-prefixed deployment environment variable names (`KARIZ_COMPOSE_PROJECT_NAME`, `KARIZ_APP_IMAGE`, `KARIZ_PUBLIC_HOST`, `KARIZ_DEPLOYMENT_MANIFEST_PATH`, `KARIZ_SELLER_*`, and the rest listed in `.env.example`) were deliberately **not** renamed to `DOLPHIN_*` — see `.env.example`'s own comment above them and `README.md`'s footnote. `compose.yml`, `nginx/default.conf`, `config/production_env.py`, `config/settings.py`, and the already-running Nerkhbaan staging deployment's own `.env` all read these exact names; renaming them would silently break that deployment's next `docker compose up` (every required setting reading as unset) for no functional gain, since nothing customer-visible reads an env var name. This is a live decision, not an oversight — do not rename these on the strength of the naming convention alone, and do not treat any older note (including a prior draft of this file, or `DOLPHIN_PROJECT_HANDOFF.md` phrasing that assumed the rename would happen) that claims these were or should be renamed as current; this paragraph is the correction.

## Working style

- During implementation, run the narrowest relevant checks/tests first.
- Do not run repository-wide, PostgreSQL, or browser-wide gates after every small change.
- Run full repository gates only at coherent integration checkpoints, feature freeze, or when a change affects database/security/concurrency infrastructure.
- Prefer delivery-focused fixes over speculative cleanup or perfection loops.
- Keep phases small and coherent. Update `DOLPHIN_PROJECT_HANDOFF.md` after a coherent phase completes.
- Do not invent business, financial, tax, legal, or integration semantics.
- Stop only when a real business decision, credential, irreversible external action, or unavailable infrastructure genuinely blocks safe progress.
