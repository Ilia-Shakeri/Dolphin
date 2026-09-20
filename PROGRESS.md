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
- [ ] 6. «اقلام و تخفیف» step redesigned
- [ ] 7. «تنظیمات» moved out of the user modal to the sidebar's end
- [ ] 7. «برند و لوگو» → «شخصی‌سازی پنل» inside admin settings
- [ ] 8. One header popover open at a time; Esc and outside-click everywhere

### Batch D — `3.0.0` — reports, postal, integrations
- [ ] 9. «گزارش اسناد فروش و پست» rebuilt as a wizard
- [ ] 9. «گزارش پیامک ورودی» rebuilt as a wizard
- [ ] 10. Four postal states with icons, shown as a stepper
- [ ] 10. Service layer ready for a future post-office API
- [ ] 11. API integrations page

### Batch E — `3.1.0` — console, profiles
- [ ] 12. Console lists every page/option from the real feature source
- [ ] 12. Persian/English tabs
- [ ] 12. `.exe` build
- [ ] 12. Typography and spacing
- [ ] 13. Profile photo upload with crop/resize, size and format limits
- [ ] 13. Metronic cartoon avatars as the default

### Final
- [ ] Full suite green (only the 7 known pre-existing Selenium errors)
- [ ] CHANGELOG + VERSION
- [ ] Main deploy to Nerkhbaan + health check

## Status

**Current batch:** C — not started. Batch B is released as `2.11.0`
(committed, not yet deployed; the deploy is the single one at the end).

**Next step:** item 6 — the «اقلام و تخفیف» step of the new-invoice wizard.
Read `common/templates/common/invoices/list.html`'s create dialog and the
`setupCreateInvoice`/line-item neighbourhood in `dolphin-app.js` before
changing anything, and find the closest Metronic form/table reference for a
line-item editor rather than inventing one.

**Files changed in batch B:**
- `reports/ranges.py` — new; the one place a window becomes buckets
- `reports/customer_insights.py`, `reports/sales_insights.py` — both read it
  instead of keeping a copy each; `granularity` is optional and derived
- `reports/list_charts.py` — `CHART_FILTERS`/`filters_for`/`narrowing`/
  `filter_params`, builders take `narrow=`, `trend_for` takes a window, the
  registry titles lost their hardcoded «دوازده هفتهٔ اخیر»
- `reports/serializers.py`, `reports/customer_views.py` — the window query
  serializer, the filter payload, the two-part validation
- `common/dashboard_layout.py` — capability tiles join the same overlay
- `common/ui_views.py` — one call to `arrange_capability_tiles`
- `common/static/common/dolphin-app.js` — `setupChartRange`,
  `chartRangeWindow`, `chartResetButton`, `chartResetEvents`,
  `renderChartFilters`, `bucketLabel`; both zoomable renderers; the
  dashboard editor (two grids, corner grip, no handle)
- `common/static/common/dolphin.css` — new §12 chart controls, §9 rewritten
  for the grip and the inset hide button
- `common/templates/common/home.html`, `includes/list_charts.inc`,
  `customers/list.html`, `users/profile.html`
- `common/tests/test_ui_overhaul_charts_dashboard.py` — new, 66 tests
- `common/tests/test_chart_labels.py`, `test_list_trend_charts.py`,
  `reports/tests/test_customer_insights.py` — restated for what changed
- `VERSION` → `2.11.0`, `CHANGELOG.md`

**Checks run:** 151 tests across the new module and the whole `reports` app —
OK. Browser-measured on the live panel: range group 360×35 in the card header
and 279px at 375px wide with no page scroll; «۳۰ روز»→«۷ روز» took the trend
from 31 x-axis labels to 8 and retitled it; «امروز» produced hourly labels;
the marketer filter narrowed both charts and survived the redraw;
`.apexcharts-toolbar` and `.apexcharts-zoom-icon` absent everywhere; 19
boxes across two grids all draggable with 19 grips, 19 hide buttons, 0
handles, 0 size selects; a 500px grip drag took a tile from `col-xl-3` to
`col-xl-6` and it survived a reload; a drag swap survived a reload; reset
put both order and width back and hid itself.