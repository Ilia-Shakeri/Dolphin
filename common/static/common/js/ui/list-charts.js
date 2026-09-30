import {apiRequest} from "dolphin/core/api.js";
import {chartPalette, renderAreaChart, renderBarChart, renderChartFilters, renderDonutChart, setupChartRange} from "dolphin/ui/charts.js";

/**
 * The direction chart beside each list page's composition chart
 * (product-owner request 2026-09-19: a ring says what a total is made of
 * and never which way it is going, so the pages that draw one now draw
 * both).
 *
 * Its column stays hidden until the server actually sends a `trend` for
 * that key — `LIST_TRENDS` (reports/list_charts.py) declares which keys
 * have one — so a page without a trend renders a single full-width chart
 * rather than a half-width one beside an empty gap.
 */
function renderListTrend(card, trend, resetButton) {
    const column = card.querySelector("[data-list-trend]");
    const canvas = card.querySelector("[data-list-trend-canvas]");
    const empty = card.querySelector("[data-list-trend-empty]");
    if (!column || !canvas || !empty) return;
    if (!trend || !trend.points?.length) {
        column.hidden = true;
        return;
    }
    column.hidden = false;
    const heading = card.querySelector("[data-list-trend-title]");
    // The server names the window it actually drew — «روند ثبت سرنخ در ۳۰
    // روز گذشته» — so the heading follows the range filter rather than
    // saying «دوازده هفتهٔ اخیر» over whatever the reader picked.
    if (heading && trend.title) heading.textContent = trend.title;
    // The same smooth area the dashboard's own trend uses — one "recent
    // direction" shape across the product.
    renderAreaChart(canvas, empty, trend.points, {
        ariaLabel: trend.title,
        summary: trend.summary || "",
        seriesName: "تعداد",
        color: chartPalette()[2],
        resetButton,
    });
}

export async function setupListCharts() {
    const cards = Array.from(document.querySelectorAll("[data-list-chart]"));
    await Promise.all(cards.map(async (card) => {
        const key = card.dataset.listChart;
        const canvas = card.querySelector("[data-list-chart-canvas]");
        const empty = card.querySelector("[data-list-chart-empty]");
        const heading = card.querySelector("[data-list-chart-title]");
        const filterHost = card.querySelector("[data-chart-filters]");
        if (!canvas || !empty) return;

        // The reader's own narrowing, kept across a redraw: changing the
        // window must not silently clear the marketer they picked.
        const chosen = {};
        const range = setupChartRange(
            card.querySelector("[data-chart-range]"),
            () => { load(); },
            {label: "بازهٔ زمانی روند"},
        );

        async function load() {
            const query = new URLSearchParams(range ? range.window() : {});
            Object.entries(chosen).forEach(([name, value]) => {
                if (value) query.set(name, value);
            });
            try {
                const report = await apiRequest(
                    `/api/v1/reports/list-chart/${key}/?${query}`
                );
                if (heading && report.title) heading.textContent = report.title;
                renderChartFilters(filterHost, report.filters, chosen, (name, value) => {
                    chosen[name] = value;
                    load();
                });
                renderListTrend(card, report.trend, range && range.resetHost);
                // Every one of these is a breakdown of a total, so the shape is
                // chosen by how many parts there are rather than by which page
                // it is. Up to six, a ring compares the parts and names the
                // whole in its middle. Past that the arcs get too small to
                // compare and bars read better — the server caps the list at
                // twelve plus a grouped «سایر», so both cases really occur.
                const slices = report.results.filter((row) => Number(row.value) > 0);
                if (slices.length && slices.length <= 6) {
                    renderDonutChart(canvas, empty, report.results, {
                        ariaLabel: report.title,
                        total: report.total_display || null,
                        totalLabel: report.total_label || "",
                    });
                } else {
                    renderBarChart(canvas, empty, report.results, {
                        // The builder already ordered them and put its grouped
                        // tail last; re-sorting here would lift "سایر" into the
                        // middle.
                        sort: false,
                        ariaLabel: report.title,
                    });
                }
            } catch (error) {
                canvas.hidden = true;
                empty.textContent = "نمودار این فهرست در دسترس نیست.";
                empty.hidden = false;
                // One request feeds both charts, so a failure takes both: a
                // trend column left open beside a "not available" message
                // would read as a second chart that is merely still loading.
                const trendColumn = card.querySelector("[data-list-trend]");
                if (trendColumn) trendColumn.hidden = true;
            }
        }

        await load();
    }));
}
