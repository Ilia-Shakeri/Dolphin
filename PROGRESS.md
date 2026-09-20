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
- [ ] Main deploy to Nerkhbaan + health check

## Status

**Current batch:** all five are implemented, tested and committed. Batch E is
released as `2.14.0` — MINOR, like the rest: one new table nothing existing
depends on, and everything else additive.

**Next step:** the single deploy to Nerkhbaan, then the health check and the
final report. Nothing else is outstanding.

**Files changed in batch E:**
- `common/deployment/pages.py` — new; the panel's page inventory, derived
- `scripts/console_strings.py` — new; the console's fa/en strings
- `scripts/build_console_exe.py` — new; the PyInstaller build and its verify
- `scripts/manifest_builder.py` — the checklist names pages, the language
  switch, `--self-check`, the grid
- `scripts/requirements-console.txt` — PyInstaller, operator-only
- `accounts/avatars.py`, `accounts/avatar_views.py`, `accounts/urls.py` —
  new; the picture, its gate and its three endpoints
- `accounts/models.py` + `accounts/migrations/0005_useravatar.py`
- `common/static/common/avatars/` — the 52 Metronic cartoons (421 KB)
- `common/static/common/dolphin-app.js` — `cropAvatarFile`,
  `setupAvatarInput`; `common/static/common/dolphin.css` — new §16
- `common/templates/common/base.html`, `common/ui_views.py` — the header face
- `scripts/bootstrap-postgres.sh`, `common/tests/test_database_privileges.py`
  — the new table's GRANT
- `reports/ranges.py` — `bucket_key` localises before taking a date
- `common/tests/test_ui_overhaul_console_avatars.py` — new, 55 tests;
  `ui_overhaul_helpers.py` gained `python_function`
- three existing tests restated
- `VERSION` → `2.14.0`, `CHANGELOG.md`

**Checks run:** full suite — 2522 tests, no failures, only the 7 pre-existing
Selenium browser errors. Browser-measured: a 1200×800 PNG of 25,444 bytes
stored as a 512×512 JPEG of 4,149 bytes with `image/jpeg`, `private,
max-age=300` and `nosniff`; the header face at 35×35 after a reload; a
non-image refused in Persian and a 3 MiB body with 413; clearing restoring
the cartoon and the image 404ing past the cache; the console showing 28
feature rows each naming its pages, and `?lang=en` flipping the document to
`lang="en" dir="ltr"`. `--self-check` run for real: 28 features, 18 opening
pages, 49 pages behind a feature.