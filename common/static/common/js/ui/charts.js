import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDateTime} from "dolphin/core/jalali.js";
import {textOrNull} from "dolphin/core/money.js";
import {setupJalaliInputs} from "dolphin/ui/jalali-picker.js";

/**
 * One horizontal bar per item, drawn from `div`s.
 *
 * The panel deliberately ships no charting library: the theme's ApexCharts
 * lives inside a 3.5 MB bundle that `collectstatic` excludes, and every
 * chart here is a comparison across a handful of rows, which a bar answers
 * without one. See docs/frontend/CHARTS_GROUNDWORK.md.
 *
 * `items` is `[{label, value, display}]` — `value` sizes the bar, `display`
 * is what the reader sees, already formatted by the caller. Keeping those
 * apart is what stops a chart printing a raw `12500000.00` beside tables
 * reading grouped rial, which is what the two renderers this replaces had
 * each drifted into doing in their own way.
 *
 * options:
 *   ariaLabel  what the chart says to a screen reader; bars announce nothing
 *   limit      keep only the first N after sorting (a "top N" chart)
 *   sort       order by value descending; off for fixed categories such as
 *              ageing buckets or a time series, where the sequence itself
 *              carries the meaning
 *   keepZero   draw zero-valued items as empty tracks instead of dropping
 *              them — for a fixed category, an empty bucket is information
 */
//: One offscreen canvas, reused rather than created per call — this is
//: called once per category on every horizontal bar chart the panel
//: draws, and a `<canvas>` is not free to allocate.
let _measureCanvas = null;

/**
 * How wide a string actually renders in a given font, in CSS pixels.
 *
 * Exists because ApexCharts' own automatic y-axis gutter sizing — meant
 * to reserve enough room for the longest category label before drawing
 * the plot — measured badly for this panel's Persian category names and
 * IRANSansWeb: on a live chart the gutter came out at 45px for labels
 * that render 150–160px wide, so every bar's own opening third drew
 * directly under the category name instead of the label sitting beside
 * it. Measuring the text ourselves and setting the gutter from that
 * number, rather than trusting Apex's own calculation, is what actually
 * keeps a bar chart's "keys" — its category names — outside the bars,
 * the same way its values now sit outside them too.
 */
function measureTextWidth(text, font) {
    _measureCanvas ??= document.createElement("canvas");
    const context = _measureCanvas.getContext("2d");
    context.font = font;
    return context.measureText(text).width;
}

/**
 * The series colours, taken from the purchased theme rather than chosen.
 *
 * Read at draw time from the live custom properties, so a chart drawn in
 * dark mode gets the theme's dark values — `--bs-primary` is `#1B84FF` in
 * light and `#006AE6` in dark, and a hard-coded hex would be wrong in one
 * of them.
 */
export function chartPalette() {
    const style = getComputedStyle(document.documentElement);
    const read = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
    return [
        read("--bs-primary", "#1B84FF"),
        read("--bs-success", "#17C653"),
        read("--bs-info", "#7239EA"),
        read("--bs-warning", "#F6C000"),
        read("--bs-danger", "#F8285A"),
        // `--bs-dark` used to close this out. On this panel's own dark
        // theme that value sits only a few shades off the card
        // background it draws on, so a chart's sixth series all but
        // vanished — the same bug `WIDGET_STYLE`'s "dark" accents had
        // (common/ui_views.py, 2026-09-11). Orange is the same fill
        // `severityRamp` below already reaches for to widen this exact
        // palette, for the same reason.
        read("--bs-orange", "#fd7e14"),
    ];
}

export function chartInk() {
    const style = getComputedStyle(document.documentElement);
    return {
        grid: style.getPropertyValue("--bs-gray-300").trim() || "#DBDFE9",
        // Axis labels and legends: gray-500 is 2.6:1 on a white card; gray-700
        // passes AA there (2.40.31). The dark theme's gray-500 already reads.
        muted: document.documentElement.getAttribute("data-bs-theme") === "dark"
            ? (style.getPropertyValue("--bs-gray-500").trim() || "#99A1B7")
            : (style.getPropertyValue("--bs-gray-700").trim() || "#4B5675"),
        text: style.getPropertyValue("--bs-gray-800").trim() || "#252F4A",
    };
}

/**
 * Everything every chart on this panel shares.
 *
 * ApexCharts is the theme's own chart library and comes from its plugin
 * bundle. What is set here is the part the theme cannot know: the panel is
 * RTL and Persian, its type is IRANSansWeb, and it has a dark mode that the
 * library has to be told about because Apex renders to SVG with its own
 * colours rather than inheriting the page's.
 */
export function apexBase(height) {
    const ink = chartInk();
    const dark = document.documentElement.getAttribute("data-bs-theme") === "dark";
    return {
        chart: {
            height,
            fontFamily: chartFontFamily(),
            // Apex flips its own axes and legend from this, so the whole
            // chart reads right-to-left like the page around it.
            defaultLocale: "en",
            toolbar: {show: false},
            // Off deliberately. Apex animates a chart from an empty state
            // to its real geometry with requestAnimationFrame, so a chart
            // that mounts where frames are not being produced — a
            // background tab, a card still hidden, a headless browser — is
            // left showing the empty first frame permanently. Measured
            // exactly that: bars stuck at `M0.101 ... L0.101`, zero width,
            // and an area path flat on its baseline below the plot.
            //
            // It also costs nothing to lose. These are dense financial
            // report charts, not a landing page, and since a theme switch
            // now redraws every chart, keeping it would replay a half-second
            // grow on all of them each time the reader toggles light/dark.
            animations: {enabled: false},
            background: "transparent",
        },
        theme: {mode: dark ? "dark" : "light"},
        grid: {
            borderColor: ink.grid,
            strokeDashArray: 4,
            padding: {top: 0, right: 8, bottom: 0, left: 8},
            // Horizontal rules only. The purchased theme's charts read
            // values off the y axis and use the x axis purely for
            // sequence, so vertical rules add ink without adding a
            // reading — the "graph paper" look that made these feel
            // heavier than the theme's own (product-owner note
            // 2026-09-09). Each chart that genuinely needs the vertical
            // set turns it back on for itself.
            xaxis: {lines: {show: false}},
            yaxis: {lines: {show: true}},
        },
        tooltip: {
            style: {fontFamily: chartFontFamily(), fontSize: "13px"},
        },
        legend: {
            fontFamily: chartFontFamily(),
            labels: {colors: ink.muted},
            markers: {radius: 3},
            // Measured on a live legend: the marker's own edge landed
            // exactly on the label's edge, a real 0px gap, not merely a
            // tight one. Apex's built-in item spacing (an inline
            // `margin: 2px 5px` on the whole item) puts room *between*
            // items but nothing between a marker and its own label, so
            // this is set explicitly rather than left to the default.
            itemMargin: {horizontal: 10, vertical: 6},
        },
        noData: {
            text: "داده‌ای برای نمایش نیست.",
            style: {fontFamily: chartFontFamily(), color: ink.muted},
        },
    };
}

//: One live chart per container. Apex keeps its own DOM and listeners, so a
//: redraw has to destroy the previous instance or every reload leaves one
//: behind — on a page whose filters redraw on every submit, that is a leak
//: that grows for as long as the tab is open.
export const liveCharts = new WeakMap();

//: What it would take to draw each chart on the page again, keyed by its
//: container. Apex bakes the palette into the SVG at draw time — including
//: the text colours — so a chart drawn in light mode keeps light-mode ink
//: after a switch to dark, where `--bs-gray-800` ink on a dark card is
//: nearly invisible. Redrawing is the only way to re-read the palette.
export const chartRedraws = new Map();

/**
 * The face Apex should draw its own text in: whatever the panel's body
 * is set in right now — the reader's own choice when they made one
 * (`common.preferences.preference_css`), the theme's IRANSans otherwise.
 * Until 2.18.7 every chart named IRANSans literally, so a reader who
 * chose another typeface still got IRANSans labels, tooltips and centre
 * figures on every chart.
 */
export function chartFontFamily() {
    return getComputedStyle(document.body).fontFamily || "IRANSansWeb, Helvetica, sans-serif";
}

export function mountApex(chart, empty, options, ariaLabel) {
    const existing = liveCharts.get(chart);
    if (existing) {
        existing.destroy();
        liveCharts.delete(chart);
    }
    chart.replaceChildren();
    chart.hidden = false;
    empty.hidden = true;
    const instance = new ApexCharts(chart, options);
    instance.render();
    liveCharts.set(chart, instance);
    if (ariaLabel) chart.setAttribute("aria-label", ariaLabel);
    return instance;
}

/* --- the shared chart controls ------------------------------------------

   One component, used by every chart in the panel that has a time axis.

   Before 2.11.0 there were three: the customers page had «هفتگی /ماهانه/
   بازه دلخواه», the seller profile had «هفتگی/ماهانه», and the eleven list
   pages had nothing at all. They looked different, offered different
   things, and two of them were asking the wrong question — «هفتگی یا
   ماهانه» is a bucket width, and a reader picking a filter is choosing how
   much time to look at, not how wide a bar is. The bucket width follows
   from the window and is decided once, on the server
   (`reports/ranges.py::granularity_for`).

   Product owner, 2026-09-20: «یک فیلتر زمانی جذاب و یکدست (مثلاً امروز /
   ۷ روز / ۳۰ روز / ۳ ماه / سال / بازه دلخواه)».
*/

//: The presets, in the order they are drawn. `days` is the window's length;
//: `null` means the reader names both ends themselves.
const CHART_RANGES = Object.freeze([
    {key: "today", label: "امروز", days: 1},
    {key: "7d", label: "۷ روز", days: 7},
    {key: "30d", label: "۳۰ روز", days: 30},
    {key: "3m", label: "۳ ماه", days: 90},
    {key: "1y", label: "یک سال", days: 365},
    {key: "custom", label: "بازه دلخواه", days: null},
]);

//: Thirty days is what a list page opens on: long enough to have a shape,
//: short enough that today is still visible in it. The two growth charts
//: open on a year, which is what they always covered — see `setupChartRange`'s
//: `initial` option.
const DEFAULT_CHART_RANGE = "30d";
//: Only where `setupChartRange` is asked for it (`allTime`): the whole history.
const ALL_TIME_RANGE = Object.freeze({key: "all", label: "همهٔ زمان‌ها", days: null});

/**
 * A range selector and, beside it, the way back from a zoom.
 *
 * Builds its own markup rather than reading it out of a template: it is
 * mounted in twelve places, and twelve copies of a button group is exactly
 * the drift this replaces. A page opts in with one empty element.
 *
 * `onChange(window)` receives `{period_start, period_end}` as ISO strings,
 * or `{}` for a custom range the reader has not finished naming yet — the
 * caller sends those straight on as query parameters.
 *
 * Returns `{value, window, resetHost}`: the last two let a caller redraw
 * with the current selection without re-reading the DOM.
 */
export function setupChartRange(host, onChange, options = {}) {
    if (!host || host.dataset.chartRangeReady === "1") return null;
    host.dataset.chartRangeReady = "1";
    const initial = options.initial || DEFAULT_CHART_RANGE;
    let active = initial;
    // «همهٔ زمان‌ها» — no window at all — for a page whose subject can be
    // older than a year (campaign analysis, 2.40.23). Off unless asked for.
    const ranges = options.allTime ? [ALL_TIME_RANGE, ...CHART_RANGES] : CHART_RANGES;

    host.classList.add("dolphin-chart-controls");
    const group = document.createElement("div");
    group.className = "btn-group btn-group-sm dolphin-chart-range";
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", options.label || "بازهٔ زمانی نمودار");

    const custom = document.createElement("div");
    custom.className = "dolphin-chart-range-custom";
    custom.hidden = true;
    const from = document.createElement("input");
    const to = document.createElement("input");
    [from, to].forEach((field, index) => {
        field.type = "text";
        field.className = "form-control form-control-sm form-control-solid";
        field.dataset.jalali = "date";
        field.placeholder = index === 0 ? "از تاریخ" : "تا تاریخ";
        field.setAttribute("aria-label", index === 0 ? "از تاریخ" : "تا تاریخ");
    });
    const apply = document.createElement("button");
    apply.type = "button";
    apply.className = "btn btn-sm btn-light";
    apply.textContent = "اعمال";
    custom.append(from, to, apply);

    const reset = chartResetButton();

    function emit() {
        onChange(chartRangeWindow(active, from.value, to.value));
    }

    ranges.forEach((range) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.chartPreset = range.key;
        button.textContent = range.label;
        const on = range.key === active;
        button.className = `btn btn-sm ${on ? "btn-primary" : "btn-light"}`;
        button.setAttribute("aria-pressed", String(on));
        button.addEventListener("click", () => {
            active = range.key;
            group.querySelectorAll("[data-chart-preset]").forEach((other) => {
                const chosen = other === button;
                other.classList.toggle("btn-primary", chosen);
                other.classList.toggle("btn-light", !chosen);
                other.setAttribute("aria-pressed", String(chosen));
            });
            const isCustom = range.key === "custom";
            custom.hidden = !isCustom;
            // A preset redraws at once; a custom range waits for both
            // ends, because half a window is not a window.
            if (!isCustom) emit();
            else from.focus();
        });
        group.append(button);
    });

    apply.addEventListener("click", emit);
    host.append(group, custom, reset);
    setupJalaliInputs(host);
    return {
        value: () => active,
        window: () => chartRangeWindow(active, from.value, to.value),
        resetHost: reset,
    };
}

/**
 * The way back from a drag-zoom.
 *
 * Apex's own toolbar used to carry this as a house glyph floating over
 * the top-right of the plot, and could not show it without also showing
 * a magnifier for a gesture the plot already had (product owner:
 * «آیکون ذره‌بین حذف شود؛ آیکون خانه جای بهتری برود با تولتیپ «حالت
 * پیش‌فرض»»). It sits in the card header now and appears only once
 * there is something to go back from — see `chartResetEvents`.
 *
 * Its own factory rather than part of `setupChartRange`, because the
 * dashboard's trend widget is zoomable but has no range filter: that
 * card is a summary of a fixed twelve weeks and re-running the whole
 * dashboard payload per click is not what a summary is for. It still
 * needs the way back.
 */
export function chartResetButton() {
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "btn btn-sm btn-light btn-icon dolphin-chart-reset";
    reset.title = "حالت پیش‌فرض";
    reset.setAttribute("aria-label", "حالت پیش‌فرض");
    reset.innerHTML = '<i class="di-outline di-home-2 fs-4"></i>';
    reset.hidden = true;
    return reset;
}

/**
 * A preset key (and, for a custom range, two typed dates) as a window.
 *
 * The end of every preset is now, not the end of today: a chart whose last
 * bucket runs into the future draws a cliff down to zero on every page
 * load after midnight.
 */
function chartRangeWindow(key, fromText, toText) {
    if (key === "custom") {
        const start = apiDateTime(textOrNull(fromText));
        const end = apiDateTime(textOrNull(toText));
        return start && end ? {period_start: start, period_end: end} : {};
    }
    const preset = CHART_RANGES.find((range) => range.key === key);
    if (!preset || preset.days === null) return {};
    const end = new Date();
    const start = new Date(end.getTime() - preset.days * 86400000);
    return {period_start: start.toISOString(), period_end: end.toISOString()};
}

/**
 * Wire a chart instance's zoom state to its reset button.
 *
 * Apex has no "is this zoomed" property, so the two events that change it
 * are what drives the button: `zoomed` fires on a drag-select (and on the
 * reset itself, with the full range, which is why the payload is read
 * rather than assumed) and `beforeResetZoom` on the way back.
 */
export function chartResetEvents(button, chartEl) {
    if (!button) return {};
    // Bound once per button, not per redraw: a chart that is redrawn
    // (a new range, a theme switch) hands the same button to a new Apex
    // instance, and a second listener would reset twice.
    if (button.dataset.chartResetBound !== "1") {
        button.dataset.chartResetBound = "1";
        button.addEventListener("click", () => {
            const live = chartEl && liveCharts.get(chartEl);
            // `resetSeries(shouldUpdateChart, shouldResetZoom)` — the
            // second argument is the one that matters here.
            if (live) live.resetSeries(true, true);
            button.hidden = true;
        });
    }
    return {
        zoomed: (_context, {xaxis}) => {
            button.hidden = !(xaxis && (xaxis.min !== undefined || xaxis.max !== undefined));
        },
        beforeResetZoom: () => { button.hidden = true; },
    };
}

/**
 * The selectors a chart declares for itself, drawn from its own payload.
 *
 * `filters` comes back with the data (`reports/list_charts.py::filters_for`)
 * rather than being written into a template, so a filter added to that
 * table appears here with no markup change — «فیلترهای معنادار اضافه شود
 * (بر اساس بازاریاب، وضعیت، منبع سرنخ)», and the next one after those.
 *
 * Rebuilt on each load, but the reader's own choices are carried across:
 * changing the window must not silently clear the marketer they picked.
 */
export function renderChartFilters(host, filters, chosen, onChange) {
    if (!host) return;
    host.replaceChildren();
    host.hidden = !filters || !filters.length;
    if (host.hidden) return;
    filters.forEach((filter) => {
        const field = document.createElement("select");
        field.className = "form-select form-select-sm form-select-solid dolphin-chart-filter";
        field.setAttribute("aria-label", filter.label);
        const any = document.createElement("option");
        any.value = "";
        // Written per filter on the server rather than built here:
        // «همهٔ» + a singular noun is wrong Persian for half of them, and
        // pluralising in JavaScript is guesswork.
        any.textContent = filter.all_label || `همهٔ ${filter.label}`;
        field.append(any);
        filter.options.forEach((option) => {
            const item = document.createElement("option");
            item.value = option.value;
            item.textContent = option.label;
            field.append(item);
        });
        field.value = chosen[filter.param] || "";
        field.addEventListener("change", () => {
            onChange(filter.param, field.value);
        });
        host.append(field);
    });
}

export function showEmptyChart(chart, empty) {
    const existing = liveCharts.get(chart);
    if (existing) {
        existing.destroy();
        liveCharts.delete(chart);
    }
    chart.replaceChildren();
    chart.hidden = true;
    empty.hidden = false;
}

/**
 * A donut, for "what is this total made of".
 *
 * Chosen over a pie because the hole carries the total, which is the number
 * a reader wants first — and because a ring compares arc lengths, which the
 * eye reads better than the wedge areas of a pie.
 */
export function renderDonutChart(chart, empty, items, options = {}) {
    const {ariaLabel = null, total = null, totalLabel = ""} = options;
    if (!chart || !empty) return;
    chartRedraws.set(chart, () => renderDonutChart(chart, empty, items, options));

    const usable = items.filter((item) => Number.isFinite(item.value) && item.value > 0);
    if (!usable.length) {
        showEmptyChart(chart, empty);
        return;
    }

    const palette = chartPalette();
    const ink = chartInk();
    // The already-formatted strings, held beside the series so the tooltip
    // and the centre can print rial rather than the bare number Apex has.
    const displays = usable.map((item) => item.display ?? String(item.value));

    mountApex(chart, empty, {
        ...apexBase(320),
        series: usable.map((item) => item.value),
        labels: usable.map((item) => item.label),
        colors: usable.map((item, index) => item.color || palette[index % palette.length]),
        chart: {...apexBase(320).chart, type: "donut"},
        // A ring of flat fills reads as a diagram; the theme's own pie and
        // donut widgets shade each wedge slightly across its own arc, which
        // is what gives them depth. `shade: "light"` keeps every wedge the
        // colour it was assigned — the ramp only varies its own lightness,
        // so two adjacent wedges never blend into one another.
        fill: {
            type: "gradient",
            gradient: {shade: "light", shadeIntensity: 0.28, opacityFrom: 1, opacityTo: 0.92},
        },
        stroke: {width: 2, colors: ["transparent"]},
        states: {
            hover: {filter: {type: "darken", value: 0.9}},
            active: {filter: {type: "none"}},
        },
        // No text drawn on the wedges themselves. A percentage printed on a
        // thin slice either overlaps its neighbour or gets clipped outside
        // the ring — the smaller the share, the less room its own label
        // has. The legend below is already outside the chart and has all
        // the room it needs, so the percentage moves there instead of
        // living on the drawing.
        dataLabels: {enabled: false},
        legend: {
            ...apexBase(320).legend,
            position: "bottom",
            // Name and share together, entirely outside the ring: "شهر X
            // — ۴۲٪" rather than a bare label the reader has to match back
            // to a wedge by colour alone.
            formatter: (label, opts) => {
                const value = opts.w.globals.series[opts.seriesIndex];
                const total = opts.w.globals.series.reduce((sum, each) => sum + each, 0);
                const percent = total > 0 ? Math.round((value / total) * 100) : 0;
                return `${label} — ${toPersianDigits(String(percent))}٪`;
            },
        },
        tooltip: {
            ...apexBase(320).tooltip,
            y: {formatter: (_value, {seriesIndex}) => displays[seriesIndex]},
        },
        plotOptions: {
            pie: {
                donut: {
                    size: "68%",
                    labels: {
                        show: true,
                        // Apex would print the raw number here; the total is
                        // formatted by the server, which is the only place
                        // that knows whether this series is rial or a count.
                        total: {
                            show: true,
                            showAlways: true,
                            label: totalLabel || "مجموع",
                            color: ink.muted,
                            fontFamily: chartFontFamily(),
                            formatter: () =>
                                total ||
                                toPersianDigits(
                                    String(usable.reduce((carry, item) => carry + item.value, 0)),
                                ),
                        },
                        value: {
                            color: ink.text,
                            fontFamily: chartFontFamily(),
                            fontSize: "20px",
                            fontWeight: 700,
                            formatter: (_value, opts) =>
                                displays[opts?.seriesIndex ?? 0] ?? _value,
                        },
                        name: {
                            color: ink.muted,
                            fontFamily: chartFontFamily(),
                        },
                    },
                },
            },
        },
    }, ariaLabel);
}

/**
 * An axis-only shorthand for a `bucketLabel` — drops the year from a
 * full `YYYY/MM/DD` so the day and month are what's left to read.
 *
 * Product owner, 2026-09-21: «نمودار های خطی، در پایینش اعداد روز ها رو
 * درست نمایش نمیده». Measured live: `xaxis.labels.trim` was chopping
 * every surviving tick down to «۱…» — Apex trims to a per-tick pixel
 * budget too narrow for the full ten-character date, and the untruncated
 * value survived only in the label's own `<title>` (a hover tooltip
 * almost nobody finds). Category array and tooltip both keep the full
 * date — this only shortens what actually draws on the axis, and only
 * for the `YYYY/MM/DD` shape `displayDay` produces; an hourly bucket's
 * `HH:۰۰` (`bucketLabel`) has no `/` and passes through unchanged.
 */
function compactAxisLabel(label) {
    const parts = String(label).split("/");
    return parts.length === 3 ? parts.slice(1).join("/") : label;
}

/**
 * A tick-label formatter that prints only every Nth category's own
 * label, blank otherwise, so at most `maxLabels` of them ever reach the
 * axis — the *category* array itself stays untouched, so the tooltip
 * (which reads the same array for its own title) still names every
 * point.
 *
 * Apex's own `tickAmount`/`hideOverlappingLabels` are built for
 * horizontal label text; measured live on this panel's own rotated
 * (-45°) date labels, neither actually thinned anything — every one of
 * twelve category labels still rendered, each overlapping the label
 * beside it (design review, 2026-09-12).
 */
/**
 * An amount axis label a reader takes in at a glance (2.40.36): «۲۵ میلیون»
 * rather than «25000000». Whole numbers below a thousand stay as they are; one
 * decimal place only where it says something («۲٫۵ میلیارد»).
 */
export function compactAmount(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "";
    const size = Math.abs(number);
    const steps = [[1e9, "میلیارد"], [1e6, "میلیون"], [1e3, "هزار"]];
    const step = steps.find(([unit]) => size >= unit);
    if (!step) return toPersianDigits(String(Math.round(number)));
    const scaled = number / step[0];
    const shown = Math.abs(scaled) >= 10 || Number.isInteger(scaled) ? Math.round(scaled) : Math.round(scaled * 10) / 10;
    return `${toPersianDigits(String(shown).replace(".", "٫"))} ${step[1]}`;
}

export function thinningFormatter(labels, maxLabels) {
    const step = Math.max(1, Math.ceil(labels.length / Math.max(1, maxLabels)));
    return (value) => {
        const index = labels.indexOf(value);
        return index === -1 || index % step === 0 ? compactAxisLabel(value) : "";
    };
}

/**
 * A filled area over a line, for a quantity moving through time.
 *
 * The fill is what separates this from a plain line: it gives the series a
 * mass the eye can compare between periods, and the gradient fades it out
 * before the axis so the shape stays legible where points sit close.
 */
/**
 * On the axis direction, so it is not re-litigated.
 *
 * The hand-drawn chart this replaced reversed its x-axis so the earliest
 * point sat on the right, which is where a reader of an RTL panel starts.
 * `xaxis.reversed: true` is the Apex equivalent and was tried here — it is
 * a no-op in the build the purchased theme ships: measured, the earliest
 * category stayed leftmost at x=66 with it set. On horizontal bars the same
 * option is worse than a no-op and collapses every bar to zero width.
 *
 * The theme's own charts set neither `reversed` nor `opposite` and read
 * left-to-right in its RTL build, so all of these do too. That is a real
 * change from the hand-drawn behaviour, not an oversight.
 */
export function renderAreaChart(chart, empty, points, options = {}) {
    const {ariaLabel = null, summary = "", maxLabels = 8} = options;
    if (!chart || !empty) return;
    chartRedraws.set(chart, () => renderAreaChart(chart, empty, points, options));

    const usable = points.filter((point) => Number.isFinite(point.value));
    // One point is not a line. Two are the fewest that can show a direction,
    // and a direction is what this chart is for.
    if (usable.length < 2) {
        showEmptyChart(chart, empty);
        return;
    }

    const palette = chartPalette();
    const accent = options.color || palette[0];
    const displays = usable.map((point) => point.display ?? String(point.value));
    const base = apexBase(300);

    mountApex(chart, empty, {
        ...base,
        // Apex's own toolbar is off (it is off in `apexBase` too) and
        // drag-to-zoom is on. Until 2.11.0 the toolbar was shown for the
        // reset icon alone, which dragged a magnifier along with it: a
        // button for a gesture the plot already had, floating over the
        // top-right of the drawing. The gesture stays, the magnifier is
        // gone, and the way back is the header's own `dolphin-chart-reset`
        // — see `chartResetEvents`.
        chart: {
            ...base.chart,
            type: "area",
            zoom: {enabled: true, type: "x", autoScaleYaxis: true},
            events: {
                ...(base.chart.events || {}),
                ...chartResetEvents(options.resetButton, chart),
            },
        },
        series: [{name: options.seriesName || "مقدار", data: usable.map((p) => p.value)}],
        colors: [accent],
        dataLabels: {enabled: false},
        stroke: {curve: "smooth", width: 3},
        // The purchased theme's own area widgets fade to nothing at the
        // baseline (`opacityTo: 0`, stops 0/80/100 — src/js/widgets/charts/
        // widget-11.js). Ours stopped at 0.05, which left a visible band
        // sitting on the axis and made the fill read as a block rather
        // than as a fade.
        fill: {
            type: "gradient",
            gradient: {shadeIntensity: 1, opacityFrom: 0.45, opacityTo: 0, stops: [0, 80, 100]},
        },
        // Markers only where the pointer is. A dot on every point turns a
        // twelve-week line into a dotted rule; the line is the shape being
        // read, and the point under the cursor is the one that matters.
        markers: {size: 0, strokeWidth: 3, hover: {size: 7}},
        xaxis: {
            categories: usable.map((point) => point.label),
            tickAmount: Math.min(maxLabels, usable.length),
            labels: {
                style: {fontFamily: chartFontFamily(), fontSize: "12px"},
                hideOverlappingLabels: true,
                // Deliberately no `trim` option here (product owner,
                // 2026-09-21: «اعداد روز ها رو درست نمایش نمیده»). Apex
                // sizes its own trim budget from the plot width divided
                // by the *category*
                // count, not the handful `thinningFormatter` actually
                // leaves visible — measured live on this exact chart,
                // a 5-character «۰۴/۱۵» (already shortened by
                // `compactAxisLabel`) still came out «۰۴…», 2 characters
                // kept. `thinningFormatter` already bounds what reaches
                // the axis to a short, complete string; `trim` only
                // chopped it again into something shorter and unreadable.
                // `hideOverlappingLabels` stays on as the real backstop.
                formatter: thinningFormatter(usable.map((point) => point.label), maxLabels),
            },
            axisBorder: {show: false},
            axisTicks: {show: false},
        },
        yaxis: {
            labels: {
                style: {fontFamily: chartFontFamily(), fontSize: "12px"},
                formatter: (value) => toPersianDigits(String(Math.round(value))),
            },
        },
        tooltip: {
            ...base.tooltip,
            y: {formatter: (_value, {dataPointIndex}) => displays[dataPointIndex]},
        },
    }, ariaLabel);

    if (summary) {
        const note = document.createElement("p");
        note.className = "text-muted fs-7 mt-3 mb-0 text-center";
        note.textContent = summary;
        chart.append(note);
    }
}

/**
 * A horizontal bar chart, for comparing named things against each other.
 *
 * Horizontal rather than vertical because the labels are Persian names of
 * arbitrary length — customer names, product names, provinces — and a
 * vertical chart has one column of width for each of them.
 */
export function renderBarChart(chart, empty, items, options = {}) {
    const {ariaLabel = null, limit = 0, sort = true, keepZero = false, colorBy = null} = options;
    if (!chart || !empty) return;
    chartRedraws.set(chart, () => renderBarChart(chart, empty, items, options));

    const palette = chartPalette();
    const usable = items.filter((item) => Number.isFinite(item.value) && item.value >= 0);
    const positive = usable.filter((item) => item.value > 0);
    // A chart of nothing but zeros is an empty chart, whatever keepZero says.
    if (!positive.length) {
        showEmptyChart(chart, empty);
        return;
    }

    let shown = keepZero ? usable.slice() : positive.slice();
    if (sort) shown.sort((a, b) => b.value - a.value);
    if (limit > 0) shown = shown.slice(0, limit);

    // The server formats every value — rial with its separators, or a plain
    // count — so the axis and the tooltip print what it sent rather than
    // Apex's own idea of the number.
    const displays = shown.map((item) => item.display ?? String(item.value));
    // The bar's own "key" and its value, combined into one label drawn
    // past the bar's tip. A separate y-axis column for the category name
    // was the first cut here, and it does not work: Apex reserves that
    // column's own width from an internal text measurement that came out
    // wrong for Persian names in IRANSansWeb on a live chart — a 45px
    // gutter for labels that render 150–160px wide, so every bar's own
    // opening third drew directly *under* its own name. `grid.padding.
    // left` does not move that gutter either; measured with it set to
    // 180px, the bars had not shifted a pixel. Rather than fight an
    // internal calculation this codebase cannot see into, the name joins
    // the value as one string, drawn through the *other* label mechanism
    // — the per-bar dataLabel already proven to land outside the bar's
    // own tip (see the `offsetX`/`textAnchor` reasoning below) — and the
    // y-axis column is turned off outright rather than left half-working.
    const combined = shown.map((item) => `${item.label} — ${item.display ?? String(item.value)}`);
    const LABEL_FONT = "600 12px IRANSansWeb, Helvetica, sans-serif";
    // How far past the longest bar's own tip its label needs the axis to
    // reach — measured in real pixels against this chart's own rendered
    // width, not guessed as a flat percentage. A flat percentage was the
    // first cut here too: it happened to clear a short value-only label,
    // and would not have scaled to a name-and-value string roughly twice
    // as wide. `chart` is the actual container element already in the
    // DOM (`mountApex` below hands it straight to ApexCharts), so its
    // real width is known before a single option is decided from it.
    const CLEARANCE_PX = 56; // the 40px offset below, plus a few px of breathing room
    const widestLabelPx = Math.max(...combined.map((text) => measureTextWidth(text, LABEL_FONT)));
    const neededPx = widestLabelPx + CLEARANCE_PX;
    const plotWidthPx = chart.clientWidth - 24; // grid.padding's own left+right, roughly
    const maxValue = Math.max(...shown.map((item) => item.value));
    const axisMax =
        plotWidthPx > neededPx
            ? (maxValue * plotWidthPx) / (plotWidthPx - neededPx)
            // The container has no real width yet — mounted while still
            // hidden, the one situation `chart.clientWidth` cannot answer
            // for. A generous fixed multiple keeps the chart readable
            // rather than betting on an unmeasurable number; a chart that
            // becomes visible without a resize/redraw is an existing,
            // separate concern (`chartRedraws`), not one this guards.
            : maxValue * 3;
    const colours = shown.map(
        (item, index) =>
            item.color || (colorBy ? colorBy(item, index) : palette[index % palette.length]),
    );
    // Enough room per bar to stay readable, and a floor so a two-bar chart
    // does not become two enormous slabs.
    const height = Math.max(220, shown.length * 44 + 60);
    const base = apexBase(height);

    mountApex(chart, empty, {
        ...base,
        chart: {...base.chart, type: "bar"},
        series: [{name: options.seriesName || "مقدار", data: shown.map((item) => item.value)}],
        colors: colours,
        // Apex fills bars at 0.85 by default, which on a white card turns
        // every one of these into a paler version of the colour that was
        // chosen to mean something. The severity ramp only reads if the
        // colours are the ones it names.
        fill: {opacity: 1},
        // A bar lifts under the pointer rather than only its tooltip
        // appearing — the theme's own charts do this, and on a ranking
        // where the rows are read one after another it is what tells you
        // which row the tooltip belongs to.
        states: {
            hover: {filter: {type: "darken", value: 0.88}},
            active: {filter: {type: "none"}},
        },
        plotOptions: {
            bar: {
                horizontal: true,
                // Rounded at the tip only (product-owner request
                // 2026-09-09: closer to the purchased theme). The theme's
                // own bar widgets round 5–6px; rounding *both* ends of a
                // horizontal bar detaches it from its own axis, which is
                // why this names the end rather than raising the radius.
                borderRadius: 6,
                borderRadiusApplication: "end",
                barHeight: "62%",
                // Without this every bar takes the first colour, because a
                // single series is one colour to Apex unless told otherwise.
                distributed: true,
                // The value used to print at the *inside* end of the bar —
                // set in the same colour the bar was filled, on a short bar
                // that is white-on-white and unreadable, and on a long one
                // it sits crammed against the tip with nothing behind it
                // but the bar's own fill. `"top"` draws it just past the
                // bar's own end instead, outside the coloured shape
                // entirely, so it reads the same for the shortest bar and
                // the longest one.
                dataLabels: {position: "top", maxItems: 100},
            },
        },
        // `distributed` gives each bar its own legend entry, which for a
        // top-ten list is ten redundant swatches beside ten labelled bars.
        legend: {show: false},
        dataLabels: {
            enabled: true,
            formatter: (_value, {dataPointIndex}) => combined[dataPointIndex],
            // 40px, not a token gesture of a few pixels: measured
            // directly against the rendered SVG, Apex places a bar's
            // dataLabel anchor a fixed ~29px *inside* the bar's own tip
            // regardless of `plotOptions.bar.dataLabels.position`, which
            // (for a plain, non-stacked horizontal bar, unlike a stacked
            // one) turned out not to move that anchor at all. 40px of
            // offset is what actually pushes the anchor past the tip
            // with a few pixels to spare, not merely past the point
            // where `position: "top"` stopped helping.
            offsetX: 40,
            // The SVG `text-anchor` axis follows the element's own
            // reading direction, inherited here as RTL from the page —
            // measured both ways rather than assumed from the property
            // name: `"start"` keeps the text's *right* edge at the
            // anchor and grows it leftward, back over the bar; `"end"`
            // keeps the *left* edge at the anchor and grows rightward,
            // away from the bar, which is the one that actually clears
            // it.
            textAnchor: "end",
            style: {
                fontFamily: chartFontFamily(),
                fontSize: "12px",
                fontWeight: 600,
                // Drawn outside the bar now, against the card's own
                // background — so this reads with the page's own ink
                // colour rather than the white Apex assumes for a label
                // sitting on top of a filled shape.
                colors: [chartInk().text],
            },
            dropShadow: {enabled: false},
        },
        xaxis: {
            categories: shown.map((item) => item.label),
            // Deliberately NOT `reversed: true`, which is the obvious way
            // to make these read right-to-left. In the Apex build the theme
            // ships, that option collapses every horizontal bar to zero
            // width — measured: each path came out as `M0.101 ... L0.101`,
            // a vertical line at the origin. The purchased theme never sets
            // it either, and draws its own charts left-to-right in the RTL
            // build. So do these.
            labels: {show: false},
            axisBorder: {show: false},
            axisTicks: {show: false},
            max: axisMax,
        },
        // No separate label column — see the comment above `combined`.
        // The category names still reach the tooltip: Apex reads them
        // from `xaxis.categories` below regardless of whether this axis
        // draws its own text, so hovering a bar still names it.
        yaxis: {
            labels: {show: false},
            axisBorder: {show: false},
            axisTicks: {show: false},
        },
        grid: {...base.grid, xaxis: {lines: {show: true}}, yaxis: {lines: {show: false}}},
        tooltip: {
            ...base.tooltip,
            y: {formatter: (_value, {dataPointIndex}) => displays[dataPointIndex]},
        },
    }, ariaLabel);
}

/**
 * Several named things, each measured on the same few counts, side by side
 * (2.40.23 — campaigns compared on their funnel). Vertical groups: one group
 * per thing, one bar per measure, the measure's colour the same in every
 * group so the eye compares like with like. `series` is `[{name, values}]`,
 * `values` lining up with `categories`.
 */
export function renderGroupedBarChart(chart, empty, categories, series, options = {}) {
    const {ariaLabel = null, height = 320, format = (value) => toPersianDigits(String(value))} = options;
    if (!chart || !empty) return;
    chartRedraws.set(chart, () => renderGroupedBarChart(chart, empty, categories, series, options));
    if (!categories.length || !series.some((one) => one.values.some((value) => Number(value) > 0))) {
        showEmptyChart(chart, empty);
        return;
    }
    const ink = chartInk();
    const base = apexBase(height);
    mountApex(chart, empty, {
        ...base,
        chart: {...base.chart, type: "bar"},
        series: series.map((one) => ({name: one.name, data: one.values.map(Number)})),
        colors: chartPalette(),
        plotOptions: {bar: {columnWidth: categories.length > 4 ? "70%" : "50%", borderRadius: 3}},
        dataLabels: {enabled: false},
        xaxis: {
            categories,
            labels: {style: {colors: ink.muted, fontFamily: chartFontFamily()}, trim: true, hideOverlappingLabels: false},
        },
        yaxis: {labels: {style: {colors: ink.muted}, formatter: (value) => format(Math.round(value))}},
        tooltip: {...base.tooltip, y: {formatter: (value) => format(value)}},
        legend: {...base.legend, position: "top"},
    }, ariaLabel);
}

/**
 * One line per named thing over the same periods (2.40.23 — valid invoices
 * per month, per campaign). `series` is `[{name, values}]`, `values` lining
 * up with `labels`; a thing with nothing in any period still gets its line.
 */
export function renderMultiLineChart(chart, empty, labels, series, options = {}) {
    const {ariaLabel = null, height = 320, format = (value) => toPersianDigits(String(value))} = options;
    if (!chart || !empty) return;
    chartRedraws.set(chart, () => renderMultiLineChart(chart, empty, labels, series, options));
    if (labels.length < 2 || !series.length || !series.some((one) => one.values.some((value) => Number(value) > 0))) {
        showEmptyChart(chart, empty);
        return;
    }
    const ink = chartInk();
    const base = apexBase(height);
    mountApex(chart, empty, {
        ...base,
        chart: {...base.chart, type: "line"},
        series: series.map((one) => ({name: one.name, data: one.values.map(Number)})),
        colors: chartPalette(),
        stroke: {curve: "smooth", width: 2.5},
        markers: {size: 3, strokeWidth: 0},
        dataLabels: {enabled: false},
        xaxis: {
            categories: labels,
            labels: {style: {colors: ink.muted, fontFamily: chartFontFamily()}, formatter: thinningFormatter(labels, 8)},
        },
        yaxis: {labels: {style: {colors: ink.muted}, formatter: (value) => format(Math.round(value))}},
        tooltip: {...base.tooltip, shared: true, y: {formatter: (value) => format(value)}},
        legend: {...base.legend, position: "top"},
    }, ariaLabel);
}
