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

**Current batch:** D — not started. Batch C is released as `2.12.0`
(committed, not yet deployed; the deploy is the single one at the end).

**Next step:** item 9 — the two report wizards. Read
`common/templates/common/reports/` and the `setupSalesDocumentReport` /
`setupInboundSMSReport` neighbourhood in `dolphin-app.js` first, and reuse
`setupWizard` (which now takes `validateStep`) rather than writing a third
stepper. Items 10 and 11 follow in the same batch.

**Files changed in batch C:**
- `common/static/common/dolphin-app.js` — `registerPopover` /
  `closeOtherPopovers` / `setupPopoverDismissal`; all five panels rewired;
  `createLineItemRows` rebuilt with price, line total and `onChange`;
  `documentTotals` / `renderDocumentTotals` / `roundMoney` /
  `validateLinesStep` / `EMPTY_LINE_ROWS`; `setupWizard` takes `validateStep`
- `common/static/common/dolphin.css` — the lines step is a column, one shared
  grid for the header and the rows, the money columns, the summary block, the
  phone layout, a wider dialog for a wizard with a line step
- `common/templates/common/invoices/list.html`, `orders/list.html` — the
  rebuilt step; `base.html` — settings to the sidebar, branding out of it;
  `settings/settings.html`, `branding/settings.html` — «شخصی‌سازی پنل»
- `common/tests/test_ui_overhaul_invoice_settings_popovers.py` — new, 43 tests
- `common/tests/test_filter_popover.py`, `test_branding.py`,
  `test_user_preferences.py`, `test_invoice_order_wizard.py` — six tests
  restated for what this batch deliberately changed
- `VERSION` → `2.12.0`, `CHANGELOG.md`

**Checks run:** full suite — 2412 tests, no failures, only the 7 pre-existing
Selenium browser errors. Browser-measured on the live panel: wizard header and
row cells right-edge-identical (1108/800/679/590/462) with identical resolved
tracks; 3 × ۱۷٬۸۰۰٬۰۰۰ at 10% and 9% previewed ۵۲٬۳۸۵٬۴۰۰ ریال and the saved
invoice held `total_amount` 52385400.00; the duplicate-product refusal blocked
the step with its own sentence; at 375px every child of the step measured
309px with no page or dialog scroll; the sidebar's last entry is «تنظیمات» and
the user menu has none; bell → search → user menu left exactly one open each
time; Escape closed and returned focus; a click on the icon inside the search
button opened rather than closed it.