# Person Profile, Integrations Framework and Asterisk Connector — Phase 0 plan

Status: **approved 2026-09-27** — every recommendation (D1–D21) accepted as
written. Implementation progress: Phase 1 in 2.19.0, Phase 2 in 2.20.0, Phase 3 in
2.21.0 (`docs/backend/INTEGRATIONS.md`), Phase 4 in 2.22.0
(`docs/backend/TELEPHONY.md`), Phase 5 in 2.23.0 (`docs/ops/ASTERISK_GO_LIVE.md`) (see
`CHANGELOG.md`; the page contract is `docs/backend/PERSON_PROFILES.md`). Written 2026-09-27 against
`main` at `0d0c878` (v2.18.9).
Deployed: Nerkhbaan (staging) 2.23.0 (2026-09-28, new features not yet in its manifest), TIARA (production) 2.18.0.

Sections: 1 findings · 2 inventory of today's detail pages · 3 data sources ·
4 infrastructure · 5 existing integration code · 6 proposed design ·
7 open decisions · 8 phases, versions and checks · 9 risks.

---

## 1. Findings that shape the design

- **One deployment, one database.** There is no tenant column anywhere; every
  customer is a separate install. The integrations framework is designed
  per-deployment, with nothing that would prevent a tenant key later.
- **Feature registry** (`common/deployment/registry.py`, `FEATURE_DEPENDENCIES`)
  plus an Ed25519-signed manifest per deployment. A new feature is off on TIARA
  until TIARA's manifest is **re-signed** with it — the signing key exists only
  on this development machine (last session's scratchpad `tiara-keys/`). That
  key should be moved somewhere deliberate before it is needed.
- **Permissions** are capabilities per role (`accounts/access.py`) with a per-user
  Read/Edit/Delete matrix (`accounts/module_permissions.py`); object scope lives
  in each module's `selectors.py`. New modules follow the same three controls.
- **Dependencies are hash-pinned** (`requirements.txt`, `--require-hashes`) and
  resolved in a clean Linux CPython 3.13 image. That image is now available (the
  release images are built in WSL Docker), so adding a reviewed dependency is
  possible — but each one is a decision (see §7).
- **No field-level encryption exists.** `SmsProviderSettings.token_password` and
  `PostProviderSettings.api_key` are stored in plain text, as a documented gap;
  `cryptography` was deliberately not added (manifest verification is an in-repo
  RFC 8032 verifier).
- **No background-job framework** (no Celery/RQ/Redis). Jobs are management
  commands run as one-shot Compose services (`--profile maintenance`) from the
  host's crontab. Long-running processes are Compose services with
  `restart: unless-stopped` (`web`, `nginx`, `backup-agent`).
- **No real-time transport.** Chat, badges and reminders poll. Gunicorn runs
  3 workers × 4 threads (since 2.18.9); the cache is file-based.
- **Protected, uncommitted work in the tree:** an app named `integration/`
  (Dolphin Accounting hand-off, with its own outbox and a
  `dispatch_outbound_events` command), `accounting/`, and edits to
  `config/settings.py`, `config/urls.py`, `base.html`, `ui_views.py`,
  `dolphin-app.js`. None of it may be committed or depended on. The new app will
  be `integrations` (plural) — a distinct label, but a similar name; see D16.
- **No linter/formatter is configured** in the repository. Phase checks are the
  Django test suite, `makemigrations --check`, `manage.py check`, and the
  repository's own validation scripts.
- **Git convention:** commits straight to `main`, pushed to `origin/main`; no PRs,
  no tags. Versions come from the single `VERSION` file; `CHANGELOG.md` is in
  Persian.

## 2. Inventory of today's detail pages (nothing below may be lost)

### 2.1 Customer detail — `/customers/<id>/` (`customers/detail.html`, `setupCustomerDetail`)

| Block | Contents |
|---|---|
| مشخصات مشتری (edit form) | نام کامل, کد ملی, شماره اقتصادی, ایمیل, استان (fixed 31-province select), شهر, کد پستی, دسته‌بندی, شناسه ثبت‌کننده (read-only), وضعیت (editable select for Platform Admin, read-only otherwise), نشانی, یادداشت; «ذخیره تغییرات» |
| تلفن‌ها | table: شماره, نرمال‌شده, برچسب, اصلی, وضعیت, عملیات; «تلفن جدید» dialog (شماره, برچسب, شماره اصلی) |
| سرنخ‌های مرتبط | paginated: مشتری, منبع, کمپین, وضعیت, مسئول, عملیات |
| تماس‌های مرتبط | paginated manual interactions: مشتری, شماره, جهت, نتیجه, زمان, عملیات |
| فاکتورهای مرتبط (`invoices` feature) | paginated: شماره, وضعیت, تسویه, مبلغ کل, مانده, تاریخ صدور, عملیات |
| تاریخچهٔ مشتری (`customer_timeline` feature) | 360° timeline from 9 sources (calls, leads, orders, invoices, payments, sales documents, after-sales, attachments, SMS in/out) |
| پیوست‌ها (`attachments` feature) | shared attachments panel (upload / delete per 2.18.8 rules) |
| Page actions | بازگشت به فهرست |

### 2.2 User detail — `/users/<id>/` (`users/detail.html`, `setupUserDetail`, User Management only)

| Block | Contents |
|---|---|
| ویرایش مشخصات | نام کاربری, نام, نام خانوادگی, ایمیل, تلفن, حوزه کاری |
| تغییر نقش کنترل‌شده (`can_change_roles`) | نقش select + the «مجوزهای اختصاصی» keep/reset dialog |
| نشست‌های فعال (`can_change_roles`) | table: شناسه نشست, انقضا; «پایان همه نشست‌ها» |
| وضعیت دسترسی | «تغییر وضعیت کاربر» (activate/deactivate) |

### 2.3 User performance profile — `/users/<id>/profile/` and `/profile/` (`users/profile.html`)

| Block | Contents |
|---|---|
| Header | initials avatar, name, فعال/غیرفعال badge, role label, username, phone, email |
| Filter | period start / end (Jalali) |
| KPIs | مشتری ثبت‌شده, تعداد فروش, مبلغ فروش, میانگین فروش |
| روند فروش تأییدشده | chart with the shared range controls |
| جزئیات همین بازه | paginated: نوع, مشتری, کاربر, محصول, مبلغ, زمان, عمل |
| Page actions | بازگشت به فهرست کاربران, ویرایش کاربر |

### 2.4 Elsewhere on User Management (`users/list.html`)

Permissions dialog (Read/Edit/Delete matrix), profile/avatar dialog, sessions
dialog. These stay; the new profile links to them rather than duplicating them.

## 3. Data sources for each profile item

| Item | Exists? | Where / gap |
|---|---|---|
| Job title (سمت) | **No** for users and customers | Users have `role` (+ `workstream`) → fallback label. Customers have `kind` and free-text `category`. Add optional `job_title` to both. |
| Province | Customers **yes** (free text, filled from a fixed 31-province select); users **no** | Shared province list exists in the customers UI and `reports/customer_insights.PROVINCE_ALIASES`. Add `province` to users, reuse one Python list. |
| Phones | Customers **yes**: `CustomerPhone` (many per customer, raw + indexed `normalized_phone`, primary flag). Users: one raw `phone`, **not normalized** | `common/phones.normalize_customer_phone` already produces E.164 `+98…` and accepts `09…`, `9…`, `+989…`, `00989…`, `021…`, Persian/Arabic digits. Gaps: users, `Interaction.phone`, PBX caller-ID quirks (trunk prefixes, 8-digit local numbers). |
| Customer debt | **Yes** | Issued invoices' `total_amount − paid_amount` with `due_at` aging (`reports/financial.build_receivables_report`); installments with `due_date`; cheques; `CustomerLedgerEntry` with a running `balance_after` (`customer_ledger` feature, includes opening balances). |
| Staff income | **Partly** | Confirmed `Sale.total_amount` by `sold_by` (the performance report's «مبلغ فروش»). **No commissions, targets or payroll** anywhere. |
| Purchases | **Yes** | Issued invoices (financial) and confirmed `Sale` rows (campaign results) — two different notions; see D4. |
| Tasks | **No** | Only `Lead.next_follow_up_at` and the reminders bell (lead follow-ups, appointments, cheque and instalment due dates). |
| Activities / notes | **Partly** | `Interaction` (manual call log, **requires a lead**), `Customer.notes` / `Lead.notes` (single text fields), the pull-based customer timeline. No standalone note or activity entity. |
| Documents | **Yes** | `attachments` (customer, lead, invoice, sales document, after-sales). |
| Online / last seen | **Partly** | `last_login` and live sessions (`accounts/sessions.py`); no last-activity tracking. |
| Calls (PBX) | **No** | Only the manual `Interaction` log; `common/integrations.py` has an honest «VoIP» placeholder row. |

## 4. Infrastructure

- **Jobs:** management commands + one-shot Compose services + host `crontab`
  (documented in `docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md` §4.4).
- **Real-time:** none; polling everywhere.
- **Deployment:** Docker Compose (`compose.yml`), images built off-host and
  loaded with `docker load`, released with `scripts/deploy.sh <tag>` (which now
  also validates and recreates nginx when its config changes).
- A long-running listener therefore becomes a new Compose service with
  `restart: unless-stopped`, in its own profile so a deployment without the
  feature never starts it.

## 5. Existing integration-like code

- `common/integrations.py` + `/settings/integrations/` («اتصال سامانه‌ها»): a
  small registry of rows (SMS, post, a VoIP placeholder, «coming soon») with
  status, masked secrets and per-row gates. It is the natural seed for Part B's
  admin page.
- SMS gateway: `SmsProviderSettings` singleton (API key or OAuth2 password),
  outbound send + campaigns + templates, inbound SMS matched to customers by
  `normalized_phone` (`communications/services.py`) — a working precedent for
  contact matching.
- Post carrier seam: `PostProviderSettings` singleton.
- API auth: session + CSRF only. No token authentication.
- The uncommitted `integration/` app (accounting hand-off tokens + outbox) —
  protected, not used by this plan.

## 6. Proposed design

### 6.1 Part A — unified person profile

**Adapters.** `profiles/` app with `PersonAdapter` (key, label, resolve, scope
check, header fields, completion fields, tabs, quick actions, timeline filter)
registered in `profiles/registry.py`. Two adapters: `customer`, `user`. A third
type (supplier, partner) is one adapter module plus registration.

**Person references.** Tables that point at "a person" (timeline entries,
tasks, scores, calls) store `person_type` (the adapter key) + `person_id`,
indexed together, validated by the adapter — not Django `ContentType` ids,
which differ between databases. See D1.

**One template, two routes.**
- `/customers/<id>/` becomes the customer profile.
- `/users/<id>/` becomes the user profile (User Management → click a user);
  `/users/<id>/profile/` and `/profile/` redirect to it with `?tab=performance`.
- `profiles/templates/profiles/profile.html` + includes for header, cards,
  completion bar and tab strip; each tab is a small include loaded lazily from
  `/api/v1/profiles/<type>/<id>/tabs/<tab>/` (HTML fragment or JSON, following
  how the page's existing lists load). Deep links via `?tab=` with
  `history.pushState`, so Back works.

**Header.** Avatar (users: photo/default avatar; customers: initials), name,
badge (users: active; customers: hidden — no "verified" concept), presence dot
(users only), #1 job title → role fallback, #2 province, #3 primary phone as
`tel:` + click-to-call when telephony is on. Email moves to «اطلاعات». Follow /
hire-me removed; quick actions: call, SMS (when `outbound_sms` + `sms.company`),
add note, add task, edit, «بیشتر» — each gated server-side.

**Tabs (customers):** بررسی اجمالی · اطلاعات (the full edit form + phones) ·
سرنخ‌ها (related leads) · فعالیت‌ها (timeline) · تماس‌ها (manual interactions +
PBX calls) · خریدها و مالی (invoices, payments, installments, ledger link) ·
وظایف · یادداشت‌ها · اسناد (attachments).
**Tabs (users):** بررسی اجمالی · اطلاعات (edit form) · مشتریان و سرنخ‌ها ·
وظایف · عملکرد (today's performance profile + score history + call stats) ·
فعالیت‌ها · تماس‌ها · دسترسی‌ها (role change, permission matrix link, sessions,
activation). Tabs of disabled features or unpermitted data are not rendered.

**Unified timeline — hybrid.** Keep the nine pull sources of
`common/customer_timeline.py` (no backfill of history), add a push store
`TimelineEntry(person_type, person_id, kind, occurred_at, actor, title, body,
source, source_ref, payload, required_capability)` written through
`timeline.services.record(...)`. Notes, calls, messages and integration events
push; the timeline service merges both. See D7.

**Stat cards.** `profiles/cards.py` registry of `StatCard` providers (key,
label, icon, person types, `visible(viewer, person)`, `compute(person, period)`
→ value + trend + tooltip or «—» with a reason). The server only serialises
visible cards. One Jalali period selector (default: current month), reusing
`reports/ranges.py`.

| Card | Users | Customers |
|---|---|---|
| #4 | درآمد — per D2 | بدهکاری — per D3, red when overdue |
| #5 | مشتریان فعال — distinct customers with an open lead assigned to the user | مجموع خرید — per D4 |
| #6 | نرخ تبدیل — per D5 | آخرین تعامل — latest timeline event, relative time |
| #7 | امتیاز | امتیاز |

Visibility: income → the user, a role holding `reports.company`, Platform
Admin. Debt / purchases → `ledger.company`, `invoices.company` or
`payments.company`; for an agent, `ledger.own` on their own customers (the
existing BACKEND_SPEC §6.3 rule).

**Scoring.** `scoring/` app: `ScoringService`, per-type strategies
(`CustomerRuleStrategy`, `UserRuleStrategy`) behind a `ScoringStrategy`
interface (an AI strategy can be registered later), weights in a
`ScoringSettings` singleton editable by Platform Admin on the settings page,
defaults in code. Output `{score, level, breakdown[factor → points, reason]}`;
`PersonScore` snapshots for history. Recalculated on relevant events (debounced
via the outbox), nightly by `manage.py recalculate_person_scores` (one-shot
service + crontab line), and on demand when a profile is opened with a stale
snapshot.

**Completion bar.** Fields and weights per adapter; the missing list links to
the «اطلاعات» tab with the field focused.

**Model changes (additive only):** `User.job_title`, `User.province`,
`User.normalized_phone` (+ index, backfill), `User.last_seen_at` (D8),
`Customer.job_title`; `Interaction.normalized_phone` (+ backfill) for matching.
New: `TimelineEntry`, `Task` (D6), `PersonScore`, `ScoringSettings`.

### 6.2 Part B — `integrations` framework

- **Provider registry** (`integrations/providers/`): key, name, capabilities
  (`telephony`, `messaging`, `sms`, `email`, `payment`, `accounting`, `webhook`),
  config schema (typed fields, required, secret), `validate_config`,
  `test_connection`, `health`, optional worker hooks.
- **Models:** `Integration` (provider_key, name, enabled, config JSON,
  encrypted secrets JSON, status, last_health_at, last_error), `IntegrationLog`
  (direction, event type, status, error, trimmed payload; retention command),
  `DomainEvent` outbox (type, payload, person ref, status, attempts),
  `InboundWebhookReceipt` (idempotency key, signature result, raw payload),
  `WebhookSubscription` + `WebhookDelivery` (HMAC-SHA256, exponential backoff,
  delivery log), `ApiToken` (hashed, scopes, bound user — D17).
- **Secrets:** encrypted at rest with a key from `DOLPHIN_SECRETS_KEY` (D9),
  write-only in the UI (masked hint via the existing `mask_secret`).
- **Events:** normalized events (`CallStarted`, `CallAnswered`, `CallEnded`,
  `CallMissed`, `MessageReceived`, `MessageSent`, `PaymentReceived`) written to
  the outbox in the same transaction as the change that caused them; core
  handlers (timeline, scores, tasks) run after commit and a sweeper retries
  anything left unprocessed.
- **Inbound webhooks:** `/api/v1/integrations/<id>/webhook/` — token or HMAC
  verification per provider, idempotency, raw payload log.
- **Contact matching:** `integrations/matching.py` — phone (normalized, then a
  lenient last-10-digits fallback), email, messenger id → customer or user;
  «create lead from this» for no match.
- **Admin page «یکپارچه‌سازی‌ها»:** supersedes `/settings/integrations/`
  (same entry points). Provider list, schema-generated forms, enable/disable,
  «تست اتصال», health, recent logs, outbound webhook subscriptions, API tokens.
  SMS and post appear as built-in providers wrapping their existing singleton
  settings (no data move now — D15).

### 6.3 Part C — Asterisk (AMI) connector

- **Provider `asterisk`** (capability `telephony`): AMI host/port/user, originate
  context (FreePBX: `from-internal`), originate channel pattern (default
  `Local/{ext}@from-internal`), timeout, caller-ID, outbound prefix, CDR DB
  host/port/name/user/table, recordings (mounted base path **or** base URL +
  filename pattern), options (missed-call task, popup, create lead from unknown
  caller). Secrets: AMI password, CDR DB password.
- **Models:** `Extension` (integration, number, user nullable, active; admin
  mapping UI; shown on the user profile), `Call` (as specified: `linkedid` unique
  per integration, direction, raw + normalized parties, person ref, user,
  status, timestamps, duration, billsec, hangup cause, recording reference,
  source flags, raw payload), `CallNotification` (per-user popup queue).
- **Listener:** in-house asyncio AMI client (D10): login, event filter
  (`Newchannel`, `Newstate`, `DialBegin`, `DialEnd`, `BridgeEnter`, `Hangup`,
  `AgentCalled`), periodic `Ping`, exponential-backoff reconnect, health written
  to `Integration`, call state keyed by `Linkedid`, never crashes on unknown or
  malformed events, never logs secrets. Command `run_telephony_listener`,
  hosted by a new Compose service (D14).
- **CDR sync:** incremental by `calldate`/`uniqueid`, idempotent, re-runnable
  over a range; fills gaps and corrects duration/billsec (D11).
- **Recordings:** reference only; streamed through Django with HTTP Range
  support, capability check and audit log (D13).
- **Popup:** a `CallNotification` row per mapped user on ring; the browser polls
  a tiny endpoint every 2 s while a tab is visible (D12); popup shows caller,
  matched person (name, avatar, score, debt/purchase summary when permitted),
  profile link, «create lead» for unknown numbers.
- **Click-to-call:** `POST /api/v1/telephony/originate/` — capability check,
  own throttle scope, audit log, Persian errors (extension not mapped, PBX
  unreachable, invalid number).
- **CRM hooks:** calls → timeline + Calls tab (both profile types); missed
  inbound from a known customer → optional follow-up task for the assigned
  salesperson; call data → scoring factors; per-user call stats in «عملکرد».
- **Capabilities** (new matrix module «تماس‌های تلفنی»): `calls.own`,
  `calls.company`, `calls.originate`, `calls.recordings` — defaults in D20.
- **Tests without a PBX:** recorded AMI event fixtures (inbound answered/missed,
  outbound answered, busy, transfer, queue), a fake AMI TCP server (including
  disconnect/reconnect), CDR reconciliation fixtures (duplicates, gaps).

### 6.4 New feature flags (registry + manifest builder + docs)

`person_scoring`, `tasks`, `person_notes`, `integrations`,
`outbound_webhooks` (→ integrations), `public_api` (→ integrations),
`telephony` (→ integrations, customers). The profile page itself is not a flag:
it *is* the customer/user detail page; its parts follow their own flags.

## 7. Open decisions (recommendation first)

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | How tables refer to "a person" | (a) `person_type` + `person_id` pair validated by adapters; (b) explicit nullable FKs per type (the attachments pattern); (c) `ContentType` generic FK | **(a)** — a new person type needs only an adapter, no migrations on every person-linked table. Deletion is guarded in the adapter (refuse while calls/tasks exist, like `PROTECT`). |
| D2 | «درآمد» for users | (a) confirmed sales attributed to the user in the period (`Sale.sold_by`, the performance report's «مبلغ فروش»); (b) paid invoice amounts attributed to the user; (c) a commission rate × sales | **(a)** now, labelled with its definition in the tooltip. (c) invents compensation rules (CLAUDE.md §31) and needs a real commission policy first. |
| D3 | «بدهکاری» for customers | (a) ledger balance when `customer_ledger` is on, else issued-invoice outstanding; overdue = past-due invoices + overdue installments; (b) invoices only | **(a)**. Trend vs previous period only where the ledger's `balance_after` can answer it; otherwise «—» with a reason. |
| D4 | «مجموع خرید» | (a) issued, non-cancelled invoices; (b) confirmed sales; (c) both | **(a)** when `invoices` is on, **(b)** otherwise — never summed together (a sale that was invoiced would count twice). |
| D5 | «نرخ تبدیل» | (a) the dashboard gauge's definition — completed ÷ (completed + cancelled), leads decided in the period, assigned to the user; (b) your wording — completed ÷ assigned in the period | **(a)**, so the dashboard and the profile never show two different "conversion rates"; (b) reads low early in each month because undecided leads count against it. |
| D6 | Tasks | (a) new minimal `tasks` module (title, notes, due, assignee, person ref, status, completed_at, source) feeding the reminders bell; (b) no tasks — drop add-task, missed-call tasks and the on-time factor | **(a)**, behind the `tasks` flag. |
| D7 | Timeline | (a) hybrid: keep the nine pull sources + a push `TimelineEntry` store for new events; (b) backfill everything into one table | **(a)** — no history migration, integrations still push through one service. |
| D8 | Presence | (a) `User.last_seen_at`, written by middleware at most once per 2 minutes per user; online = seen in the last 5 minutes; (b) last login only | **(a)**. |
| D9 | Secret encryption | (a) add `cryptography` (hash-pinned, reviewed) and encrypt with `DOLPHIN_SECRETS_KEY`; (b) secrets only in `secrets/.env`, not editable in the UI | **(a)** — the only way to meet "write-only, encrypted, editable by an admin". Existing SMS/post plaintext secrets can move into it in a later release. |
| D10 | AMI client | (a) in-house asyncio client (~300 lines, no dependency); (b) `panoramisk` | **(a)** — AMI is a simple line protocol; full control over reconnect, heartbeat and the fake-server tests; no new dependency. |
| D11 | CDR access | (a) `PyMySQL` (pure Python, hash-pinned) against FreePBX's MariaDB `asteriskcdrdb.cdr`; (b) PBX team writes CDR to PostgreSQL (`cdr_pgsql`/ODBC); (c) AMI `Cdr` events only | **(a)**, with (c) as a supplementary live source. (c) alone cannot fill gaps while disconnected. |
| D12 | Popup transport | (a) short polling, 2 s, visible tabs only, indexed per-user query; (b) SSE (holds one Gunicorn thread per open tab — 12 threads total); (c) Channels + Redis (new services) | **(a)** — ≤ 2 s latency while the phone is still ringing, no new infrastructure; upgrade path kept behind one JS function. |
| D13 | Recordings | (a) read-only mount of the PBX recordings directory (NFS/SSHFS) on the Dolphin host; (b) PBX serves them over HTTPS to the CRM IP only | **(a)** if the PBX team can export a mount; **(b)** supported as the alternative. Both are configurable. |
| D14 | Processes | (a) one new Compose service `integrations-worker` running the AMI listener(s) plus periodic jobs (CDR sync, outbox, webhooks, health); nightly scores via crontab; (b) separate services per job | **(a)** — one thing to run and monitor; `run_telephony_listener` also exists standalone for debugging. |
| D15 | Existing «اتصال سامانه‌ها» page, SMS and post | (a) the new page supersedes it; SMS/post become built-in providers over their existing settings; (b) keep two pages | **(a)**. |
| D16 | The uncommitted `integration/` (accounting) app | (a) leave it untouched; new app is `integrations`; the accounting hand-off can become a provider once that work is decided; (b) merge now | **(a)** — it is protected, unreviewed work. |
| D17 | Public API tokens | (a) a token bound to a designated user (normal role + capability overrides) and narrowed by scopes; (b) standalone service tokens with their own permission model | **(a)** — reuses every permission and object-scope rule as-is. |
| D18 | Defaults | New flags off by default in the manifest builder; on for development; TIARA gets `telephony`/`integrations` only after its manifest is re-signed | As stated — please confirm which flags TIARA should get. |
| D19 | Git | (a) repo convention: commit to `main`, push `main` in Phase 6; (b) a feature branch | **(a)** — the repository has a clear convention (your instruction: follow it when one exists). |
| D20 | Telephony permission defaults | Agent: `calls.own`, `calls.originate`; Sales Manager / Company IT: `calls.company`, `calls.originate`, `calls.recordings`; Platform Admin: all | As stated, all adjustable per user in the matrix. |
| D21 | Score defaults | Customer: recency 25, frequency 20, monetary 20, punctuality 25, engagement 10. User: task on-time 20, conversion 30, follow-up speed 20, activity 20, missed-call follow-up 10 | As stated, editable by Platform Admin. |

## 8. Phases, versions and checks

| Phase | Scope | Version |
|---|---|---|
| 1 | Profile layout, adapters, header #1–#3, quick actions, all tabs migrated (no score), `job_title`/`province`/presence/normalized phone fields for users | 2.19.0 |
| 2 | Stat cards #4–#6, scoring #7, completion bar, tasks + notes (if D6/D7 approved) | 2.20.0 |
| 3 | Integrations framework, admin page, contact matching, phone normalization backfills, webhooks, API tokens | 2.21.0 |
| 4 | Asterisk provider, listener service, `Call`, CDR sync, recordings | 2.22.0 |
| 5 | Popup, click-to-call, timeline/score/task hooks, Asterisk deployment docs | 2.23.0 |
| 6 | Full suite, migration test from 2.18.0 on PostgreSQL with synthetic data (`seed_synthetic_uat`), browser pass (admin + marketer, desktop + mobile), push | — |

Each phase: tests for touched code, `makemigrations --check`, `manage.py
check`, browser checks for UI work, docs (CLAUDE.md, CHANGELOG, `docs/`,
runbook, BACKEND_SPEC, OpenAPI via drf-spectacular), VERSION bump, one commit.

## 9. Risks

- **Size.** This is the largest single change since 2.0; phases 1–2 touch the
  two most used pages. Everything currently on them is inventoried in §2 and
  will be checked item by item in Phase 6.
- **TIARA runs 2.18.0.** Going live needs the 2.18.x migrations as well as
  these; the Phase 6 migration test starts from 2.18.0 for that reason.
- **Two new dependencies** (D9 `cryptography`, D11 `PyMySQL`) if approved; each
  is resolved hash-pinned in the clean build image.
- **PBX unknowns** until the PBX team answers: FreePBX or plain Asterisk,
  originate channel/context, caller-ID format on the trunks, recordings access,
  queue usage, timezone/NTP. Every one of them is a configuration value, not code.
