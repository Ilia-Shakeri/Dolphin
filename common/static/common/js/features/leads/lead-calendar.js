import {apiRequest} from "dolphin/core/api.js";
import {tehranParts} from "dolphin/core/jalali.js";
import {globalMessage} from "dolphin/core/messages.js";
import {createJalaliCalendar} from "dolphin/ui/calendar.js";
import {chartPalette} from "dolphin/ui/charts.js";
import {loadAllPages} from "dolphin/ui/lists.js";

export async function setupLeadCalendar() {
    const container = document.getElementById("lead-calendar");
    if (!container || typeof FullCalendar === "undefined") return;
    const loading = document.getElementById("lead-calendar-loading");
    const errorNode = document.getElementById("lead-calendar-error");

    const palette = chartPalette();
    // pending/completed/cancelled — the three backend-owned Lead statuses,
    // same order and same colours `sales_by_agent`-style charts already use
    // for "needs attention" (primary), "done" (success), "closed out, no
    // action" (danger) — and the same three the legend above already shows.
    const STATUS_META = {
        pending: {label: "در انتظار تکمیل", color: palette[0], badgeClass: "badge-light-primary"},
        completed: {label: "تکمیل", color: palette[1], badgeClass: "badge-light-success"},
        cancelled: {label: "کنسل شده", color: palette[4], badgeClass: "badge-light-danger"},
        // A person in a campaign (2.39.25): their follow-up lives on them, not on
        // the campaign's hidden container, so they are a source of their own.
        member: {label: "مخاطب کمپین", color: palette[2], badgeClass: "badge-light-info"},
    };

    function memberEvent(member, now) {
        const meta = STATUS_META.member;
        const parts = tehranParts(member.next_follow_up_at);
        const lead = {
            customer_name: member.full_name,
            assigned_to_display: member.assigned_to_display,
            source: "کمپین",
            campaign_or_batch: member.campaign_name,
            notes: "",
        };
        const overdue = new Date(member.next_follow_up_at) < now;
        return {
            id: `m${member.id}`,
            title: `${member.full_name} — ${member.campaign_name}`,
            start: member.next_follow_up_at,
            allDay: Boolean(parts && parts.hour === 0 && parts.minute === 0),
            backgroundColor: meta.color,
            borderColor: meta.color,
            startEditable: false,
            durationEditable: false,
            classNames: overdue ? ["fc-event-overdue"] : [],
            extendedProps: {lead, meta, overdue, campaignUrl: `/campaigns/${member.campaign}/`},
        };
    }

    /**
     * A hover preview richer than one title-attribute line: who it's for,
     * status, agent, source/campaign, and a notes preview — everything a
     * follow-up needs to be actioned without leaving the calendar.
     *
     * Every piece of text below goes through `textContent`, never through
     * an HTML string built by hand — a customer name, note, or source is
     * free text someone typed, and this file never assigns to `innerHTML`
     * from a template literal anywhere. `content.innerHTML` is read once,
     * at the very end, only to hand Bootstrap's Popover the markup it
     * requires — by then every value in it was already escaped by the
     * browser itself when each `textContent` assignment above ran.
     */
    function buildEventPopoverContent(lead, meta, overdue, when) {
        const wrap = document.createElement("div");

        const nameLine = document.createElement("div");
        nameLine.className = "fw-bold fs-6 mb-1";
        nameLine.textContent = lead.customer_name || "سرنخ بدون مشتری";
        wrap.append(nameLine);

        const badgeRow = document.createElement("div");
        badgeRow.className = "d-flex flex-wrap gap-2 mb-2";
        const statusBadge = document.createElement("span");
        statusBadge.className = `badge ${meta.badgeClass}`;
        statusBadge.textContent = meta.label;
        badgeRow.append(statusBadge);
        if (overdue) {
            const overdueBadge = document.createElement("span");
            overdueBadge.className = "badge badge-light-danger";
            overdueBadge.textContent = "دیرکرد";
            badgeRow.append(overdueBadge);
        }
        wrap.append(badgeRow);

        [
            ["کارشناس", lead.assigned_to_display],
            ["منبع", lead.source],
            ["کمپین", lead.campaign_or_batch],
            ["زمان پیگیری", when],
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

        if (lead.notes) {
            const notes = document.createElement("div");
            notes.className = "fs-8 text-gray-600 mt-2 pt-2 border-top border-gray-300";
            notes.textContent = lead.notes.length > 100 ? `${lead.notes.slice(0, 100)}…` : lead.notes;
            wrap.append(notes);
        }
        return wrap;
    }

    async function saveFollowUp(id, instant) {
        await apiRequest(`/api/v1/leads/${id}/`, {
            method: "PATCH",
            body: {next_follow_up_at: instant},
        });
        globalMessage("تاریخ پیگیری به‌روزرسانی شد.", true);
    }

    // `let`, declared before the config that references it: the two
    // custom month buttons below close over this and only ever run
    // after the assignment has happened.
    // The shell — toolbar, Jalali titles, drag and «انتقال به تاریخ» — is
    // `createJalaliCalendar`, shared with the after-sales calendar.
    createJalaliCalendar({
        liveKinds: ["lead", "campaign"],
        container,
        loading,
        errorNode,
        fetchEvents: async (fetchInfo) => {
            const query = new URLSearchParams({
                follow_up_from: fetchInfo.startStr,
                follow_up_to: fetchInfo.endStr,
            });
            const [leads, members] = await Promise.all([
                loadAllPages(`/api/v1/leads/?${query}`),
                // People in a campaign have their own follow-ups (2.39.25); a
                // reader without that feature simply gets none.
                apiRequest(`/api/v1/campaign-members/follow-ups/?${query}`).catch(() => []),
            ]);
            const now = new Date();
            return [...leads.map((lead) => {
                const parts = tehranParts(lead.next_follow_up_at);
                const allDay = Boolean(parts && parts.hour === 0 && parts.minute === 0);
                const meta = STATUS_META[lead.status] || STATUS_META.pending;
                // Only a pending follow-up can be late.
                const overdue = lead.status === "pending" && new Date(lead.next_follow_up_at) < now;
                return {
                    id: String(lead.id),
                    title: lead.customer_name
                        ? `${lead.customer_name}${lead.assigned_to_display ? " — " + lead.assigned_to_display : ""}`
                        : `سرنخ بدون مشتری${lead.assigned_to_display ? " — " + lead.assigned_to_display : ""}`,
                    start: lead.next_follow_up_at,
                    allDay,
                    backgroundColor: meta.color,
                    borderColor: meta.color,
                    classNames: overdue ? ["fc-event-overdue"] : [],
                    extendedProps: {lead, meta, overdue},
                };
            }), ...(Array.isArray(members) ? members : []).map((member) => memberEvent(member, now))];
        },
        // A campaign person is shown here and opened on its campaign; it is
        // not moved from this calendar (no `lead`).
        recordOf: (event) => event.extendedProps.lead,
        save: saveFollowUp,
        popover: (event, when) => buildEventPopoverContent(event.extendedProps.lead, event.extendedProps.meta, event.extendedProps.overdue, when),
        eventUrl: (event) => event.extendedProps.campaignUrl || `/leads/${event.id}/`,
    });
}
