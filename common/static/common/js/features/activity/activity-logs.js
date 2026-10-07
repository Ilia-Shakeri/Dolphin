import {ROLE_LABELS} from "dolphin/core/config.js";
import {apiDate, displayDate} from "dolphin/core/jalali.js";
import {setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {appendCell, appendDetailLink} from "dolphin/ui/table.js";

function activityLogRow(item) {
    const row = document.createElement("tr");
    appendCell(row, item.operation_display || item.operation);
    appendCell(row, item.object_type_display || item.object_type);
    appendCell(row, item.object_id);
    appendCell(row, ROLE_LABELS[item.actor_role_snapshot] || item.actor_role_snapshot);
    appendCell(row, displayDate(item.created_at));
    appendDetailLink(row, `/activity-logs/${item.id}/`);
    return row;
}

export function setupActivityLogs() {
    const form = document.getElementById("activity-log-search-form");
    setupListFilter("activity-log");
    const controller = setupPagedList({
        key: "activity-logs",
        form,
        search: document.getElementById("activity-log-search"),
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page), ordering: document.getElementById("activity-log-ordering").value});
            const search = document.getElementById("activity-log-search").value.trim();
            if (search) query.set("search", search);
            // The recorded-at window (product-owner request 2026-09-20).
            // `apiDate` turns what the Jalali picker wrote into the
            // `YYYY-MM-DD` the API stores; an empty box sends nothing, so
            // an untouched filter produces the URL it always produced.
            const from = apiDate(document.getElementById("activity-log-from").value);
            const to = apiDate(document.getElementById("activity-log-to").value);
            if (from) query.set("created_from", from);
            if (to) query.set("created_to", to);
            return `/api/v1/activity-logs/?${query}`;
        },
        renderRow: activityLogRow,
    });
    controller.load();
}
