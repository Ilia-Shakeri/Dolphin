import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDate} from "dolphin/core/jalali.js";
import {clearMessages, showError} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {enhanceChecklistSelect} from "dolphin/ui/checklist-select.js";
import {loadAllPages} from "dolphin/ui/lists.js";
import {renderAreaChart, renderBarChart} from "dolphin/ui/charts.js";

const count = (value) => toPersianDigits(String(value));

function chartHost(name) {
    return [document.getElementById(`chart-${name}`), document.getElementById(`chart-${name}-empty`)];
}

export async function setupCampaignAnalytics() {
    const form = document.getElementById("analytics-form");
    const select = document.getElementById("analytics-campaigns");
    enhanceChecklistSelect(select);

    try {
        const campaigns = await loadAllPages("/api/v1/campaigns/");
        select.replaceChildren(...campaigns.map((campaign) => new Option(campaign.name, String(campaign.id))));
    } catch (error) {
        showError(error);
    }

    function query() {
        const params = new URLSearchParams();
        const chosen = Array.from(select.selectedOptions).map((option) => option.value);
        if (chosen.length) params.set("campaigns", chosen.join(","));
        const from = apiDate(document.getElementById("analytics-from").value);
        const to = apiDate(document.getElementById("analytics-to").value);
        if (from) params.set("date_from", from);
        if (to) params.set("date_to", to);
        return params;
    }

    function draw(data) {
        const funnel = data.funnel.map((step) => ({label: step.label, value: step.value, display: count(step.value)}));
        renderBarChart(...chartHost("funnel"), funnel, {ariaLabel: "قیف کمپین", sort: false, keepZero: true});
        const compare = data.campaigns
            .filter((row) => row.conversion_rate !== null)
            .map((row) => ({label: row.name, value: row.conversion_rate, display: `${count(row.conversion_rate)}٪`}));
        renderBarChart(...chartHost("compare"), compare, {ariaLabel: "مقایسهٔ نرخ تبدیل"});
        renderAreaChart(...chartHost("invoices"), data.invoices_by_month.map((point) => ({
            label: point.label || point.month, value: Number(point.count), display: count(point.count),
        })), {ariaLabel: "فاکتورهای معتبر در هر ماه"});
        renderAreaChart(...chartHost("joined"), data.members_by_day.map((point) => ({
            label: point.day, value: point.count, display: count(point.count),
        })), {ariaLabel: "ورود مخاطب در هر روز"});

        const totalMembers = data.funnel[0]?.value ?? 0;
        document.getElementById("analytics-members").textContent = count(totalMembers);
        document.getElementById("analytics-converted").textContent = count(data.funnel[3]?.value ?? 0);
        document.getElementById("analytics-first-contact").textContent = data.first_contact_hours === null
            ? "—" : `${count(data.first_contact_hours)} ساعت`;
        const table = document.getElementById("analytics-table");
        table.replaceChildren(...data.campaigns.map((row) => {
            const tr = document.createElement("tr");
            [
                row.name, count(row.members), count(row.contacted), count(row.engaged), count(row.converted),
                row.conversion_rate === null ? "—" : `${count(row.conversion_rate)}٪`,
                count(row.valid_invoices_count), money(row.valid_invoices_amount), money(row.collected_amount),
            ].forEach((value) => {
                const td = document.createElement("td");
                td.textContent = value;
                tr.append(td);
            });
            return tr;
        }));
    }

    async function load() {
        clearMessages();
        const error = document.getElementById("analytics-error");
        error.hidden = true;
        try {
            draw(await apiRequest(`/api/v1/campaigns/analytics/?${query()}`));
        } catch (failure) {
            showError(failure);
        }
    }

    form.addEventListener("submit", (event) => { event.preventDefault(); load(); });
    document.getElementById("analytics-export").addEventListener("click", () => {
        window.location.assign(`/api/v1/campaigns/export/?${query()}`);
    });
    document.getElementById("analytics-print").addEventListener("click", () => window.print());
    load();
}
