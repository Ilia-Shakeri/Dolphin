# Charts — what exists, and the one decision to make first

Groundwork only. Nothing here is built yet; this records what the codebase
already has so the first real chart is a choice rather than an accident.

## What already exists

**One chart ships today.** `renderPerformanceChart` in
`common/static/common/forooshbin-app.js` draws a horizontal bar per user for
confirmed sales amount. It is **hand-built from `div`s and CSS**, with no
library at all — the bar is a `<span>` whose `width` is a percentage of the
largest value. It appears on the dashboard and on the company report, driven by
`setupPerformancePanel("dashboard")` and `setupPerformancePanel("report")`.

Its styling is `.performance-chart*` in `common/static/common/forooshbin.css`.
It carries an `aria-label` describing what it shows, which is the only reason it
is readable to a screen reader — bars alone announce nothing.

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

**A recommendation:** start with A. Of the five endpoints above, four are
comparisons across a handful of rows — exactly what a bar does well and where a
library buys nothing. Revisit B only when a genuine time series arrives, and if
it does, extract ApexCharts alone rather than shipping the 3.5 MB bundle.

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

## Where a chart would go first

The dashboard already reserves the markup: `[data-performance-panel]` with
`*-performance-chart` and `*-performance-chart-empty` beside it. Anything new
should follow that shape rather than invent a second one.
