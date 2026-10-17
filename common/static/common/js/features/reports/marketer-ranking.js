import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {clearMessages, errorText, globalMessage, withSubmit} from "dolphin/core/messages.js";
import {money, moneyOrNull, setupMoneyInputs} from "dolphin/core/money.js";
import {renderBarChart, setupChartRange} from "dolphin/ui/charts.js";
import {countCard, figureCard} from "dolphin/ui/conversion.js";
import {guardDirtyDialog} from "dolphin/ui/dialogs.js";
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
    successful_calls: {value: (row) => row.successful_calls, show: (row) => `${count(row.successful_calls)} تماس موفق`},
    qualified_calls: {value: (row) => row.qualified_calls, show: (row) => `${count(row.qualified_calls)} واجد شرایط`},
    conversion_rate: {value: (row) => Number(row.conversion_rate || 0), show: (row) => percent(row.conversion_rate)},
    resolution_rate: {value: (row) => Number(row.resolution_rate || 0), show: (row) => percent(row.resolution_rate)},
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
    const exportLink = document.getElementById("marketers-export");

    async function load() {
        if (!windowParams.period_start) return;
        if (exportLink) exportLink.href = `/api/v1/exports/marketers.xlsx?${new URLSearchParams({...windowParams, ordering: ordering.value || "sales_amount"})}`;
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
        // The unified rates for everyone together, each with its definition,
        // numerator and denominator (2.40.59, BIZ-004).
        const repeat = data.definitions.find((item) => item.key === "repeat");
        document.getElementById("marketers-rates").replaceChildren(
            figureCard(data.totals.lead_to_sale),
            figureCard(data.totals.resolution),
            countCard(repeat.label, data.totals.repeat_purchases, repeat.definition),
        );
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
            cell(count(row.successful_calls));
            cell(count(row.qualified_calls));
            cell(`${percent(row.conversion_rate)} (${count(row.won_leads)} از ${count(row.qualified_leads)})`);
            cell(`${percent(row.resolution_rate)} (${count(row.closed_won)} از ${count(row.closed_leads)})`);
            cell(count(row.repeat_purchases));
            return tr;
        }));
    }

    const range = setupChartRange(document.getElementById("marketers-range"), (window) => {
        windowParams = window;
        load();
    }, {label: "بازهٔ رتبه‌بندی"});
    windowParams = range ? range.window() : {};
    ordering.addEventListener("change", load);
    setupMonthlyTargets();
    await load();
    // Live: a new invoice, payment, customer or call moves the table.
    onRealtime(["invoice", "payment", "customer", "interaction", "lead"], load, {delay: 1500});
}

/** The month a target reading is about, stepped one month at a time. */
function stepMonth({year, month}, delta) {
    const index = year * 12 + (month - 1) + delta;
    return {year: Math.floor(index / 12), month: (index % 12) + 1};
}

/** «۷۲٪»: a target's progress as a whole percentage, Persian digits. */
function wholePercent(value) {
    if (value === null || value === undefined) return "—";
    return `${toPersianDigits(String(Math.round(Number(value))))}٪`;
}

/** A target's progress colour: met, close, or still far. */
function progressTone(percent) {
    if (percent === null || percent === undefined) return "secondary";
    const value = Number(percent);
    if (value >= 100) return "success";
    if (value >= 60) return "primary";
    return "warning";
}

/**
 * «هدف ماهانهٔ فروش» (2.40.41): each marketer's sales in a Jalali month
 * against the target a manager set, one bar each; and for whoever holds
 * `sales_targets.manage` (the server says so in `can_manage`) a dialog that
 * sets the whole month's targets at once.
 */
function setupMonthlyTargets() {
    const list = document.getElementById("marketer-targets-list");
    if (!list) return;
    const loading = document.getElementById("marketer-targets-loading");
    const errorNode = document.getElementById("marketer-targets-error");
    const empty = document.getElementById("marketer-targets-empty");
    const monthLabel = document.getElementById("marketer-targets-month");
    const summary = document.getElementById("marketer-targets-summary");
    const editButton = document.getElementById("marketer-targets-edit");
    const dialog = document.getElementById("marketer-targets-dialog");
    const form = document.getElementById("marketer-targets-form");
    const fields = document.getElementById("marketer-targets-fields");
    let shown = null;
    let report = null;
    let token = 0;

    async function load(month = shown) {
        const mine = ++token;
        errorNode.hidden = true;
        const query = new URLSearchParams(month ? {year: String(month.year), month: String(month.month)} : {});
        let data;
        try {
            data = await apiRequest(`/api/v1/reports/marketers/targets/?${query}`);
        } catch (error) {
            if (mine !== token) return;
            loading.hidden = true;
            errorNode.textContent = errorText(error);
            errorNode.hidden = false;
            return;
        }
        if (mine !== token) return;
        draw(data);
    }

    function draw(data) {
        report = data;
        shown = {year: data.year, month: data.month};
        loading.hidden = true;
        monthLabel.textContent = data.label;
        editButton.hidden = !data.can_manage;
        const totals = data.totals;
        summary.textContent = totals.with_target
            ? `${toPersianDigits(String(totals.with_target))} بازاریاب هدف دارند — ${money(totals.achieved)} از ${money(totals.target)}${totals.percent === null ? "" : ` (${wholePercent(totals.percent)})`}`
            : "برای این ماه هنوز هدفی تعیین نشده است.";
        empty.hidden = data.results.length > 0;
        list.hidden = data.results.length === 0;
        list.replaceChildren(...data.results.map((row) => {
            const item = document.createElement("li");
            item.className = "marketer-target";
            const who = document.createElement("span");
            who.className = "marketer-target-who";
            who.append(avatar(row.name), profileLink(row));
            const figures = document.createElement("span");
            figures.className = "marketer-target-figures";
            figures.textContent = row.target === null
                ? `بدون هدف · فروش ${money(row.achieved)}`
                : `${money(row.achieved)} از ${money(row.target)}`;
            const bar = document.createElement("span");
            bar.className = "marketer-target-bar";
            bar.dataset.tone = progressTone(row.percent);
            bar.setAttribute("role", "progressbar");
            bar.setAttribute("aria-valuemin", "0");
            bar.setAttribute("aria-valuemax", "100");
            const reached = row.percent === null ? 0 : Math.min(100, Number(row.percent));
            bar.setAttribute("aria-valuenow", String(Math.round(reached)));
            bar.setAttribute("aria-label", `پیشرفت ${row.name}`);
            bar.style.setProperty("--progress", `${reached}%`);
            const share = document.createElement("span");
            share.className = "marketer-target-percent";
            share.textContent = wholePercent(row.percent);
            item.append(who, figures, bar, share);
            return item;
        }));
    }

    document.getElementById("marketer-targets-prev").addEventListener("click", () => shown && load(stepMonth(shown, -1)));
    document.getElementById("marketer-targets-next").addEventListener("click", () => shown && load(stepMonth(shown, 1)));

    if (dialog && form) {
        guardDirtyDialog(dialog, form);
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        editButton.addEventListener("click", () => {
            if (!report) return;
            clearMessages(form);
            document.getElementById("marketer-targets-dialog-month").textContent = report.label;
            fields.replaceChildren(...report.results.map((row) => {
                const field = document.createElement("div");
                field.className = "marketer-targets-field";
                const label = document.createElement("label");
                label.className = "form-label fw-semibold mb-0";
                label.setAttribute("for", `marketer-target-${row.user_id}`);
                label.textContent = row.name;
                const input = document.createElement("input");
                input.className = "form-control form-control-solid";
                input.id = `marketer-target-${row.user_id}`;
                input.type = "text";
                input.dir = "ltr";
                input.dataset.moneyInput = "";
                input.dataset.userId = String(row.user_id);
                input.placeholder = "بدون هدف";
                input.value = row.target === null ? "" : money(row.target, {withCurrency: false, exact: true});
                field.append(label, input);
                return field;
            }));
            setupMoneyInputs(fields);
            dialog.showModal();
        });
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const targets = Array.from(fields.querySelectorAll("[data-user-id]")).map((input) => ({
                    user_id: Number(input.dataset.userId),
                    amount: moneyOrNull(input.value),
                }));
                const data = await apiRequest("/api/v1/reports/marketers/targets/", {
                    method: "PUT",
                    body: {year: report.year, month: report.month, targets},
                });
                dialog.close();
                draw(data);
                globalMessage(`هدف‌های ${data.label} ذخیره شد.`, true);
            });
        });
    }

    load();
    // A new invoice moves a bar; a target set elsewhere redraws the month.
    onRealtime(["invoice", "sales_target"], () => load(), {delay: 1500});
}
