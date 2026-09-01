# Dates and the calendar (`BIZ-007`)

> Status: **resolved** by direct product-owner decision, 2026-08-16. This
> document records the resolved contract; the open question it replaces is
> struck from `OPEN_BUSINESS_DECISIONS.md`.

## The rule in one line

**Canonical everywhere, Jalali at the edge.** Storage and the versioned API keep
Gregorian ISO-8601; everything a Client-1 user reads or types is Jalali.

**No legal, tax, or accounting compliance is claimed.** This is presentation and
input behaviour. It does not decide which calendar an invoice is legally dated
in, nor define a fiscal year.

## Canonical side — unchanged

| Layer | Representation |
|---|---|
| Database columns | unchanged; timezone-aware, no schema change, no migration |
| `/api/v1/**` request and response bodies | Gregorian ISO-8601 |
| Query parameters (`period_start`, `due_before`, …) | Gregorian ISO-8601 |
| XLSX `filters` sheet | Gregorian ISO-8601 — it is the normalized query echoed back, and a test holds it identical to the JSON response |

The API is a machine contract with its own consumers and versioning. Rewriting
it in Jalali would have made every integration calendar-aware for a change that
is entirely about what a person sees.

## Presentation side — Jalali

| Surface | Behaviour |
|---|---|
| Every list, table, and detail field | `۱۴۰۵/۰۵/۲۵` / `۱۴۰۵/۰۵/۲۵ ۱۴:۳۰` |
| Every date and date-time input | typed Jalali, Persian or Latin digits accepted |
| Invoice and quotation print pages | Jalali |
| Server-generated PDF | Jalali (it renders the same print page) |
| XLSX data columns and `summary` sheets | Jalali text |
| XLSX `filters` sheet | canonical ISO **plus** a `*_jalali` row beside it |

Operational timezone is **`Asia/Tehran`**. A stored instant is converted to the
Tehran wall clock before its calendar date is taken, so an evening UTC timestamp
shows the Tehran date a user would expect rather than the previous day.

## Where the code lives

Two implementations, one algorithm, because the browser must convert without a
round trip and the server must render print, PDF, and XLSX:

* `common/jalali.py` — conversion, formatting, parsing, the operational
  timezone. Used by `common/templatetags/jalali_tags.py` (`|jalali`,
  `|jalali_datetime`, `|jalali_long`) and by `reports/xlsx.py`.
* `common/static/common/dolphin-app.js` — the same arithmetic, plus
  `displayDate` / `displayDay` for rendering, `apiDate` / `apiDateTime` for
  submitting, and `setupJalaliInputs` which gives every `[data-jalali]` field
  its behaviour once at start-up.

There is deliberately **no per-template conversion**: a template calls a filter,
a script call site calls a helper, and the arithmetic exists in exactly two
places that are tested against each other.

## Why the arithmetic is written here rather than imported

The conversion is exact integer arithmetic over the 33-year leap cycle — about
forty lines, and checkable to the day. It was verified against ICU over **16,801
consecutive days (1990–2035), in both directions, for both implementations, with
zero mismatches**; the first draft was off by one day at the epoch, and that
comparison is what caught it.

Adding a package would have meant regenerating the hash-pinned dependency lock
on a Linux host (`docs/ops/DEPENDENCIES.md`) for forty lines. Note the contrast
with `common/pdf.py`, which refuses to hand-roll Persian *text shaping*: shaping
plus bidi plus font embedding is a rendering engine and cannot be verified this
cleanly. The test is whether correctness can be established, not whether the
code is short.

## Input handling

* Persian `۰۱۲۳`, Arabic-Indic `٠١٢٣`, and Latin `0123` digits all parse.
* `/`, `-`, and `.` all separate.
* The year is bounded to **1200–1700**. `2026` is a valid Jalali year
  arithmetically — it means 2647 CE — so without the bound a Gregorian date
  pasted into a Jalali field would be accepted silently and stored six centuries
  out. This bound is enforced identically in both implementations.
* A field validates on blur and reports its own Persian message;
  `setCustomValidity` then blocks submission, so an unreadable date never
  reaches the API.
* `apiDate` / `apiDateTime` return `null` rather than throwing on an unreadable
  value, because they run on every keystroke to rebuild export links. The field
  validation above is what makes that safe.

## Deliberately not implemented

* A calendar picker widget. Typed entry with validation is the smallest correct
  answer; a picker is a UI addition, not a correctness one.
* Jalali fiscal-year or reporting-period semantics. Report periods are still
  arbitrary ranges — which period a business year covers is an unresolved
  business question, and is not answered by displaying a date.
* Jalali month names in exports (numeric form only), and any Jalali handling in
  the API.
