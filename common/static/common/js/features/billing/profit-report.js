import {apiRequest} from "dolphin/core/api.js";
import {apiDateTime, displayDate, localDateTimeValue} from "dolphin/core/jalali.js";
import {clearMessages, showError} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {loadCustomerOptions, renderReportRows, reportSection} from "dolphin/features/billing/shared.js";
import {chartPalette, renderBarChart} from "dolphin/ui/charts.js";
import {bindReportTableSearch} from "dolphin/ui/report-wizard.js";
import {appendActionLinks, appendCell, appendMoneyCell} from "dolphin/ui/table.js";

/**
 * Revenue against cost against gross profit, for the period.
 *
 * Three bars rather than a ratio, because the question a reader brings to
 * this page is how much of the revenue the cost ate. Not sorted: revenue is
 * always the largest and the sequence is the comparison.
 *
 * Profit can be negative, and the renderer draws no bar below zero. The
 * figure is still printed beside the empty track, and the summary card
 * above carries it too, so a loss is never hidden — it simply has no bar.
 */
function renderProfitCompositionChart(report) {
    const order = [
        ["درآمد", report.revenue],
        ["بهای تمام‌شده", report.cost],
        ["سود ناخالص", report.profit],
    ];
    renderBarChart(
        document.getElementById("profit-composition-chart"),
        document.getElementById("profit-composition-chart-empty"),
        order.map(([label, amount]) => ({
            label,
            value: Math.max(0, Number(amount)),
            display: money(amount),
        })),
        {
            sort: false,
            keepZero: true,
            // Revenue is the whole, cost is what it ate, profit is what
            // survived — so cost is warned and profit is green.
            colorBy: (item, index) => {
                const palette = chartPalette();
                return [palette[0], palette[3], palette[1]][index] || palette[0];
            },
            ariaLabel: "نمودار مقایسه درآمد، بهای تمام‌شده و سود ناخالص",
        },
    );
}

export async function setupProfitReport() {
    const form = document.getElementById("profit-filter-form");
    const exportLink = document.getElementById("profit-export");
    bindReportTableSearch(
        document.getElementById("profit-search"),
        [document.getElementById("profit-table-body")],
    );
    const startField = document.getElementById("profit-period-start");
    const endField = document.getElementById("profit-period-end");

    // A month back to now, so the page shows real numbers on arrival rather
    // than an empty frame waiting for the operator to guess a range.
    const now = new Date();
    const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    startField.value = localDateTimeValue(monthAgo.toISOString());
    endField.value = localDateTimeValue(now.toISOString());

    function query() {
        const params = new URLSearchParams();
        params.set("period_start", apiDateTime(startField.value));
        params.set("period_end", apiDateTime(endField.value));
        const customer = document.getElementById("profit-customer").value;
        if (customer) params.set("customer_id", customer);
        return params;
    }

    async function load() {
        const nodes = reportSection("profit");
        nodes.loading.hidden = false;
        nodes.wrap.hidden = true;
        nodes.empty.hidden = true;
        clearMessages();
        const params = query();
        exportLink.href = `/api/v1/exports/profit.xlsx?${params}`;
        try {
            const report = await apiRequest(`/api/v1/reports/profit/?${params}`);
            document.getElementById("profit-revenue").textContent = money(report.revenue);
            document.getElementById("profit-cost").textContent = money(report.cost);
            document.getElementById("profit-profit").textContent = money(report.profit);
            document.getElementById("profit-margin").textContent = `${report.margin_percent}٪`;
            document.getElementById("profit-measured").textContent = report.measured_invoice_count;
            document.getElementById("profit-unmeasured").textContent = report.unmeasured_invoice_count;
            renderProfitCompositionChart(report);
            renderReportRows("profit", report.results, (item) => {
                const row = document.createElement("tr");
                appendCell(row, item.number).dir = "ltr";
                appendCell(row, item.customer_name);
                appendCell(row, displayDate(item.issued_at));
                appendMoneyCell(row, item.revenue);
                appendMoneyCell(row, item.cost);
                appendMoneyCell(row, item.profit);
                appendCell(row, `${item.margin_percent}٪`);
                appendActionLinks(row, [[`/invoices/${item.invoice_id}/`, "فاکتور"]]);
                return row;
            });
        } catch (error) {
            reportSection("profit").loading.hidden = true;
            showError(error);
        }
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        load();
    });
    try {
        await loadCustomerOptions(document.getElementById("profit-customer"), "همه مشتریان");
    } catch (error) {
        showError(error);
    }
    load();
}
