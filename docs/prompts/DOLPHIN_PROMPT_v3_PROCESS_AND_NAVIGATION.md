# Dolphin — Implementation Prompt v3: Sales Process, Navigation, Dashboard Polish

You are a senior full-stack engineer and product-minded UI/UX engineer working on **Dolphin (دلفین)**: a production Persian-RTL CRM/ERP (Django 5.2 + DRF, themed UI kit, one codebase per customer, becoming multi-tenant SaaS). It holds real data. This is a **careful evolution, not a rewrite**. Current version is 2.38.0.

## 0. How to work

1. Read first: `CLAUDE.md`, `CHANGELOG.md`, `BACKEND_SPEC.md`, `DOLPHIN_FEATURE_MAP_AND_ROADMAP.md`, the feature registry, `accounts/module_permissions.py`, `accounts/access.py`, and the earlier prompt `DOLPHIN_MASTER_PROMPT_v2.md` (its rules still apply: expand-only schema, idempotent data migrations with dry-run, feature flags, backup first, Persian CHANGELOG, no vendor/UI-kit name in first-party files — a repo test enforces this, so never write the kit's name or folder anywhere).
2. Project rules in `CLAUDE.md` override this prompt where more specific.
3. Investigate before editing. Cite file:line for each claim you act on. Never guess; if the code contradicts this prompt, stop and report.
4. Plan → implement in small steps → run the narrowest relevant tests → run the full suite once at the end → critical self-review against Section 9.
5. Run tests with `python manage.py test --settings=config.test_settings` (serial; sqlite in-memory does not support `--parallel`). Note: the repo may have CRLF line endings on Windows; do not "fix" tests by weakening them. Add `* text=auto eol=lf` to `.gitattributes` and renormalize **only** in its own commit (see Section 8, item L).
6. Do not expose secrets. Do not delete user data. Preserve unrelated work.

## 1. Release policy (must follow)

- **One big mechanism = one atomic version, so we can roll back to the last good one.** Everything in Sections 2–5 and 7 (data model + process + bug fixes) ships together as **2.39.0**, behind a feature flag, with a backup step, expand-only migrations, a dry-run data migration, and a smoke test that the previous version's data still renders.
- **Cosmetic and naming changes are small patches**: Sections 6 (sidebar naming/grouping) → **2.39.1**, Section 6b (dashboard visuals) → **2.39.2**, further polish 2.39.3 …. Patches must not change data or behavior.
- Each version: bump `VERSION`, add a Persian CHANGELOG entry (what changed, who is affected, how to roll back), and update docs.
- Never mix a mechanism change into a patch.

## 2. The business process (source of truth — the code must match this)

This is the process the product owner described. Treat it as the specification:

1. A **store manager** (preferably) creates a **campaign**. A campaign contains many **sub-campaigns** (ریز کمپین‌ها). Each sub-campaign is where the people (leads) actually live.
2. A campaign may use **several communication channels** (e.g. phone call, SMS, Instagram, exhibition). The word "channel" must be shown as **«کانال ارتباطی»** (communication channel), never alone, and it is optional metadata, not a core entity users must understand to get work done.
3. Every sub-campaign is full of **leads (سرنخ)**. Each marketer sees **only the leads assigned to them**, calls them, and every activity (call, note, follow-up, result) is logged against that lead.
4. When a lead buys and an **invoice is issued**, the person **automatically becomes a customer** and appears in the **Customers** tab, owned by that marketer, with the link back to the campaign/sub-campaign that produced them.
5. For existing invoices, the marketer opens **«درخواست‌های تأمین»**, selects the relevant invoices, and creates the **request to the warehouse** for them.

### 2.1 Decisions you must make explicit (do not silently choose)

Before coding, write a short design note (`docs/design/campaign-process-2.39.md`, Persian headings OK) answering each, with the option you chose and why:

- **Hierarchy depth.** Recommended: exactly **two levels** (campaign → sub-campaign), via a nullable self-FK `parent` on `Campaign` limited to depth 1. Parent campaigns hold no members directly; members belong to sub-campaigns only. A campaign with no children is allowed to hold members itself (so simple campaigns stay simple) — in that case treat it as its own single leaf. Validate depth at the service layer and with a DB constraint where feasible.
- **Channels.** Recommended: a small managed list `CommunicationChannel` (phone, SMS, Instagram, exhibition, referral, other; editable by managers) and an M2M from `Campaign` (any level). Analytics may group by channel but the default views do not require it. If you find an existing "channel/source" field, migrate or reuse it rather than duplicating.
- **Money and counts roll up** from sub-campaigns to the parent; never double count a person or an invoice. A person belongs to exactly one sub-campaign per participation; keep the existing unique(campaign, phone) rule at leaf level.
- **Who may create campaigns/sub-campaigns**: manager by default; marketers only if a capability in the module matrix grants it. Marketers never see other marketers' leads.
- **Invoice → customer → campaign link**: when an invoice is **issued** for a person who has no customer yet, create the customer from the person (name, phone, owner = the member's assigned marketer) inside the same transaction as issuing, idempotently (re-issuing or retry must not create a second customer; match on normalized phone within the tenant). Preserve the existing attribution rules (issued invoices only, one attribution per invoice, no counting of cancelled/draft invoices).
- **Request for warehouse (درخواست تأمین) from several invoices**: keep the existing rule "one active request per invoice". The multi-select UI creates **one request per selected invoice** in one transaction (all-or-nothing), shows a per-invoice result list, and caps the batch (e.g. 50). A marketer can only select **issued invoices of customers they own**; managers can select any.

## 3. Data model and services (mechanism — version 2.39.0)

Expand-only; reversible where possible; no destructive change.

- `Campaign.parent` (nullable FK to self, `PROTECT`, depth ≤ 1) and `CommunicationChannel` + M2M. Keep `system_key` campaigns (the «بدون کمپین (قدیمی)» bucket etc.) protected from edit and delete: override `_extra_delete_guard` in `CampaignViewSet` to refuse system campaigns, and have the bulk-delete route use it too.
- **Data migration `migrate_campaign_hierarchy`** (management command, dry-run by default, `--apply` to write, writes a CSV report to a path argument, idempotent). Existing campaigns become top-level campaigns; no automatic guessing of children. Report counts. Provide a documented reverse: since the change is additive, rollback = deploy the previous version; data stays valid.
- Services (not views) own all rules. Add or fix:
  - `create_campaign`, `create_sub_campaign`, `move_member_to_sub_campaign` (audit log + assignment history).
  - `ensure_customer_for_member(member)` used by invoice issue and by a manual «تبدیل به مشتری» action; idempotent.
  - Leads form (create lead) **requires choosing a campaign/sub-campaign** from a dropdown (only leaf campaigns; searchable; shows parent › child). The legacy form that leaves `campaign` NULL must stop doing so.
  - `mark_sale` / «ثبت فروش» from a person: either delegate to `ensure_customer_for_member` and then proceed, or remove the Sale entry path and send the user to create an invoice. Pick one in the design note; the dead-end error «مشتری را مشخص کنید» must not appear for campaign people.
  - Marketer permissions flow through `member.assigned_to`: fix `record_interaction`, `mark_sale`, `update_lead`, `leads_for` and any follow-up/calendar/reminder query so a marketer can act on **their** members, and cannot act on others'. Follow-up date is stored **on the member**, not on the shared container record.
  - Calendar, kanban/board, reminders and search read **members** (with their campaign), and container records with `source="campaign"` are excluded from legacy lists.
  - `attribute_issued_invoice`: accept an explicit campaign/sub-campaign context when the invoice comes from an order/quotation that has one; manual attribution applies the same eligibility filter as auto (person created before invoice issue, not LOST, deterministic ordering); require an interaction inside the window for auto last-touch (no fallback to `member.created_at`).
  - Excel import of people: scope the "already exists" check to the **target campaign** (a phone existing in another campaign is allowed).
  - Move date semantics to one definition: document that results are "cohort by member creation date" or switch to a single date basis; use the same population for rate and revenue.
- Add `ensure_system_campaigns` as a migration/startup step, not a side-effect of a GET list.

## 4. Payments / invoices / fulfillment bugs to close in the same version (2.39.0)

These come from a code review of 2.38.0. Fix each with a failing test first.

1. **Allocation idempotency**: repeated allocation of one receipt to one invoice is allowed (e.g. 20M split into 5M ×4), but a double submit/retry must not create a second row. Add a client-supplied idempotency key (UUID per form open) stored on `PaymentAllocation` with a unique constraint, or reject an identical (payment, invoice, amount) allocation created within a short window with a clear Persian message. Keep the `unallocated_amount` / «مانده دریافت» display.
2. `update_payment`: when the amount is reduced below the allocated total, edits to customer/reference/notes must not be lost (apply changes after the release loop or re-apply them after `refresh_from_db`).
3. Changing a payment's **customer** must release all active allocations (or be refused while allocations exist). Add this check to `check_allocation_integrity` too.
4. Lock order: always lock the payment first, then invoices sorted by pk; fix `release_allocation`, `cancel_payment`, `allocate_payment_across`. Add a concurrency test (skip on sqlite, run on PostgreSQL in CI).
5. Manual settlement must not block real allocations: allocate against the canonical balance, not `balance_due` when `manual_settled_at` is set; disable the unused `manual-paid/` endpoint or guard it.
6. Store a **reason** for allocation release and payment cancel (new nullable field), show it in the audit trail.
7. Fulfillment request: copy the invoice's header discount, `discount_percent` and tax rate (not the current default); block creating a request if the invoice is linked through the legacy `Invoice.order` link or already has stock applied; add a backfill (dry-run) for old order→invoice links; allow cancelling a **fulfilled** request (returns stock) or otherwise provide a way to cancel/reissue the invoice.
8. Invoice issue error (2.34.2): replace the driver-text match (`"number" in str(exc)`) with `exc.__cause__.diag.constraint_name` (PostgreSQL) and the equivalent for sqlite in tests; make `update_invoice` handle the same race.
9. Cancelled-invoice immutability: extend the guard to `PaymentAllocation` creation and installment objects tied to a cancelled invoice.
10. Installment unwind on release should unwind the installments that the released allocation actually paid, not always the last one.

## 5. Security / realtime items (2.39.0)

- Make `customers.import` (and optionally `customers.assign_owner`) grantable through the per-user module matrix so a manager can authorize specific marketers to import Excel; keep the server checks.
- Realtime SSE: per-user connection cap (≈3, evict oldest), gunicorn threads = global cap + ~8, nginx `limit_conn` on the stream path; subscribe inside the stream generator (or unsubscribe via response close) so a slot cannot leak; send `resync` as the first event on every connect and after the listener reconnects; scope customer/invoice/inventory events by capability or owner and coalesce bursts (import of thousands of rows must not send thousands of notifications). Do not enable realtime by default.
- `/api/v1/realtime/health/` must not be reachable from the public ingress.
- Customer owner must not be settable to an after-sales operator (reject in the service, not just the UI).
- Free-text customer category must not bypass the managed list for non-managers.
- Export of phone numbers starting with `+` must round-trip on re-import (strip the leading apostrophe on import).
- Dockerfile/.dockerignore: exclude `.claude/`, `docs/`, `*.md`, scratch scripts from the image.
- Delete stray files from the repo root: `_fix_test.py`, `_edit_dash*.py`, `.scratch/`; add them to `.gitignore` if they are tooling.

## 6. Navigation, tabs and names (patch 2.39.1 — cosmetic only)

### 6.1 Principles (benchmark against leading CRM panels — HubSpot, Salesforce, Zoho, Pipedrive — and the common conventions in Iranian CRM/accounting panels)

- Order the sidebar by the **work flow of the user**, not by data tables: marketing → leads → customers → invoices → warehouse request → money → inventory → after-sales → reports → settings.
- Every group title and item is a **short, plain Persian noun phrase a new employee understands without training**. No internal/technical words (e.g. «اسناد فروش» and «اسناد مالی» are vague — replace). One concept = one name everywhere (menu, page title, breadcrumb, button, empty state).
- At most **8–9 top-level groups**, at most 6 items per group; nothing nested a third level. Frequently used items first. Active item and parent highlighted; parent group opens automatically for the current page.
- Tabs inside a page follow the same names as the menu and are limited to the page's own sub-views; no tab that duplicates a menu item.
- Respect the permission matrix: a group with no visible item is hidden; marketers see a short, focused menu.

### 6.2 Step 1 — inventory

Before changing anything, produce a table (in the design note) of **every current sidebar group, item, URL, page `<h1>`, breadcrumb, tab label**, and which roles see it. Find where the sidebar is defined (templates/`base.html` or a menu registry) and change it **in one place**. Do **not** change URLs or permissions in this patch.

### 6.3 Step 2 — target structure (adjust to what actually exists; keep your reasoning in the note)

| Group (گروه) | Items |
| --- | --- |
| داشبورد | — |
| بازاریابی | کمپین‌ها (فهرست) · نتایج کمپین‌ها · تحلیل کمپین‌ها |
| سرنخ‌ها و تماس‌ها | سرنخ‌های من / همه‌ی سرنخ‌ها · تقویم پیگیری · تابلوی سرنخ‌ها · تاریخچه‌ی تماس‌ها |
| مشتریان | فهرست مشتریان · دسته‌بندی‌ها (as a page action if it is one today) |
| فروش | فاکتورها · درخواست‌های تأمین از انبار · تابلوی درخواست‌ها |
| مالی | دریافت‌ها · پرداخت‌ها · چک‌ها · اقساط · گزارش مطالبات |
| انبار و کالا | موجودی · حرکت‌های انبار · انبارها · محصولات · دسته‌بندی محصولات · رهگیری پستی |
| خدمات پس از فروش | پرونده‌ها · تقویم خدمات |
| ارتباطات | گفتگو · پیامک |
| گزارش‌ها | عملکرد کاربران · … (existing reports) |
| تنظیمات | existing |

Rules for names: use «فاکتورها»، «درخواست‌های تأمین از انبار» (not just «درخواست‌های تأمین»), «تحلیل کمپین‌ها» (not «آنالیز»), «سرنخ» (not «مرکز ارتباطات» for lead lists). Make labels, page titles, breadcrumbs, buttons and empty-state sentences consistent with the final names; grep for the old words (`اسناد فروش`, `اسناد مالی`, `مرکز ارتباطات`, `کمپین یا نوبت`, `آنالیز`) and fix every remaining occurrence in templates, JS and docstrings that reach users. Keep Persian digits and RTL arrows (chevron points left for "go forward").

### 6.4 Step 3 — verify

Open every menu item as manager and as marketer; confirm no 404, correct active highlighting, correct breadcrumb, and no label drift. Add a test that walks the sidebar definition and asserts: every item resolves to a URL the role may open, no duplicate labels inside a group, no group over 6 items.

## 6b. Dashboard visual polish (patch 2.39.2 — cosmetic only)

Goal: calmer, more readable widgets; less glow; numbers and labels clearly legible.

- **Remove or sharply reduce glow/halo**: find every `box-shadow`, `filter: drop-shadow`, `text-shadow`, blurred gradient and colored outer glow on dashboard tiles, icon wells and chart cards. Replace with a flat card: 1px neutral border, at most one very soft shadow (e.g. `0 1px 2px rgba(0,0,0,.06)`), no colored shadows. Icon wells: light neutral tint, no glow. Keep hover feedback subtle (border color change), not a halo.
- **Numbers first**: KPI value is the largest element (about 28–32px, weight 700), tabular/lining figures, Persian digits, a consistent compact money format with the unit shown once (e.g. «۶۱۲ میلیون ریال»), full value on hover/title. Label below in 13–14px, secondary color; delta (↑/↓) small and colored with sufficient contrast.
- **Contrast**: text ≥ 4.5:1, large numbers ≥ 3:1, in both light and any dark theme the product supports; do not rely on color alone for good/bad.
- **Layout**: fix the empty grid cells and uneven row heights seen in the manager dashboard (tiles wrapping into holes). Use a consistent grid (equal-height rows, one tile size per row type), RTL-correct ordering; collapse cleanly to 1–2 columns on phones.
- **Make the dashboard tell the truth**: the «فروش‌های شرکت» tile must read from **issued, non-cancelled invoices** (same source as campaign analytics), not the legacy Sale model. Add, if absent: sales this month vs last month, collected vs outstanding (مانده), share of sales by campaign including «بدون کمپین», and overdue invoices. Add a short tooltip explaining each number's definition. This part is a data change → if you add new queries/endpoints, ship them in 2.39.0, and keep only styling in 2.39.2.
- **States**: loading skeleton, empty state with a clear next action, error state with retry — none of them with glow or animation that distracts. Respect `prefers-reduced-motion`.
- Charts: calm palette (max 5 hues), thin gridlines, labels not clipped (the analytics bar labels were cut at the edge), Persian numerals, Jalali month names (server-side Jalali bucketing for monthly series).
- Keep the existing UI-kit components and tokens; change **tokens/CSS variables** where possible instead of per-widget overrides, so the whole panel calms down consistently.

## 7. Campaign pages — what the manager must be able to see (2.39.0)

- **فهرست کمپین‌ها**: tree view (campaign › sub-campaigns), status, dates, owner, channels, member count; create campaign / create sub-campaign; system campaigns protected.
- **نتایج کمپین‌ها**: one row per campaign (expandable to sub-campaigns): people, contacted, interested, customers, valid invoices, sales amount, collected, **outstanding (مانده)**; a pinned row **«بدون کمپین»** for issued invoices with no attribution; the whole row is clickable; missing values show «—» (never "null" or blank); invalid date input shows an error instead of being ignored.
- **تحلیل کمپین‌ها**: replace the raw multi-select with a searchable multi-select component (chips, select-all, parent selects its children); filters: date range (Jalali, with sensible default such as current month), campaign/sub-campaign, marketer, channel (labelled «کانال ارتباطی»), product category; funnel that is monotonic and includes the money steps (valid invoice → collected); monthly series in Jalali months; loading state and visible error state; average time to first contact computed from interactions; export Excel/PDF with the same numbers.
- Every number has a one-line definition in a tooltip.
- Marketers see only their own people and **no finance columns**; verify with an agent-role test.

## 8. Tests, verification and housekeeping

Write tests first for each fix. Minimum set:

- A. Campaign hierarchy: depth limit, roll-up with no double counting, system campaign protected from delete.
- B. Marketer role end-to-end: sees only assigned people, logs a call, follow-up saved on member, cannot act on others', calendar/reminders show own members.
- C. Invoice issue creates exactly one customer for a person (retry and re-issue idempotent); attribution unchanged for cancelled/draft.
- D. Sale-from-person path no longer errors for campaign people.
- E. Allocation: repeated allocation of one receipt to one invoice works (20M = 4×5M); double-submit does not duplicate; amount reduction keeps other edits; customer change releases allocations; deadlock-safe lock order (PostgreSQL only).
- F. Fulfillment: header discount/tax copied; legacy link blocks; fulfilled request can be cancelled; batch creation all-or-nothing and per-invoice ownership for marketers.
- G. Excel import scoped per campaign; `+` phone round-trip.
- H. Realtime: per-user cap, slot release, resync on connect (unit-level).
- I. Sidebar test (Section 6.4) and a label-consistency test for the renamed terms.
- J. Dashboard: «فروش» tile equals the count/sum of issued invoices; no cancelled/draft.
- K. Migration: dry-run vs apply on a copy of realistic data; backward-compat smoke test (open every list page after migrating).
- L. Hygiene, in separate commits: `.gitattributes` renormalization to LF; remove stray scripts; update the three outdated dashboard/tile tests to the current UI instead of weakening them.

Visual verification (required for 2.39.1 and 2.39.2): run the panel with the dev settings, log in as manager and as marketer, screenshot the dashboard and every sidebar page at 1440px and at phone width (375px), RTL check, and attach before/after.

Do not claim a test passed unless you ran it. If something cannot be verified (PostgreSQL, SSE), say so explicitly.

## 9. Self-review before you finish

Ask: Does the code match the process in Section 2 (manager creates campaign → sub-campaigns hold leads → marketer calls and logs → invoice makes a customer → marketer requests warehouse supply from selected invoices)? Is every rule enforced in a service, not just the UI? Can the release be rolled back to 2.38.0 without data loss? Did I keep cosmetic changes out of 2.39.0 and mechanism changes out of the patches? Is every visible name consistent and understandable? Did I add or weaken any test improperly?

## 10. Final report (keep it short)

- **Changed:** per version (2.39.0 / 2.39.1 / 2.39.2).
- **Issues:** defects found and not fixed, with `[file] issue → consequence → fix`.
- **Checks:** commands actually run and their results; what was not verified.
- **Blockers:** or "None".
- **Next:** one exact next action.
