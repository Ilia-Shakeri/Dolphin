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

**Current batch:** E — not started. Batch D is released as `2.13.0`
(committed, not yet deployed; the deploy is the single one at the end).
Released as MINOR rather than the `3.0.0` first planned: nothing in it breaks
a contract, and §23 says the number follows what changed.

**Next step:** item 12 — the Python build console. Find the console's own
source first (it is an operator tool, not part of the served panel) and the
real feature source it must read from — `common/deployment/registry.py` and
the manifest — rather than the hand-maintained list it has now. Item 13
(marketer profile photos, Metronic cartoon avatars) follows.

**Files changed in batch D:**
- `sales/postal.py` — new; the four states and the carrier seam
- `sales/serializers.py`, `sales/views.py`, `sales/services.py` — the
  label/stepper fields, the `postal-states` endpoint, the default state
- `reports/list_charts.py` — the status chart groups by label; a postal
  filter
- `reports/xlsx.py`, `reports/views.py`, `reports/financial_views.py`,
  `reports/urls.py`, `communications/views.py`, `communications/urls.py` —
  two workbook builders, two export views, `build` split out of `get`
- `common/integrations.py` — new; the registry behind the new page
- `common/ui_views.py`, `common/ui_urls.py` — `IntegrationsView`
- `common/templates/common/settings/integrations.html` — new
- `common/templates/common/reports/sales_documents.html`,
  `reports/inbound_sms.html` — both rebuilt as wizards
- `common/templates/common/sales_documents/detail.html`, `list.html`,
  `settings/settings.html`
- `common/static/common/dolphin-app.js` — `setupReportWizard`,
  `renderPostalStepper`, `fillPostalStates`/`loadPostalStates`/
  `postalStateLabel`, `setupIntegrations`; both report pages rewired
- `common/static/common/dolphin.css` — new §13 postal stepper, §14
  integrations, §15 report wizards
- `common/tests/ui_overhaul_helpers.py` — new; one copy of the readers the
  four overhaul modules had each been carrying
- `common/tests/test_ui_overhaul_reports_postal_integrations.py` — new, 53
  tests; the other three overhaul modules switched to the shared helper
- seven existing tests restated, including one Selenium test that could not
  be executed here
- `VERSION` → `2.13.0`, `CHANGELOG.md`

**Checks run:** full suite — 2467 tests, no failures, only the 7 pre-existing
Selenium browser errors (the 8th, the SMS shell, was restated for the wizard
and is one of the seven suites that cannot run in this environment). OpenAPI
schema generates with no errors and no warnings. Browser-measured: the
parcels wizard stepping 1/1 → 4/4 with the report visible at the end, section
toggles hiding panels in place, going back and changing the range rebuilding
on the way forward, both exports returning real XLSX with the right headers,
the postal stepper reading done/done/current/upcoming after a real transition
with no horizontal overflow at 1536px or 375px, and the integrations page
listing SMS (test printing the provider's own refusal), post and «به‌زودی».