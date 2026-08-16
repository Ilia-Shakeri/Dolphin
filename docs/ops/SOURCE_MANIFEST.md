# Source manifest - final reference 2026-08-10

> This is an immutable historical manifest for the named reference. It is not live project status or a list of current paths. Current progress, blockers, evidence, and exact next action exist only in `KARIZ_PROJECT_HANDOFF.md`.

## Identity and boundary

- Base commit: `50a978abc206e43032ce96b36dc0433366198e60`.
- Base subject: `chore: establish durable production roadmap`.
- User-created final commit: `95dbc71ea3a3e773a620271f3d3fbe0e88646e8b` (`feat: Enhance security and API response handling`).
- Remote proof: local `HEAD` and `origin/main` both resolved to that full commit with a clean worktree before `C-REF` and `C-REPO`.
- Candidate form: one immutable 134-path base-to-final reference delta. No source overlay remains outside that reference.
- Repository root: curated ForooshBin workspace only.
- Deployment scope: first-party backend, active Django UI, production configuration, scripts, and operator documentation.
- Excluded scope: dependency/vendor/minified/media/font/binary/cache trees and the unserved static template archive.

The pushed commit is the exact repository candidate reference. This does not prove container, database, TLS, browser, backup, load, or scanner runtime behavior. Regenerate the manifest after any later source or reference change.

## Review method

```powershell
git rev-parse HEAD
git rev-parse origin/main
git diff --name-status 50a978abc206e43032ce96b36dc0433366198e60 95dbc71ea3a3e773a620271f3d3fbe0e88646e8b
git status --porcelain=v1 --untracked-files=all
git diff --check
git diff --stat
```

The final path scan also rejects secret environment files, credentials, keys, databases, archives, binary/media/font artifacts, dependency/vendor/build trees, and excluded active-archive paths. Secret-content checks report file names only and never copy matching values into evidence.

## Exact final reference path set

The 134 paths below exactly equal `git diff --name-status 50a978abc206e43032ce96b36dc0433366198e60 95dbc71ea3a3e773a620271f3d3fbe0e88646e8b`. The original pre-commit capture state is retained as provenance: ` M` maps to `M` in the reference diff and `??` maps to `A`. `SHIP` means the path belongs in the reviewed candidate source package.

| Original capture state | Path | Class | Disposition | Reason |
|---|---|---|---|---|
| ` M` | `.dockerignore` | image context policy | SHIP | Reviewed first-party modified path |
| ` M` | `.env.example` | environment template | SHIP | Reviewed first-party modified path |
| `??` | `.gitattributes` | repository policy | SHIP | Reviewed first-party added path |
| ` M` | `.gitignore` | repository policy | SHIP | Reviewed first-party modified path |
| `??` | `accounts/access.py` | identity source/test/schema | SHIP | Reviewed first-party added path |
| `??` | `accounts/management/__init__.py` | identity source/test/schema | SHIP | Reviewed first-party added path |
| `??` | `accounts/management/commands/__init__.py` | identity source/test/schema | SHIP | Reviewed first-party added path |
| `??` | `accounts/management/commands/bootstrap_platform_admin.py` | identity source/test/schema | SHIP | Reviewed first-party added path |
| `??` | `accounts/management/commands/seed_synthetic_uat.py` | identity source/test/schema | SHIP | Reviewed first-party added path |
| ` M` | `accounts/permissions.py` | identity source/test/schema | SHIP | Reviewed first-party modified path |
| `??` | `accounts/platform_admin_guard.py` | identity source/test/schema | SHIP | Reviewed first-party added path |
| ` M` | `accounts/serializers.py` | identity source/test/schema | SHIP | Reviewed first-party modified path |
| ` M` | `accounts/services.py` | identity source/test/schema | SHIP | Reviewed first-party modified path |
| ` M` | `accounts/tests/test_accounts.py` | identity source/test/schema | SHIP | Reviewed first-party modified path |
| `??` | `accounts/tests/test_bootstrap_platform_admin.py` | identity source/test/schema | SHIP | Reviewed first-party added path |
| `??` | `accounts/tests/test_seed_synthetic_uat.py` | identity source/test/schema | SHIP | Reviewed first-party added path |
| ` M` | `accounts/views.py` | identity source/test/schema | SHIP | Reviewed first-party modified path |
| ` M` | `ASSUMPTIONS.md` | durable project evidence | SHIP | Reviewed first-party modified path |
| `??` | `auditlog/migrations/0002_activitylog_role_snapshots.py` | audit source/test/schema | SHIP | Reviewed first-party added path |
| ` M` | `auditlog/models.py` | audit source/test/schema | SHIP | Reviewed first-party modified path |
| `??` | `auditlog/permissions.py` | audit source/test/schema | SHIP | Reviewed first-party added path |
| `??` | `auditlog/selectors.py` | audit source/test/schema | SHIP | Reviewed first-party added path |
| `??` | `auditlog/serializers.py` | audit source/test/schema | SHIP | Reviewed first-party added path |
| ` M` | `auditlog/services.py` | audit source/test/schema | SHIP | Reviewed first-party modified path |
| `??` | `auditlog/tests/test_api.py` | audit source/test/schema | SHIP | Reviewed first-party added path |
| ` M` | `auditlog/tests/test_services.py` | audit source/test/schema | SHIP | Reviewed first-party modified path |
| `??` | `auditlog/urls.py` | audit source/test/schema | SHIP | Reviewed first-party added path |
| `??` | `auditlog/views.py` | audit source/test/schema | SHIP | Reviewed first-party added path |
| ` M` | `BLOCKERS.md` | durable project evidence | SHIP | Reviewed first-party modified path |
| ` M` | `CODEBASE_MAP.md` | durable project evidence | SHIP | Reviewed first-party modified path |
| `??` | `common/admin.py` | shared runtime source | SHIP | Reviewed first-party added path |
| `??` | `common/error_views.py` | shared runtime source | SHIP | Reviewed first-party added path |
| ` M` | `common/exceptions.py` | shared runtime source | SHIP | Reviewed first-party modified path |
| ` M` | `common/middleware.py` | shared runtime source | SHIP | Reviewed first-party modified path |
| `??` | `common/openapi.py` | shared runtime source | SHIP | Reviewed first-party added path |
| `??` | `common/parsers.py` | shared runtime source | SHIP | Reviewed first-party added path |
| ` M` | `common/permissions.py` | shared runtime source | SHIP | Reviewed first-party modified path |
| ` M` | `common/phones.py` | shared runtime source | SHIP | Reviewed first-party modified path |
| `??` | `common/request_logging.py` | shared runtime source | SHIP | Reviewed first-party added path |
| ` M` | `common/serializers.py` | shared runtime source | SHIP | Reviewed first-party modified path |
| `??` | `common/static/common/kariz.css` | active UI asset | SHIP | Reviewed first-party added path |
| `??` | `common/templates/common/home.html` | active UI template | SHIP | Reviewed first-party added path |
| `??` | `common/tests/test_backup_scripts.py` | shared test proof | SHIP | Reviewed first-party added path |
| `??` | `common/tests/test_database_privileges.py` | shared test proof | SHIP | Reviewed first-party added path |
| `??` | `common/tests/test_dependency_contract.py` | shared test proof | SHIP | Reviewed first-party added path |
| `??` | `common/tests/test_load_readiness.py` | shared test proof | SHIP | Reviewed first-party added path |
| `??` | `common/tests/test_postgres_concurrency.py` | database test proof | SHIP | Reviewed first-party added path |
| `??` | `common/tests/test_postgres_harness.py` | database test proof | SHIP | Reviewed first-party added path |
| ` M` | `common/tests/test_postgres_test_guard.py` | database test proof | SHIP | Reviewed first-party modified path |
| ` M` | `common/tests/test_production_settings.py` | shared test proof | SHIP | Reviewed first-party modified path |
| `??` | `common/tests/test_query_growth.py` | shared test proof | SHIP | Reviewed first-party added path |
| `??` | `common/tests/test_release_images.py` | shared test proof | SHIP | Reviewed first-party added path |
| `??` | `common/tests/test_request_limits.py` | shared test proof | SHIP | Reviewed first-party added path |
| `??` | `common/tests/test_request_logging.py` | shared test proof | SHIP | Reviewed first-party added path |
| `??` | `common/tests/test_security_scan_runbook.py` | security test proof | SHIP | Reviewed first-party added path |
| `??` | `common/tests/test_sensitive_throttles.py` | security test proof | SHIP | Reviewed first-party added path |
| ` M` | `common/tests/test_system_api.py` | shared test proof | SHIP | Reviewed first-party modified path |
| `??` | `common/tests/test_ui.py` | shared test proof | SHIP | Reviewed first-party added path |
| `??` | `common/throttles.py` | shared runtime source | SHIP | Reviewed first-party added path |
| `??` | `common/ui_urls.py` | shared runtime source | SHIP | Reviewed first-party added path |
| `??` | `common/ui_views.py` | shared runtime source | SHIP | Reviewed first-party added path |
| ` M` | `common/viewsets.py` | shared runtime source | SHIP | Reviewed first-party modified path |
| `??` | `compose.restore-verify.yml` | recovery stack config | SHIP | Reviewed first-party added path |
| `??` | `compose.write-stop.yml` | stack config | SHIP | Reviewed first-party added path |
| ` M` | `compose.yml` | stack config | SHIP | Reviewed first-party modified path |
| `??` | `config/postgres_contract_guard.py` | database test config | SHIP | Reviewed first-party added path |
| `??` | `config/postgres_contract_settings.py` | database test config | SHIP | Reviewed first-party added path |
| `??` | `config/production_env.py` | application config | SHIP | Reviewed first-party added path |
| ` M` | `config/production_settings.py` | application config | SHIP | Reviewed first-party modified path |
| ` M` | `config/settings.py` | application config | SHIP | Reviewed first-party modified path |
| ` M` | `config/test_settings.py` | application config | SHIP | Reviewed first-party modified path |
| ` M` | `config/urls.py` | application config | SHIP | Reviewed first-party modified path |
| ` M` | `Dockerfile` | image source | SHIP | Reviewed first-party modified path |
| ` M` | `docs/backend/API_CONTRACT.md` | backend contract | SHIP | Reviewed first-party modified path |
| ` M` | `docs/backend/DISCOVERY.md` | backend contract | SHIP | Reviewed first-party modified path |
| ` M` | `docs/backend/ENTITY_CATALOG.md` | backend contract | SHIP | Reviewed first-party modified path |
| ` M` | `docs/backend/RELATIONSHIPS.md` | backend contract | SHIP | Reviewed first-party modified path |
| `??` | `docs/codebase/BRANDING_CLEANUP.md` | codebase evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/codebase/LANGUAGE_CLEANUP.md` | codebase evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/ops/BACKUP_RESTORE.md` | operations/release evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/ops/DATABASE_ROLES.md` | operations/release evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/ops/DEPENDENCIES.md` | operations/release evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/ops/DEPLOYMENT_BOOTSTRAP.md` | operations/release evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/ops/DEPLOYMENT.md` | operations/release evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/ops/INCIDENT_RESPONSE.md` | operations/release evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/ops/LOAD_TEST.md` | operations/release evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/ops/RELEASE_CHECKLIST.md` | operations/release evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/ops/RELEASE_NOTES.md` | operations/release evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/ops/ROLLBACK.md` | operations/release evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/ops/SECURITY_SCANS.md` | operations/release evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/ops/SOURCE_MANIFEST.md` | operations/release evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/ops/TLS.md` | operations/release evidence | SHIP | Reviewed first-party added path |
| `??` | `docs/ops/UAT.md` | operations/release evidence | SHIP | Reviewed first-party added path |
| ` M` | `FILE_REVIEW_LEDGER.md` | durable project evidence | SHIP | Reviewed first-party modified path |
| ` M` | `nginx/default.conf` | edge config | SHIP | Reviewed first-party modified path |
| `??` | `nginx/write-stop-off.conf` | edge config | SHIP | Reviewed first-party added path |
| `??` | `nginx/write-stop-on.conf` | edge config | SHIP | Reviewed first-party added path |
| ` M` | `PRODUCTION_READINESS_CHECKLIST.md` | durable project evidence | SHIP | Reviewed first-party modified path |
| ` M` | `PROJECT_ROADMAP.md` | durable project evidence | SHIP | Reviewed first-party modified path |
| `??` | `reports/selectors.py` | report source/test | SHIP | Reviewed first-party added path |
| `??` | `reports/serializers.py` | report source/test | SHIP | Reviewed first-party added path |
| `??` | `reports/services.py` | report source/test | SHIP | Reviewed first-party added path |
| `??` | `reports/tests/__init__.py` | report source/test | SHIP | Reviewed first-party added path |
| `??` | `reports/tests/test_user_performance.py` | report source/test | SHIP | Reviewed first-party added path |
| `??` | `reports/urls.py` | report source/test | SHIP | Reviewed first-party added path |
| `??` | `reports/views.py` | report source/test | SHIP | Reviewed first-party added path |
| `??` | `reports/xlsx.py` | report source/test | SHIP | Reviewed first-party added path |
| `??` | `requirements-direct.txt` | dependency contract | SHIP | Reviewed first-party added path |
| ` M` | `requirements.txt` | dependency contract | SHIP | Reviewed first-party modified path |
| ` M` | `sales/exceptions.py` | sales runtime source | SHIP | Reviewed first-party modified path |
| `??` | `sales/migrations/0006_global_active_phone_identity.py` | sales schema | SHIP | Reviewed first-party added path |
| `??` | `sales/migrations/0007_product_price_positive.py` | sales schema | SHIP | Reviewed first-party added path |
| `??` | `sales/migrations/0008_customer_phone_normalized_shape.py` | sales schema | SHIP | Reviewed first-party added path |
| `??` | `sales/migrations/0009_bounded_free_text.py` | sales schema | SHIP | Reviewed first-party added path |
| `??` | `sales/migrations/0010_interaction_contract.py` | sales schema | SHIP | Reviewed first-party added path |
| ` M` | `sales/models.py` | sales runtime source | SHIP | Reviewed first-party modified path |
| ` M` | `sales/selectors.py` | sales runtime source | SHIP | Reviewed first-party modified path |
| ` M` | `sales/serializers.py` | sales runtime source | SHIP | Reviewed first-party modified path |
| ` M` | `sales/services.py` | sales runtime source | SHIP | Reviewed first-party modified path |
| `??` | `sales/tests/test_migration_preflights.py` | sales test proof | SHIP | Reviewed first-party added path |
| `??` | `sales/tests/test_scope_attacks.py` | sales test proof | SHIP | Reviewed first-party added path |
| ` M` | `sales/tests/test_workflows.py` | sales test proof | SHIP | Reviewed first-party modified path |
| ` M` | `sales/views.py` | sales runtime source | SHIP | Reviewed first-party modified path |
| `??` | `scripts/backup-postgres.ps1` | operator script | SHIP | Reviewed first-party added path |
| `??` | `scripts/backup-postgres.sh` | operator script | SHIP | Reviewed first-party added path |
| `??` | `scripts/bootstrap-postgres.sh` | operator script | SHIP | Reviewed first-party added path |
| `??` | `scripts/load_readiness.py` | operator script | SHIP | Reviewed first-party added path |
| ` M` | `scripts/test-postgres.ps1` | operator script | SHIP | Reviewed first-party modified path |
| `??` | `scripts/validate_release_images.py` | operator script | SHIP | Reviewed first-party added path |
| `??` | `scripts/verify-postgres-privileges.sql` | database contract | SHIP | Reviewed first-party added path |
| `??` | `scripts/verify-postgres-restore.ps1` | operator script | SHIP | Reviewed first-party added path |
| `??` | `scripts/verify-postgres-restore.sh` | operator script | SHIP | Reviewed first-party added path |
| `??` | `scripts/verify-postgres-schema.sql` | recovery contract | SHIP | Reviewed first-party added path |
| ` M` | `WORKLOG.md` | durable project evidence | SHIP | Reviewed first-party modified path |

## Review result

- Final reference path classification: 134 exact paths; 47 modified, 87 added, 0 deleted, 0 renamed; all 134 are first-party `SHIP` paths.
- Reference proof: `C-REF` passed for `95dbc71ea3a3e773a620271f3d3fbe0e88646e8b`; `HEAD` and `origin/main` matched and the pre-proof worktree was clean.
- Repository proof: `C-REPO` passed from that exact reference; 232 tests passed with six PostgreSQL-only skips, plus check, no-drift, schema, static, and package gates.
- Forbidden path count: 0.
- High-confidence secret pattern count: 0. The scan checked private-key headers, common cloud/source tokens, and credential-bearing PostgreSQL URLs; it reported file names only.
- Whitespace/diff check: passed after manifest insertion; line-ending notices are Git conversion warnings, not whitespace errors.
- File ledger: 179 scoped active first-party files have 179 exact ledger rows and exact Phase 1 links.
- Temporary wheel/cache candidate path count: 0; the reviewed temporary wheelhouse is absent and excluded from this manifest.
- Immutable repository reference: present and reviewed. SRC-002 is closed. Runtime artifact storage and rollback ownership remain OPS-001.
