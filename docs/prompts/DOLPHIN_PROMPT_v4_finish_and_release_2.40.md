# DOLPHIN — Prompt v4: finish everything that is open, add the 8 new UI items, release as 2.40.x

> For Claude Code. Current version: **2.39.27**. This prompt **supersedes the open items** of `DOLPHIN_MASTER_PROMPT_v2.md` and `DOLPHIN_PROMPT_v3_*.md`; where those files conflict with this one, this one wins; where `CLAUDE.md` is more specific than this prompt, `CLAUDE.md` wins.
> All file:line references come from an audit of 2.39.27. **Re-read the code and confirm each one before changing it** — lines may have moved.
> Never write the name of the UI-kit vendor in any first-party file (a test enforces it).

---

## 0. Operating protocol (read first, obey strictly)

### 0.1 Ask everything FIRST — in Persian — then never ask again
Before touching any code, read the repo, then send **one single message in Persian** that asks every question you still have (see §0.2 for the ones I already know you need). Wait for the answers. From that moment on:

- **Do not ask anything in the middle of the work.** If something is ambiguous later, pick the safest option consistent with this prompt, record it in the final report under "Decisions taken", and keep going.
- If I don't answer a question, use the **default** written next to it and say so in the final report.
- Questions must be short, numbered, answerable in one line, written in Persian. No questions about things you can find by reading the repo.

### 0.2 Questions to ask in that first message (with defaults)
1. Git: which **remote** and **branch** do I push to? *(default: `origin`, a new branch `release/2.40`; never force-push; never push to `main`/`master`).*
2. Is it OK to push after **every** section's version (one commit + one annotated tag per version), or only at the end? *(default: after every version)*.
3. Image: which **registry/path and naming** for the final image? *(default: `dolphin-app:2.40.N`, saved with `docker save` if no registry is given)*.
4. Test server: **host, user, SSH key path or registry credentials, directory, compose project name**, and whether I may SSH to it from here. *(No default: if access is impossible, do everything except the upload and hand me the exact commands — see §6.)*
5. Test server database: may the deploy run migrations automatically after the backup? *(default: yes, after `pg_dump` backup)*.
6. Merged postal integration name: use **«سرویس پست»** with subtitle «پست ایران — بازار الکترونیک»? *(default: yes)*.
7. Dashboard: should widgets be allowed to **overlap-push** (others move down automatically when you drop one on them) or **refuse the drop**? *(default: push others down, then compact upward only on "Tidy up" button — never automatically)*.
8. Sub-campaign budget: parent over-budget is a **warning** or a **hard error**? *(default: warning, as today)*.

### 0.3 Versioning law (non-negotiable)
- **Only `2.40.x`.** Start at **2.40.0**. **You may never create 2.41.0 or higher.** If you run out of numbers or the plan would need 2.41, stop adding versions, merge the remaining work into the last open `2.40.x` patch (squash its changelog entry), and say so in the report. The maximum allowed is `2.40.99`.
- **2.40.0 = the one big atomic mechanism release** (§1 groups A–E): everything that changes models, services, permissions, analytics semantics or migrations. It must be **expand-only** (new nullable columns/tables, no drops), data migrations **idempotent with a dry-run**, new behaviour behind existing feature flags where one exists, and **rollback to 2.39.27 must work** (rehearse it on a copy of data: restore backup → run 2.39.27 code → app boots, pages open). Write the rehearsal result in the changelog entry.
- **2.40.1, 2.40.2, … = one cosmetic/UI item each** (§2 items 1–8, §3 cleanups). One item → one version → one commit → one tag → one Persian CHANGELOG entry. Never mix two items in a version.
- Bump `VERSION` only (the single source). Tag format as existing tags.

### 0.4 The per-section cycle (repeat for every version)
1. Re-read the relevant code and tests; write down the root cause or the design in 3–5 lines in the commit body.
2. Implement the smallest correct change. Reuse shared components (`ui/…`, segmented, checklist-select, dialogs, icons table); no copy-paste forks.
3. Add/adjust tests **for this section** (see each item's "Tests"). Do not weaken or delete an existing valid test; fix stale tests to the new real behaviour.
4. Run the **narrow** tests for the touched apps, then `python manage.py check`, `makemigrations --check --dry-run`.
5. **Verify in a real browser** (Playwright/Chromium against `config.devcheck_settings` or the compose stack): desktop 1440, tablet 1024, phone 390; light **and** dark theme; RTL; reduced-motion on/off. Save before/after screenshots under `docs/release-evidence/2.40.N/` (small PNGs, not committed if >200 KB each — keep them in the report instead).
6. CHANGELOG entry in Persian (what was added/changed/removed/fixed, migrations, rollback note), bump `VERSION`, commit, tag, **push** (per the answer to Q1–Q2).
7. Only then start the next section.

Never claim a test passed that you did not run. Never fabricate output. Anything you could not verify goes under "Unverified" in the final report.

### 0.5 Repo hygiene first (before 2.40.0, as its own patch commit inside the same release branch — no version bump of its own; fold its CHANGELOG line into 2.40.0)
- `.gitattributes` is already `* text=auto eol=lf`: run a one-time **renormalize** in a **separate commit** so later diffs are readable, and confirm `.sh` files are LF (11 deploy/quickstart tests fail today only because of CRLF checkouts).
- Move the prompt/handoff `.md` files from the repo root into `docs/prompts/`; delete `Claude outputs/`, `codex-plugin-cc-probe/`, empty `wheels/`, `.scratch/`.
- `.dockerignore`: add `manifest.json` (signed customer manifest must **never** be baked into an image), `config/devcheck_settings.py`, `.claude/`, `docs/`, `*.md` (except what the build needs), `.scratch/`, `Claude outputs/`, `codex-plugin-cc-probe/`, `wheels/`; remove the entry for the non-existent `.editorconfig`.
- Make the one flaky test (`test_free_port_skips_a_port_already_bound`) deterministic.

---

## 1. Everything still open from the previous reviews → release **2.40.0** (one atomic version)

Definition of done for every line: a **test that fails before and passes after**, and the behaviour seen once in the browser/API as the correct role.

### Group A — Campaign ↔ person ↔ customer ↔ invoice chain (the business flow)
Business flow to make true end to end: *manager creates campaign (+ sub-campaigns, multi contact-ways) → persons in it → marketer sees only own persons, logs calls → first valid invoice makes the person a customer → invoice is attributed to the campaign → marketer picks own invoices and files a supply request.*

A1. **Person becomes a customer automatically on invoice issue.** Today only the manual button/endpoint exists (`POST campaign-members/{id}/customer/`, `campaign_views.py:410`); issue (`billing/services.py:~1479`) only calls `attribute_issued_invoice`. Required:
- In the invoice wizard step 1, the customer picker must also accept a **campaign person** ("انتخاب از اشخاص کمپین"): choosing one finds-or-creates the customer by normalised phone (owner = the person's responsible marketer) **inside the invoice-create transaction** and links `member.customer`, sets member status to customer, writes the activity log.
- On **issue**, if the invoice's customer matches a campaign member by normalised phone and that member is not yet linked/converted, link it (idempotent, savepoint, failure logged, never blocks issue).
- Keep the manual endpoint working. No duplicate customers ever (phone uniqueness is the key; test with formatting variants `0912…`, `+98912…`, Persian digits).
A2. **Marketer can log a call on a person assigned to them from the UI/API.** `InteractionSerializer` (`serializers.py:~465`) restricts `lead` to `leads_for(user).filter(assigned_to=user)` while the container lead has no assignee → 400. `interactions.js:~85` posts `lead = member.lead`. Fix by authorising through `member.assigned_to == actor` (accept `target_member` as the primary key of the request), and fix `interactions_for` (`selectors.py:~103`) so the marketer **sees the calls they logged**; fix the post-create redirect (no 404). Add a **role-based API test** (marketer), not just a service test.
A3. **Container leads (`source="campaign"`) must stop leaking** into: legacy lead list/API (`leads_for`, `LeadViewSet`), dashboard lead-conversion gauge, reminders, lead search, kanban. Exclude them centrally in one selector.
A4. **Global search finds campaign persons** (`common/search.py`, add a member source scoped by `members_for(user)`; show campaign name + responsible).
A5. **Old lead creation must require a campaign** (`create_lead`, `LeadSerializer`, legacy target-audience path `services.py:~1186`): a campaign-less new lead/person is invalid (existing campaign-less rows keep working).
A6. **Old `POST /api/v1/sales/`** still dead-ends for campaign persons (`services.py:~794`). Decision: make the endpoint refuse with a clear Persian message pointing to "فاکتور جدید" (410/400) instead of the misleading «مشتری را مشخص کنید»; keep read/list/cancel of historical sales. Fix `seed_synthetic_uat.py` accordingly.
A7. `PATCH /leads/{id}/ {"customer": null}` on a customer-less lead returns **500** (`services.py:~503`, `None.pk`) → return 400/no-op.
A8. Campaign form: **edit** form for existing campaigns (name, dates, budget, target, responsibles, **contact ways as checkboxes**, status) — today channels cannot be changed after creation. At least one contact way required (client + server).
A9. Sub-campaign rules still open: `create_campaign` must refuse a child under a parent that already has direct members/container (or migrate those members into an auto «بدون زیرکمپین» child, your choice — document it); depth ≤ 2 also as a **DB-level or model `clean`/`save` guard**, not only in the service; parent `target_progress` and `budget` must roll up from children (`campaign_analytics.py:~147`).
A10. `_mark_converted` (`campaign_attribution.py:~67`) must not mark `was_customer_on_entry=True` members as converted (contradicts the module docstring) — fix the code or the docstring + analytics wording, but make them agree and tested.
A11. `migrate_campaigns` (`campaign_migration.py:~88`): `by_key` must be restricted to top-level campaigns (`parent__isnull=True`); dry-run must not count the legacy system campaign as "to create"; make reverse migrations of `sales/0031` and `0032` safe (or document and guard them so a rollback to 2.39.27 can never crash: tolerate NULLs, keep the old unique constraint off).

### Group B — Reports/analytics a manager can trust
B1. Results + analysis: add the **«بدون کمپین» row** (issued valid invoices with no attribution) and an **«مانده» column** (`valid − collected`) everywhere totals appear (page, Excel, PDF/print). Totals of rows must equal company totals — add a reconciliation test.
B2. **Funnel is monotonic and ends in money:** members ⊇ contacted ⊇ engaged ⊇ converted ⊇ valid invoice ⊇ collected. Derive each step as a subset of the previous (today `engaged` can exceed `contacted`, `analytics.py:~125`). Add two money steps.
B3. **Date semantics labelled and consistent:** members by entry date (cohort), money by issue date; put a visible info tooltip on each KPI/chart title; same filter object feeds every card.
B4. Zero-fill months with no invoices in the Jalali series; `null` must never render (use «—» only for "no data"); avg first-contact time must handle back-dated calls without silently dropping them (show count of excluded rows).
B5. Results/analysis polish: whole row clickable; analysis page gets loading skeleton, visible error state (`#analytics-error` is never shown today), empty state, and campaign filter via checklist; invalid typed date shows an error instead of being ignored.

### Group C — Money (highest sensitivity: be paranoid)
C1. `record_manual_paid_entry` (`billing/services.py:~1637`) has no status check: only ISSUED, non-cancelled invoices; reject draft. Manual settlement must not block real allocation: `allocate_payment` (`payments.py:~672`) must use the canonical balance, and releasing an allocation on a manually settled invoice must keep state consistent.
C2. **Lock order everywhere = payment → allocations (by id) → invoices (by pk ascending).** Fix `release_allocation` (`:~711`, locks allocation→payment→invoice), `cancel_payment`, `update_payment` loops (`:~802/818/918`). Add a **concurrency test running on PostgreSQL** (threads/processes): concurrent release vs cancel of the same payment; two cancels sharing invoices; opposite-order splits. No deadlock, correct totals.
C3. `check_allocation_integrity`: also verify same-customer across payment/allocation/invoice, allocations on cancelled/non-confirmed payments, `paid_amount ≤ total`, installments sum; `--fix` must stay opt-in and dry-run by default.
C4. Cancelled-invoice immutability: also guard `bulk_create/bulk_update` on `Invoice`, `PaymentAllocation`, `Installment`, `InstallmentPlan` and updates (not only creation).
C5. Duplicate-number detection (`services.py:~281`): `"number" in name and "uniq" in name` also matches `invoice_official_number_unique` → compare against the **exact constraint name(s)**; same for the SQLite fallback. Test both constraints give different messages.
C6. Allocation API: the single-allocate endpoint must accept/require the same `request_key` as `allocate-across`; make `request_key` + payment **unique at DB level** (partial unique index on non-empty keys) and return 409/the original rows when the same key arrives with different splits instead of silently returning old rows.
C7. Supply requests: re-check the legacy `Invoice.order` link at **confirm/transition** time too (`transition_order`, `~857`) and in `issue_invoice` (`~1432`); write the **data backfill** for legacy `Invoice.order` → `Order.invoice` (idempotent, dry-run, report); cancelling a FULFILLED/CONFIRMED request requires `inventory.manage` (today any document writer can return stock).
C8. Release/Cancel reasons already stored — expose them in the payment detail timeline.
C9. «مانده دریافت» in the create form preview must come from the server (no second calculation in JS); use integer arithmetic in `allocation-preview.js`.

### Group D — Security & real-time (only matters when `realtime` is on; default stays off)
D1. **Listener reconnect** must broadcast `resync` (`realtime.py:_listen_forever`), otherwise events during a DB outage are lost.
D2. **Per-user eviction ping-pong:** with ≥4 tabs, evicted tabs reconnect and evict each other, each reconnect = full list reload. Make the cap a setting (`REALTIME_MAX_PER_USER`, env documented), evicted streams get a terminal `bye` event (client must **not** auto-reconnect on it), hidden tabs release their stream (reconnect on visible), optional leader-tab via `BroadcastChannel` so N tabs = 1 stream.
D3. nginx `limit_conn` is **per IP** (6): offices behind NAT get 429. Make it a documented variable and raise the default sensibly, key it on `$http_cookie` session hash or user header if feasible.
D4. `/api/v1/realtime/health/` is unauthenticated and publicly proxied → restrict to internal network/healthcheck only (nginx `allow`/`deny`, or move under an internal-only location) and return nothing sensitive; report **real** listener health (connection alive), not just "started".
D5. Check `Origin`/`Sec-Fetch-Site` on the stream; reject cross-site.
D6. Server-side coalescing/debounce of NOTIFY per (kind, user-set) for bulk operations (import of 5000 rows must not produce 5000 NOTIFYs).
D7. Owner assignment API: reject `AFTER_SALES` workstream owners (done) — add the missing audit detail (old/new owner) if not yet present.
D8. Dockerfile `COPY . .` + hardened `.dockerignore` (see §0.5); add a CI/test assertion that `manifest.json` is excluded.

### Group E — Navigation structure (not only names)
E1. Build the sidebar from **one data registry** (list of groups/items with label, url name, icon, required capability, order) consumed by `base.html`, breadcrumbs, page eyebrows, `<title>` and global search. No hard-coded duplicates left in templates.
E2. Target structure (process order, ≤ 9 top-level entries, ≤ 6 items per group):
**داشبورد · کمپین‌ها (فهرست، نتایج، تحلیل) · سرنخ‌ها و پیگیری (سرنخ‌ها، تقویم، تابلو، تماس‌ها) · مشتریان · فروش (فاکتورها، درخواست‌های تأمین، تابلوی تأمین) · انبار و کالا (موجودی، انبارها، گردش انبار، محصولات، دسته‌بندی‌ها) · مالی (دریافت‌ها، پرداخت‌ها، چک‌ها، اقساط) · پس از فروش · ارسال و پست · ارتباط (پیامک، گفتگو) · گزارش‌ها · تنظیمات**. Adjust only where the code proves a better grouping, but keep process order (campaign → lead → customer → invoice → supply → finance). Fold «فروش‌های ثبت‌شده» into Invoices (historical-sales tab) or into a «بایگانی» sub-item; there must be **one** «نتایج».
E3. Section captions must equal group names; use **تحلیل** consistently (was «آنالیز»); remove every «مرکز ارتباطات» (menu, `module_permissions.py`, `profiles/adapters.py`, `users.js`, `ui_views.py`); page title = menu label = breadcrumb.
E4. **In-page tab bars** (shared component, URL-addressable via `?view=` or sub-path, RTL arrow keys, `role=tablist`): leads (فهرست/تقویم/تابلو), supply requests (فهرست/تابلو), campaigns (فهرست/نتایج/تحلیل), after-sales (فهرست/تقویم). Old URLs keep working (301 or same view).
E5. Tests: per role, menu items == permission matrix; no duplicate labels in a role's menu; ≤ 6 items/group; breadcrumb/eyebrow/title equal menu label.

> **Release 2.40.0 gate:** full narrow tests of campaigns, sales, billing, accounts, common; PostgreSQL concurrency tests; migration forward on a copy of 2.39.27 data and **rollback rehearsal**; role-based end-to-end test of the 5-step business flow (below, §5). Only then tag 2.40.0.

---

## 2. The 8 new items → one version each (2.40.1 … 2.40.8, in this order)

Design language for every item: Persian RTL first, existing design tokens (`--dolphin-*`), light + dark, no vendor name, no external CDN/font, `prefers-reduced-motion` respected, touch targets ≥ 44 px, visible focus rings, WCAG AA contrast, no layout shift. Reuse existing components; add one shared component only if none exists.

### 2.40.1 — Top-bar search: expanding input (like the board cards' motion)
- Find the **board card open/expand animation** (kanban cards in `lead-board.js` / `order-board.js` + their CSS) and reuse the same easing, duration and keyframe approach.
- Clicking the search icon in the top bar (`#global-search-toggle`, `base.html:~205`, `shell/search.js`) **expands a field sideways in place** (toward the inline-start, i.e. leftwards in RTL), pushing neighbouring top-bar items (never covering them), icon stays as the field's leading glyph. **Height and vertical alignment equal the top-bar items** (use the same CSS variable as the bell/avatar buttons, no magic numbers). Collapses on Esc, on blur-when-empty, and on the close glyph.
- Results panel opens **under the field**, same width as the expanded field (min 360 px, max viewport − gutters), grouped results as today.
- **Behaviour must stay exactly as good as before:** live search with debounce (keep current value), in-flight request cancellation (`AbortController`), stale-response guard, Persian/Arabic digit and ی/ي/ک normalisation, keyboard navigation (↑ ↓ Enter, Esc), `Ctrl/⌘+K` opens and focuses, empty state, error state, result counts, scoped results per permission. On phones (< 576 px) the expanded field takes the full bar width and overlays the other items.
- Accessibility: `role="combobox"` + `aria-expanded`/`aria-controls`/`aria-activedescendant`; focus returns to the icon on close; announce result count politely.
- Tests: JS/DOM tests for open/close/Esc/blur, digit normalisation, request cancellation; browser screenshots at 3 widths in light/dark; existing search tests must keep passing untouched.

### 2.40.2 — Dashboard: true cellular grid with per-widget minimum sizes
Today: 12-column grid, `grid-auto-flow: row dense`, positions in `UserDashboardLayout.widget_positions` (see `dashboard.js` ~1137), and some widgets break when small (the «روند فروش ۱۲ هفتهٔ اخیر» chart).
- **Cell model:** 12 columns × fixed row unit (e.g. 40 px) — each widget stores `{col, row, w, h}`. A widget may be dropped **anywhere** (any free cell, including leaving gaps). Collisions: per Q7 default — push colliding widgets down (never overlap), never auto-compact upward except via a «مرتب‌سازی» button.
- **Widget registry** (single source, in JS and mirrored/validated server-side): each widget type declares `defaultSize`, `minW/minH`, `maxW/maxH`, `resizable`, and `compactVariant` threshold. Examples (tune after measuring): KPI tiles min 3×4; the 12-week sales trend min **6×9** (and never below the height at which axis labels + legend fit); tables min 6×8; gauges min 3×6.
- **Enforcement in three places:** (1) resize handles clamp at min/max and show a subtle "minimum size" feedback; (2) the server **clamps or rejects** saved sizes below min (serializer validation + migration of old saved layouts: raise undersized widgets to min, resolve overlaps); (3) every widget renders correctly at its min size — use container queries / `ResizeObserver` to switch to a compact variant instead of overflowing; **no chart may overflow, clip labels or render NaN** at any allowed size.
- Edit mode: drag handle, resize handle (corner, RTL-aware), keyboard moves (arrow keys + Enter), live ghost placeholder showing the target cell, snap to cells, drop highlight, undo (Esc), "Reset to default" and "Save" (draft state not persisted until Save). Mobile (< 768 px): single column, ordered by row then col; edit mode disabled with a message.
- Per-user layout persisted as today (expand-only migration; keep reading old `widget_sizes/positions`; write new fields; rollback-safe).
- Tests: registry min/max validation; server clamps undersized widgets; migration of an old layout; Playwright test that renders **every widget at its min size and at 2× min** and asserts `scrollWidth ≤ clientWidth`, no console errors, chart has ≥ 1 visible data point; drag/resize e2e.

### 2.40.3 — Dashboard widgets: modern KPI cards (match the attached reference)
Reference (dark theme, 4 cards in a row): rounded card (≈14–16 px radius, 1 px border, **no glow**); top-start: **icon in a rounded-square tinted tile** + **title** beside it; top-end: a small **delta chip** (e.g. «+۱۲٫۴٪» green, «۷ باقی‌مانده» amber, «۶ مورد جدید» cyan); under the chip a smooth **sparkline** in the same hue as the icon; bottom: the **big bold number** (with unit like «مت» = million toman) and one muted **caption line** («نسبت به شهریور»، «ارزش ۸٫۱ میلیارد»، «میانگین ۳۰ روز»، «۳ مورد با اولویت بالا»). In RTL the icon/title sit on the right, chip and sparkline on the left.
Build it as **one `kpi-card` component** with data contract `{icon, tone, title, value, unit, delta{value, direction, tone}, sparkline[], caption, href}`:
- Tones map to a fixed palette (success/warning/info/violet/neutral) with AA contrast in light and dark; tinted tile = tone at 12–16 % alpha; sparkline = single stroke + very soft fill (≤ 10 % alpha), no shadow.
- Number: `tabular-nums`, Persian digits, abbreviated with unit, full value in tooltip and `aria-label`; delta chip has an arrow icon + sign, not colour alone; whole card is a link when `href` is set, with hover = border colour change only (no lift/shadow).
- Sparkline: 12–30 points, no axes, last-point dot, `role="img"` with text alternative; hides gracefully when < 3 points; respects reduced motion (draw-in animation off).
- Apply to all existing KPI/tile widgets; **delta and sparkline data come from the server** (real previous-period comparison and real series), not invented. Where no comparison exists, omit the chip instead of faking it.
- Remove the remaining coloured glow on kanban boards (`dolphin.css ~1764`), stale "glow" comments (`dashboard.js:~740`), and invalid vendor `box-shadow: false` declarations in `dolphin-theme.rtl.css`.
- Tests: component unit tests (tones, RTL, missing data), contrast test computing ratios for every tone in both themes (≥ 4.5:1 for text), screenshot comparison against the reference layout.

### 2.40.4 — Modern login page with animations
- Redesign `common/templates/common/login.html` + `features/login/login.js` + CSS: split layout (brand/illustration panel + form card), brand name/logo from the branding settings, tasteful **CSS-only** animated background (soft moving gradient/blobs or slow particle lines — GPU-friendly `transform/opacity` only), staggered entrance animation of logo → title → fields → button, animated focus states on inputs (floating labels), password show/hide toggle, Caps-Lock warning, inline error shake (plays once), button **loading state** on submit, success transition before redirect.
- Must be **fully self-contained** (no external fonts/scripts/images; inline SVG), light + dark, RTL, responsive (form card only on phones, background simplified), `prefers-reduced-motion` → no motion at all, WCAG AA.
- **Do not change the contract:** same form field names, CSRF, `next` handling, error messages, lock-out/rate-limit behaviour, autofocus and password-manager friendliness (`autocomplete="username"/"current-password"`).
- Tests: existing login tests untouched and green; add a test that the page makes zero external requests, that reduced-motion removes animations, and that a failed login shows the error accessibly (`role="alert"`).

### 2.40.5 — New-invoice wizard: payment type toggle
In `common/templates/common/invoices/list.html:~178` and `features/billing/invoices.js`:
- **Remove the visible words «نوع پرداخت»** above the control (keep an accessible name via `aria-label`/visually-hidden text, and keep the label in the review step summary which already reads it from the field).
- The **نقدی / اقساط segmented toggle is centered** in its step (full-width row, `justify-content:center`, comfortable width, larger hit area).
- When «اقساط» is selected, the **installment inputs appear directly under the toggle** (down payment, count, first due date, interval days) in a 2-column grid with the existing reveal animation; when «نقدی» they collapse and are disabled/un-required/`inert` (keep current behaviour and payload branching).
- Tests: DOM test for toggle → reveal → payload; keyboard (arrow keys on radiogroup); RTL screenshot.

### 2.40.6 — Settings → «نمایش پنل»
In `common/templates/common/settings/settings.html` (display tab):
- **Every option's heading is bold** (`fw-bold`; consistent size/spacing across all groups).
- **Currency unit (تومان / ریال) becomes a toggle** (the shared segmented component, **larger** than the current radios: min height 44 px, text ≥ 1rem), same field name `currency_unit` and same save/preview behaviour. Keep the helper text that all amounts are stored in rial.
- Tests: form submit still sends `currency_unit`; segmented has radiogroup semantics; screenshot.

### 2.40.7 — Merge «پست ایران — بازار الکترونیک» and «سرویس پست» into one integration
Today they appear as two things (`common/integrations.py` `_post_status/_post_details`, `settings/integrations.html`, `sales_documents/post_provider_settings.html`, `sales/ebazar.py`, `sales/postal.py`, `sales/postal_provider`).
- **One** integration card/key/capability/settings page named per Q6 (default «سرویس پست», subtitle «پست ایران — بازار الکترونیک»). It contains **all** options in one place (credentials, service address, service type, wallet/credit info, test connection, enable/disable, manual-vs-connected mode, tracking sync settings). Remove the duplicate entries from the integrations list, settings tabs, search and permissions; migrate any stored settings/permissions idempotently (expand-only) and keep old URLs redirecting.
- **Every postal status gets its own icon** (single table `POSTAL_STATES` → icon + tone + label, one place to change; already half exists near `integrations.py:~93`). Verify each state has a **distinct** icon and show them in: shipment list, detail, filters, timeline, dashboard widget, reports. Add a test that every state has an icon, no two states share one, and every icon exists in the icon set.
- Tests: settings save/test endpoints unchanged in contract; permission mapping; redirects; icon-table test.

### 2.40.8 — Icons beside «حقیقی» / «حقوقی» everywhere
- One helper only: Django template tag/filter `{% customer_kind kind %}` and JS `customerKindBadge(kind)` that output **inline SVG + label**, with `width:1em;height:1em; vertical-align:-0.125em; fill/stroke:currentColor` so the icon always **matches the surrounding font size and colour**. Person icon for حقیقی, building icon for حقوقی (existing icon set).
- Replace **every** place the words appear: customer list, detail, filters/segmented switch in create/edit forms, import/export dialogs, invoice wizard review, invoice detail/print, receivables and ledger reports, campaigns/person tables, global search results, dashboard widgets, any tooltip/chip. `grep` the whole repo (templates, JS, Python label tables, report PDFs) and list each replaced location in the commit body.
- Excel/CSV exports keep plain text (no icons).
- Tests: a **static test** failing if «حقیقی»/«حقوقی» appear in templates/JS outside the helper/label table; DOM test for size = font size; a11y: icon is decorative (`aria-hidden`) because text is present.

---

## 3. Remaining UI/UX debt (fold each into the *nearest* 2.40.x item above, or as extra patches 2.40.9+, never 2.41)

1. Checklist-select: empty-search state, Persian digit/ی-ي normalisation in search, search typing must not mark the wizard dirty, counter text «هیچ‌کدام (یعنی همه)» only where true, options changed from code resync, proper CSS (no fixed 200 px search), mobile layout.
2. Non-stepper dialogs: 9+ still have a redundant «انصراف» (`campaigns/list.html`, `campaigns/detail.html`, `orders/list.html:151`, `payments/cheques.html`, `leads/detail.html`, customers import/export, `sms/outbound.html`, profile dialog, `calendar.js:237`, `person-profile.js:1165`) → remove and give them a **dirty guard**; backdrop closes only when mousedown+mouseup are on the backdrop (stepper-only today).
3. Bulk delete after realtime refresh: drop selected ids that disappeared, call `updateToolbar` after redraw (`ui/lists.js`), trash icon + confirm per original spec.
4. Calendar duplication: ~186 identical lines between `lead-calendar.js` and `after-sales-calendar.js` → `createJalaliCalendar(options)` in `ui/calendar.js`; drag-direction comment vs behaviour consistent; fix `toISOString()` on local dates.
5. Settings tabs: `history.pushState` + `popstate` + arrow-key roving tabindex.
6. 17 `type="number"` inputs (discount, rates, quantities, weights…) → shared decimal input accepting Persian digits and «٫».
7. Manual-settlement endpoint `manual-paid/` documented or removed from the UI surface.
8. Leftover wording sweep (menu, eyebrows, placeholders) after E-group naming.

---

## 4. Test plan (per version, then global)

- **Per version:** narrow tests (touched apps) + `check` + `makemigrations --check` + browser evidence (§0.4). Do not rerun the whole suite after every cosmetic patch.
- **Before the release candidate:** full suite on sqlite (`python manage.py test --settings=config.test_settings`, serial) **and** the PostgreSQL job: all tests, including lock/concurrency tests (skipped ones that are SQLite-specific stay skipped), real `LISTEN/NOTIFY` + SSE smoke (2 users, resync after listener restart, eviction, health restricted), and `check --deploy` with the production settings module.
- Baseline today: 3204 tests, 11 failures (CRLF `.sh` only) + 1 flaky port test. Final target: **0 failures, 0 errors**, skipped only where documented.
- **Role-based end-to-end test (must exist and pass) — the 5-step flow:**
  manager creates campaign + 2 sub-campaigns with 3 contact ways ticked → imports 20 persons, assigns 10 to marketer M → M sees only his 10, logs a call **through the API as M** → M creates an invoice choosing a campaign person → the person is now a customer (visible in customers, no duplicate) → invoice issued, attributed to the sub-campaign, appears in results with «بدون کمپین» row and «مانده» column reconciling to company totals → M selects 3 own issued invoices and files a supply request (one `SB-…` batch) → finance allocates a 20 M receipt as 4 × 5 M to one invoice, double-submit creates no extra row, «مانده دریافت» correct, cancel of the invoice blocked while allocations exist.

---

## 5. Final release (after the last 2.40.x is tagged)

1. Final version = the last `2.40.N`. Confirm `VERSION`, CHANGELOG, tags and that **no 2.41** exists anywhere.
2. Run the complete test plan of §4. If anything fails, fix it in a new `2.40.N+1` patch (within the 2.40.99 ceiling), rerun.
3. Build the **release image** from a clean checkout of the tag (`docker build`, tag `2.40.N`, plus the digest). Smoke-test the image locally: container boots, `migrate --plan` clean, `/health` OK, static assets present, `manifest.json` **not** in the image, no dev settings in the image, image size reported.
4. Take/verify the **backup step** and **rollback command** (to `2.39.27`) and include both in the output.
5. **Upload to the TEST server only** (host from Q4): push to the registry or `docker save | ssh … docker load`, copy compose/env templates only if changed, never print secrets, never touch TIARA/production or any host not named in Q4.
6. Do **not** run the deploy yourself unless I allowed it in Q4/Q5; **give me the exact deploy command(s)** from `docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md` / `scripts/deploy.sh <image-tag>` with real values filled in (host, tag, compose project), the pre-deploy backup command, the post-deploy smoke checks (URLs, `showmigrations`, `check_allocation_integrity`, `migrate_campaigns --dry-run` report), and the rollback command.
7. If SSH/registry access turned out to be impossible, still produce the image + `docker save` tarball path/checksum and the full command list, and say plainly what was not uploaded.

---

## 6. Final report (only this format, short)

- **Changed:** one line per version `2.40.0 … 2.40.N` (what + migration yes/no).
- **Issues:** newly found problems, `[file/component] problem → consequence → fix`.
- **Checks:** exactly what ran and the result (sqlite, PostgreSQL, browser, rollback rehearsal, image smoke). Counts of tests before/after.
- **Unverified:** anything not proven.
- **Decisions taken:** every default you applied because a question stayed unanswered.
- **Blockers:** or "None".
- **Next:** the deploy command block (test server), backup and rollback commands.
