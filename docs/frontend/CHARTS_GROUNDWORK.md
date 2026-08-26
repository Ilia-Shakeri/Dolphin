# Charts

Option A was taken: no charting library, one shared renderer, bars drawn from
`div`s. This records what exists and why, and the decision that was made.

## What ships

`renderBarChart(chart, empty, items, options)` in
`common/static/common/forooshbin-app.js` is the only chart renderer. `items` is
`[{label, value, display}]` — `value` sizes the bar, `display` is the already
formatted text the reader sees. Keeping those apart is deliberate: it is what
stops a chart printing `12500000.00` beside tables reading `۱۲،۵۰۰،۰۰۰ ریال`.

Options: `ariaLabel`, `limit` (top N), `sort` (off for a fixed sequence),
`keepZero` (draw an empty category rather than dropping it).

Five charts call it:

| Chart | Page | Shape |
|---|---|---|
| user performance | dashboard, company report | bar per user, sales amount |
| inbound SMS | SMS report | bar per hour, chronological (`sort: false`) |
| receivables ageing | receivables report | five buckets, fixed order, `keepZero` |
| profit composition | profit report | revenue / cost / gross profit |
| stock valuation | stock valuation report | top ten products by value |

Styling is `.performance-chart*` in `common/static/common/forooshbin.css`. Every
chart carries an `aria-label`, because bars announce nothing on their own, and
every one of these pages has an XLSX export that is the real accessible
alternative.

**Before this, there were two near-identical renderers** — one for performance,
one for inbound SMS — and they had drifted apart: the performance chart printed
raw decimals, and the SMS chart printed Gregorian dates and Latin digits in a
Persian panel. Both were consequences of the copy, and both are gone.

**Aggregate data already exists.** These return the shape a chart needs, already
feature-gated and role-scoped, so a chart needs no new backend:

| Endpoint | View |
|---|---|
| `/api/v1/reports/user-performance/` | `reports/views.py` `UserPerformanceReportView` |
| `/api/v1/reports/receivables/` | `reports/financial_views.py` `ReceivablesReportView` |
| `/api/v1/reports/profit/` | `reports/financial_views.py` `ProfitReportView` |
| `/api/v1/reports/stock-valuation/` | `reports/financial_views.py` `InventoryValuationReportView` |
| `/api/v1/reports/sales-documents/` | `reports/views.py` `SalesDocumentReportView` |

## The decision: library or no library

**ApexCharts is already inside the purchased theme** —
`assets/plugins/global/plugins.bundle.js` contains it. It is not available at
runtime, for two deliberate reasons that both have to be undone to use it:

* `STATICFILES_COLLECT_IGNORE` in `config/settings.py` excludes
  `plugins.bundle.js` from `collectstatic`;
* `common/templates/common/base.html` never references it.

That bundle is **3.5 MB**. It is Bootstrap JS plus every Metronic plugin, not
ApexCharts alone, and the panel currently needs only `KTMenu` and `KTDrawer`
from the theme's runtime. Loading it to draw a bar chart would multiply the
panel's JavaScript payload for one feature.

So the fork is:

**A. Keep hand-building.** Extend the `.performance-chart` pattern. Costs
nothing, stays inside the theme, keeps the payload where it is, and every result
is RTL- and Persian-correct because we write it. Fine for bars and simple
comparisons; poor for time series with many points, tooltips and zoom.

**B. Ship a charting library.** Either extract ApexCharts from the vendor bundle
as its own file, or add a small dedicated library. Buys interaction and time
series; costs payload, a dependency to keep current, and RTL/Persian
configuration that has to be got right per chart.

**A was chosen.** Of the five endpoints above, four are comparisons across a
handful of rows — exactly what a bar does well and where a library buys nothing.
Revisit B only when a real time series arrives with enough points to need
tooltips and zoom, and if it does, extract ApexCharts alone rather than shipping
the 3.5 MB bundle.

## Constraints any chart must satisfy

These are settled in the codebase already and are not open questions:

1. **Amounts go through `money()`.** Grouped rial with no decimals. The existing
   chart printed `12500000.00` until this was corrected — a chart is the easiest
   place to forget, because the number is a label rather than a table cell.
2. **Counts go through `toPersianDigits()`.**
3. **Dates are Jalali** via `displayDay` / `displayDate`; storage stays
   Gregorian ISO.
4. **RTL.** Categories read right to left. A library defaulting to LTR needs
   configuring per chart, not once globally.
5. **Never colour alone.** A series must be distinguishable without colour —
   label, pattern, or direct value.
6. **A text alternative is required.** `aria-label` at minimum; a table
   alternative is better, and every one of these endpoints already has an XLSX
   export that serves as one.
7. **`prefers-reduced-motion`.** Entrance animation must be skippable, and the
   data must be readable without it.
8. **Feature and scope gating.** A chart shows only what its endpoint already
   returns for that role. No chart may aggregate over rows its viewer could not
   list — the selectors decide this, not the chart.
9. **Empty and error states.** Every panel here already has
   `*-chart-empty`; a chart with no data shows that, never an empty axis frame.

## Adding another chart

Three steps, and no fourth:

1. Markup: a `div.performance-chart` with `role="img"` and an `aria-label`, and
   a sibling `p` with the same id plus `-empty`, both `hidden`.
2. Map the report rows to `{label, value, display}` — formatting the `display`
   with `money()` for amounts, `toPersianDigits()` for counts, `displayDay()`
   for dates.
3. Call `renderBarChart` with the two nodes and the items.

Do not write a second renderer. The two that existed before diverged in exactly
the ways the shared one now prevents.
