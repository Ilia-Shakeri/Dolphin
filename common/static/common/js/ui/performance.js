import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate, localDateTimeValue} from "dolphin/core/jalali.js";
import {clearMessages, errorText, showError} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {renderBarChart} from "dolphin/ui/charts.js";
import {fillSelect, loadAllPages} from "dolphin/ui/lists.js";
import {reportQuery} from "dolphin/ui/report-wizard.js";
import {appendCell, appendDetailLink, appendMoneyCell, pageRangeLabel} from "dolphin/ui/table.js";

function renderPerformanceChart(prefix, rows) {
    const items = rows.map((row) => ({
        label: row.username,
        value: Number(row.sales_amount),
        display: money(row.sales_amount),
    }));
    const drawn = items.filter((item) => Number.isFinite(item.value) && item.value > 0).length;
    renderBarChart(
        document.getElementById(`${prefix}-performance-chart`),
        document.getElementById(`${prefix}-performance-chart-empty`),
        items,
        {ariaLabel: `نمودار مبلغ فروش تأییدشده برای ${toPersianDigits(String(drawn))} کاربر مجاز`},
    );
}

export async function loadPerformanceDetails(prefix, userId, username, metric, page = 1) {
    const form = document.getElementById(`${prefix}-performance-filter-form`);
    const section = document.getElementById(`${prefix}-performance-details`);
    const loading = document.getElementById(`${prefix}-details-loading`);
    const errorNode = document.getElementById(`${prefix}-details-error`);
    const empty = document.getElementById(`${prefix}-details-empty`);
    const wrap = document.getElementById(`${prefix}-details-table-wrap`);
    const pager = document.getElementById(`${prefix}-details-pagination`);
    const metricLabel = metric === "customers_created_count" ? "مشتری‌های ثبت‌شده" : "فروش‌های تأییدشده";
    const query = reportQuery(form);
    query.set("metric", metric);
    query.set("page", String(page));
    if (userId) query.set("user_id", String(userId));
    else query.delete("user_id");
    section.hidden = false;
    loading.hidden = false;
    errorNode.hidden = true;
    empty.hidden = true;
    wrap.hidden = true;
    pager.hidden = true;
    document.getElementById(`${prefix}-details-scope`).textContent = `${metricLabel} — ${username || "همه کاربران مجاز"}`;
    try {
        const data = await apiRequest(`/api/v1/reports/user-performance/details/?${query}`);
        const rows = data.results.map((item) => {
            const row = document.createElement("tr");
            [
                item.record_type === "customer" ? "مشتری" : "فروش",
                item.title,
                item.owner,
                item.product_name || "—",
                item.amount === null ? "—" : item.amount,
                displayDate(item.occurred_at),
            ].forEach((value) => appendCell(row, value));
            appendDetailLink(row, item.detail_url);
            return row;
        });
        document.getElementById(`${prefix}-details-body`).replaceChildren(...rows);
        loading.hidden = true;
        if (!rows.length) {
            empty.hidden = false;
            return;
        }
        wrap.hidden = false;
        const previous = document.getElementById(`${prefix}-details-prev`);
        const next = document.getElementById(`${prefix}-details-next`);
        previous.disabled = !data.previous;
        next.disabled = !data.next;
        previous.onclick = () => loadPerformanceDetails(prefix, userId, username, metric, page - 1);
        next.onclick = () => loadPerformanceDetails(prefix, userId, username, metric, page + 1);
        document.getElementById(`${prefix}-details-page-label`).textContent = pageRangeLabel(data, page);
        pager.hidden = !data.previous && !data.next;
    } catch (error) {
        loading.hidden = true;
        errorNode.textContent = errorText(error);
        errorNode.hidden = false;
    }
}

function renderPerformanceReport(prefix, report) {
    const panel = document.querySelector(`[data-performance-panel="${prefix}"]`);
    // Two of the four KPIs are amounts and the other two are counts. Sending
    // an amount through `String()` printed it exactly as the API serialises
    // a decimal — `12500000.00` — with no grouping and a fraction the panel
    // shows nowhere else.
    const MONEY_KPIS = new Set(["sales_amount", "average_sale_amount"]);
    Object.entries(report.summary).forEach(([name, value]) => {
        const node = panel.querySelector(`[data-kpi="${name}"]`);
        if (node) node.textContent = MONEY_KPIS.has(name) ? money(value) : String(value);
    });
    const rows = report.results.map((item) => {
        const row = document.createElement("tr");
        // The first three are text and counts; the last two are money and
        // need the same grouping every other table in the panel uses.
        [item.username, item.customers_created_count, item.sales_count]
            .forEach((value) => appendCell(row, value));
        appendMoneyCell(row, item.sales_amount);
        appendMoneyCell(row, item.average_sale_amount);
        const actions = document.createElement("td");
        // Three buttons in one narrow column, unlike every other
        // `row-actions` cell in the app (one or two, which the
        // `margin-inline-start` rule in dolphin.css handles fine) —
        // narrow enough that they wrapped onto their own lines with no
        // gap between them. `flex-wrap` first tried here fixed the gap
        // but not the wrapping itself: three stacked lines multiplied
        // across every `<td>` in the row (they all share one height),
        // and the whole table grew a few hundred pixels of dead space
        // per row for it. `flex-nowrap` keeps the three side by side, as
        // asked, and any overflow is exactly what `.table-responsive`
        // (this table already sits in one) is for — a horizontal
        // scrollbar the panel already uses on nine-column tables.
        actions.className = "row-actions d-flex flex-nowrap gap-2";
        const profileLink = document.createElement("a");
        profileLink.className = "btn btn-sm btn-light";
        profileLink.href = `/users/${item.user_id}/profile/`;
        profileLink.textContent = "پروفایل";
        actions.appendChild(profileLink);
        [
            ["customers_created_count", "مشتری‌ها", item.customers_created_count],
            ["sales_count", "فروش‌ها", item.sales_count],
        ].forEach(([metric, label, count]) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-sm btn-light";
            button.textContent = label;
            button.disabled = Number(count) === 0;
            button.addEventListener("click", () => loadPerformanceDetails(prefix, item.user_id, item.username, metric));
            actions.appendChild(button);
        });
        row.appendChild(actions);
        return row;
    });
    document.getElementById(`${prefix}-performance-table-body`).replaceChildren(...rows);
    // The content wrapper has to become visible *before* the chart mounts
    // inside it, not after: ApexCharts measures its container's real width
    // at render time, and a container still under `hidden` (`display:none`)
    // measures zero — the chart then draws with `width: 0` and stays that
    // way forever, since `animations: {enabled: false}` (set for a
    // different, related reason above) means nothing ever retries the
    // measurement. Reproduced live: a fresh page load raced the fetch
    // against layout and mounted the chart at 0×220 while this div was
    // still hidden, leaving the whole chart panel blank with no error.
    const hasActivity = Number(report.summary.customers_created_count) > 0 || Number(report.summary.sales_count) > 0;
    document.getElementById(`${prefix}-performance-empty`).hidden = hasActivity;
    document.getElementById(`${prefix}-performance-content`).hidden = false;
    renderPerformanceChart(prefix, report.results);
    panel.querySelectorAll("[data-performance-detail]").forEach((button) => {
        const metric = button.dataset.performanceDetail;
        button.disabled = Number(report.summary[metric === "customers_created_count" ? metric : "sales_count"]) === 0;
    });
}

export async function setupPerformancePanel(prefix) {
    const form = document.getElementById(`${prefix}-performance-filter-form`);
    if (!form) return;
    const now = new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    document.getElementById(`${prefix}-period-start`).value = localDateTimeValue(start);
    document.getElementById(`${prefix}-period-end`).value = localDateTimeValue(new Date(now.getTime() + 60000));
    const exportLink = document.getElementById(`${prefix}-performance-xlsx`);
    const updateExport = () => { exportLink.href = `/api/v1/exports/user-performance.xlsx?${reportQuery(form)}`; };
    form.addEventListener("input", updateExport);
    form.addEventListener("change", updateExport);
    updateExport();
    form.closest("[data-performance-panel]").querySelectorAll("[data-performance-detail]").forEach((button) => {
        button.addEventListener("click", () => {
            const userSelect = document.getElementById(`${prefix}-user`);
            const userId = userSelect?.value || null;
            const username = userId ? userSelect.options[userSelect.selectedIndex].textContent : "همه کاربران مجاز";
            loadPerformanceDetails(prefix, userId, username, button.dataset.performanceDetail);
        });
    });
    let userOptionsLoaded = false;
    const load = async () => {
        clearMessages(form);
        const loading = document.getElementById(`${prefix}-performance-loading`);
        const errorNode = document.getElementById(`${prefix}-performance-error`);
        const content = document.getElementById(`${prefix}-performance-content`);
        // Not `form.querySelector(...)`: the submit button moved out of
        // the form and into the panel's header (2026-09-08, "بالا سمت چپ
        // باکس" — `performance_panel.inc`), wired back only through its
        // own `form="..."` HTML attribute, so it is a sibling of `<form>`
        // now, not a descendant. Found the same way the browser itself
        // associates it with the form it submits.
        const button = document.querySelector(`button[type="submit"][form="${form.id}"]`);
        loading.hidden = false;
        errorNode.hidden = true;
        content.hidden = true;
        document.getElementById(`${prefix}-performance-details`).hidden = true;
        button.disabled = true;
        const query = reportQuery(form);
        exportLink.href = `/api/v1/exports/user-performance.xlsx?${query}`;
        try {
            const report = await apiRequest(`/api/v1/reports/user-performance/?${query}`);
            const userSelect = document.getElementById(`${prefix}-user`);
            if (userSelect && !userOptionsLoaded) {
                fillSelect(
                    userSelect,
                    report.results.map((row) => ({id: row.user_id, username: row.username})),
                    (user) => user.username,
                    "همه کاربران مجاز",
                );
                userOptionsLoaded = true;
            }
            renderPerformanceReport(prefix, report);
        } catch (error) {
            errorNode.textContent = errorText(error);
            errorNode.hidden = false;
            showError(error, form);
        } finally {
            loading.hidden = true;
            button.disabled = false;
        }
    };
    // Claim the submit event before any awaited load. Without this the
    // filter button performs a native form submission during the first
    // moments of the page, which reloads instead of filtering.
    form.addEventListener("submit", (event) => { event.preventDefault(); load(); });
    try {
        const products = await loadAllPages("/api/v1/products/?ordering=name");
        fillSelect(document.getElementById(`${prefix}-product`), products, (product) => product.name, "همه محصولات مجاز");
    } catch (error) {
        showError(error);
    }
    await load();
}
