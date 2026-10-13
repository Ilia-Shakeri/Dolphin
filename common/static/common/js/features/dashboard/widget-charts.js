import {toPersianDigits} from "dolphin/core/digits.js";
import {apexBase, chartFontFamily, chartInk, chartPalette, chartRedraws, chartResetEvents, compactAmount, liveCharts, mountApex, showEmptyChart, thinningFormatter} from "dolphin/ui/charts.js";

/**
 * Make a widget's chart use the room its box has been given.
 *
 * A chart is drawn at one fixed height, so a box dragged taller (or
 * shorter) left the plot the same size with empty card around it (product
 * owner, 2026-09-29: «وقتی سایزشون عوض میشه اطلاعات توشون هم همراه باهاش
 * تغییر سایز بدن»). Width already followed: Apex redraws on its parent's
 * width. Height is worked out here from the box's own minimum height minus
 * everything in the card that is *not* the chart, so the card stays
 * exactly as tall as the reader made it and nothing is pushed out.
 * Observed rather than triggered by the editor, so it also holds after a
 * reload, a theme switch and a phone rotation.
 */
export function fitWidgetChart(column) {
    const card = column.querySelector(":scope > .card");
    const host = card && card.querySelector("[id$='-chart'], .dashboard-gauge-canvas");
    if (!host || column.dataset.chartFit || column.dataset.widgetKey === "performance") return;
    column.dataset.chartFit = "1";
    let base = null;
    let frame = 0;
    const usedAround = () => {
        let used = 0;
        let node = host;
        while (node && node !== card.parentElement) {
            const parent = node.parentElement;
            if (!parent) break;
            for (const sibling of parent.children) {
                if (sibling === node) continue;
                const style = getComputedStyle(sibling);
                if (style.display === "none" || style.position === "absolute") continue;
                used += sibling.offsetHeight + parseFloat(style.marginTop) + parseFloat(style.marginBottom);
            }
            const box = getComputedStyle(parent);
            used += parseFloat(box.paddingTop) + parseFloat(box.paddingBottom)
                + parseFloat(box.borderTopWidth) + parseFloat(box.borderBottomWidth);
            if (parent === card) break;
            node = parent;
        }
        const hostStyle = getComputedStyle(host);
        return used + parseFloat(hostStyle.marginTop) + parseFloat(hostStyle.marginBottom);
    };
    const apply = () => {
        frame = 0;
        const instance = liveCharts.get(host);
        if (!instance) return;
        if (base === null) base = Number(instance.w.config.chart.height) || host.offsetHeight;
        const minimum = parseFloat(getComputedStyle(card).minHeight) || 0;
        const target = Math.max(base, Math.floor(minimum - usedAround()));
        if (Math.abs(target - Number(instance.w.config.chart.height)) < 4) return;
        instance.updateOptions({chart: {height: target}}, false, false);
    };
    const schedule = () => {
        if (!frame) frame = requestAnimationFrame(apply);
    };
    if (typeof ResizeObserver === "function") new ResizeObserver(schedule).observe(card);
    new MutationObserver(schedule).observe(column, {attributes: true, attributeFilter: ["style"]});
    schedule();
}

/**
 * An amount as a smooth area with a count overlaid as bars — one series
 * answering "how much", the other "how many", read together. Apex's own
 * combo-chart mode (the purchased theme's own mixed-chart widgets page): two
 * series, each naming its own `type`, sharing one x-axis.
 *
 * `points` carries the area series exactly as `renderAreaChart` reads it
 * (`{label, value, display}`); `counts` is the bar series, one integer
 * per point, same order — `_sales_trend` (common/dashboard.py) is the one
 * caller today and already returns the two aligned.
 */
export function renderMixedChart(chart, empty, points, counts, options = {}) {
    const {ariaLabel = null, summary = "", maxLabels = 8, seriesNames = ["مقدار", "تعداد"]} = options;
    if (!chart || !empty) return;
    chartRedraws.set(chart, () => renderMixedChart(chart, empty, points, counts, options));

    const usable = points.filter((point) => Number.isFinite(point.value));
    if (usable.length < 2) {
        showEmptyChart(chart, empty);
        return;
    }

    const palette = chartPalette();
    const amountColor = options.amountColor || palette[0];
    const countColor = options.countColor || palette[1];
    const displays = usable.map((point) => point.display ?? String(point.value));
    const base = apexBase(300);

    // Apex's own per-series `fill.type` array (`["gradient","solid"]`) is
    // the documented way to gradient-shade one series and leave another
    // solid — and does exactly that for a single area's own fill
    // (`renderAreaChart`, same `gradient` object, above). Combined with a
    // second `bar` series on the same chart it does not: measured live,
    // the bar's own `<path fill>` still points at the area's
    // black-to-transparent gradient def rather than a solid `countColor`,
    // rendering "تعداد فروش" as a near-invisible smudge instead of a
    // green bar (design review, 2026-09-12). Rather than chase which
    // Apex internal combo triggers that, the bar's own fill is set
    // directly once the chart (and every redraw/theme switch) has drawn
    // it — the same "fix what the vendor library gets wrong at the
    // point it's wrong" this codebase already does for FullCalendar and
    // the theme's own broken box-shadow declarations.
    const forceSolidBars = (chartCtx) => {
        chartCtx.el.querySelectorAll(".apexcharts-bar-series path").forEach((bar) => {
            bar.setAttribute("fill", countColor);
            bar.setAttribute("fill-opacity", "1");
        });
    };

    mountApex(chart, empty, {
        ...base,
        chart: {
            ...base.chart,
            type: "line",
            // Apex's drag-to-zoom is on by default for a line/area
            // series, so a reader can already narrow the range and needs
            // a way back (design review, 2026-09-12). Until 2.11.0 that
            // way back was Apex's own toolbar, which could not show the
            // reset icon without also showing a magnifier for the gesture
            // the plot already had. The toolbar is off now and the way
            // back lives in the card header beside the range filter —
            // see `chartResetEvents` and `renderAreaChart`'s copy of this.
            zoom: {enabled: true, type: "x", autoScaleYaxis: true},
            events: {
                mounted: (ctx) => forceSolidBars(ctx),
                updated: (ctx) => forceSolidBars(ctx),
                ...chartResetEvents(options.resetButton, chart),
            },
        },
        series: [
            {name: seriesNames[0], type: "area", data: usable.map((point) => point.value)},
            {name: seriesNames[1], type: "bar", data: counts},
        ],
        colors: [amountColor, countColor],
        dataLabels: {enabled: false},
        stroke: {curve: "smooth", width: [3, 0]},
        fill: {
            type: ["gradient", "solid"],
            gradient: {shadeIntensity: 1, opacityFrom: 0.45, opacityTo: 0, stops: [0, 80, 100]},
            opacity: [1, 1],
        },
        plotOptions: {
            bar: {columnWidth: "35%", borderRadius: 4},
        },
        markers: {size: 0, strokeWidth: 3, hover: {size: 7}},
        legend: {...base.legend, show: true, position: "top", horizontalAlign: "center"},
        xaxis: {
            categories: usable.map((point) => point.label),
            tickAmount: Math.min(maxLabels, usable.length),
            labels: {
                style: {fontFamily: chartFontFamily(), fontSize: "12px"},
                hideOverlappingLabels: true,
                // Deliberately no `trim` option — see the identical
                // comment in `renderAreaChart`'s own copy of this block,
                // above.
                formatter: thinningFormatter(usable.map((point) => point.label), maxLabels),
            },
            axisBorder: {show: false},
            axisTicks: {show: false},
        },
        // Two y-axes, one per series: an amount in the millions and a
        // count in the single digits would otherwise share one scale and
        // flatten the bar series to an invisible sliver at the bottom.
        yaxis: [
            {
                seriesName: seriesNames[0],
                labels: {
                    style: {fontFamily: chartFontFamily(), fontSize: "12px", colors: amountColor},
                    formatter: compactAmount,
                },
            },
            {
                seriesName: seriesNames[1],
                opposite: true,
                forceNiceScale: true,
                labels: {
                    style: {fontFamily: chartFontFamily(), fontSize: "12px", colors: countColor},
                    formatter: (value) => toPersianDigits(String(Math.round(value))),
                },
            },
        ],
        tooltip: {
            ...base.tooltip,
            shared: true,
            y: {
                formatter: (value, {seriesIndex, dataPointIndex}) =>
                    seriesIndex === 0 ? displays[dataPointIndex] : toPersianDigits(String(value)),
            },
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
 * A radial gauge — one 0–100 figure as a filled ring with the number in
 * its own hollow centre, ApexCharts' `radialBar` type. Product-owner
 * request 2026-09-11: the purchased theme uses this for exactly this
 * shape of number (a rate, a quota, a completion percentage — see
 * `custom/widgets.js`'s "mixed widget 5"/"mixed widget 11" and
 * `widgets/sliders/widget-1.js`) and this panel had never actually drawn
 * one, despite having several numbers of exactly that shape on the
 * dashboard already.
 *
 * `value` is a plain 0–100 number, already computed by the caller from a
 * real ratio — this function only draws it, it invents no rate of its
 * own.
 */
export function renderGaugeChart(chart, empty, value, options = {}) {
    const {ariaLabel = null, accent = "primary", label = ""} = options;
    if (!chart || !empty) return;
    chartRedraws.set(chart, () => renderGaugeChart(chart, empty, value, options));

    if (!Number.isFinite(value)) {
        showEmptyChart(chart, empty);
        return;
    }
    const clamped = Math.max(0, Math.min(100, value));

    const style = getComputedStyle(document.documentElement);
    const base = style.getPropertyValue(`--bs-${accent}`).trim() || chartPalette()[0];
    const track = style.getPropertyValue(`--bs-${accent}-light`).trim();
    const ink = chartInk();
    const base320 = apexBase(220);

    mountApex(chart, empty, {
        ...base320,
        chart: {
            ...base320.chart,
            type: "radialBar",
            // The theme's own gauges are sparklines — no axis, no grid,
            // just the ring — and `apexBase`'s grid/tooltip settings mean
            // nothing on a chart with one data point and no plot area.
            sparkline: {enabled: true},
        },
        series: [Math.round(clamped * 10) / 10],
        colors: [base],
        stroke: {lineCap: "round"},
        plotOptions: {
            radialBar: {
                hollow: {margin: 0, size: "65%"},
                track: {background: track, strokeWidth: "100%"},
                dataLabels: {
                    show: true,
                    name: {show: false},
                    value: {
                        show: true,
                        offsetY: 10,
                        fontSize: "28px",
                        fontWeight: 700,
                        color: ink.text,
                        fontFamily: chartFontFamily(),
                        formatter: (raw) => toPersianDigits(String(Math.round(raw))) + "٪",
                    },
                },
            },
        },
        labels: [label],
    }, ariaLabel);
}

/**
 * A tiny trend line inside a KPI tile — no axis, no grid, no tooltip
 * text beyond the raw values, exactly ApexCharts' own `sparkline` mode.
 * Product-owner request 2026-09-11: the tile's own number and the
 * one-line comparison next to it both say "more or less than before";
 * this is the shape of that story, at a glance, before the reader has
 * even read the comparison.
 *
 * Never shown empty: `kpiCard` only calls this when the KPI carried a
 * `spark` array at all, so there is no empty-state to draw here — a
 * missing series is a tile with no spark slot, not a slot with nothing
 * in it.
 */
export function renderSparkline(el, values, options = {}) {
    if (!el || !Array.isArray(values) || values.length < 3) return;
    const {accent = "primary"} = options;
    const color = getComputedStyle(document.documentElement).getPropertyValue(`--bs-${accent}`).trim()
        || chartPalette()[0];
    const existing = liveCharts.get(el);
    if (existing) {
        existing.destroy();
        liveCharts.delete(el);
    }
    el.replaceChildren();
    // One smooth stroke over a very soft fill of the same hue, no axes, no
    // shadow, and a dot on the latest point — the figure below is that
    // point (2.40.3). Not animated: a tile redraws on every theme switch.
    const instance = new ApexCharts(el, {
        chart: {height: 36, type: "area", sparkline: {enabled: true}, animations: {enabled: false}, dropShadow: {enabled: false}},
        series: [{data: values}],
        colors: [color],
        stroke: {curve: "smooth", width: 2},
        fill: {type: "solid", opacity: 0.08},
        markers: {
            size: 0,
            discrete: [{seriesIndex: 0, dataPointIndex: values.length - 1, size: 3, fillColor: color, strokeColor: color}],
        },
        tooltip: {enabled: false},
    });
    instance.render();
    liveCharts.set(el, instance);
}

/**
 * Several 0–100 figures as concentric rings in one drawing — ApexCharts'
 * own multi-series `radialBar`, the theme's own pattern for "several
 * shares that together read as one whole"
 * (`src/js/widgets/charts/widget-30.js`). `renderGaugeChart` above draws
 * one ratio; this is its many-ring sibling, for the one place on this
 * panel several ratios are meant to be compared at once — each seller's
 * share of the same month (product-owner request 2026-09-11).
 *
 * `items` is `[{label, value, amount_display}]`, values already 0–100 and
 * already summing to (at most) 100 — this draws what it is given, it
 * does not normalise or invent a remainder ring.
 */
export function renderMultiGaugeChart(chart, empty, items, options = {}) {
    const {ariaLabel = null} = options;
    if (!chart || !empty) return;
    chartRedraws.set(chart, () => renderMultiGaugeChart(chart, empty, items, options));

    const usable = items.filter((item) => Number.isFinite(item.value) && item.value > 0);
    if (!usable.length) {
        showEmptyChart(chart, empty);
        return;
    }

    const palette = chartPalette();
    const ink = chartInk();
    const base340 = apexBase(340);

    mountApex(chart, empty, {
        ...base340,
        chart: {...base340.chart, type: "radialBar"},
        series: usable.map((item) => item.value),
        labels: usable.map((item) => item.label),
        colors: usable.map((item, index) => item.color || palette[index % palette.length]),
        stroke: {lineCap: "round"},
        plotOptions: {
            radialBar: {
                // Measured live at the old 18%: the innermost ring's own
                // radius came out to 19.5px, while the two-line total
                // label ("مجموع" + "۱۰۰٪") it sits inside is ~58px tall —
                // three times too small a hollow for what has to fit in
                // it, so the total overlapped the innermost ring's own
                // arc (design review, 2026-09-12). Widened, and the total
                // value's own font shrunk a step, so both lines clear the
                // ring at up to six sellers.
                hollow: {size: "34%"},
                track: {strokeWidth: "88%"},
                dataLabels: {
                    name: {fontSize: "13px", fontFamily: chartFontFamily()},
                    value: {
                        fontSize: "16px",
                        fontWeight: 700,
                        color: ink.text,
                        fontFamily: chartFontFamily(),
                        formatter: (raw) => toPersianDigits(String(Math.round(raw))) + "٪",
                    },
                    total: {
                        show: true,
                        label: "مجموع",
                        color: ink.muted,
                        fontSize: "13px",
                        fontFamily: chartFontFamily(),
                        formatter: () =>
                            toPersianDigits(String(Math.round(usable.reduce((sum, item) => sum + item.value, 0)))) + "٪",
                    },
                },
            },
        },
        legend: {
            ...base340.legend,
            show: true,
            position: "bottom",
            formatter: (label, opts) => {
                const item = usable[opts.seriesIndex];
                return `${label} — ${item.amount_display ?? ""}`;
            },
        },
    }, ariaLabel);
}
