import {apiRequest} from "dolphin/core/api.js";
import {clearMessages, showError} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {loadCustomerOptions, renderReportRows, reportSection} from "dolphin/features/billing/shared.js";
import {chartPalette, renderBarChart} from "dolphin/ui/charts.js";
import {bindReportTableSearch} from "dolphin/ui/report-wizard.js";
import {appendActionLinks, appendCell, appendMoneyCell} from "dolphin/ui/table.js";
import {onRealtime} from "dolphin/ui/realtime.js";

/**
 * Five colours that escalate, for the receivables ageing buckets.
 *
 * Not decoration: the buckets run from "not yet due" to "over ninety days",
 * so the colour has to carry the same direction the reader is already
 * looking for — and it has to keep moving at every step. Built from the
 * palette's own success/primary/warning/danger with Bootstrap's `--bs-orange`
 * filling the gap between warning and danger, because the theme has no
 * colour there and repeating the yellow made buckets three and four look
 * equally bad when one is twice as old as the other.
 */
function severityRamp() {
    const palette = chartPalette();
    const orange =
        getComputedStyle(document.documentElement).getPropertyValue("--bs-orange").trim()
        || "#fd7e14";
    return [palette[1], palette[0], palette[3], orange, palette[4]];
}

/**
 * Where the outstanding money is sitting, by age.
 *
 * The five buckets are a fixed sequence running from not-yet-due to more
 * than ninety days late, so this neither sorts nor drops empties: an
 * ageing chart reordered by size would say nothing, and a missing bucket
 * is the reader's good news.
 */
function renderReceivablesAgingChart(buckets) {
    const order = [
        ["سررسید نشده", buckets.not_due],
        ["۱ تا ۳۰ روز", buckets.days_1_30],
        ["۳۱ تا ۶۰ روز", buckets.days_31_60],
        ["۶۱ تا ۹۰ روز", buckets.days_61_90],
        ["بیش از ۹۰ روز", buckets.days_over_90],
    ];
    renderBarChart(
        document.getElementById("receivables-aging-chart"),
        document.getElementById("receivables-aging-chart-empty"),
        order.map(([label, amount]) => ({
            label,
            value: Number(amount),
            display: money(amount),
        })),
        {
            sort: false,
            keepZero: true,
            ariaLabel: "نمودار سنی مطالبات در پنج بازه سررسید",
            // Not decoration: the buckets run from "not yet due" to "over
            // ninety days", so the colour carries the same order the reader
            // is already looking for.
            colorBy: (item, index) => severityRamp()[index] || severityRamp()[0],
        },
    );
}

export async function setupReceivablesReport() {
    const form = document.getElementById("receivables-filter-form");
    const exportLink = document.getElementById("receivables-export");
    bindReportTableSearch(
        document.getElementById("receivables-search"),
        [document.getElementById("receivables-table-body")],
    );

    function query() {
        const params = new URLSearchParams();
        const customer = document.getElementById("receivables-customer").value;
        if (customer) params.set("customer_id", customer);
        return params;
    }

    async function load() {
        const nodes = reportSection("receivables");
        nodes.loading.hidden = false;
        nodes.wrap.hidden = true;
        nodes.empty.hidden = true;
        clearMessages();
        const params = query();
        exportLink.href = `/api/v1/exports/receivables.xlsx${params.toString() ? `?${params}` : ""}`;
        try {
            const report = await apiRequest(`/api/v1/reports/receivables/?${params}`);
            document.getElementById("receivables-total").textContent = money(report.total_outstanding);
            document.getElementById("receivables-not-due").textContent = money(report.buckets.not_due);
            document.getElementById("receivables-1-30").textContent = money(report.buckets.days_1_30);
            document.getElementById("receivables-31-60").textContent = money(report.buckets.days_31_60);
            document.getElementById("receivables-61-90").textContent = money(report.buckets.days_61_90);
            document.getElementById("receivables-over-90").textContent = money(report.buckets.days_over_90);
            renderReceivablesAgingChart(report.buckets);
            renderReportRows("receivables", report.results, (item) => {
                const row = document.createElement("tr");
                appendCell(row, item.customer_name);
                appendCell(row, item.invoice_count);
                appendMoneyCell(row, item.total_outstanding);
                appendMoneyCell(row, item.not_due);
                appendMoneyCell(row, item.days_1_30);
                appendMoneyCell(row, item.days_31_60);
                appendMoneyCell(row, item.days_61_90);
                appendMoneyCell(row, item.days_over_90);
                appendActionLinks(row, [[`/invoices/?customer=${item.customer_id}`, "فاکتورها"]]);
                return row;
            });
        } catch (error) {
            reportSection("receivables").loading.hidden = true;
            showError(error);
        }
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        load();
    });
    try {
        await loadCustomerOptions(document.getElementById("receivables-customer"), "همه مشتریان");
    } catch (error) {
        showError(error);
    }
    load();
    // Live (2.40.34): the figures follow the records they add up.
    onRealtime(["invoice", "payment"], () => load(), {delay: 1500});
}
