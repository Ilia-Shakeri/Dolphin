import {apiRequest} from "dolphin/core/api.js";
import {tehranParts} from "dolphin/core/jalali.js";
import {globalMessage} from "dolphin/core/messages.js";
import {createJalaliCalendar} from "dolphin/ui/calendar.js";
import {chartPalette} from "dolphin/ui/charts.js";
import {loadAllPages} from "dolphin/ui/lists.js";

/**
 * The after-sales side of the follow-up calendar
 * (DOLPHIN_FEATURE_MAP_AND_ROADMAP.md §7 phase E) — the same FullCalendar
 * setup as `setupLeadCalendar` above, adapted for two real differences:
 *
 * - after-sales `status` is free text an elevated role or the assigned
 *   technician types (`transition_after_sales_status`), not a fixed
 *   three-value enum like Lead's — so colour here comes from open/closed
 *   (`closed_at`), the one status fact every deployment shares, not from
 *   the status string itself.
 * - dragging an event PATCHes a plain field on `setupLeadCalendar`
 *   because `next_follow_up_at` is a directly writable Lead field; here
 *   it POSTs to `schedule-appointment` instead, because scheduling an
 *   after-sales appointment carries its own rules (elevated role or the
 *   assigned technician only, refused on a closed case) that a bare
 *   PATCH would bypass — `next_appointment_at` is deliberately read-only
 *   on `AfterSalesRequestSerializer` for exactly that reason.
 */
export async function setupAfterSalesCalendar() {
    const container = document.getElementById("after-sales-calendar");
    if (!container || typeof FullCalendar === "undefined") return;
    const loading = document.getElementById("after-sales-calendar-loading");
    const errorNode = document.getElementById("after-sales-calendar-error");

    const palette = chartPalette();
    const OPEN_COLOR = palette[0];
    const CLOSED_COLOR = palette[1];

    function buildEventPopoverContent(item, overdue, when) {
        const wrap = document.createElement("div");

        const nameLine = document.createElement("div");
        nameLine.className = "fw-bold fs-6 mb-1";
        nameLine.textContent = item.subject || item.customer_name || "پروندهٔ بدون موضوع";
        wrap.append(nameLine);

        const badgeRow = document.createElement("div");
        badgeRow.className = "d-flex flex-wrap gap-2 mb-2";
        const statusBadge = document.createElement("span");
        statusBadge.className = `badge ${item.closed_at ? "badge-light-success" : "badge-light-primary"}`;
        statusBadge.textContent = item.status || (item.closed_at ? "بسته" : "باز");
        badgeRow.append(statusBadge);
        if (overdue) {
            const overdueBadge = document.createElement("span");
            overdueBadge.className = "badge badge-light-danger";
            overdueBadge.textContent = "دیرکرد";
            badgeRow.append(overdueBadge);
        }
        wrap.append(badgeRow);

        [
            ["مشتری", item.customer_name],
            ["کارشناس", item.assigned_to_display],
            ["زمان قرار", when],
        ].forEach(([label, value]) => {
            if (!value) return;
            const row = document.createElement("div");
            row.className = "fs-8 text-gray-600 mb-1";
            const strong = document.createElement("span");
            strong.className = "text-gray-800 fw-semibold";
            strong.textContent = `${label}: `;
            row.append(strong, document.createTextNode(value));
            wrap.append(row);
        });

        if (item.description) {
            const description = document.createElement("div");
            description.className = "fs-8 text-gray-600 mt-2 pt-2 border-top border-gray-300";
            description.textContent = item.description.length > 100 ? `${item.description.slice(0, 100)}…` : item.description;
            wrap.append(description);
        }
        return wrap;
    }

    async function saveAppointment(id, instant) {
        await apiRequest(`/api/v1/after-sales/${id}/schedule-appointment/`, {
            method: "POST",
            body: {appointment_at: instant},
        });
        globalMessage("زمان قرار به‌روزرسانی شد.", true);
    }

    // The shell — toolbar, Jalali titles, drag and «انتقال به تاریخ» — is
    // `createJalaliCalendar`, shared with the follow-up calendar.
    createJalaliCalendar({
        liveKinds: ["after_sales"],
        container,
        loading,
        errorNode,
        fetchEvents: async (fetchInfo) => {
            const query = new URLSearchParams({
                appointment_from: fetchInfo.startStr,
                appointment_to: fetchInfo.endStr,
            });
            const items = await loadAllPages(`/api/v1/after-sales/?${query}`);
            const now = new Date();
            return items.map((item) => {
                const parts = tehranParts(item.next_appointment_at);
                const allDay = Boolean(parts && parts.hour === 0 && parts.minute === 0);
                // Only a still-open case can be "late" — a closed one has
                // nothing left to act on, so a past appointment on one is
                // expected, not a warning.
                const overdue = !item.closed_at && new Date(item.next_appointment_at) < now;
                return {
                    id: String(item.id),
                    title: item.customer_name
                        ? `${item.customer_name}${item.assigned_to_display ? " — " + item.assigned_to_display : ""}`
                        : item.subject,
                    start: item.next_appointment_at,
                    allDay,
                    backgroundColor: item.closed_at ? CLOSED_COLOR : OPEN_COLOR,
                    borderColor: item.closed_at ? CLOSED_COLOR : OPEN_COLOR,
                    classNames: overdue ? ["fc-event-overdue"] : [],
                    extendedProps: {item, overdue},
                };
            });
        },
        recordOf: (event) => event.extendedProps.item,
        save: saveAppointment,
        popover: (event, when) => buildEventPopoverContent(event.extendedProps.item, event.extendedProps.overdue, when),
        eventUrl: (event) => `/after-sales/${event.id}/`,
    });
}
