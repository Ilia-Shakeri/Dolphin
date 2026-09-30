import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate, displayDay} from "dolphin/core/jalali.js";
import {keepBadgeFresh} from "dolphin/shell/badges.js";
import {registerPopover} from "dolphin/ui/popover.js";

/**
 * The topbar reminder bell, on every page.
 *
 * Two requests, deliberately: the badge count is polled on a timer for
 * every open tab, and the grouped list is fetched only when someone
 * opens the panel. Building and sending every row on a poll nobody is
 * looking at would be avoidable load on every page of every session —
 * the same split `chat` makes between its thread list and
 * `unread-count`.
 *
 * There is no read/dismiss state anywhere in this feature. The badge is
 * a count of work that is actually due, so it clears when the work is
 * done — the follow-up is rescheduled, the cheque clears — not when
 * somebody glances at the panel. See `common/reminders.py` for why.
 */
export function setupReminderBell() {
    const toggle = document.getElementById("reminder-bell-toggle");
    const menu = document.getElementById("reminder-bell-menu");
    if (!toggle || !menu) return;

    const body = document.getElementById("reminder-bell-body");
    const empty = document.getElementById("reminder-bell-empty");
    const errorNote = document.getElementById("reminder-bell-error");
    const badge = document.querySelector("[data-reminder-badge]");
    const count = document.querySelector("[data-reminder-count]");
    const summary = document.querySelector("[data-reminder-summary]");
    let loading = false;

    registerPopover({toggle, panel: menu, onOpen: () => load()});

    function setBadge(total) {
        if (!badge || !count) return;
        badge.hidden = total <= 0;
        // Three digits is already an unusual amount of overdue work; past
        // that the exact figure stops being the useful part and the
        // button would start growing to fit it.
        count.textContent = total > 999 ? "+۹۹۹" : toPersianDigits(String(total));
    }

    function renderItem(item) {
        const link = document.createElement("a");
        link.className = "topbar-list-item";
        link.href = item.url;

        const text = document.createElement("span");
        text.className = "flex-grow-1 min-w-0";
        const title = document.createElement("span");
        title.className = "d-block text-gray-900 fw-semibold fs-7 text-truncate";
        title.textContent = item.title;
        const subtitle = document.createElement("span");
        subtitle.className = "d-block text-muted fs-8 text-truncate";
        subtitle.textContent = item.subtitle;
        text.append(title, subtitle);

        const due = document.createElement("span");
        due.className = "topbar-list-meta fs-8 fw-semibold " + (item.overdue ? "text-danger" : "text-muted");
        // A cheque's due date is a calendar day with no clock of its own
        // (`DateField`); a follow-up is an instant. Rendering the first
        // through the instant path would push it through a time zone and
        // could land it on the day before.
        due.textContent = item.due_kind === "date" ? displayDay(item.due_at) : displayDate(item.due_at);

        link.append(text, due);
        return link;
    }

    function renderGroup(group) {
        const section = document.createElement("div");
        section.className = "topbar-list-group";

        const heading = document.createElement("div");
        heading.className = "d-flex align-items-center gap-2 px-2 mb-1";
        const icon = document.createElement("i");
        icon.className = `di-duotone ${group.icon} fs-5 text-${group.accent}`;
        // A duotone icon-font glyph is drawn from nested `.path*` spans, and the
        // count differs per glyph — `di-call` has eight. The server sends
        // it with the group, the same way the dashboard tiles carry
        // `icon_paths`; drawing two for an eight-path icon draws a
        // quarter of it.
        for (let index = 1; index <= (group.icon_paths || 2); index += 1) icon.append(pathSpan(index));
        const label = document.createElement("span");
        label.className = "text-gray-700 fw-bold fs-8";
        label.textContent = `${group.label} (${toPersianDigits(String(group.count))})`;
        heading.append(icon, label);
        section.appendChild(heading);

        group.items.forEach((item) => section.appendChild(renderItem(item)));

        // The group holds more than the page it returned: say so rather
        // than letting the list look complete when it is not.
        if (group.count > group.items.length) {
            const more = document.createElement("div");
            more.className = "text-muted fs-8 px-2 pt-1";
            more.textContent = `و ${toPersianDigits(String(group.count - group.items.length))} مورد دیگر`;
            section.appendChild(more);
        }
        return section;
    }

    function pathSpan(index) {
        const span = document.createElement("span");
        span.className = `path${index}`;
        return span;
    }

    async function load() {
        if (loading) return;
        loading = true;
        try {
            const data = await apiRequest("/api/v1/reminders/");
            body.replaceChildren();
            data.groups.forEach((group) => body.appendChild(renderGroup(group)));
            empty.hidden = data.count > 0;
            errorNote.hidden = true;
            setBadge(data.count);
            if (summary) {
                summary.textContent = data.overdue_count > 0
                    ? `${toPersianDigits(String(data.overdue_count))} مورد گذشته از موعد`
                    : `${toPersianDigits(String(data.count))} مورد`;
            }
        } catch (error) {
            body.replaceChildren();
            empty.hidden = true;
            errorNote.hidden = false;
            if (summary) summary.textContent = "";
        } finally {
            loading = false;
        }
    }

    // Slower than chat's twenty seconds: a due date does not move while
    // someone is looking at it, and this query touches four tables.
    keepBadgeFresh({url: "/api/v1/reminders/count/", intervalMs: 60000, key: "reminders", apply: setBadge});
}
