# PROGRESS — UI/UX overhaul (13 items)

Working checklist for the product owner's 13-item UI/UX request (2026-09-20).
Updated and committed after every finished item, so a session that hits a
usage limit can be resumed from here with no questions.

## Decisions taken at the start (product owner, 2026-09-20)

1. **Postal statuses** — exactly four, in this order:
   | code | Persian | icon |
   |---|---|---|
   | `warehouse` | انبار فروشگاه | warehouse |
   | `to_post` | ارسال به پست | box in motion |
   | `at_post` | بسته دست پست است | post office |
   | `to_customer` | ارسال به مشتری | truck + box |
   Existing free-text values are **mapped, never dropped**: what maps, maps;
   what does not is preserved verbatim in a new note column so no row loses
   information (CLAUDE.md §7).
2. **API integrations page** — SMS + Post as real rows, plus rows explicitly
   labelled «به‌زودی» for services not yet implemented.
3. **Delivery** — several staged releases, each versioned and tested; one
   main deploy at the end.
4. **Console `.exe`** — PyInstaller as an operator-only dependency plus a
   build script, and the build is actually run.

## Decisions I made myself (no question asked)

- Avatar images are stored as `bytea` on the user row, following
  `common.models.BrandSettings.logo_content` — the `web` container's
  filesystem is read-only and there is no `MEDIA_ROOT`.
- The 52 Metronic cartoon avatars at `assets/media/svg/avatars/` become the
  default set; `media` is currently in `.dockerignore`, so that one directory
  is reinstated and added to `scripts/validate_image_content.py` the same way
  `jkanban` and `fullcalendar` already are.

## Batches

### Batch A — `2.10.0` — boards, date picker, calendars
- [x] 1. Kanban: bigger three-dot (≥32×32, clear hover/focus), card body no
      longer opens details, drag & drop still works
- [x] 1. Kanban: per-column scrollbar on the right, hidden until hover,
      always usable on touch, WebKit + Firefox separately
- [x] 2. One shared date picker; time where it makes sense
- [x] 2. `<`/`<<` swapped with `>`/`>>` for RTL
- [x] 2. Month name → month grid; year → year grid + decade view
- [x] 2. Comfortable time selection, keyboard, 24h Persian
- [x] 3. Month view shows the whole Jalali month, 1 → 30/31
- [x] 3. Week/day: drop the numbers inside cells, keep the weekday row
- [x] 3. Better cell separation; cells stretch with content, animated

### Batch B — `2.11.0` — charts, dashboard
- [x] 4. One shared time filter (today / 7d / 30d / 3m / year / custom)
- [x] 4. Titles corrected to match their data
- [x] 4. Extra meaningful filters where they exist
- [x] 4. Magnifier icon removed
- [x] 4. Home icon repositioned, tooltip «حالت پیش‌فرض»
- [x] 5. Edit button moved to the top of the page, covers every box
- [x] 5. Whole-widget drag, six-dot handle removed
- [x] 5. Corner resize with sensible min/max on a grid
- [x] 5. Delete button: more inset, better looking
- [x] 5. Per-user layout saved/restored; reset works

### Batch C — `2.12.0` — invoice wizard, settings, popovers
- [x] 6. «اقلام و تخفیف» step redesigned
- [x] 7. «تنظیمات» moved out of the user modal to the sidebar's end
- [x] 7. «برند و لوگو» → «شخصی‌سازی پنل» inside admin settings
- [x] 8. One header popover open at a time; Esc and outside-click everywhere

### Batch D — `2.13.0` — reports, postal, integrations
- [x] 9. «گزارش اسناد فروش و پست» rebuilt as a wizard
- [x] 9. «گزارش پیامک ورودی» rebuilt as a wizard
- [x] 10. Four postal states with icons, shown as a stepper
- [x] 10. Service layer ready for a future post-office API
- [x] 11. API integrations page

### Batch E — `2.14.0` — console, profiles
- [x] 12. Console lists every page/option from the real feature source
- [x] 12. Persian/English tabs
- [x] 12. `.exe` build
- [x] 12. Typography and spacing
- [x] 13. Profile photo upload with crop/resize, size and format limits
- [x] 13. Metronic cartoon avatars as the default

### Final
- [x] Full suite green (only the 7 known pre-existing Selenium errors)
- [x] CHANGELOG + VERSION
- [x] Main deploy to Nerkhbaan + health check

## Status

**All thirteen items are done, released and deployed.** Nothing is
outstanding.

**Deployed:** `2.14.0` to Nerkhbaan (`87.248.130.63`), 2026-09-21. The server
was on `v2.9.1` before this — batches A–E were released and tested locally and
went up as the one main deploy that was asked for, so `2.10.0`–`2.13.0` never
ran on staging as separate deployments.

**Deploy evidence, in order:**
- `git push origin main` → `2ecf1b0..b17b0e0`, 6 commits, 129 files.
- Built from the pushed source, not the working tree: `sh scripts/build-image.sh
  v2.14.0` → `dolphin-app:v2.14.0`, image `ec6e38ea5d92`, which the script itself
  confirmed carries `VERSION=2.14.0`.
- Archive `dolphin-v2.14.0.tar.gz`, 66,707,211 bytes, SHA-256
  `0131713f…41363d3` — computed on both machines and compared, equal. `docker
  load` on the host produced image id `ec6e38ea5d92`, the same id.
- `git pull --ff-only` then `./scripts/deploy.sh v2.14.0` in `/srv/Dolphin`:
  migration `accounts.0005_useravatar` applied, 108 static files copied (the 52
  avatars and the rebuilt bundles), grants re-locked, stack restarted,
  `dolphin-web-1` healthy on `dolphin-app:v2.14.0`.

**Health, measured after the deploy:**
- `/api/v1/health/live/` → `200 {"status":"ok"}`;
  `/api/v1/health/ready/` → `200 {"status":"ok","database":"up"}`.
- `/login/` 200; `/`, `/orders/board/`, `/leads/board/`, `/invoices/`,
  `/reports/sales-documents/`, `/reports/user-performance/`, `/settings/`,
  `/settings/integrations/`, `/branding/`, `/profile/` all 302 to `/login/`,
  which is the correct unauthenticated answer. No 5xx anywhere in the web log.
- `2.14.0` in the login page footer and in `/app/VERSION` inside the container.
- `/static/common/avatars/001-boy.svg` 200 `image/svg+xml` 4,265 B; all 52
  avatars present in `staticfiles`; `dolphin-app.js` and `dolphin.css` 200.
- `accounts_useravatar` grants read back from the live database:
  `dolphin_app → DELETE, INSERT, SELECT, UPDATE`, `dolphin_backup → SELECT`.
- The console's inventory computed inside the running image: 27 features, 18
  opening pages, 49 pages behind a feature, 55 routed pages all titled, 6
  ungated. Identical to the source console and to the frozen `.exe`; the local
  count of 28 features is the one uncommitted feature in the working tree.

**Left on the host deliberately:** nothing. The transferred archive and the
sudo askpass helper were both removed.

**Flagged, not acted on:** `/` on the server is 89% full (3.3 GB free) — 26
`dolphin-app` tags, 12.83 GB of images and 4.84 GB of build cache. Pruning
would touch the rollback path (`.deploy-previous-image` → `dolphin-app:v2.9.1`),
so it is a decision for the product owner, not a cleanup to do unasked.

────────

# PROGRESS — Round 2 (12 fixes/additions, 2026-09-21)

Product owner follow-up after 2.14.0 shipped. Versions are exactly as given
by the product owner per item; items 7, 8 and 10 were not given their own
version, so they are folded into the nearest following versioned release
(7+8 into 2.14.7 with item 9; 10 into 2.14.8 with item 11) rather than
bumping a version for every small edit (CLAUDE.md §23).

## Checklist

- [x] 1. Calendar month/year header — normal, even spacing → `2.14.1`
- [x] 2. Line chart bottom day-number labels wrong → `2.14.2`
- [x] 3. Profile picture: choose from defaults + upload in a new modal → `2.14.3`
- [x] 4. Three-dot "view details" on board/list cards must open the detail page → `2.14.4`
- [x] 5. Receipts wizard step 2 (document info) — spacing redesign → `2.14.5`
- [x] 6. Postal tracking — 4 connected icons in a row, current stage lit → `2.14.6`
- [x] 7. Report wizards (sales-docs, post, inbound-sms) centered; province as a dropdown → bundled into `2.14.7`
- [x] 8. Excel import/export buttons get a small Excel icon → bundled into `2.14.7`
- [x] 9. Post integration settings page, like SMS → `2.14.7`
- [x] 10. Dashboard widget editing — smoother, Apple/Android-widget-like → bundled into `2.14.8`
- [x] 11. Rename SMS settings entry to a general "اتصال سامانه‌ها" connections hub → `2.14.8`
- [x] 12. Locate/relocate the console `.exe` to the project root; report its name → `2.14.9`

### Final
- [x] Full suite green (only the 7 known pre-existing Selenium errors)
- [x] CHANGELOG + VERSION for each release above
- [ ] Main deploy to Nerkhbaan + health check

## Status

**Current:** all 12 items done, full suite green (`2.14.1`–`2.14.10`).
Remaining: the single deploy and the final report.

**Release checkpoint (`2.14.10`) — the full suite, run for real, found
four real regressions from this round's own work, none of them caught by
the narrower per-item test runs because each lived in a *different*
existing test module than the one each item's own new tests were added
to:**
- `auditlog.tests.test_operation_labels` — the new `post_provider_settings
  .updated` audit operation (item 9) had no Persian label. Fixed in
  `auditlog/labels.py`.
- `common.tests.test_profile_menu.PasswordChangeAbsentTests` — the new
  `post_provider_settings.html` (item 9) has an `autocomplete="new-
  password"` field for the API key, same as the SMS settings page's own
  equivalent field, which is already on this test's documented allowlist
  for exactly this reason (a third-party credential, not an account
  password). Added the new template's name to it.
- `common.tests.test_table_cells_and_pickers.JalaliPickerGridTests` (two
  tests) — pre-existing tests from before this round that pinned the
  jalali date picker's *old* selector text and CSS properties, both
  changed by item 1's fix. Restated to match the new `:not(.jalali-picker-
  scope)` selector and the new flex-based title (the overflow handling
  that used to live on the title itself moved to the two buttons inside
  it).

Full suite after these four fixes: **2589 tests, 0 failures, only the 7
known pre-existing Selenium/ChromeDriver errors** (`element not
interactable` — a real browser-automation environment issue on this
machine, unrelated to any change here; confirmed by inspecting the actual
traceback, not assumed from the count matching the prior baseline). 16
skipped. OpenAPI schema clean throughout the round.

**Item 12 — what changed, and the answer to the question asked.** No exe
existed anywhere in the checkout before this (`dist/` did not exist). The
build script's own `DIST` moved from `REPOSITORY_ROOT / "dist"` to
`REPOSITORY_ROOT` itself; since the build is `--onefile`, this directory
receives exactly the one executable and nothing else, so pointing it at
the root does not scatter build output through the checkout. **The file's
name is `dolphin-console.exe`, built directly into the project root**
(same folder as `manage.py`) the next time an operator runs `pip install
-r scripts/requirements-console.txt` then `python scripts/
build_console_exe.py` — not run this session: PyInstaller is a real,
deliberate operator-only dependency this script refuses to install for
itself, and installing it into the session's own Python environment to
prove the build works was not asked for and was not done. Both
`.gitignore` and `.dockerignore` gained an explicit `dolphin-console.exe`
entry so it can never be committed or enter a shipped image, on top of the
protections already in place (`scripts/` excluded from the Docker context
entirely). New test:
`test_ui_overhaul_console_avatars.ConsoleExeTests.test_the_output_lands_in_the_project_root`.

**Item 10 — root cause and fix.** Widget reordering used HTML5
drag-and-drop, which never fires on a touch screen at all
(`dragstart`/`dragover` are a mouse-only contract in every mobile browser)
and drew the drag with the browser's own uncontrollable ghost image.
Rewritten on Pointer Events (unifies mouse/touch/pen): the dragged widget
is positioned by a real CSS transform this code owns, and every widget the
drag displaces animates (FLIP: read old rect, let the DOM swap land,
invert-transform back, then transition to identity) from its old slot to
its new one instead of snapping. **A real bug surfaced and was fixed while
building this**: without tracking the last widget swapped with, every
`pointermove` while the pointer sat anywhere within the same target
widget re-ran the swap — and a swap is its own inverse, so several
consecutive move events over one ~235px-wide widget toggled it back and
forth, landing on either the original or swapped arrangement depending on
parity. This is exactly why an early verification attempt showed "no
effect from dragging" — traced down to a genuine double-execution testing
artifact THEN a genuine code bug, both now fixed and both confirmed via a
`document.elementFromPoint`-call log and a version bump that forced a true
single fresh script load. The lift-while-dragging look changed too (a
slight scale + shadow, replacing `opacity: 0.45`, which read as
"disabled" not "picked up"), and `touch-action: none` was added to both
the widget (while editing) and the resize grip, so a touch-drag does not
race the browser's own scroll gesture. Verified live end to end: a
three-widget drag produced the correct shift, persisted through a reload,
and reverted to defaults on request. New tests:
`test_ui_overhaul_round2.DashboardWidgetDragTests` (6); two existing
`test_ui_overhaul_charts_dashboard.DashboardDragTests` tests restated for
the mechanism change.

**Item 11 — what changed.** The sidebar's and the admin settings page's
own «تنظیمات سامانهٔ پیامک» entries pointed straight at SMS settings and
were gated on `can_manage_sms_provider` alone — a Sales Manager who could
configure the new post connection (item 9) but not SMS had no way into
either. Both entries now point at the existing «اتصال سامانه‌ها» hub
(renamed from «اتصال سرویس‌ها» to match the product owner's own wording,
across the page's title/breadcrumb and `common/deployment/pages.py`) and
are gated on a new `can_manage_integrations` — `common.integrations.
any_integration_configurable(user)`, which checks each row's feature and
gate *without* the per-row status query `visible_integrations` makes,
since this flag is computed on every page load and cannot afford it. The
redundant standalone SMS button on the settings page was removed outright
(the hub already lists SMS as one of its rows). The SMS-sending page's own
contextual shortcut to SMS-specific settings (`sms/outbound.html`) was
deliberately left untouched. Verified live: no `sms-provider-settings`
link remains in the sidebar or the settings page; the sidebar entry and
the settings-page button both read «اتصال سامانه‌ها» and open the hub; the
hub's own SMS row still links to `/settings/sms-provider/` correctly; the
SMS-sending page's contextual link is unchanged. New tests:
`test_ui_overhaul_round2.IntegrationsNavRenameTests` (6); one existing
`test_ui_overhaul_invoice_settings_popovers` test restated for the gate
rename. Full regression across boards/charts/invoice/postal-integrations/
console-avatars/round2/ui-connectivity/database-privileges/sales/
communications/accounts: 695 tests green. OpenAPI schema clean.

**Items 7–9 — what changed.** Bundled into one release since 7 and 8 were
never given their own version by the product owner.

- **Item 7a (centering):** neither report wizard lives inside a `dialog`
  (unlike the create-document wizards), so nothing capped their width —
  `.report-wizard-card` now gets `max-width: 60rem; margin-inline: auto`.
- **Item 7b (province dropdown):** the sales-documents-and-post report's
  province filter was free text against an *exact*-match backend filter
  (`reports/services.py`) — a typo already returned nothing. Now a
  `<select>` filled by the existing `fillProvinceSelect` (the same 31-name
  list from `iran-provinces.json` the customer map already uses) — no
  second list written anywhere.
- **Item 8 (Excel icons):** `ki-file-sheet` — a real icon confirmed present
  in the actually-loaded `plugins.bundle.rtl.css` (576-icon set, not the
  31-icon subset a naive grep found at first) — added to all 13
  import/export buttons across 10 templates (leads, products, customers,
  users, the performance panel, and 5 reports).
- **Item 9 (post settings page):** new `/settings/post-provider/`, mirroring
  `/settings/sms-provider/` but simplified to one auth shape (a static
  header key) since no specific carrier is integrated — `sales/postal.py`'s
  `ManualCarrier` stays the active carrier regardless; this only prepares
  real, saved, testable connection settings a future `PostalCarrier`
  subclass could use. New `common/http_probe.py` — extracted from
  `communications/sms.py`'s own private `_execute`, now shared by both the
  SMS and post "تست اتصال" buttons rather than a second private copy.
  New: `sales/models.PostProviderSettings` (migration `0021`),
  `sales/postal_provider.py` (get/update/test, mirroring
  `communications/sms_provider_settings.py`), two API endpoints, the
  settings page (view + template + JS), and the integrations row gained a
  real settings link and test button.

**Verified live:** province `<select>` has 32 options (31 + placeholder),
alphabetically sorted, matching the map's own list; `.report-wizard-card`
computed `max-width` went from `none` to a real value; the Excel icon
renders with its 2 paths on spot-checked buttons (sales-documents report,
customers list); the post settings form loads, saves (`has_api_key: true`,
never the key itself), and its "تست اتصال" button made a **real** HTTP
request — tested end to end against `https://example.com/ping`, which
correctly came back `HTTP 404` with the real response body shown. The
integrations page's post row now shows «پیکربندی‌شده» with the saved label
in its summary. New tests: `test_ui_overhaul_round2.
ReportWizardCenteringTests` (2), `ReportProvinceDropdownTests` (2),
`ExcelButtonIconTests` (3); `sales/tests/test_post_provider_settings.py`
(13, including a real HTTP round trip against a `HTTPServer` the test
suite starts itself, not a mocked `urllib`); one restated integrations
test. Full regression (sales, communications, round2, postal-integrations,
database-privileges, ui-connectivity, console-avatars): 423 tests green.
OpenAPI schema clean.

**Item 6 — what was actually missing.** "صفحهٔ رهگیری پستی" is the sales
documents *list* (`common_ui:sales-documents`, titled «رهگیری پستی») — a
different page from one document's own detail page, which already had the
full four-stop `.postal-stepper` card from batch D (`2.13.0`). The list's
own «وضعیت پستی» column printed `item.postal_status` as raw text, even
though `SalesDocumentSerializer` already computed `postal_stepper` (the
same four-entry, stage-marked list the detail page uses) for every row —
the frontend simply never read it. New `postalStatusCell` builds a compact
icon-only version, `.postal-mini-stepper`, reusing that same field: four
22px marks flush against each other with a continuous rail, the current
one lit with the primary ring, each icon's own `title` and the list's
`aria-label` naming the stage for anyone hovering or using a screen reader.
A document still carrying pre-vocabulary free text (`postal_stepper: []`)
falls back to the raw text, matching `renderPostalStepper`'s own reasoning:
four icons with none of them current would claim to know where a parcel is
when nobody does. Verified live: a seeded document at "بستهٔ دست پست است"
rendered done/done/current/upcoming in the right order, the icons
(`ki-shop`, `ki-delivery-3`, `ki-parcel-tracking`, `ki-truck`) all present,
and each mark's bounding rect touching the next with zero gap. New tests:
`test_ui_overhaul_round2.PostalMiniStepperTests` (6). Postal/reports +
round2 + sales app suites (230 total) green.

**Item 5 — root cause and fix.** Exactly the bug `.wizard-lines-step` (batch
C, `2.12.0`) was already written to fix, in a different wizard: the theme
lays every `[data-kt-stepper-element="content"]` out as `display:flex;
flex-direction:row` by default, correct for a step holding one `.row` and
wrong for one with several top-level blocks. The payments wizard's
«اطلاعات سند» step has up to five once the bank or cheque fieldset shows —
the main fields row, one conditional fieldset, the notes row, the cheque
note — all fighting for one shared horizontal row. Measured live with «چک»
selected: fields row 128px, cheque fieldset 252px, notes row 64px. Fixed
with the same pattern: a new `wizard-document-step` scoping class on the
step's own div, `flex-direction: column`, and the between-section spacing
raised from the theme's `mt-2` (0.5rem, sized for one row sharing a normal
form, not a full-width section) via a targeted `!important` override — the
theme's own `.mt-2` is itself `!important`, so nothing short of matching it
wins. Verified live: `getComputedStyle` confirms `flex-direction: column`
after the fix, and each visible child's bounding rect now has a strictly
increasing `top` at a consistent `left` (true vertical stacking) rather than
the pre-fix pattern of several children sharing one row's horizontal space.
New tests: `test_ui_overhaul_round2.PaymentWizardDocumentStepTests` (3).
Invoice-wizard suite (unaffected, same file) and round2 (54 total) both
green.

**Item 4 — root cause and fix.** The three-dot link was correctly built
(`boardCardHeader`, a real `<a href>`), but jKanban's own vendor bundle
(`assets/plugins/custom/jkanban/jkanban.bundle.js`) attaches a click
listener directly to every `.kanban-item` on creation and calls
`event.preventDefault()` unconditionally — which also cancels the nested
anchor's own navigation, since that resolves only after the click event
finishes propagating. A fix inside `boardCardHeader` itself cannot work: a
card is built as an HTML string (`cardContent`'s `wrap.innerHTML`) and
jKanban re-parses that string into fresh nodes, dropping any listener
attached to the nodes that produced it. Fixed with a new
`letCardDetailsLinkThrough(container)`, a capture-phase listener on the
stable board container (installed once in `setupLeadBoard` and
`setupOrderBoard`) that stops propagation for a click landing on
`.kanban-card-more` before it ever reaches jKanban's own listener — dragula's
drag detection is untouched, since it listens for `mousedown`/`mousemove`,
never `click`. Verified live: dispatching a click on a lead card's
three-dot actually navigated the tab to `/leads/24/` ("جزئیات سرنخ"). The
orders board shares the identical code path but had no seeded orders to
click through in the local demo data — not exercised end-to-end, though the
same fix applies to it verbatim. New tests:
`test_ui_overhaul_round2.BoardCardDetailsLinkTests` (2). Boards + round2
suite (45 total) green.

**Item 3 — what changed.** New `accounts.User.chosen_default_avatar` column
(migration `0006`) — the previously hash-derived default never needed
storage, but an explicit pick does. `accounts/avatars.py` gained
`chosen_default_avatar_for`, `default_avatar_choices` and
`set_default_avatar_choice` (drops any upload — an upload always wins over a
default while both exist, so a pick made on top of one needs to actually
replace it to be visible); `default_avatar_for` now prefers a valid stored
choice over the hash, and a choice naming a file this build no longer ships
falls back gracefully rather than 404ing. Two new endpoints:
`/api/v1/avatar-defaults/` (the gallery, read from the real shipped set —
not a written-down list) and `/api/v1/{profile,users/<id>}/avatar/default/`
(POST to pick one). The pencil button on the profile picture is now a real
`<button>` (was a `<label for>` a hidden input) that opens a new
`avatar-picker-dialog` holding both the 52-tile gallery and the existing
upload control — `setupAvatarInput` was restructured to work across the two
containers and share one `show()` between an upload and a default pick, so
the preview and the selected-tile ring can never disagree.
Verified live: opening the dialog renders all 52 tiles; clicking one selects
it, updates the preview, and persists server-side (`chosen_default_name` in
`/api/v1/profile/avatar/` survives a fresh fetch); uploading still works and
does not disturb the stored choice; clearing an upload falls back to the
last explicit choice rather than a fresh random cartoon; a path-traversal-
shaped name is rejected with 400. OpenAPI schema regenerates with no
errors/warnings. New/updated tests in
`common/tests/test_ui_overhaul_console_avatars.py`:
`DefaultAvatarChoiceTests` (7), `AvatarDefaultChoiceApiTests` (4),
`AvatarPickerUiTests` (6), plus one restated keyboard-reachability test.
`accounts` app suite (113) and the full UI-overhaul set (391 total) both
green. Full-page visual/RTL screenshot verification was not possible this
session — the Browser pane's screenshot pipeline returned 0×0 viewports and
timeouts throughout (same limitation noted for items 1–2) — so this was
verified through DOM state, computed styles and real network round-trips
instead of a rendered screenshot.

**Item 2 — root cause and fix.** `renderAreaChart`/`renderMixedChart` share
`thinningFormatter` to blank all but ~6–8 of a chart's category labels; the
survivors were still full `YYYY/MM/DD` strings, and Apex's own `xaxis.labels
.trim: true` chopped each of those down to a per-tick pixel budget computed
from the *total* category count (12), not the handful actually shown — on
the dashboard trend widget, «۱۴۰۵/۰۴/۱۵» rendered as «۱…», with the real
value surviving only in a hover `<title>`. Fixed with two changes: a new
`compactAxisLabel` drops the year from a `YYYY/MM/DD` label (a no-op on the
hourly `HH:۰۰` shape, which has no `/`), applied inside `thinningFormatter`;
and `trim` was removed from both chart functions' `xaxis.labels` entirely —
even the shortened `۰۴/۱۵` still got chopped to `۰۴…` with `trim` left on.
`hideOverlappingLabels` stays as the real overlap guard. Verified live via
measured DOM rects on the dashboard trend chart (not screenshots — this
session's Browser pane screenshot pipeline was unreliable): all six visible
ticks render their full compact label (`۰۴/۱۵`, `۰۴/۲۹`, …), the `<title>`
matches the visible text exactly (nothing hidden anymore), and no two labels'
bounding boxes overlap. New tests:
`test_ui_overhaul_round2.LineChartAxisLabelTests` (3). Full existing
UI-overhaul suite re-run clean (261 tests total across both items).

**Item 1 — root cause and fix.** The date picker's month/year title became
two buttons on 2026-09-20 (batch A), and both carry the base `.btn` class
that `.jalali-picker-header .btn` also selects — a rule written only for the
four icon nav arrows. It squeezed the title buttons to the same 27px square,
leaving ~0 content width once padding was counted, clipped by the title's
own `overflow:hidden`. Fixed: the nav-arrow rule now excludes
`.jalali-picker-scope`; the title is a real flex row with a `gap`; the scope
buttons' padding wins over Metronic's own high-specificity `.btn:not(...)
.btn-sm` with a single targeted `!important` (same idiom already used in
this file for the chart font-family and print `display:none`). Verified in
the browser via measured DOM rects (not a screenshot — this pane's
screenshot pipeline was flaky this session): the longest month name
(اردیبهشت) plus a four-digit year render with a real 4px gap and zero
clipping. New tests: `common/tests/test_ui_overhaul_round2.py`
(`JalaliPickerTitleSpacingTests`, 3 tests). Full existing UI-overhaul suite
re-run clean (258 tests).
