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
- [ ] 4. One shared time filter (today / 7d / 30d / 3m / year / custom)
- [ ] 4. Titles corrected to match their data
- [ ] 4. Extra meaningful filters where they exist
- [ ] 4. Magnifier icon removed
- [ ] 4. Home icon repositioned, tooltip «حالت پیش‌فرض»
- [ ] 5. Edit button moved to the top of the page, covers every box
- [ ] 5. Whole-widget drag, six-dot handle removed
- [ ] 5. Corner resize with sensible min/max on a grid
- [ ] 5. Delete button: more inset, better looking
- [ ] 5. Per-user layout saved/restored; reset works

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

**Current batch:** B — not started. Batch A is released as `2.10.0`
(committed, not yet deployed; the deploy is the single one at the end).

**Next step:** item 4 — the line charts. Start by reading the existing
`renderLineChart`/`setupChartRangeFilter` neighbourhood in
`common/static/common/dolphin-app.js` and §6 of `dolphin.css`, and list every
page that draws one before changing any of them; the shared time filter has to
be one component, not one per page.

**Files changed in batch A:**
- `common/static/common/dolphin.css` — §7 kanban card control and column
  padding, §8 the rewritten picker's month/year/time CSS, new §10 the shared
  hover scrollbar, new §11 calendar cells
- `common/static/common/dolphin-app.js` — jKanban `click` removed on both
  boards, `dolphin-hover-scroll` applied, `openJalaliPicker` rewritten,
  `jalaliMonthRange`/`shiftJalaliMonth`/`JALALI_MONTH_VIEW`/
  `jalaliCalendarButtons` added and used by both calendars
- `common/templates/common/leads/list.html`, `leads/detail.html`,
  `orders/list.html`, `orders/detail.html` — four scheduling fields moved to
  `data-jalali="datetime"`
- `common/tests/test_ui_overhaul_boards_dates.py` — new, 37 tests
- `common/tests/test_board_cards_and_search.py`,
  `test_bounded_lists_and_province_select.py`, `test_jalali_picker.py` — six
  tests restated for the behaviour this batch deliberately changed
- `VERSION` → `2.10.0`, `CHANGELOG.md`

**Checks run:** 82 tests across the four affected modules — OK. Full suite
before the restatements: 2293 tests, 6 failures (those six), 7 pre-existing
Selenium errors. Browser-measured: 32.5×32.5 control, card body inert, dragula
still bound, scrollbar on the right at 8px, a 31-day Mehr grid.
