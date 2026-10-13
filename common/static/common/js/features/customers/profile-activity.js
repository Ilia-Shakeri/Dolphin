import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate} from "dolphin/core/jalali.js";

/** One timeline event, as the customer timeline has always drawn it. */
function timelineEntry(event) {
    const item = document.createElement("li");
    item.className = "customer-timeline-entry";

    const marker = document.createElement("span");
    marker.className = `customer-timeline-marker bg-light-${event.accent}`;
    const icon = document.createElement("i");
    icon.className = `di-duotone ${event.icon} fs-5 text-${event.accent}`;
    for (let index = 1; index <= (event.icon_paths || 2); index += 1) {
        const path = document.createElement("span");
        path.className = `path${index}`;
        icon.append(path);
    }
    marker.appendChild(icon);

    const box = document.createElement("div");
    box.className = "customer-timeline-body";

    const head = document.createElement("div");
    head.className = "d-flex flex-wrap align-items-center justify-content-between gap-2";
    const kind = document.createElement("span");
    kind.className = `badge badge-light-${event.accent} fs-8`;
    kind.textContent = event.label;
    const when = document.createElement("span");
    when.className = "text-muted fs-8";
    when.textContent = displayDate(event.at);
    head.append(kind, when);

    const title = document.createElement(event.url ? "a" : "span");
    title.className = "d-block text-gray-900 fw-semibold fs-6 mt-1 text-decoration-none text-break";
    if (event.url) title.href = event.url;
    title.textContent = event.title;

    const subtitle = document.createElement("span");
    subtitle.className = "d-block text-muted fs-7";
    subtitle.textContent = event.subtitle;

    box.append(head, title, subtitle);
    item.append(marker, box);
    return item;
}

/**
 * The «فعالیت‌ها» tab. It reports its own failure in its own card and
 * leaves the rest of the profile standing.
 */
export async function loadProfileTimeline(personType, personId) {
    const list = document.getElementById("profile-timeline-list");
    if (!list) return;
    const loadingNode = document.getElementById("profile-timeline-loading");
    const empty = document.getElementById("profile-timeline-empty");
    const failed = document.getElementById("profile-timeline-error");
    const more = document.getElementById("profile-timeline-more");
    try {
        const data = await apiRequest(`/api/v1/profiles/${personType}/${personId}/timeline/`);
        list.replaceChildren(...data.events.map(timelineEntry));
        loadingNode.hidden = true;
        list.hidden = data.events.length === 0;
        empty.hidden = data.events.length > 0;
        // `count` is everything found; `events` is the page shown.
        if (data.count > data.events.length) {
            more.textContent = `${toPersianDigits(String(data.count - data.events.length))} رویداد قدیمی‌تر نشان داده نشده است.`;
            more.hidden = false;
        }
    } catch (error) {
        loadingNode.hidden = true;
        failed.hidden = false;
    }
}

/** The overview's «آخرین رویدادها»: the newest five of the same timeline. */
export async function loadRecentActivity(personType, personId) {
    const card = document.querySelector("[data-recent-activity]");
    if (!card) return;
    const list = card.querySelector("[data-recent-activity-list]");
    const loadingNode = card.querySelector("[data-recent-activity-loading]");
    const empty = card.querySelector("[data-recent-activity-empty]");
    const failed = card.querySelector("[data-recent-activity-error]");
    const more = card.querySelector("[data-recent-activity-more]");
    // A customer's box holds the whole timeline and scrolls (2.27.0);
    // a user's still shows the newest few beside «همهٔ رویدادها».
    const all = card.hasAttribute("data-recent-activity-all");
    try {
        // Both addresses written out whole, so each one is a path the
        // route check (`test_ui_connectivity`) can resolve.
        const data = await apiRequest(all
            ? `/api/v1/profiles/${personType}/${personId}/timeline/`
            : `/api/v1/profiles/${personType}/${personId}/timeline/?limit=5`);
        list.replaceChildren(...data.events.map(timelineEntry));
        loadingNode.hidden = true;
        list.hidden = data.events.length === 0;
        empty.hidden = data.events.length > 0;
        // The server shows at most so many events; say when there are more
        // rather than letting the list look complete.
        if (all && more && Number(data.count) > data.events.length) {
            more.hidden = false;
            more.textContent = `${toPersianDigits(String(data.events.length))} رویداد تازه‌تر از ${toPersianDigits(String(data.count))} رویداد نمایش داده شده است.`;
        }
    } catch (error) {
        loadingNode.hidden = true;
        failed.hidden = false;
    }
}
