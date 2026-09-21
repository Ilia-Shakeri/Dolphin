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

- [ ] 1. Calendar month/year header — normal, even spacing → `2.14.1`
- [ ] 2. Line chart bottom day-number labels wrong → `2.14.2`
- [ ] 3. Profile picture: choose from defaults + upload in a new modal → `2.14.3`
- [ ] 4. Three-dot "view details" on board/list cards must open the detail page → `2.14.4`
- [ ] 5. Receipts wizard step 2 (document info) — spacing redesign → `2.14.5`
- [ ] 6. Postal tracking — 4 connected icons in a row, current stage lit → `2.14.6`
- [ ] 7. Report wizards (sales-docs, post, inbound-sms) centered; province as a dropdown → bundled into `2.14.7`
- [ ] 8. Excel import/export buttons get a small Excel icon → bundled into `2.14.7`
- [ ] 9. Post integration settings page, like SMS → `2.14.7`
- [ ] 10. Dashboard widget editing — smoother, Apple/Android-widget-like → bundled into `2.14.8`
- [ ] 11. Rename SMS settings entry to a general "اتصال سامانه‌ها" connections hub → `2.14.8`
- [ ] 12. Locate/relocate the console `.exe` to the project root; report its name

### Final
- [ ] Full suite green
- [ ] CHANGELOG + VERSION for each release above
- [ ] Main deploy to Nerkhbaan + health check

## Status

**Current:** starting item 1.
