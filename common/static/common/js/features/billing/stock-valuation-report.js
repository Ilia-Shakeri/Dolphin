import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {clearMessages, showError} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {renderReportRows, reportSection} from "dolphin/features/billing/shared.js";
import {renderBarChart} from "dolphin/ui/charts.js";
import {bindReportTableSearch} from "dolphin/ui/report-wizard.js";
import {loadWarehouseOptions} from "dolphin/ui/searchable-select.js";
import {appendCell, appendMoneyCell} from "dolphin/ui/table.js";
import {onRealtime} from "dolphin/ui/realtime.js";

/**
 * The ten products holding the most stock value.
 *
 * Sorted and capped, because a valuation report can run to hundreds of rows
 * and a bar per row is unreadable. The rest stay in the table below, which
 * is also the accessible alternative to this chart.
 */
function renderValuationChart(rows) {
    const items = rows.map((row) => ({
        label: `${row.product_name} (${row.warehouse_name})`,
        value: Number(row.stock_value),
        display: money(row.stock_value),
    }));
    const drawn = Math.min(10, items.filter((item) => Number.isFinite(item.value) && item.value > 0).length);
    renderBarChart(
        document.getElementById("valuation-chart"),
        document.getElementById("valuation-chart-empty"),
        items,
        {
            limit: 10,
            ariaLabel: `نمودار ${toPersianDigits(String(drawn))} کالای با بیشترین ارزش موجودی`,
        },
    );
}

export async function setupStockValuationReport() {
    const form = document.getElementById("valuation-filter-form");
    const exportLink = document.getElementById("valuation-export");
    bindReportTableSearch(
        document.getElementById("valuation-search"),
        [document.getElementById("valuation-table-body")],
    );

    async function load() {
        const nodes = reportSection("valuation");
        nodes.loading.hidden = false;
        nodes.wrap.hidden = true;
        nodes.empty.hidden = true;
        clearMessages();
        const params = new URLSearchParams();
        const warehouse = document.getElementById("valuation-warehouse").value;
        if (warehouse) params.set("warehouse_id", warehouse);
        exportLink.href = `/api/v1/exports/stock-valuation.xlsx${params.toString() ? `?${params}` : ""}`;
        try {
            const report = await apiRequest(`/api/v1/reports/stock-valuation/?${params}`);
            document.getElementById("valuation-quantity").textContent = report.total_quantity;
            document.getElementById("valuation-value").textContent = money(report.total_value);
            renderValuationChart(report.results);
            renderReportRows("valuation", report.results, (item) => {
                const row = document.createElement("tr");
                appendCell(row, item.warehouse_name);
                appendCell(row, item.product_sku).dir = "ltr";
                appendCell(row, item.product_name);
                appendCell(row, item.quantity);
                appendMoneyCell(row, item.average_cost);
                appendMoneyCell(row, item.stock_value);
                return row;
            });
        } catch (error) {
            reportSection("valuation").loading.hidden = true;
            showError(error);
        }
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        load();
    });
    try {
        await loadWarehouseOptions(document.getElementById("valuation-warehouse"), "همه انبارها");
    } catch (error) {
        showError(error);
    }
    load();
    // Live (2.40.34): the figures follow the records they add up.
    onRealtime(["inventory", "product"], () => load(), {delay: 1500});
}
