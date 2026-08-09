# AGENTS.md patch — Continuous Kariz execution

Merge this section into the root `AGENTS.md`. It explicitly replaces any older instruction that says to stop after each slice, end after a phase report, or wait for the user to type `continue`.

## Continuous roadmap execution

When the active user task is a long-running Kariz completion/production-readiness goal:

- Create and maintain `PROJECT_ROADMAP.md` in the repository root.
- A task, slice, milestone, test report, or phase report is a checkpoint, not a stopping point.
- After a successful checkpoint, update `WORKLOG.md` and immediately begin the highest-priority unblocked roadmap item.
- Never ask the user to type `continue` for normal workspace edits, tests, documentation, safe refactors, or reviewed file deletions.
- If one item is blocked, record it in `BLOCKERS.md` and continue independent unblocked work.
- Pause only for a real credential/secret, an irreversible external action, a data-semantic decision with no safe isolated fallback, a required sandbox approval, or when no independent unblocked work remains.
- If the session is forced to stop, persist an exact resume point in `WORKLOG.md`: phase, task, files, commands, evidence, and next action.

## Durable codebase understanding

Maintain:

```text
CODEBASE_MAP.md
FILE_REVIEW_LEDGER.md
WORKLOG.md
ASSUMPTIONS.md
BLOCKERS.md
PRODUCTION_READINESS_CHECKLIST.md
```

Review active first-party code subsystem by subsystem in bounded batches. Record each file’s purpose, dependencies, entry points, domain impact, security concerns, tests, and branding/language status. Do not recursively consume dependency, vendor, minified, generated, build, media, font, binary, or cache trees.

## Safe deletion policy

Before deleting locale, demo, duplicated, or branding-related files:

1. Ensure a safe Git/checkpoint baseline exists.
2. Produce an exact candidate manifest.
3. Prove imports/templates/static references do not require the files.
4. Delete only a small reviewed group.
5. Run targeted checks plus relevant template/static/browser smoke tests.
6. Restore the group if behavior regresses.

Never run broad `rm -rf`, `git clean`, or `git reset --hard`.

## Persian-only active application

The active Kariz user interface is Persian-only unless `BACKEND_SPEC.md` explicitly overrides it. Remove unused non-Persian locale resources and language-switch UI/behavior only after reference analysis. Preserve Persian/RTL resources, programming-language source, API/database identifiers, framework dependency locales, and required third-party notices.

## Kariz branding

All user-visible and project-owned product branding must use `Kariz CRM` / `کاریز`. Remove active vendor purchase/preview/demo links and vendor-visible branding. Do not blindly rename stable theme runtime identifiers such as `KTMenu`, `KTDrawer`, `KTUtil`, or `data-kt-*`, and do not erase legally required third-party notices.

## Verification and continuation

After each batch, run the narrowest relevant checks, inspect the diff, update roadmap evidence, and continue. Run full backend/schema/production-like checks at phase gates. Never claim production readiness without runtime and operational evidence; use “production candidate; external verification pending” when only external infrastructure proof remains.
