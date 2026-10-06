import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate, displayDay} from "dolphin/core/jalali.js";
import {errorText, showError} from "dolphin/core/messages.js";
import {motionBehavior} from "dolphin/core/motion.js";
import {renderAreaChart, renderBarChart} from "dolphin/ui/charts.js";
import {enhanceChecklistSelect} from "dolphin/ui/checklist-select.js";
import {bindReportTableSearch, setupReportWizard} from "dolphin/ui/report-wizard.js";
import {appendCell} from "dolphin/ui/table.js";

function renderInboundSMSChart(rows) {
    // `local_date` is a DateField, so it arrives as a bare `YYYY-MM-DD`.
    // `displayDay` reads that as a calendar day rather than pushing it
    // through a time zone, and returns Jalali — this chart was the one
    // surface still showing Gregorian dates and Latin digits.
    //
    // Not sorted: the sequence is the chart. Reordering hourly counts by
    // size would destroy the only thing a time series is for.
    const items = rows.map((item) => ({
        label: `${displayDay(item.local_date)} — ساعت ${toPersianDigits(String(item.local_hour).padStart(2, "0"))}`,
        value: Number(item.inbound_sms_count),
        display: toPersianDigits(String(item.inbound_sms_count)),
    }));
    // An area rather than bars: these are consecutive hours, and the
    // question is the shape over time, not which single hour was tallest.
    // One reading has no shape, so that case falls back to a bar.
    const chart = document.getElementById("inbound-sms-chart");
    const empty = document.getElementById("inbound-sms-chart-empty");
    const ariaLabel = `نمودار تعداد پیامک ورودی در ${toPersianDigits(String(items.length))} بازه زمانی`;
    if (items.length >= 2) {
        renderAreaChart(chart, empty, items, {ariaLabel, maxLabels: 6});
    } else {
        renderBarChart(chart, empty, items, {sort: false, ariaLabel});
    }
}

async function showInboundSMSMessage(messageId) {
    try {
        const item = await apiRequest(`/api/v1/reports/inbound-sms/messages/${messageId}/`);
        document.getElementById("inbound-sms-detail-external").textContent = item.external_message_id;
        document.getElementById("inbound-sms-detail-system-time").textContent = displayDate(item.system_received_at);
        document.getElementById("inbound-sms-detail-lead").textContent = item.lead_label || "بدون تطبیق قطعی";
        document.getElementById("inbound-sms-detail-metadata").textContent = JSON.stringify(item.metadata, null, 2);
        const detail = document.getElementById("inbound-sms-message-detail");
        detail.hidden = false;
        detail.scrollIntoView({behavior: motionBehavior(), block: "start"});
    } catch (error) {
        showError(error);
    }
}

async function loadInboundSMSDrilldown(localDate, localHour, page = 1) {
    const section = document.getElementById("inbound-sms-drilldown");
    const loading = document.getElementById("inbound-sms-drilldown-loading");
    const errorNode = document.getElementById("inbound-sms-drilldown-error");
    const empty = document.getElementById("inbound-sms-drilldown-empty");
    const wrap = document.getElementById("inbound-sms-drilldown-wrap");
    const pager = document.getElementById("inbound-sms-drilldown-pagination");
    // The same window and filters the hourly table was built from: a
    // drill-down into a different range than the row that was clicked
    // would be a different question entirely.
    const query = inboundSMSReportWizard
        ? inboundSMSReportWizard.query()
        : new URLSearchParams();
    query.set("local_date", localDate);
    query.set("local_hour", String(localHour));
    query.set("page", String(page));
    section.hidden = false;
    loading.hidden = false;
    errorNode.hidden = true;
    empty.hidden = true;
    wrap.hidden = true;
    pager.hidden = true;
    document.getElementById("inbound-sms-drilldown-title").textContent =
        `جزئیات ${displayDay(localDate)} — ساعت ${toPersianDigits(String(localHour).padStart(2, "0"))}`;
    try {
        const data = await apiRequest(`/api/v1/reports/inbound-sms/drilldown/?${query}`);
        const rows = data.results.map((item) => {
            const row = document.createElement("tr");
            [
                item.provider_code,
                item.sender_normalized,
                item.recipient_normalized,
                displayDate(item.provider_received_at),
                item.customer_name || "بدون تطبیق قطعی",
                item.processing_state === "linked" ? "متصل" : "بدون تطبیق",
            ].forEach((value) => appendCell(row, value));
            const actions = document.createElement("td");
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-sm btn-light";
            button.textContent = "نمایش";
            button.addEventListener("click", () => showInboundSMSMessage(item.id));
            actions.appendChild(button);
            row.appendChild(actions);
            return row;
        });
        document.getElementById("inbound-sms-drilldown-body").replaceChildren(...rows);
        loading.hidden = true;
        if (!rows.length) {
            empty.hidden = false;
            return;
        }
        wrap.hidden = false;
        const previous = document.getElementById("inbound-sms-drilldown-prev");
        const next = document.getElementById("inbound-sms-drilldown-next");
        previous.disabled = !data.previous;
        next.disabled = !data.next;
        previous.onclick = () => loadInboundSMSDrilldown(localDate, localHour, page - 1);
        next.onclick = () => loadInboundSMSDrilldown(localDate, localHour, page + 1);
        document.getElementById("inbound-sms-drilldown-page").textContent = `صفحه ${page}`;
        pager.hidden = !data.previous && !data.next;
    } catch (error) {
        loading.hidden = true;
        errorNode.textContent = errorText(error);
        errorNode.hidden = false;
    }
}

//: The inbound report's own wizard, so its drill-down can ask for the
//: same window and filters the table above it was built from. Set when
//: the page is set up; `null` anywhere else.
let inboundSMSReportWizard = null;

export async function setupInboundSMSReport() {
    // Rebuilt as a wizard in 3.0.0 on the same driver the parcels report
    // uses. The drill-down below the wizard is untouched: it answers a
    // click on an hour rather than being a step.
    bindReportTableSearch(
        document.getElementById("inbound-sms-report-search"),
        [document.getElementById("inbound-sms-table-body")],
    );

    enhanceChecklistSelect(document.getElementById("inbound-sms-state"), {emptyMeansAll: true});
    inboundSMSReportWizard = setupReportWizard({
        prefix: "inbound-sms-report",
        endpoint: "/api/v1/reports/inbound-sms/",
        exportUrl: "/api/v1/exports/inbound-sms.xlsx",
        extraQuery: () => ({
            provider_code: document.getElementById("inbound-sms-provider").value,
            recipient_normalized: document.getElementById("inbound-sms-recipient").value,
            // Several states may be ticked (2.40.21); none means all.
            processing_state: Array.from(document.getElementById("inbound-sms-state").selectedOptions, (option) => option.value),
        }),
        isEmpty: (report) => !report.total,
        render: (report) => {
            // A new report answers a different question than whatever
            // hour was open under the old one.
            document.getElementById("inbound-sms-drilldown").hidden = true;
            document.getElementById("inbound-sms-message-detail").hidden = true;

            document.getElementById("inbound-sms-total").textContent =
                toPersianDigits(String(report.total));
            const rows = report.results.map((item) => {
                const row = document.createElement("tr");
                [
                    displayDay(item.local_date),
                    toPersianDigits(String(item.local_hour).padStart(2, "0")),
                    toPersianDigits(String(item.inbound_sms_count)),
                ].forEach((value) => appendCell(row, value));
                const actions = document.createElement("td");
                const drill = document.createElement("button");
                drill.type = "button";
                drill.className = "btn btn-sm btn-light";
                drill.textContent = "جزئیات";
                drill.addEventListener("click", () => loadInboundSMSDrilldown(item.local_date, item.local_hour));
                actions.appendChild(drill);
                row.appendChild(actions);
                return row;
            });
            document.getElementById("inbound-sms-table-body").replaceChildren(...rows);
            renderInboundSMSChart(report.results);
            document.getElementById("inbound-sms-empty").hidden = Boolean(rows.length);
            document.getElementById("inbound-sms-table-wrap").hidden = !rows.length;
        },
    });
}
