# Dolphin CRM — Master Implementation Prompt (v2)

Campaign architecture · payments/allocations · invoice flow · warehouse fulfillment · wizards · permissions · real-time · UX fixes
Baseline: Dolphin **v2.34.1**. Written 2026-10-03.

---

## 0. How to work (read first)

You are working on **Dolphin (دلفین)**: a production Persian-RTL CRM/ERP (Django 5.2 + DRF, themed UI kit, one codebase deployed per customer, becoming multi-tenant SaaS). It holds real data. This is **a careful product-level evolution, not a rewrite**.

Operating rules:

1. Read `CLAUDE.md`, `CHANGELOG.md`, `BACKEND_SPEC.md`, `DOLPHIN_FEATURE_MAP_AND_ROADMAP.md`, `docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md`, the feature registry (e.g. `registry.py`), `common/module_permissions.py`, and the UI-kit reference folder named in CLAUDE.md **before** designing anything. Follow every convention they define (versioning, changelog language, feature toggles, `DOLPHIN_*` env vars, permission modules, labels, tests). Project rules override this prompt wherever they are more specific.
2. Never guess model/field/route names. Verify in code. The "Verified facts" in §3 were read from the code on 2026-10-03 at v2.34.1. **Re-verify each one before relying on it.** If the code differs, keep the business intent and adapt.
3. Fix root causes. No workaround, no fake data, no placeholder UI. Never show an invented number: if a value cannot be computed, show `—` with a tooltip explaining why. `—` (unknown) is never `0`.
4. Backend is authoritative. Hiding UI is never authorization. Every new restriction is enforced in the service/domain layer **and** the API, with tests that try to bypass it directly.
5. Preserve working behavior and existing data. No destructive migration, no unrelated refactor.
6. All new UI: Persian, RTL (including icon direction), Jalali dates, Persian digits where the panel already uses them, the panel's existing money format, responsive down to phone width, with empty / loading / error states. Reuse shared components and the existing UI patterns; do not invent new ones.
7. Priority order when in conflict: **Correctness → Data integrity → Security → Maintainability → UX → Visual polish.**
8. Do not weaken or skip a valid test to make it pass. Do not claim a check passed if it was not run. Do not hide known regressions.

---

## 1. Release strategy (mandatory)

Current version is **2.34.1**. The owner's rule:

- **Small/visual/isolated changes → small patch versions** (2.34.2, 2.34.3, …). One cohesive batch per patch.
- **Big changes that alter how the system works → exactly ONE version per mechanism, landed atomically at the end**, so a problem means rolling back to the last good version.

### Release map

| Order | Version | Kind | Scope |
|---|---|---|---|
| 1 | 2.34.2 | patch | Fix: invoice issue / status change error (§6.1) |
| 2 | 2.34.3 | patch | Cancelled-invoice immutability guard + hard-delete audit (§6.2) |
| 3 | 2.34.4 | patch | Payments: «مانده دریافت» in allocation box + repeated allocations to the same invoice (§6.3) |
| 4 | 2.34.5 | patch | Wizard behavior system-wide (§6.4) |
| 5 | 2.34.6 | patch | Invoice wizard UI, numeric inputs, cash/installment toggle (§6.5) |
| 6 | 2.34.7 | patch | Customer UI: economic-number visibility, type icons/filters, marketer Excel import (§6.6) |
| 7 | 2.34.8 | patch | Navigation & terminology: back buttons, paperclip icon, «مرکز ارتباطات», bulk-delete trash (§6.7) |
| 8 | 2.34.9 | patch | Calendars: month rendering + cross-month drag (§6.8) |
| 9 | 2.34.10 | patch | Settings page IA (§6.9) |
| 10 | **2.35.0** | **big** | Customer ownership, structured categories, Admin/permission rules (§7) |
| 11 | **2.36.0** | **big** | Campaign architecture: Campaign, lead-as-participation, attribution, «کمپین‌ها» menu with 3 pages (§8) |
| 12 | **2.37.0** | **big** | Warehouse fulfillment: invoice-driven request, immutable pricing, rename (§9) |
| 13 | **2.38.0** | **big** | Real-time infrastructure (§10) |

Patch numbers may be split further if a batch grows (2.34.11, …). Do **not** merge a big mechanism into a patch, and do **not** spread one big mechanism across several released versions. Each big release is developed on its own branch and released as one version only when it is complete and verified. (If the owner prefers fewer big releases, they will say so; default is one version per mechanism so rollback stays granular.)

### Rollback contract (applies to every release, mandatory for 2.35.0+)

1. **Expand-only schema.** A release may add tables/columns/indexes and may *relax* constraints. It must not drop, rename, or tighten anything the previous version relies on. Goal: **the previous version's code still runs against the new schema**, so rolling back is a code-only redeploy. Contraction (dropping legacy columns/text fields) is deferred to a later release after a soak period and is *not* part of this task.
2. **Data migrations** are idempotent, re-runnable, never delete legacy data, and have a no-op reverse. Each big release also ships a **dry-run command** that prints exactly what the migration would create/change/skip, plus a "needs human review" report for ambiguous rows. Never silently merge when identity is uncertain.
3. **Backup first.** Document the exact pre-upgrade backup step using the project's existing backup mechanism (see `common/backups.py` and the runbook). Test that restore works on a realistic copy.
4. **Backward-compat smoke test** for each big release: migrate forward, then run the *previous tag's* code against the migrated DB (`manage.py check`, and the read paths of the main pages/APIs) and record the result.
5. **Feature flag** every new user-visible module in the feature registry, default OFF for the first deployment where sensible, so a bad release can be neutralized without redeploying.
6. Maintain a short **"last known good version"** note in the changelog/runbook and tag every release if the project tags releases.

### Per-release checklist

Version bump in **every** place the version lives (no drift) → changelog entry in the project's format/language (features, migrations, data backfills, env vars, services/processes, registry flags, required deployment actions, rollback notes) → docs updated *in the same commit* (CLAUDE.md, `docs/`, runbook, API schema, feature-registry docs) → search docs/templates/labels for stale references → checks run (below) → commit(s) with the version in the message → tag if the project tags. **Push only when the owner asks / per project convention; never force-push; never commit secrets, `.env`, DB files, or recordings.**

---

## 2. Stop-and-approve checkpoint

**Phase 0 (audit + plan) comes first and ends with a written plan saved under `docs/`. STOP and wait for the owner's approval before writing code.** After approval, proceed release by release in the §1 order. Between releases do not stop for routine reports; stop only for a real blocker (unavoidable destructive migration, a conflict with the business intent that the plan does not cover, missing credentials/access, or failing tests you cannot fix without changing intended behavior).

Short report after each release: **Version · Changed · Checks actually run (and result) · Issues · Blockers**.

---

## 3. Verified facts (re-verify before use)

These were read from the code at v2.34.1.

**Campaign / lead / customer (`sales/models.py`, `sales/services.py`)**
- `Lead` is *not* a person. It behaves as a campaign work container: `source`, `campaign_or_batch` (**free text, max 100**), `status` (3 states: pending/completed/cancelled), `assigned_to/by/at`, `next_follow_up_at`, `customer` (nullable). The code comments call it "a campaign".
- The real people being worked are `TargetAudienceMember` (جامعه هدف): FK to `Lead`, `full_name`, `raw_phone`, `normalized_phone`, `status` (lead/engaged/customer/failed) and optional `customer` FK.
- **`TargetAudienceMember` has a global `UniqueConstraint(normalized_phone)` (`uniq_target_member_phone`)**: a phone can exist once in the entire system. This blocks "same person in several campaigns".
- `TargetAudienceMember.status` is derived in `_derived_target_status` / `refresh_target_member_status`: if the phone exists in the customer book → `customer`; elif any interaction exists → `engaged`. Consequence: **an existing customer who joins a new campaign is instantly "customer" → conversion would be inflated.**
- `Interaction` has FK `lead` (required) plus `customer` or `target_member` (at least one).
- `Sale` has required FKs `lead` and `customer`. `mark_sale` **refuses when `lead.customer_id` is null** («پیش از ثبت نتیجه این کمپین، مشتری را مشخص کنید»). The «ثبت فروش» form asks only lead/product/quantity/notes, and the «ساخت سرنخ» form no longer asks for a customer. **Probable bug (unverified by running): recording a sale for a new campaign cannot succeed.** Verify, and resolve inside §8.
- `LEAD_MUTABLE_FIELDS` excludes `customer`, so `lead.customer` is never set after creation.
- `Customer`: has `created_by` but **no `owner` field**; `category` is a free-text CharField (filtered with `icontains`); `kind` (individual/legal, default individual); `economic_code`; `job_title`; `province` (index). `CustomerPhone` has `uniq_active_normalized_phone` (this is the customer-identity constraint and must stay).
- Existing dependents of `Lead` that must keep working: lead list/detail/board (kanban)/calendar, reminders (`common/reminders.py`), global search (`common/search.py`), customer timeline (`common/customer_timeline.py`), dashboard insights, `LeadAssignmentHistory`, call-center «فعالیت مرکز تماس», the `sales_agent` queue «صف سرنخ من», `Quotation.lead`, `Order.lead`, `reports/services.py` user-performance (aggregates `Sale` by `sold_by`; **there is no per-campaign report today**), and the `telephony/`, `scoring/`, `profiles/`, `timeline/`, `integrations/` apps.
- `SmsCampaign` (communications) is an unrelated SMS bulk-send entity that merely shares the word «کمپین».

**Menu (`common/templates/common/base.html`)**: «مرکز تماس» group → مشتریان, سرنخ‌ها / صف سرنخ من (`leads`), تقویم پیگیری (`lead-calendar`), تابلوی سرنخ‌ها (`lead-board`), فعالیت مرکز تماس (`interactions`), **نتایج کمپین** (`sales`, = the `Sale` list); then «اسناد فروش»: سفارش‌ها (`orders`), تابلوی سفارش‌ها (`order-board`), فاکتورها (`invoices`), …

**Billing (`billing/models.py`, `billing/services.py`, `billing/payments.py`)**
- `CommercialDocument` (abstract): `customer` required. `Quotation`/`Order` have nullable `lead`.
- `Order` statuses: draft/confirmed/fulfilled/cancelled. It **owns the stock movement** (`stock_applied`, `stock_revision`, idempotent apply/release/reconcile); approved orders are still editable. It has its own `OrderItem` rows.
- `Invoice`: statuses **draft / issued / cancelled** only (editable only in `draft`); `settlement` unpaid/partially_paid/paid; `invoice_type` unofficial/official; nullable FKs `order`, `quotation`, `sale`, `warehouse`; `stock_applied`; `paid_amount`, `balance_due`. `InvoiceViewSet.records_deletable = False`. There is no state literally named "finalized voided"; the immutable state to protect is `cancelled`.
- `issue_invoice` (single transaction) does: transition check → items required → official-identity validation + official number → `_snapshot_parties` → cost snapshot → optional stock deduction (`invoice_affects_stock()`) → status/number write → `build_plan_at_issue` (installments) → ledger debit → activity log → `integration.services.enqueue_event("invoice.issued")`. Any of these can raise.
- `PaymentAllocation`: FKs `payment`, `invoice`, `amount`, `is_reversed`. **`UniqueConstraint(payment, invoice) where is_reversed=False` (`uniq_active_payment_invoice_allocation`)** plus service checks forbid allocating the same payment to the same invoice twice: `allocate_payment` maps `IntegrityError` to «این پرداخت قبلاً به این فاکتور تخصیص یافته است» and `allocate_payment_across` rejects a repeated invoice («این فاکتور بیش از یک‌بار فهرست شده است»). `Payment.unallocated_amount` exists (`billing/models.py`). Rules that must stay: receipt only, confirmed only, same customer, invoice issued, amount ≤ unallocated, amount ≤ `balance_due`.
- The allocation UI is `common/templates/common/payments/detail.html` (`#payment-allocate-section`, «تخصیص به فاکتور») + `common/static/common/js/features/billing/payment-detail.js`; the same operation exists inside the receipt wizard (`payments.js` / `payments/list.html`).

**Infrastructure**: gunicorn WSGI only (`Dockerfile`); **no Channels / Redis / ASGI** in requirements or compose. Cron-style management commands are the established pattern for periodic work.

---

## 4. Domain definitions (use these exact meanings everywhere)

Terminology (UI, API labels, docs, tests):

| Term | Meaning |
|---|---|
| **کمپین** | A structured initiative (e.g. فروش تابستانه، فروش اینستاگرام، نمایشگاه پاییزه). Open to unlimited leads; converting a lead never closes it. |
| **سرنخ** | One person's participation in one campaign: own campaign, status, assignee, interactions, dates, outcome. |
| **مشتری** | A real identity in the customer book. Appears once; may have many سرنخ across campaigns. |
| ~~نوبت کاری~~ | Legacy work-batch layer. **Not exposed to users.** |

Business flow users must understand: **کمپین → سرنخ → مشتری → فاکتور → درخواست تأمین از انبار → دریافت/تسویه.** Interactions (calls) belong to the سرنخ.

Metric definitions (state them in the UI as tooltips and in docs):
- **Conversion** = a سرنخ is *converted* when the first **valid invoice** attributed to its campaign for that customer is issued **after the سرنخ was created**. A pre-existing customer joining a campaign is *not* converted by that fact alone.
- **Valid invoice** = `issued` and not `cancelled` (draft excluded). Show amount **with tax** and label it.
- **Collected (وصولی)** = sum of active (non-reversed) `PaymentAllocation.amount` against those invoices. Reuse the existing settlement semantics (`paid_amount`, `balance_due`, and the cheque rules incl. bounced/cleared handling) instead of recomputing; add a footnote for cheque handling.
- **Outstanding** = valid − collected.
- **Recorded sale (legacy `Sale`)** is a different concept from valid invoice and from collected. Never merge them in one number.
- **Unattributed** is a visible bucket («بدون کمپین»), never silently dropped and never counted as 0 for a campaign.

---

## 5. Phase 0 — Audit & plan (NO code)

Inspect and write the plan (`docs/` file, concise, Persian where existing user docs are Persian) covering:

1. Current state of everything listed in §3, including each dependent of `Lead`, the permission modules (`module_permissions.py`), the shared wizard/modal components, calendars, settings, the integrations page (structural reference for Settings), notifications/bell, and deployment (compose, nginx, runbook).
2. **Reproduce the invoice issue/status-change error** (§6.1) with a concrete scenario matrix and report the exact failing request/response/log. If it cannot be reproduced locally, say precisely what extra information you need.
3. Proposed data models and migrations for 2.35.0 / 2.36.0 / 2.37.0 / 2.38.0 with the expand-only/rollback analysis for each, incl. the dry-run report format.
4. The **`Sale` decision**: recommended default = *invoice is the single source of truth for revenue and conversion; `Sale` becomes a legacy/derived record kept for history and for the existing user-performance report*, and no path may leave the user with «مشتری را مشخص کنید». Propose the exact migration of «ثبت فروش».
5. Customer visibility scoping: confirm whether customer lists are currently scoped by `created_by`; adding `owner` changes visibility semantics — describe the safe transition.
6. Role/permission matrix for campaigns, results, analysis, attribution, categories, import, invoice actions — expressed through the existing permission modules (no hardcoded role ids).
7. Open decisions with options and a recommendation. Defaults proposed in this prompt (change only with the owner's approval): conversion definition (§4); **last-touch attribution** (§8.6); **one active fulfillment request per invoice** (§9.2); refuse invoice cancellation while an active fulfillment request exists (§9.4); real-time in its own release (§10).

**Stop. Wait for approval.**

---

## 6. Patch releases 2.34.2 – 2.34.10

### 6.1 — 2.34.2: Invoice issue / status-change error

Problem reported by the owner: changing an invoice's status and **issuing** it produces an error.

- Reproduce through the real UI and API (`POST /…/invoices/<id>/issue/`; also check what `invoice-detail.js` actually calls). Capture HTTP status, response body, and server traceback.
- Walk this matrix at minimum: unofficial/official; with/without warehouse; `invoice_affects_stock()` on/off (watch for double deduction when the order already moved stock); stock shortfall; with/without installment plan (`build_plan_at_issue`); customer missing official identity (`official_invoice_identity_errors`); missing/Jalali `document_date`; discount percent vs amount; items with zero/rounded totals; `integration.enqueue_event` configured vs not; DB CHECK constraints from `_document_constraints`; concurrent double-click on issue; non-manager actor.
- Find the **root cause**, fix it, and add a regression test that fails before the fix and passes after.
- A user-facing failure must be a clear Persian message mapped to the right field/state (400/409), **never a 500 and never a generic "error"**. The whole issue operation stays atomic: no half-issued invoice, no stray stock movement, ledger entry, or official number.

### 6.2 — 2.34.3: `cancelled` invoices are immutable

- A cancelled invoice is a historical/audit record. **Even Admin/superuser** cannot edit it, edit its items, re-attribute it, change settlement-related fields, or delete it — through the UI, the DRF API, services, or Django admin.
- Enforce in the **domain/service layer and the model/queryset layer** (not UI-only), including `save()`/`delete()` guards and any bulk-update/bulk-delete path. Audit every existing hard-delete path (`HardDeleteMixin`, `can_hard_delete`, bulk delete) for invoices and for rows that reference them.
- Do not confuse draft cancellation with the real `cancelled` state; read the actual state machine first.
- Admin may edit/delete **drafts**. An `issued` invoice or any invoice with payments/ledger entries is never hard-deleted; the only way out is cancellation (`cancel_invoice`) or reissue (`reissue_invoice`).
- Tests: direct API/service calls as Admin on cancelled, issued-with-payment, and draft invoices.

### 6.3 — 2.34.4: Payments — «مانده دریافت» and repeated allocations

**(a) «مانده دریافت» in the allocation box.** In the receipt detail page's «تخصیص به فاکتور» box (`#payment-allocate-section`), always show: **مبلغ دریافت · تخصیص‌یافته · مانده دریافت** (= `unallocated_amount`) in the panel's money format, plus a live «مانده پس از این تخصیص» that updates as the user types/adds rows and turns red/blocks submit if it would go negative. When the remainder is 0, disable the form and say so. Apply the same display in the receipt wizard's allocation section. The value comes from the server; the live preview is client-side only and the server stays authoritative.

**(b) One receipt can be allocated to the same invoice several times.** Example: a 20,000,000 receipt allocated 5,000,000 four times to one invoice.
- Replace the `uniq_active_payment_invoice_allocation` unique constraint with a plain index on `(payment, invoice)` (relaxation = expand-only, safe for rollback). Remove the `IntegrityError → «قبلاً تخصیص یافته»` mapping, and allow a repeated invoice in `allocate_payment_across` (for repeated rows of one invoice, validate the **cumulative** requested amount against `balance_due` and against the receipt's unallocated amount, all-or-nothing).
- Every allocation stays its own auditable row, individually releasable (`release_allocation`). Do **not** merge rows.
- Rules that must remain: receipt only, confirmed payment, same customer, invoice `issued`, amount ≤ unallocated, amount ≤ `balance_due`, `select_for_update` ordering safe against concurrent requests.
- Invariants to test: Σ active allocations = `payment.allocated_amount`; invoice `paid_amount`/`balance_due`/settlement and installment application stay consistent after N allocations and after releasing any one; the example above ends with `unallocated = 0`, releasing one returns 5,000,000. Add a read-only `check_allocation_integrity` management command that reports any drift, and a concurrency test.
- Update the allocation tables (receipt page and invoice page) so repeated rows read clearly (date, amount, actor, status), and fix any copy that says "once".

### 6.4 — 2.34.5: Wizard behavior, system-wide

Implement in the **shared wizard/modal layer**, not per page. Audit every multi-step create/edit wizard first and list them.
- Remove the redundant bottom «انصراف» button where the header already has a close control.
- **Backdrop click never closes a wizard.** Disable outside-click dismissal. The explicit header close still works. Decide Escape deliberately (recommended: Escape does not close a dirty wizard; it may close a pristine one).
- **Unsaved-changes guard:** if the user explicitly closes a *dirty* wizard, confirm with «تغییرات ذخیره نشده‌اند. آیا مطمئن هستید که می‌خواهید خارج شوید؟». Pristine wizard closes immediately. Dirty = any user-entered change; define it centrally. Also warn on browser tab close/reload only while dirty.
- Works with `<dialog>`-based and stepper-based wizards currently used; keyboard + focus-trap + screen-reader behavior preserved; RTL.

### 6.5 — 2.34.6: Invoice wizard

- Fix the crowded layout: spacing, alignment, grouping, hierarchy, responsiveness, RTL, step clarity, validation feedback. Do not rewrite working business logic for layout reasons.
- **Tax and discount accept numbers only.** First confirm what each field means in the model (tax rate is a percent with 2 decimals; discount exists as amount and as stored percent — make the UI label explicit: «٪» vs money). Support decimals (tenths/hundredths) where the model does. Normalize Persian/Arabic digits and decimal separators, strip stray characters on paste, use `inputmode="decimal"`; do not rely on `type=number` alone. Authoritative validation on the backend with Persian error messages.
- **نقد / اقساط** becomes a polished segmented toggle with an obvious selected state. نقد: installment fields hidden **and disabled/excluded from the payload and validation**. اقساط: reveal with a short smooth transition (respect `prefers-reduced-motion`). Switching back and forth never leaves stale values affecting submission.

### 6.6 — 2.34.7: Customers UI

- **شماره اقتصادی:** for «حقیقی» it is *hidden completely* (not disabled); for «حقوقی» it appears with a subtle transition. Backend validation follows the selected kind. Stale hidden value: the UI sends nothing for a hidden field; on create the server rejects a non-blank `economic_code` for an individual; on an update from legal → individual, the server clears it explicitly with an audit entry (confirm the choice in Phase 0, as official invoices depend on identity fields).
- Marketers can create and work with **both** حقیقی and حقوقی and get the same type filters in the list. Icons (existing icon set): حقیقی → person, حقوقی → building.
- **Excel import for marketers:** allow authorized marketers to use the existing customer import (reuse its validation/infrastructure), gated through the existing permission modules, enforced server-side. Imported rows are owned by the marketer (consistent with §7 once it lands).

### 6.7 — 2.34.8: Navigation & terminology

- **Back buttons:** audit all detail/view/edit pages; produce a table (page → has back? → destination) in the report; add «بازگشت به فهرست …» where missing, with consistent placement, correct destination, correct RTL arrow direction. Do not duplicate working navigation.
- **Attachment icon:** one consistent paperclip icon (existing icon system) wherever there is a پیوست‌ها area or attachment action.
- **«مرکز تماس» → «مرکز ارتباطات»** in user-facing menus, titles, breadcrumbs, labels, permission-module labels, docs, i18n/label registries (check `common/labels.py`, `auditlog/labels.py`, label-coverage tests). Do **not** rename internal keys/routes/permission ids unless trivially safe, and do **not** alter historical user-generated content or audit-log text.
- **Bulk delete trash:** replace the plain red text button with a professional red trash icon action. After the user confirms **and the backend confirms success**, a short, subtle, non-blocking animation may move the selected rows toward the trash; respect `prefers-reduced-motion`. Never remove rows visually before success; on failure restore state and show the error. Build it as one reusable pattern.

### 6.8 — 2.34.9: Calendars

- Audit every calendar (leads follow-up, orders/legacy orders, after-sales, others). Some months render incorrectly or overlap: find and fix the **root cause**; consolidate duplicated calendar logic into the shared component where practical.
- Tests: all 12 Jalali months, month lengths (31×6, 30×5, Esfand 29/30), leap years, year transitions, first/last weekday alignment, RTL, timezone (Asia/Tehran), no repeated/overlapping cells.
- **Drag across months** for items that already support drag-and-drop: in RTL, holding the dragged item near the **left** edge goes to the **next** month, near the **right** edge to the **previous** month, after a short hover delay (named constant, no accidental switching); the drag stays alive after the switch so the drop can land on the desired day. Persist the new date; on backend failure revert the item and show the error. Provide a non-drag alternative (e.g. «انتقال به تاریخ…» in the item menu) for touch/keyboard users.

### 6.9 — 2.34.10: Settings information architecture

- Settings is crowded. Use the existing «یکپارچه‌سازی‌ها» page as the structural reference: top tabs, one section per tab, clear active state, deep-linkable routes, back button works, RTL, responsive, permitted tabs only, no monolithic component, easy to extend. Derive the grouping from what the page actually contains; do not invent categories.

---

## 7. Big release 2.35.0 — Customer ownership, categories, permissions

Expand-only; read §1 rollback contract.

1. **Customer owner.** Add `Customer.owner` (nullable FK to user, PROTECT) distinct from `created_by`; backfill `owner = created_by` (idempotent data migration). Admin and Sales Manager choose the owner at creation via a searchable selector. A marketer can only create customers for themselves: no selector shown **and** the server ignores/rejects any other owner (test with a manipulated request). Never forge `created_by` to express ownership. Re-check every list/selector/report that scopes by `created_by` (see Phase 0 item 5).
2. **Structured categories.** New `CustomerCategory` (unique normalized name, `is_active`, soft-delete semantics). Add `Customer.category_ref` FK; **keep the legacy text column** (expand-only). Data migration: collect distinct existing `category` values, normalize obvious variants (whitespace, ZWNJ, Arabic/Persian ي/ی ك/ک, digits), create categories, link customers; ambiguous near-duplicates are *reported, not merged*. Forms use a searchable select; list filter uses the FK.
3. **«مدیریت دسته‌بندی‌ها»** action on the Customers page opens a large modal (list, create, edit, delete). Deleting a used category is **blocked with the usage count** and offers deactivate (soft) or reassign — never orphaning customers.
4. **Permissions** through the existing permission modules (e.g. `customers.categories.view/create/edit/delete`, plus import and owner-assignment capabilities as the architecture supports). No second permission system. UI and API both enforce.
5. **Admin global CRUD** across manageable entities, enforced in the domain layer, **bounded by domain safety**: nothing in §6.2 is overridable; issued invoices and anything with ledger/payment effects are corrected by cancel/reissue, not edited or deleted. Document the resulting capability matrix.
6. Sales Manager capabilities (assigning customers, campaign management) exactly as the matrix from Phase 0 says.

---

## 8. Big release 2.36.0 — Campaign architecture

Expand-only; legacy data preserved; flagged in the registry.

### 8.1 Campaign as a first-class entity
New `Campaign`: unique normalized name, status (draft/active/paused/completed/archived), start/end dates (Jalali in UI), channel/source (structured choices), responsible user(s), optional target count and optional budget, description, `is_system`, audit fields. Keep it lean; make it extensible for analytics. **System campaigns** (non-deletable): «ورودی مستقیم», «معرفی», «بدون کمپین (قدیمی)» so that no سرنخ is ever campaign-less and no one invents campaign names from free text.

### 8.2 سرنخ = participation (separate from identity)
- Promote the per-person record (today's `TargetAudienceMember`) to the user-facing **سرنخ**, with: `campaign` FK, assignee (`assigned_to/by/at`), status (new / contacted / engaged / converted / lost + lost reason), `next_follow_up_at`, dates, conversion fields, nullable `customer` FK, and a `legacy_lead` FK for traceability.
- **Identity vs participation:** customer identity stays unique by normalized phone (`CustomerPhone` constraint untouched). Replace the global `uniq_target_member_phone` with **unique (campaign, normalized_phone)**. The same person can be in many campaigns as separate سرنخ without duplicating the customer. Unless the audit proves otherwise, keep the normalized phone as the identity key rather than introducing a new Person table; add a **«احتمال تکراری»** review queue instead of any automatic merge.
- Replace the status derivation: a سرنخ becomes *converted* only by the §4 definition; "already a customer" is shown as a flag, not as conversion.
- `Interaction`, `Quotation`, `Order`, `Sale` get nullable FKs to the سرنخ/campaign; backfill them; leave the old FKs untouched.
- Compatibility: legacy `Lead` rows become a hidden, read-only "legacy batch". Provide selectors/adapters so **all dependents in §3** (kanban, follow-up calendar, reminders, search, timeline, dashboard, assignment history, call-center page, `sales_agent` queue, `Quotation`/`Order` links) operate on سرنخ with no loss of function or history. «نوبت کاری» disappears from the UI. Rename menu items consistently: سرنخ‌ها / صف سرنخ من / تابلوی سرنخ‌ها / تقویم پیگیری.

### 8.3 Creating a سرنخ
A required, **searchable campaign select** (only campaigns the user may use; active ones), with inline «+ کمپین جدید» for permitted users and a clear label of which campaign the سرنخ belongs to. Bulk/Excel add-to-campaign inherits the campaign. Remove the free-text «کمپین یا نوبت» field.

### 8.4 Data migration (the risky part)
1. Group legacy `Lead.campaign_or_batch` by a normalized key (trim, collapse spaces, ZWNJ/ZWSP, ي→ی, ك→ک, Persian/Arabic→ASCII digits, casefold) → one `Campaign` each; blank → «بدون کمپین (قدیمی)». Near-matches that are not identical after normalization are *not* merged; list them in the review report.
2. Each existing target-audience member → one سرنخ in the matching campaign, inheriting the old Lead's assignee/status/follow-up; `LeadAssignmentHistory` preserved/linked.
3. Backfill interaction/sale/quotation/order links; keep `legacy_campaign_label` text.
4. `manage.py migrate_campaigns --dry-run` prints counts (campaigns, سرنخ, links, skipped, ambiguous) and writes the review report; the real run is idempotent. Test on a realistic fixture shaped like TIARA's data.

### 8.5 Sale / invoice relationship
Apply the Phase 0 `Sale` decision. Whatever is chosen: no dead-end «مشتری را مشخص کنید» path; registering a result works from a specific سرنخ (customer derived or created from that person at that moment); revenue and conversion come from invoices.

### 8.6 Hybrid attribution
- Fields on `Invoice` (expand-only): `campaign` FK (nullable), `attribution_source` (`auto` / `manual` / `none`, default `none`), `attributed_by`, `attributed_at`; plus an append-only attribution log (who/when/from→to/reason).
- **Automatic:** when an invoice is created for a customer, attribute in this order: (1) explicit سرنخ/campaign context the user came from; (2) otherwise **last-touch**: the customer's most recent *open* سرنخ with an interaction inside a configurable window (setting, default to be confirmed in Phase 0). Users never re-pick the campaign at each step; quotations, requests and invoices inherit it.
- **Manual:** authorized users can attribute/re-attribute an existing independent invoice for a legitimate reason (reason required). It changes **only** the campaign link — never items, price, tax, discount, settlement, inventory, or ledger. Permission enforced server-side.
- **One invoice → one primary campaign** for financial reporting; no fractional/multi-touch allocation. No double counting, tested.
- `cancelled` invoices (immutable, §6.2) and drafts contribute nothing to valid revenue. Their attribution cannot be edited.

### 8.7 Sidebar group «کمپین‌ها» with exactly three pages
Move the existing «نتایج کمپین» (module `sales`) into the new group; keep a redirect from the old URL; give each page its own permission-module key; `sales_agent` sees only their own campaigns/سرنخ and no finance columns unless permitted.

1. **فهرست کمپین‌ها** — operational management: create/edit/pause/archive/delete (system campaigns protected), name/status/dates/owner/high-level counts. Uncluttered; the shared table component + a good create/edit experience (modal or drawer, your UX judgment).
2. **نتایج کمپین‌ها** — fast management overview, **no redundant «جزئیات» button**; the row and the campaign name are the click targets to a campaign detail view. Columns only if reliably computable: name, status, date range, سرنخ count, converted customers, valid invoice amount, collected, outstanding, conversion rate. A visible «بدون کمپین» row for unattributed invoices. Deep questions are pointed to آنالیز.
3. **آنالیز کمپین‌ها** — a purpose-built report generator, not another dashboard. Start with a polished wizard that builds the question (campaigns: one/many · Jalali date range · marketers · product/category · channel · dimensions · comparison), then generate a management-grade report: funnel (سرنخ → تماس‌گرفته → در تعامل → مشتری → فاکتور معتبر → وصول‌شده), conversion rate, avg time to first contact / to conversion, contact-outcome drop-off, product and marketer performance within the selection, campaign-to-campaign comparison, time series, tables. Keep **recorded sale / valid invoice / collected** visibly separate; unprovable attribution shows `—`. v1 = a fixed set of well-designed report templates behind the wizard (not a generic BI builder); progressive disclosure; Excel and PDF export; fast aggregate queries with proper indexes and no N+1; honest loading/empty/error states.

### 8.8 Tests (minimum)
Campaign CRUD and permissions · سرنخ creation requires a campaign · same person in several campaigns · conversion definition (existing customer joining ≠ converted) · migration dry-run/real/re-run idempotency · auto-attribution (explicit and last-touch) · manual attribution permission + audit + no side effects · no double counting · cancelled/draft excluded · unattributed bucket · results/analysis numbers against hand-computed fixtures · role scoping (sales_agent) · all `Lead` dependents still work · old URL redirect · backward-compat smoke (previous tag on new schema).

---

## 9. Big release 2.37.0 — Warehouse fulfillment request

Expand-only; flagged in the registry.

1. **Meaning change.** The module called «سفارش‌ها» is not a customer sales order. The customer purchase is the **invoice**; this module is an internal **درخواست تأمین از انبار**. Rename user-facing text everywhere (menu «سفارش‌ها» / «تابلوی سفارش‌ها», headings, buttons, messages, reports, dashboard, search, labels, audit labels, docs, tests). Keep DB tables/classes/internal names unless a rename is trivially safe; keep old API paths working via aliases.
2. **Invoice-driven creation.** Add `Order.invoice` FK (nullable only for legacy). Default rule: **one active (non-cancelled) request per invoice** (partial unique constraint); revisit partial shipments later. Creation is allowed only from an **issued** invoice; **customer, campaign, items and quantities are derived server-side** from the invoice, never trusted from the client. Backfill `Order.invoice` from the existing `Invoice.order` link where unambiguous; report ambiguous cases (do not guess). Traceable both ways (links on both detail pages).
3. **Creation wizard** (replaces the customer-first flow; remove the customer-name step): *Step 1* select invoice (searchable; shows number, customer, date, total, status; only issued invoices without an active request) → *Step 2* fulfillment info (source warehouse, requested/expected date, existing required operational fields only) → *Step 3* review invoice items (read-only list; not a pricing screen) → confirmation summary → create.
4. **Immutable pricing.** Remove discount and price inputs/actions from the request UI **and reject them in the API**. Price may appear read-only as a snapshot only where useful and permitted. Commercial changes happen by correcting/reissuing the invoice, then cancelling/recreating the request. A request's item quantities are not edited in place (cancel & recreate). Keep `OrderItem` price snapshots read-only if reports (profit/valuation) depend on them — verify first.
5. **Stock integrity.** Preserve the existing idempotent mechanism (`stock_applied`, `stock_revision`, idempotency keys). Verify `invoice_affects_stock()` semantics so goods are never deducted twice (invoice issue vs request approval) and are returned exactly once on cancel. Default: **cancelling an invoice that has a non-cancelled request is refused** with a clear message («ابتدا درخواست تأمین مرتبط را لغو کنید»); invoice cancellation never leaves an orphan active request.
6. Order board, orders calendar, shipping method/postal tracking (`SalesDocument`) keep working. Tests: starts from invoice · customer/items derived · price & discount rejected on API · one active request per invoice · stock deduct/release once · cancel/recreate consistency · backfill dry-run/idempotency · backward-compat smoke.

---

## 10. Big release 2.38.0 — Real-time

Today the app is gunicorn/WSGI with no Channels/Redis. This release adds infrastructure, so it ships alone with its own rollback notes.

- **Design for the real constraints:** tens of concurrent users, unstable internet (reconnects are normal), per-customer/self-hosted deployments (some without Redis), Iran-friendly (no third-party CDN or SaaS).
- **Architecture:** Django Channels (ASGI) with a Redis channel layer when available. Put the whole feature behind a registry flag; **if Redis/ASGI is absent or the flag is off, Dolphin behaves exactly as today** (graceful degradation: refresh on tab focus and a slow low-frequency fallback poll — not 5–10 s polling as the main mechanism).
- **One authenticated connection per browser session** (shared across tabs via BroadcastChannel/leader tab), session-cookie auth with Origin check, per-user groups; every event is checked for authorization at publish time and never carries sensitive payload — events are tiny (`type`, `id`, `seq`) and the client refetches through the normal REST API so existing authorization applies.
- Publish only after the DB commit (`transaction.on_commit`). Initial events: `lead.assigned`, `notification.created`, `customer.updated`, `invoice.updated`, `warehouse_request.updated`. The bell updates immediately.
- **Reliability:** per-user monotonic `seq`; on reconnect the client sends its last `seq` and receives a catch-up (or a "refetch" hint if the gap is too large); duplicate-event protection; heartbeat; exponential backoff with jitter; connection cleanup on logout/session expiry.
- **Deployment:** ASGI service in compose, Redis service, nginx WebSocket upgrade config, env vars (`DOLPHIN_*`), health checks, runbook updates, and explicit "how to turn it off" steps. Build it as reusable infrastructure (a small publish API in `common/`), and keep it compatible with the incoming-call popup planned in `claude/specs/profile-integrations-voip-prompt.md`.
- **Tests:** Channels communicator tests; user B never receives user A's private events; reconnect/catch-up; duplicate suppression; multi-tab; flag-off and Redis-down behavior; a small load check at ~50 concurrent connections.

---

## 11. Cross-cutting requirements

- **Security:** server-side checks on every new endpoint; audit-log sensitive actions (attribution changes, category deletion, owner assignment, allocation/release, invoice issue/cancel); no secrets in code/logs; direct-API bypass tests for every restriction.
- **Quality:** reuse existing services and components; no duplicated logic; Persian error messages; RTL + responsive verified in a browser at desktop and mobile widths; at least two roles (admin and marketer, plus sales manager where relevant) for permission-dependent UI; no console errors.
- **Performance:** indexes for new filters/joins; aggregate queries instead of per-row loops; no N+1 in new lists/reports.
- **Checks to run (per release):** tests for the touched code, then the full suite before a big release; `makemigrations --check`; `manage.py check` (and `--deploy` for big releases); configured linters/formatters/type checks/build; migration forward on a realistic fixture and re-run of data migrations (no change); the backward-compat smoke test for big releases.
- **Docs:** CLAUDE.md, changelog, `docs/`, runbook, API schema, feature-registry docs, user/admin guides in Persian where existing user docs are Persian.

---

## 12. Final report (after each big release and at the end)

1. What changed (by version) · 2. Architectural decisions · 3. Campaign/participation/attribution model as implemented · 4. Migrations and exactly how old data was handled (counts from the dry-run and the real run) · 5. Attribution and metric rules implemented · 6. Payment-allocation and invoice-issue root causes and fixes · 7. Warehouse request changes · 8. Permission changes · 9. Real-time architecture and deployment steps · 10. Significant files modified · 11. Tests/checks **actually run** and results · 12. Issues found outside scope · 13. Rollback instructions per version (last known good, backup step, flag to disable) · 14. Remaining risks and follow-ups (including the deferred "contract" cleanup of legacy columns).

**Final principle:** Dolphin is a long-term commercial CRM. Build durable architecture, not patches, and keep the flow understandable: **Campaign → Lead → Customer → Invoice → Warehouse Fulfillment Request → Payment/Settlement**, with the same person able to take part in several campaigns through separate lead records and with reliable, auditable campaign attribution.
