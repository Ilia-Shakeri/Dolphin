import {campaignLabel} from "dolphin/core/labels.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {showError} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {renderAreaChart, renderBarChart, renderGroupedBarChart, renderMultiLineChart} from "dolphin/ui/charts.js";
import {enhanceChecklistSelect} from "dolphin/ui/checklist-select.js";
import {loadAllPages} from "dolphin/ui/lists.js";
import {setupReportWizard} from "dolphin/ui/report-wizard.js";

const count = (value) => toPersianDigits(String(value));

function chartHost(name) {
    return [document.getElementById(`chart-${name}`), document.getElementById(`chart-${name}-empty`)];
}

/**
 * «تحلیل کمپین‌ها» as a step-by-step report (2.40.23): which campaigns,
 * which window, which parts, the result — on the same driver as every other
 * step-by-step report (`setupReportWizard`). Several campaigns chosen are
 * compared side by side (`comparison` in the payload, `sales.campaign_analytics`).
 */
export async function setupCampaignAnalytics() {
    const select = document.getElementById("analytics-campaigns");
    enhanceChecklistSelect(select, {emptyMeansAll: true});
    try {
        const campaigns = await loadAllPages("/api/v1/campaigns/");
        select.replaceChildren(...campaigns.map((campaign) => new Option(
            campaignLabel(campaign), String(campaign.id),
        )));
    } catch (error) {
        showError(error);
    }

    function chosenCampaigns() {
        return Array.from(select.selectedOptions, (option) => option.value);
    }

    function drawSummary(data) {
        const totalMembers = data.funnel[0]?.value ?? 0;
        document.getElementById("analytics-members").textContent = count(totalMembers);
        document.getElementById("analytics-converted").textContent = count(data.funnel[3]?.value ?? 0);
        const amount = data.campaigns
            .filter((row) => !row.parent_id)
            .reduce((sum, row) => sum + Number(row.valid_invoices_amount || 0), 0);
        document.getElementById("analytics-amount").textContent = money(amount);
        document.getElementById("analytics-first-contact").textContent = data.first_contact_hours === null
            ? "—" : `${count(data.first_contact_hours)} ساعت`;
        document.getElementById("analytics-first-contact-note").textContent = data.first_contact_excluded
            ? `${count(data.first_contact_excluded)} نفر با تماسِ پیش از تاریخ ورود کنار گذاشته شدند.` : "";
    }

    function drawComparison(comparison) {
        const rows = comparison.campaigns;
        const names = rows.map((row) => row.name);
        document.getElementById("analytics-compare-note").textContent = rows.length > 1
            ? `${count(rows.length)} کمپین کنار هم؛ هر رنگ یک مرحله است.`
            : "برای مقایسه، در مرحلهٔ اول چند کمپین را تیک بزنید.";
        renderGroupedBarChart(...chartHost("compare-funnel"), names, [
            {name: "مخاطب", values: rows.map((row) => row.members)},
            {name: "تماس گرفته‌شده", values: rows.map((row) => row.contacted)},
            {name: "تبدیل‌شده", values: rows.map((row) => row.converted)},
            {name: "فاکتور معتبر", values: rows.map((row) => row.valid_invoices_count)},
        ], {ariaLabel: "مقایسهٔ کمپین‌ها"});
        renderBarChart(...chartHost("compare"), rows
            .filter((row) => row.conversion_rate !== null)
            .map((row) => ({label: row.name, value: row.conversion_rate, display: `${count(row.conversion_rate)}٪`})),
        {ariaLabel: "مقایسهٔ نرخ تبدیل"});
        const monthly = rows.map((row) => ({name: row.name, values: row.invoices_by_month}));
        if (comparison.months.length > 1) {
            renderMultiLineChart(...chartHost("monthly"), comparison.months, monthly, {ariaLabel: "فاکتورهای معتبر هر کمپین در هر ماه"});
        } else {
            // One month is not a line; the campaigns side by side in it are.
            renderGroupedBarChart(...chartHost("monthly"), comparison.months, monthly, {ariaLabel: "فاکتورهای معتبر هر کمپین در هر ماه"});
        }
    }

    function drawTable(data) {
        document.getElementById("analytics-table").replaceChildren(...data.campaigns.map((row) => {
            const tr = document.createElement("tr");
            [
                row.parent_id ? `— ${row.name}` : row.name,
                count(row.members), count(row.contacted), count(row.engaged), count(row.converted),
                row.conversion_rate === null ? "—" : `${count(row.conversion_rate)}٪`,
                count(row.valid_invoices_count), money(row.valid_invoices_amount), money(row.collected_amount),
                row.remaining_amount === undefined || row.remaining_amount === null ? "—" : money(row.remaining_amount),
            ].forEach((value) => {
                const td = document.createElement("td");
                td.textContent = value;
                tr.append(td);
            });
            if (row.parent_id) tr.classList.add("text-muted");
            return tr;
        }));
    }

    setupReportWizard({
        prefix: "campaign-analytics",
        endpoint: "/api/v1/campaigns/analytics/",
        exportUrl: "/api/v1/campaigns/export/",
        // A campaign can run for more than a year; the whole of it is the
        // natural first look.
        rangeOptions: {initial: "all", allTime: true, label: "بازهٔ تحلیل"},
        extraQuery: () => {
            const chosen = chosenCampaigns();
            return chosen.length ? {campaigns: chosen.join(",")} : {};
        },
        isEmpty: (data) => !data.campaigns.length,
        render: (data) => {
            drawSummary(data);
            drawComparison(data.comparison);
            renderBarChart(...chartHost("funnel"), data.funnel.map((step) => ({
                label: step.label, value: step.value, display: count(step.value),
            })), {ariaLabel: "قیف کمپین", sort: false, keepZero: true});
            renderAreaChart(...chartHost("joined"), data.members_by_day.map((point) => ({
                label: point.day, value: point.count, display: count(point.count),
            })), {ariaLabel: "ورود مخاطب در هر روز"});
            drawTable(data);
        },
    });
    document.getElementById("analytics-print").addEventListener("click", () => window.print());
}
