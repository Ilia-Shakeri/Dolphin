import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate, displayDay} from "dolphin/core/jalali.js";
import {LEAD_STATUS_LABELS} from "dolphin/core/labels.js";
import {appendCell, appendDetailLink, directionText} from "dolphin/ui/table.js";

/** An E.164 Iranian number the way it is written here (`۰۹۱۲…`). */
export function localPhone(number) {
    const text = String(number || "");
    return toPersianDigits(text.startsWith("+98") ? `0${text.slice(3)}` : text);
}

export function leadRow(lead) {
    const row = document.createElement("tr");
    // The customer column is gone: a campaign is worked from its target
    // audience rather than from one customer.
    appendCell(row, lead.source);
    appendCell(row, lead.campaign_or_batch);
    const [label, badgeClass] = LEAD_STATUS_LABELS[lead.status] || [lead.status || "—", "badge-light"];
    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `badge ${badgeClass}`;
    badge.textContent = label;
    statusCell.append(badge);
    row.append(statusCell);
    appendCell(row, lead.assigned_to_display || lead.assigned_to);
    // Follow-up and registration are both days; the time of day was never
    // acted on and only made the column harder to scan.
    appendCell(row, displayDay(lead.next_follow_up_at));
    appendCell(row, displayDay(lead.created_at));
    appendDetailLink(row, `/leads/${lead.id}/`);
    return row;
}

export function interactionRow(interaction) {
    const row = document.createElement("tr");
    appendCell(row, interaction.customer_name || interaction.customer);
    appendCell(row, interaction.phone);
    appendCell(row, directionText(interaction.direction));
    appendCell(row, interaction.outcome);
    appendCell(row, displayDate(interaction.occurred_at));
    appendCell(row, displayDate(interaction.next_follow_up_at));
    appendDetailLink(row, `/interactions/${interaction.id}/`);
    return row;
}
