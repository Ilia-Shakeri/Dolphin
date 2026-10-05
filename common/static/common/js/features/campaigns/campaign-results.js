import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDate} from "dolphin/core/jalali.js";
import {clearMessages, showError} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {campaignStatusBadge} from "dolphin/features/campaigns/campaigns.js";

const count = (value) => toPersianDigits(String(value));
const percent = (value) => (value === null || value === undefined ? "—" : `${toPersianDigits(String(value))}٪`);

const BASE_COLUMNS = [
    ["کمپین", (row) => row.name],
    ["وضعیت", (row) => campaignStatusBadge(row.status, row.status_display)],
    ["مخاطب", (row) => count(row.members)],
    ["تماس‌گرفته", (row) => count(row.contacted)],
    ["در تعامل", (row) => count(row.engaged)],
    ["تبدیل‌شده", (row) => count(row.converted)],
    ["از قبل مشتری", (row) => count(row.already_customers)],
    ["نرخ تبدیل", (row) => percent(row.conversion_rate)],
];
const MONEY_COLUMNS = [
    ["فروش ثبت‌شده", (row) => `${count(row.registered_sales_count)} — ${money(row.registered_sales_amount)}`],
    ["فاکتور معتبر", (row) => `${count(row.valid_invoices_count)} — ${money(row.valid_invoices_amount)}`],
    ["وصول‌شده", (row) => money(row.collected_amount)],
    ["مانده", (row) => (row.remaining_amount === undefined ? "—" : money(row.remaining_amount))],
];

export function setupCampaignResults() {
    const loading = document.getElementById("results-loading");
    const empty = document.getElementById("results-empty");
    const wrap = document.getElementById("results-table-wrap");
    const head = document.getElementById("results-head");
    const body = document.getElementById("results-body");

    async function load() {
        loading.hidden = false;
        empty.hidden = true;
        wrap.hidden = true;
        clearMessages();
        const query = new URLSearchParams();
        const from = apiDate(document.getElementById("results-from").value);
        const to = apiDate(document.getElementById("results-to").value);
        if (from) query.set("date_from", from);
        if (to) query.set("date_to", to);
        try {
            const data = await apiRequest(`/api/v1/campaigns/results/?${query}`);
            loading.hidden = true;
            if (!data.results.length) { empty.hidden = false; return; }
            // The money columns are drawn only when the server sent them: a
            // marketer's rows carry counts, never amounts.
            const columns = data.with_money ? [...BASE_COLUMNS, ...MONEY_COLUMNS] : BASE_COLUMNS;
            const headRow = document.createElement("tr");
            headRow.className = "text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0";
            columns.forEach(([label]) => {
                const th = document.createElement("th");
                th.textContent = label;
                headRow.append(th);
            });
            head.replaceChildren(headRow);
            body.replaceChildren(...data.results.map((row) => {
                const tr = document.createElement("tr");
                // The whole row opens the campaign (2.40.0); «بدون کمپین» has no page.
                if (row.id) {
                    tr.classList.add("cursor-pointer");
                    tr.addEventListener("click", (event) => {
                        if (!event.target.closest("a")) window.location.assign(`/campaigns/${row.id}/`);
                    });
                }
                columns.forEach(([, render], index) => {
                    const td = document.createElement("td");
                    const value = render(row);
                    if (value instanceof Node) td.append(value);
                    else if (index === 0 && row.id) {
                        const link = document.createElement("a");
                        link.href = `/campaigns/${row.id}/`;
                        link.textContent = value;
                        td.append(link);
                    } else td.textContent = value;
                    tr.append(td);
                });
                return tr;
            }));
            wrap.hidden = false;
        } catch (error) {
            loading.hidden = true;
            showError(error);
        }
    }

    document.getElementById("results-apply").addEventListener("click", load);
    load();
}
