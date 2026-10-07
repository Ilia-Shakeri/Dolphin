import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {errorText} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {renderBarChart, setupChartRange} from "dolphin/ui/charts.js";
import {onRealtime} from "dolphin/ui/realtime.js";

const count = (value) => toPersianDigits(String(value));
const percent = (value) => (value === null || value === undefined ? "—" : `${toPersianDigits(String(value))}٪`);

/** How each ordering's figure is written and charted. */
const METRICS = {
    sales_amount: {value: (row) => Number(row.sales_amount), show: (row) => money(row.sales_amount)},
    sales_count: {value: (row) => row.sales_count, show: (row) => `${count(row.sales_count)} فاکتور`},
    collected_amount: {value: (row) => Number(row.collected_amount), show: (row) => money(row.collected_amount)},
    average_amount: {value: (row) => Number(row.average_amount), show: (row) => money(row.average_amount)},
    customers_count: {value: (row) => row.customers_count, show: (row) => `${count(row.customers_count)} مشتری`},
    calls_count: {value: (row) => row.calls_count, show: (row) => `${count(row.calls_count)} تماس`},
    conversion_rate: {value: (row) => Number(row.conversion_rate || 0), show: (row) => percent(row.conversion_rate)},
};

/** «↑ ۲» / «↓ ۱» / «تازه» — the place against the window before. */
function rankMove(row) {
    const chip = document.createElement("span");
    chip.className = "marketer-move";
    if (row.previous_rank === null) {
        chip.textContent = "تازه";
        chip.dataset.move = "new";
        chip.title = "در بازهٔ قبل فعالیتی نداشت";
        return chip;
    }
    const delta = row.previous_rank - row.rank;
    chip.dataset.move = delta > 0 ? "up" : delta < 0 ? "down" : "same";
    chip.textContent = delta === 0 ? "—" : `${delta > 0 ? "▲" : "▼"} ${count(Math.abs(delta))}`;
    chip.title = delta === 0 ? "همان جایگاه بازهٔ قبل" : `در بازهٔ قبل رتبهٔ ${count(row.previous_rank)}`;
    return chip;
}

function avatar(name) {
    const node = document.createElement("span");
    node.className = "marketer-avatar";
    node.textContent = (name || "?").trim().charAt(0);
    node.setAttribute("aria-hidden", "true");
    return node;
}

function profileLink(row) {
    const link = document.createElement("a");
    link.href = `/users/${row.user_id}/`;
    link.className = "text-gray-900 text-hover-primary fw-bold";
    link.textContent = row.name;
    return link;
}

/**
 * «تحلیل و رتبه‌بندی بازاریاب‌ها» (2.40.34): the three in front on a podium,
 * everyone on one chart by the chosen figure, and the full table — each
 * marketer's sales, collections, customers, calls and lead conversion, with
 * how their place moved against the window just before.
 */
export async function setupMarketerRanking() {
    const ordering = document.getElementById("marketers-ordering");
    const loading = document.getElementById("marketers-loading");
    const empty = document.getElementById("marketers-empty");
    const errorNode = document.getElementById("marketers-error");
    const content = document.getElementById("marketers-content");
    if (!ordering || !content) return;
    let windowParams = {};

    async function load() {
        if (!windowParams.period_start) return;
        errorNode.hidden = true;
        const query = new URLSearchParams({...windowParams, ordering: ordering.value || "sales_amount"});
        let data;
        try {
            data = await apiRequest(`/api/v1/reports/marketers/?${query}`);
        } catch (error) {
            loading.hidden = true;
            errorNode.textContent = errorText(error);
            errorNode.hidden = false;
            return;
        }
        loading.hidden = true;
        if (!ordering.options.length) {
            data.orderings.forEach((option) => ordering.append(new Option(option.label, option.value)));
            ordering.value = data.ordering;
        }
        document.getElementById("marketers-total-amount").textContent = money(data.totals.sales_amount);
        document.getElementById("marketers-total-count").textContent = count(data.totals.sales_count);
        document.getElementById("marketers-total-collected").textContent = money(data.totals.collected_amount);
        document.getElementById("marketers-total-people").textContent = count(data.totals.marketers);
        empty.hidden = data.results.length > 0;
        content.hidden = data.results.length === 0;
        if (!data.results.length) return;
        const metric = METRICS[data.ordering] || METRICS.sales_amount;
        const label = ordering.selectedOptions[0]?.textContent || "";
        drawPodium(data.results.slice(0, 3), metric);
        document.getElementById("marketers-chart-title").textContent = `مقایسه بر اساس ${label}`;
        renderBarChart(
            document.getElementById("marketers-chart"),
            document.getElementById("marketers-chart-empty"),
            data.results.map((row) => ({label: row.name, value: metric.value(row), display: metric.show(row)})),
            {ariaLabel: `مقایسهٔ بازاریاب‌ها بر اساس ${label}`, sort: false, keepZero: true},
        );
        drawTable(data.results);
    }

    function drawPodium(top, metric) {
        const host = document.getElementById("marketers-podium");
        host.replaceChildren(...top.map((row, index) => {
            const card = document.createElement("article");
            card.className = "marketer-podium-card";
            card.dataset.place = String(index + 1);
            const medal = document.createElement("span");
            medal.className = "marketer-medal";
            medal.textContent = count(row.rank);
            medal.setAttribute("aria-label", `رتبهٔ ${count(row.rank)}`);
            const who = document.createElement("div");
            who.className = "d-flex align-items-center gap-3";
            const names = document.createElement("div");
            names.className = "d-flex flex-column";
            names.append(profileLink(row));
            const sub = document.createElement("span");
            sub.className = "text-muted fs-8";
            sub.textContent = `${count(row.sales_count)} فاکتور · ${percent(row.share)} از فروش`;
            names.append(sub);
            who.append(avatar(row.name), names);
            const figure = document.createElement("div");
            figure.className = "marketer-podium-figure";
            figure.textContent = metric.show(row);
            card.append(medal, who, figure, rankMove(row));
            return card;
        }));
    }

    function drawTable(rows) {
        document.getElementById("marketers-table").replaceChildren(...rows.map((row) => {
            const tr = document.createElement("tr");
            const cell = (content, className = "") => {
                const td = document.createElement("td");
                if (className) td.className = className;
                if (content instanceof Node) td.append(content); else td.textContent = content;
                tr.append(td);
                return td;
            };
            const rank = document.createElement("span");
            rank.className = "d-inline-flex align-items-center gap-2";
            const badge = document.createElement("span");
            badge.className = "marketer-rank";
            badge.dataset.place = String(Math.min(row.rank, 4));
            badge.textContent = count(row.rank);
            rank.append(badge, rankMove(row));
            cell(rank);
            const who = document.createElement("span");
            who.className = "d-inline-flex align-items-center gap-3";
            who.append(avatar(row.name), profileLink(row));
            cell(who);
            cell(count(row.sales_count));
            cell(money(row.sales_amount), "fw-bold");
            const share = document.createElement("span");
            share.className = "marketer-share";
            const bar = document.createElement("span");
            bar.className = "marketer-share-bar";
            bar.style.setProperty("--share", `${Math.min(100, Number(row.share))}%`);
            const text = document.createElement("span");
            text.textContent = percent(row.share);
            share.append(bar, text);
            cell(share);
            cell(money(row.collected_amount));
            cell(money(row.average_amount));
            cell(count(row.customers_count));
            cell(count(row.calls_count));
            cell(`${count(row.leads_completed)} / ${count(row.leads_assigned)}`);
            cell(percent(row.conversion_rate));
            return tr;
        }));
    }

    const range = setupChartRange(document.getElementById("marketers-range"), (window) => {
        windowParams = window;
        load();
    }, {label: "بازهٔ رتبه‌بندی"});
    windowParams = range ? range.window() : {};
    ordering.addEventListener("change", load);
    await load();
    // Live: a new invoice, payment, customer or call moves the table.
    onRealtime(["invoice", "payment", "customer", "interaction", "lead"], load, {delay: 1500});
}
