Dolphin — Repository Constitution

This file defines stable, project-specific engineering rules for Dolphin.
Global assistant instructions still apply. This file exists to encode Dolphin’s architecture,
product constraints, visual source of truth, modular deployment model, documentation discipline,
and repository safety rules.

Keep this document stable. Do not turn it into a task log, changelog, or temporary scratchpad.

────────

1. Product Mission

Dolphin / دلفین is a production-grade, long-lived, modular CRM/business platform intended to be
licensed and deployed for multiple independent customer companies.

Treat Dolphin as a commercial product, not a demo, prototype, template customization, or one-off
client project.

Every implementation decision should preserve:

• maintainability over years,
• modular feature composition,
• customer-independent shared source code,
• security and data integrity,
• predictable deployment,
• consistent UI/UX,
• Persian/RTL quality,
• extensibility without speculative over-engineering.

Do not optimize for a single screenshot, single customer, or single immediate task at the expense
of the product architecture.

────────

2. Authority and Source of Truth

When sources disagree, use this order:

1. Direct, explicit product-owner decisions in the current conversation.
2. Actual current code and executed repository/runtime evidence.
3. BACKEND_SPEC.md as the normative backend/business contract.
4. DOLPHIN_PROJECT_HANDOFF.md as the live status/evidence register.
5. DOLPHIN_CLIENT1_CODEX_ROADMAP.md as the phased delivery plan.
6. docs/backend/*.md for backend/entity/API contracts.
7. docs/ops/*.md for operational/runbook contracts.
8. Current maintained tests where they accurately represent intended behavior.
9. Older Git history and historical prose.
10. Vendor/demo source as visual/technical reference only.

Current code overrides stale prose.

If code and documentation disagree:

• determine actual current behavior from code/runtime evidence,
• preserve working behavior unless the task explicitly changes it,
• update stale documentation when the correct behavior is established,
• never silently rewrite code merely to make it match stale documentation.

Never derive business rules, permissions, statuses, accounting semantics, workflows, or customer
behavior from vendor/demo UI.

────────

3. Repository Orientation

Before non-trivial work, locate and inspect the relevant first-party implementation.

The maintained served Dolphin UI is:

• common/templates/common/**
• common/static/common/dolphin-app.js
• common/static/common/dolphin.css
• common/ui_urls.py
• common/ui_views.py

These are the maintained first-party application UI surfaces unless current repository evidence
shows otherwise.

The purchased Metronic/vendor source may exist under locations such as:

• assets/
• src/
• dashboards/
• pages/
• apps/
• layouts/
• toolbars/
• widgets/
• utilities/
• account/
• authentication/
• index.html
• landing.html

These vendor/demo sources are retained primarily as implementation and visual references.

Do not assume a file is relevant merely from its filename. Search, open, and inspect the actual
implementation before modifying behavior.

────────

4. Product Architecture

Dolphin uses one shared product codebase for multiple customer deployments.

Do not create permanent customer-specific forks, branches, or duplicated application trees.

Each customer deployment may have independent:

• database,
• secrets,
• runtime identity,
• enabled feature set,
• configuration,
• branding/configuration values where supported,
• users and roles,
• data scope.

Customer differences must be represented through supported configuration, feature controls,
permissions, deployment configuration, and data — not scattered source-code conditions such as:

```python
if client_name == "customer_x":
    ...
```

Do not hardcode customer names into shared business logic, templates, fixtures, tests, default
configuration, or reusable product code.

When customer-specific behavior is genuinely required, design a reusable configuration or extension
point appropriate to the product rather than creating a customer fork.

────────

5. Modular Product Model

Modularity is a core product requirement.

Features must be designed so different customer deployments can enable different product
capabilities without destabilizing the rest of Dolphin.

Examples include customers that may or may not license or enable:

• chat,
• analytics,
• dashboards,
• reports,
• CRM modules,
• workflow capabilities,
• integrations,
• accounting-related capabilities,
• future product modules.

A feature should not become an accidental hard dependency merely because it exists in the primary
development deployment.

5.1 Three Separate Controls

Always distinguish:

1. Feature availability — does this deployment have the feature?
2. Role permission — may this user/role perform this action?
3. Object/data scope — which records may this user access?

These are separate concerns.

Never treat:

• a hidden menu item as authorization,
• an unavailable feature as a role permission,
• a role permission as object-level access,
• frontend visibility as backend security.

Backend enforcement is authoritative.

5.2 Feature Disablement

Disabling a feature must not delete historical data.

A disabled feature should:

• disappear from served navigation/UI where appropriate,
• reject unauthorized/unavailable backend actions safely,
• preserve historical records,
• avoid breaking unrelated modules,
• remain safely re-enableable unless explicit product behavior says otherwise.

Do not implement feature disablement by destructive schema/data operations.

5.3 Module Boundaries

Prefer explicit module boundaries.

Avoid:

• hidden cross-module imports,
• circular dependencies,
• unrelated modules querying each other’s internals,
• duplicated permission logic,
• duplicated business rules,
• global assumptions that every module is enabled.

When modules interact, use the project’s established service/selectors/contracts rather than
reaching into implementation details.

Do not create a new abstraction merely to make something theoretically modular. Use the minimum
architecture required to preserve real module independence.

5.4 Admin/Deployment Console

The internal admin/deployment console is an engineering/operator surface, not ordinary customer UI.

Its purpose includes configuring a customer deployment, selecting supported capabilities, previewing
the resulting product configuration, and producing/deploying the appropriate customer setup where
the current architecture supports it.

Changes to this console must preserve the distinction between:

• product features,
• permissions,
• data scope,
• deployment configuration.

Never expose internal operator-only controls to customer users accidentally.

Every control shown in a served production UI must have real behavior. Do not ship fake toggles,
demo controls, placeholder actions, or controls that only alter appearance without enforcing the
corresponding backend behavior.

────────

6. Backend Architecture

Existing backend behavior is the functional truth unless the task explicitly changes it.

Keep business logic out of templates and presentation JavaScript.

Use the project’s established separation of concerns, including selectors/services/permissions where
present.

Prefer:

• selectors/query layers for reusable data retrieval,
• services/use-case layers for mutations and business operations,
• explicit permission enforcement,
• validated inputs at system boundaries,
• transactions where atomicity matters,
• database constraints where they represent real invariants.

Avoid duplicating business rules across views, templates, JavaScript, APIs, and services.

The frontend may improve usability by hiding unavailable actions, but backend authorization must
still independently enforce them.

────────

7. Data and Database Safety

Data integrity outranks convenience.

For database changes:

• inspect existing models, constraints, migrations, and data assumptions first,
• make schema changes through the project’s normal migration mechanism,
• preserve existing customer data,
• avoid destructive migrations unless explicitly required and reviewed,
• provide safe transition paths when changing stored semantics,
• consider existing deployed databases, not only fresh installations,
• do not invent financial/accounting/legal semantics.

Do not delete historical data because a module is disabled or a field becomes unused.

For potentially destructive data migrations, stop when a genuine product/business decision is
required rather than guessing.

Where practical, migrations should be operationally reversible or have a documented safe recovery
path. Do not fake reversibility when the underlying business transformation cannot truly be reversed.

────────

8. Query and Performance Discipline

Treat production-scale data as a real constraint.

Avoid obvious:

• N+1 queries,
• repeated equivalent queries,
• unbounded large result sets,
• loading entire tables for a small UI,
• unnecessary serialization,
• expensive work inside loops,
• duplicate network requests,
• large frontend payloads without reason.

Use existing pagination, filtering, prefetch/select-related patterns, caching, and indexing strategy
where appropriate.

Do not add caching merely because something might become slow. Measure or establish the need first.

Performance changes must preserve correctness and permission/data-scope enforcement.

────────

9. Security

Security boundaries are backend responsibilities.

Always preserve:

• authentication,
• authorization,
• role checks,
• object/data scope,
• feature availability enforcement,
• CSRF protections,
• input validation,
• output escaping,
• safe file handling,
• secret isolation.

Never trust hidden/disabled frontend controls as authorization.

Never log or expose:

• passwords,
• access tokens,
• refresh tokens,
• API keys,
• private keys,
• secret values,
• database credentials,
• connection strings,
• sensitive .env values.

When confirming configuration, report variable names and paths, not secret contents.

Do not weaken security controls to make a test, demo, or UI flow work.

────────

10. Dolphin Branding

The active first-party product brand is:

• Dolphin
• دلفین

Customer-facing and new first-party product text must use Dolphin branding.

Historical/internal names such as ForooshBin / فروش‌بین / FrooshBin / Kariz / کاریز are not active
product branding.

Do not introduce those names into new first-party source, UI, fixtures, tests, default configuration,
or live documentation.

10.1 Important Naming Exceptions

Do not blindly rename identifiers merely because their names are historical or vendor-derived.

Stable technical identifiers may be intentionally preserved for compatibility — but only for as long
as the product owner has not explicitly decided otherwise. A preserved identifier is a standing
default, not a permanent one.

Former exception, now closed (2026-09-05): KARIZ_* deployment environment variable names were a
deliberate compatibility exception from 2026-09-01 until the product owner explicitly requested a
coordinated deployment migration on 2026-09-05. Every environment variable name in this codebase is
now DOLPHIN_*; nothing reads a KARIZ_* name anymore. This is recorded here as a worked example of the
one condition under which such an exception may be lifted — an explicit, direct product-owner
decision, not a default first-party rename pass — not as a precedent for changing it back. An
already-deployed customer's own `.env` file may still use the old names; see the migration note in
`docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md` for what that requires before its next deploy.

Also preserve required vendor/runtime identifiers when changing them would break the purchased
template or third-party runtime, including examples such as:

• KTMenu
• KTDrawer
• KTUtil
• data-kt-*

Do not rename third-party library identifiers, CSS classes, JavaScript APIs, package names, license
references, or runtime hooks solely for branding.

10.2 Metronic Branding Rule

Metronic is the purchased visual/component source, not Dolphin’s customer-facing brand.

When adapting a Metronic component into first-party Dolphin UI:

• customer-visible labels must use Dolphin/product terminology,
• copied demo content must be replaced with real Dolphin behavior/content,
• do not expose “Metronic” as the product name,
• preserve vendor technical identifiers where required for functionality,
• preserve required third-party LICENSE/NOTICE attribution.

Never perform a blind repository-wide replacement of Metronic, Kariz, or other names.

Classify each occurrence first:

• customer-facing product branding → convert to Dolphin,
• stale first-party historical naming → migrate when safe,
• deliberate deployment compatibility identifier → preserve,
• vendor runtime identifier → preserve,
• required historical changelog record → preserve,
• third-party license/attribution → preserve.

This distinction is mandatory.

────────

11. Frontend Source of Truth

The purchased Metronic HTML template is the canonical visual and component source for Dolphin.

This is a hard frontend rule.

For normal frontend work, do not invent a parallel design system.

Dolphin should look and behave like a professionally adapted Metronic product, not like a generic
AI-generated dashboard.

Unless the product owner explicitly requests a different design, prefer Metronic’s existing:

• shell,
• page structure,
• grids,
• cards,
• typography hierarchy,
• spacing,
• tables,
• forms,
• dropdowns,
• menus,
• modals,
• drawers,
• tabs,
• badges,
• buttons,
• icons,
• toolbars,
• widgets,
• charts,
• responsive behavior,
• interaction patterns,
• RTL conventions,
• empty/loading patterns when available.

Custom design should be the exception, not the default.

────────

12. Mandatory Frontend Investigation Protocol

For every task that materially changes visible UI/UX, do not begin by inventing markup or CSS.

Use this sequence.

Step 1 — Inspect Dolphin

Find and inspect:

• the currently served template,
• related JavaScript,
• related CSS,
• route/view/API supplying the data,
• parent layout/container,
• existing reusable Dolphin components,
• existing responsive/RTL behavior.

Understand the actual defect or requirement before editing.

Step 2 — Search Metronic

Search the purchased Metronic source for the closest matching component or page.

Search by:

• component type,
• visible text from demo examples,
• relevant CSS classes,
• data-kt-* attributes,
• JS initialization names,
• chart library configuration,
• layout structure.

Do not stop at filenames or screenshots.

Open and inspect the actual Metronic:

• HTML,
• classes,
• wrapper structure,
• JavaScript,
• initialization,
• relevant CSS/SASS where needed,
• responsive behavior.

Step 3 — Adapt, Do Not Reinvent

Use this preference order:

1. Exact Metronic implementation.
2. Closest Metronic implementation adapted to Dolphin data.
3. Existing Dolphin component already derived from Metronic.
4. Minimal custom extension of a Metronic pattern.
5. New custom design only when no suitable pattern exists or the product owner explicitly requests it.

Do not create a new component merely because writing one from scratch is faster.

Step 4 — Preserve Real Behavior

Metronic demo source supplies visual/component patterns only.

Dolphin backend/API/service/model behavior supplies functional truth.

Never copy:

• fake demo data,
• demo permissions,
• demo workflows,
• demo statuses,
• placeholder actions,
• nonfunctional controls.

Every visible production control must perform a real supported action.

Step 5 — Verify Rendered Behavior

When browser/render tooling is available, visually inspect the actual rendered result.

Check at minimum where relevant:

• desktop,
• narrower viewport/mobile,
• Persian RTL,
• long Persian labels,
• empty state,
• loading state,
• populated state,
• validation/error state,
• hover/focus/open states,
• clipping/overflow,
• alignment,
• interaction behavior.

Passing backend/unit tests alone is not sufficient evidence that a frontend task is correct.

────────

13. RTL and Persian UI

Persian/RTL is a first-class product requirement, not a final translation pass.

Every new or changed component must work naturally in RTL where served in Persian.

Verify:

• direction,
• text alignment,
• icon placement,
• input adornments,
• dropdown positioning,
• breadcrumbs,
• pagination,
• table alignment,
• chart labels,
• legends,
• tooltips,
• drawers,
• modals,
• date/number presentation,
• responsive wrapping,
• long Persian strings.

Do not solve RTL defects with arbitrary per-element offsets when the underlying layout can be made
direction-aware.

Prefer logical CSS properties and existing Metronic RTL behavior where appropriate.

Do not assume that mirroring every visual element is correct. Follow established Metronic RTL and
Dolphin product conventions.

────────

14. Chart and Analytics UI Rules

Charts are a known high-risk visual area and require explicit verification.

Before changing or creating a chart:

1. Find the closest Metronic chart/widget reference.
2. Inspect its actual markup and JS configuration.
3. Inspect the Dolphin chart container and surrounding card/layout.
4. Determine the chart library and existing initialization lifecycle.
5. Preserve real Dolphin data semantics.
6. Verify the result in Persian RTL.

Check:

• chart container width/height,
• responsive dimensions,
• legend placement,
• series names,
• axis direction and alignment,
• tick labels,
• data labels,
• tooltip direction/alignment,
• value formatting,
• number formatting,
• overflow,
• clipping,
• card padding,
• spacing between legend and plot,
• empty/no-data state,
• loading state,
• resizing behavior.

If labels, legends, values, or controls overlap the visualization, fix the actual layout or chart
configuration cause.

Do not “fix” overlap by blindly:

• shrinking the chart,
• pushing the chart sideways,
• adding arbitrary margins,
• adding magic pixel offsets,
• hiding labels,
• clipping overflow,

unless the Metronic reference or a demonstrated layout requirement justifies that behavior.

A chart that technically renders but has misplaced labels, legends, tooltips, or values is not
complete.

────────

15. CSS Discipline

Minimize custom CSS.

Use existing:

• Metronic utility classes,
• Bootstrap/layout utilities used by the project,
• established Dolphin classes,
• component classes,
• responsive utilities,
• RTL mechanisms.

Custom CSS is appropriate primarily for:

• Dolphin branding,
• behavior not supported by existing utilities,
• RTL corrections that cannot be expressed cleanly otherwise,
• print-specific behavior,
• genuinely product-specific components.

Avoid:

• arbitrary pixel nudges,
• large !important chains,
• duplicated vendor styles,
• global selectors for local problems,
• hardcoded layout hacks,
• custom design tokens that duplicate Metronic.

If custom CSS grows significantly for a standard component, stop and search Metronic again. A
canonical implementation may already exist.

────────

16. JavaScript Frontend Discipline

Prefer the existing frontend architecture and initialization patterns.

Do not:

• duplicate global event listeners,
• initialize the same component repeatedly,
• create hidden dependencies between unrelated modules,
• copy large vendor JS blocks when a supported initializer already exists,
• hardcode fake API responses,
• make UI state the source of truth for permissions.

Keep reusable behavior reusable, but do not create abstractions for one-time trivial behavior.

Preserve compatibility with Metronic runtime hooks used by the served UI.

For dynamically inserted content, ensure required component initialization/reinitialization follows
the existing project/vendor pattern.

────────

17. Accessibility and Interaction Quality

For changed UI, preserve basic production accessibility.

Where applicable verify:

• keyboard reachability,
• visible focus behavior,
• semantic controls,
• labels for form inputs,
• disabled state,
• accessible names for icon-only actions,
• modal/drawer interaction,
• error association,
• sufficient semantic distinction between action and decoration.

Do not replace native/semantic controls with clickable generic elements merely for visual
convenience.

Accessibility improvements should follow the existing component system rather than creating a
parallel visual style.

────────

18. Dependencies

Prefer existing project and vendor dependencies.

Before adding a dependency:

• confirm existing libraries cannot reasonably solve the problem,
• verify compatibility with the current stack,
• consider maintenance and security impact,
• avoid introducing overlapping UI/component libraries.

Do not add a new design system or component framework alongside Metronic for ordinary UI work.

Do not add a library for a trivial function that can be implemented safely and clearly with existing
dependencies or standard platform features.

────────

19. Testing Strategy

Use risk-based verification.

During implementation, run the narrowest relevant checks first.

Examples:

• changed backend unit/service tests,
• changed permission tests,
• template/static checks,
• focused frontend tests,
• targeted lint/type checks,
• focused browser verification.

Do not repeatedly run:

• full repository suites,
• PostgreSQL harnesses,
• complete browser matrices,
• collectstatic,
• exhaustive audits,

after every small edit.

Run broader/full gates at meaningful integration checkpoints, feature freeze, release preparation,
or when changes affect high-risk infrastructure such as:

• database behavior,
• permissions/security,
• concurrency,
• deployment,
• shared module infrastructure.

Never weaken a valid test just to make it pass.

Tests verify the implementation; they do not define incorrect business behavior.

If a test is proven stale or defective, fix the test and document why.

Never fabricate test results.

If a test cannot run because infrastructure is unavailable, report the exact blocker.

────────

20. Visual Verification Standard

Frontend work is incomplete when visual correctness has not been reasonably evaluated.

If browser tooling is available, use it for meaningful frontend changes.

Visual review should compare the implementation against:

• the relevant Metronic reference,
• existing Dolphin page conventions,
• Persian RTL behavior,
• responsive behavior.

Do not judge quality solely from source code.

If visual tooling is unavailable, state that visual verification was not performed. Do not claim
pixel-level or rendered correctness from code inspection alone.

────────

21. Git Safety

Preserve all existing user work.

Before any action that could discard changes, inspect:

```bash
git status --short
```

Never use destructive Git operations unless explicitly requested for that exact operation.

Examples requiring explicit authorization include:

• git reset --hard
• git clean -f
• discarding unfamiliar working-tree changes
• force push
• history rewrite
• deleting branches containing unknown work

Do not assume an unfamiliar modification is disposable.

Do not silently revert changes outside the task.

────────

22. Commits and Pushes

Do not automatically commit or push merely because code changed.

By default, leave a reviewable working-tree diff.

Create a commit when:

• the current task explicitly requests a commit, or
• the product owner’s current instruction clearly defines commit/push as part of completion.

Push only when explicitly requested or when the current task explicitly includes deployment/repository
publication requiring it.

Before a requested push:

1. Review the diff.
2. Run the appropriate meaningful verification for the completed scope.
3. Ensure no secrets or accidental files are included.
4. Ensure documentation/version/changelog requirements for that release scope are satisfied.
5. Commit coherently.
6. Push to the intended branch/remote.

Never force-push unless explicitly authorized.

Do not use --no-verify to bypass valid repository checks unless the product owner explicitly
approves the specific exception.

────────

23. Versioning

Use semantic versioning when Dolphin’s current release process uses version numbers:

• PATCH — compatible bug fixes and small corrections.
• MINOR — backward-compatible product features/capabilities.
• MAJOR — intentionally incompatible/breaking product changes.

Do not bump versions after every tiny edit.

Version changes belong to coherent release/release-candidate checkpoints, not arbitrary file changes.

Do not accelerate version numbers for perceived importance.

Before changing the version:

• inspect the current version source of truth,
• inspect recent release/changelog convention,
• determine whether the current scope actually warrants a release bump.

DOLPHIN_VERSION and the repository’s established release mechanism remain authoritative where
present.

Do not invent a second version source.

────────

24. Changelog

CHANGELOG.md is a historical release record.

Update it when the completed work is user-visible, operationally meaningful, architectural, security
relevant, or part of a release scope according to the repository’s existing convention.

Do not rewrite historical entries merely because the product was later renamed.

Historical entries should remain historically accurate.

Do not flood the changelog with every internal micro-edit.

Prefer concise entries describing what materially changed.

Never claim something shipped if it has not actually shipped; distinguish implemented, released, and
deployed states where relevant.

────────

25. Documentation Is Part of the Product

Documentation must evolve with the code.

When a coherent change affects any of the following, update the relevant live documentation in the
same task:

• architecture,
• business behavior,
• API contracts,
• models/entities,
• permissions,
• feature availability,
• deployment,
• environment/configuration,
• operational procedures,
• security assumptions,
• customer-visible workflow,
• module boundaries.

Do not update unrelated documents merely to create activity.

Do not duplicate the same truth across many documents when one authoritative document can be linked.

Maintain the authority structure defined in this file.

25.1 Live Status

After a coherent phase completes, update DOLPHIN_PROJECT_HANDOFF.md with meaningful current
state/evidence according to its existing structure.

Do not turn it into verbose session narration.

Record facts that will help the next engineering session understand:

• what is complete,
• what changed,
• what was verified,
• what remains,
• genuine blockers.

25.2 Roadmap

Update DOLPHIN_CLIENT1_CODEX_ROADMAP.md only when roadmap/phase status genuinely changes.

Do not rewrite the roadmap after every implementation detail.

25.3 Backend Contract

If intentional business/backend behavior changes, update BACKEND_SPEC.md and relevant
docs/backend/*.md only after establishing that the behavior change is a real product decision.

Do not invent business rules to fill documentation gaps.

────────

26. Temporary Findings and Technical Debt

Do not derail an active task for unrelated speculative cleanup.

If a significant unrelated defect is discovered:

• determine whether it blocks the current objective,
• fix it only if required for safe completion or tightly related,
• otherwise record it in the project’s existing appropriate tracking/status document if such a
mechanism exists.

Do not create a new “technical debt” document for every observation.

Do not create endless improvement lists.

────────

27. Production Quality

Code served to customers must be real production behavior.

Do not ship:

• TODO-powered functionality,
• fake data presented as real,
• placeholder buttons,
• nonfunctional menus,
• demo actions,
• mock success responses,
• hardcoded customer-specific behavior,
• temporary bypasses,
• security-disabled shortcuts.

Temporary development instrumentation must not leak into production output.

If a feature is not ready, keep it unavailable rather than presenting a fake implementation.

────────

28. Error Handling

Handle failures at appropriate boundaries.

User-facing failures should be understandable and should not expose sensitive internals.

Logs should contain enough context for diagnosis without leaking secrets.

Do not catch broad exceptions merely to hide defects.

Do not silently swallow failures that affect data integrity or user actions.

Follow existing project error-response and messaging conventions.

────────

29. Observability

Use the existing logging/observability conventions.

Preserve established dolphin.* logger naming where applicable.

Do not log entire request bodies, credentials, tokens, or sensitive records merely for debugging.

Add logging only when it provides actionable operational value.

Remove temporary debug output before completion.

────────

30. External Integrations

Treat external APIs and integrations as unreliable boundaries.

Where applicable:

• use established timeout/retry patterns,
• validate responses,
• preserve idempotency for retried mutations when required,
• avoid duplicate side effects,
• handle unavailable integrations gracefully,
• never expose integration secrets to the browser.

Do not invent integration semantics when provider/business requirements are unknown.

────────

31. Accounting, Financial, Tax, and Legal Behavior

Accounting is a high-consequence domain.

Never invent:

• ledger semantics,
• tax rules,
• invoice legal requirements,
• rounding policy,
• fiscal periods,
• accounting entries,
• payment settlement rules,
• jurisdiction-specific compliance behavior.

If implementation requires a genuine accounting/legal/business decision not established by current
code or authoritative product documentation, stop and request that decision.

Technical implementation may proceed only where semantics are already defined.

────────

32. Deployment Compatibility

Treat deployed customer environments as real systems.

Do not assume a fresh install.

Changes to:

• environment variables,
• Docker/Compose behavior,
• reverse proxy configuration,
• database bootstrap,
• backup/restore,
• static assets,
• runtime paths,
• deployment manifests,

must consider existing deployments and upgrade behavior.

Do not rename an existing environment-variable contract casually, without weighing existing
deployments and upgrade behavior — see §10.1's KARIZ_*→DOLPHIN_* rename (2026-09-05) for what
"casually" is not: an explicit product-owner decision, a hard cutover with no dual-read fallback, and
a documented migration note for every already-deployed customer.

When deployment behavior changes, update relevant docs/ops/*.md, examples, and scripts together.

Do not claim deployment success unless the deployment or relevant verification actually ran.

────────

33. File and Repository Hygiene

Do not create unnecessary files.

Reuse existing project structure.

If temporary scripts/files are created for investigation or iteration, remove them before completion
unless they provide durable project value.

Do not commit:

• generated junk,
• local editor state,
• temporary screenshots,
• debug dumps,
• secrets,
• local databases,
• transient test output,

unless the repository explicitly tracks that artifact type.

────────

34. Scope Control

Solve the requested product outcome.

Do not expand a focused task into a broad refactor without a concrete reason.

A bug fix does not automatically justify:

• redesigning the architecture,
• replacing a library,
• renaming unrelated files,
• reformatting the repository,
• cleaning unrelated code,
• rebuilding working components.

If a broader change is genuinely necessary to safely solve the task, explain the dependency and keep
the change coherent.

────────

35. Decision Boundaries

Proceed autonomously on reversible implementation details when evidence is sufficient.

Stop for a genuine unresolved decision involving:

• business semantics,
• legal/accounting policy,
• credentials/secrets,
• irreversible external actions,
• destructive production data changes,
• unavailable required infrastructure,
• release-blocking ambiguity that cannot safely be resolved from repository evidence.

Do not stop for ordinary implementation choices that can be resolved from code, tests, Metronic
references, or established project conventions.

Do not ask the product owner questions that repository inspection can answer.

────────

36. Evidence Standard

Do not make repository claims from memory when they can be verified.

Before saying:

• “this component uses X,”
• “there is no existing implementation,”
• “this API behaves like Y,”
• “this test passes,”
• “this name no longer exists,”
• “the deployment supports Z,”

inspect or execute the relevant evidence.

Distinguish explicitly between:

• CURRENT CODE BEHAVIOR
• TARGET BEHAVIOR
• VERIFIED
• UNVERIFIED

when ambiguity matters.

Never fabricate evidence.

────────

37. Completion Criteria

A task is complete when:

• the requested outcome is implemented,
• the implementation follows current Dolphin architecture,
• relevant feature/permission/data-scope boundaries remain correct,
• relevant checks have been run,
• meaningful frontend changes have been visually verified when tooling is available,
• documentation affected by the change is current,
• no known release-blocking defect remains,
• no unrelated user work was destroyed.

Do not create arbitrary self-scoring loops.

Use concrete defects, tests, rendered behavior, and product requirements as completion evidence.

────────

38. Completion Report

At the end of implementation work, report only:

• Changed: what changed.
• Issues: important defects found.
• Checks: tests/checks actually run and results.
• Blockers: unresolved blockers, or None.
• Next: exact next action only when one is required.

Keep it concise.

For individual issues, prefer:

- [file/component] Issue → consequence → fix

Do not provide long narration of routine work.

────────

39. Frontend Completion Checklist

For a meaningful frontend change, confirm as applicable:

• served Dolphin implementation inspected,
• closest Metronic reference found and inspected,
• existing Dolphin/Metronic component reused where possible,
• no unnecessary parallel design system introduced,
• real backend behavior preserved,
• no demo/placeholder controls introduced,
• Persian RTL checked,
• responsive behavior checked,
• long labels/overflow checked,
• empty/loading/error states checked,
• chart/table/form-specific behavior checked,
• custom CSS kept minimal,
• browser/render verification performed when available.

If one of these is not applicable, do not manufacture work merely to check the box.

────────

40. Backend Completion Checklist

For a meaningful backend change, confirm as applicable:

• current implementation and contract inspected,
• feature availability enforced,
• role permission enforced,
• object/data scope enforced,
• input validated at the correct boundary,
• transaction/data-integrity requirements preserved,
• query behavior remains reasonable,
• migrations are safe for existing deployments,
• focused tests executed,
• affected contracts/docs updated.

────────

41. Release Checkpoint

At a real release/integration checkpoint — not after every edit — review:

• focused tests already passed,
• broader relevant suite,
• security/permission-sensitive paths,
• migrations,
• deployment configuration,
• static/frontend build requirements,
• visual smoke test of critical served UI,
• documentation,
• changelog,
• version,
• clean intended diff,
• secret/artifact leakage.

Only perform expensive full verification when the scope warrants it.

────────

42. Final Principle

Dolphin is a shared commercial product with a purchased, proven visual system and a modular backend.

When uncertain:

• inspect before guessing,
• reuse before inventing,
• adapt Metronic before designing from scratch,
• enforce security in the backend,
• keep customer features modular,
• preserve data,
• preserve compatibility,
• keep changes focused,
• verify what actually changed,
• document durable truth.

Build Dolphin as a product that another engineering team can safely maintain years from now.