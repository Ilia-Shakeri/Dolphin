# ForooshBin — repository rules

Concise, stable rules only. This file replaces the former long `AGENTS.md` (deleted as intentional prior work, not restored). It does not gate what may be inspected — read any first-party code relevant to the task.

## Authority order

1. Direct, explicit product-owner decisions stated in the current conversation.
2. Actual current code and executed repository evidence (tests you ran, greps you did) — not remembered prose.
3. `BACKEND_SPEC.md` as the normative business/backend contract.
4. `KARIZ_PROJECT_HANDOFF.md` as the only live status/evidence register, and `KARIZ_CLIENT1_CODEX_ROADMAP.md` as the phased plan.
5. `docs/backend/*.md` (entity/relationship/API contracts) and `docs/ops/*.md` (runbooks).
6. Older Git history/commit prose.
7. Vendor/demo HTML under `assets/`, `src/`, `dashboards/`, `pages/`, `apps/`, `layouts/`, `toolbars/`, `widgets/`, `utilities/`, `account/`, `authentication/`, `index.html`, `landing.html` — visual reference only, **never** a source of business rules, permissions, statuses, or workflows.

**Current code overrides stale prose.** If a document and the actual code disagree, trust the code, then correct the document — do not silently rewrite code behavior as though a document's claim were already true.

## Product architecture

- One shared codebase for multiple customer deployments. No permanent customer-specific fork or branch.
- Each customer deployment uses a separate database, secrets, and runtime identity — never `if client_name == ...` scattered through code.
- Feature availability, role permission, and object/data scope are three separate controls. Disabling a feature must never delete historical data.
- The maintained first-party UI is `common/templates/common/**` + `common/static/common/forooshbin-app.js` + `common/static/common/forooshbin.css`, routed through `common/ui_urls.py`/`common/ui_views.py`. This is the only served application UI.
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

- Active first-party product branding is `ForooshBin` / `فروش‌بین` only. No customer name hardcoded into shared source, fixtures, tests, or default config.
- Do not blindly rename stable vendor runtime identifiers (`KTMenu`, `KTDrawer`, `KTUtil`, `data-kt-*`) or delete required third-party `LICENSE`/`NOTICE` attribution.

## Working style

- During implementation, run the narrowest relevant checks/tests first.
- Do not run repository-wide, PostgreSQL, or browser-wide gates after every small change.
- Run full repository gates only at coherent integration checkpoints, feature freeze, or when a change affects database/security/concurrency infrastructure.
- Prefer delivery-focused fixes over speculative cleanup or perfection loops.
- Keep phases small and coherent. Update `KARIZ_PROJECT_HANDOFF.md` after a coherent phase completes.
- Do not invent business, financial, tax, legal, or integration semantics.
- Stop only when a real business decision, credential, irreversible external action, or unavailable infrastructure genuinely blocks safe progress.
