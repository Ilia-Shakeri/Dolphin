import {apiRequest} from "dolphin/core/api.js";
import {displayDate} from "dolphin/core/jalali.js";
import {errorText} from "dolphin/core/messages.js";

/**
 * The header's activity and help drawers (2.40.42, roadmap item 13). The
 * drawers themselves are the UI kit's `data-dolphin-drawer`, which opens and
 * closes them; this fills them when they open.
 */

/** «آخرین رویدادها»: the newest entries of the system log, read when opened. */
export function setupActivityDrawer() {
    const toggle = document.getElementById("dolphin_drawer_activity_toggle");
    const list = document.getElementById("activity-drawer-list");
    if (!toggle || !list) return;
    const loading = document.getElementById("activity-drawer-loading");
    const empty = document.getElementById("activity-drawer-empty");
    const errorNode = document.getElementById("activity-drawer-error");

    async function load() {
        errorNode.hidden = true;
        let data;
        try {
            data = await apiRequest("/api/v1/activity-logs/?page=1");
        } catch (error) {
            loading.hidden = true;
            errorNode.textContent = errorText(error);
            errorNode.hidden = false;
            return;
        }
        loading.hidden = true;
        const rows = data.results.slice(0, 30);
        empty.hidden = rows.length > 0;
        list.hidden = rows.length === 0;
        list.replaceChildren(...rows.map((row) => {
            const item = document.createElement("li");
            item.className = "activity-drawer-item";
            const link = document.createElement("a");
            link.href = `/activity-logs/${row.id}/`;
            link.className = "activity-drawer-link";
            const what = document.createElement("span");
            what.className = "activity-drawer-what";
            what.textContent = row.operation_display;
            const meta = document.createElement("span");
            meta.className = "activity-drawer-meta";
            meta.textContent = [row.actor_display, row.object_type_display, displayDate(row.created_at)].filter(Boolean).join(" · ");
            link.append(what, meta);
            item.append(link);
            return item;
        }));
    }

    toggle.addEventListener("click", load);
}

/** «راهنما»: the topic of the section in view, and the others on request. */
export function setupHelpDrawer() {
    const toggle = document.getElementById("dolphin_drawer_help_toggle");
    const topics = [...document.querySelectorAll("[data-help-topic]")];
    if (!toggle || !topics.length) return;

    function show(key) {
        const wanted = topics.find((topic) => topic.dataset.helpTopic === key) || topics[0];
        topics.forEach((topic) => { topic.hidden = topic !== wanted; });
        document.querySelectorAll("[data-help-show]").forEach((button) => {
            button.classList.toggle("active", button.dataset.helpShow === wanted.dataset.helpTopic);
            button.setAttribute("aria-pressed", String(button.dataset.helpShow === wanted.dataset.helpTopic));
        });
    }

    // The section in view is the sidebar group the page marked as current; a
    // group of one link (dashboard, customers, settings) is that link, whose
    // module is named like the group.
    toggle.addEventListener("click", () => {
        const current = document.querySelector("#app-sidebar [data-nav-group].here")?.dataset.navGroup
            || document.querySelector('#app-sidebar .menu-link[aria-current="page"]')?.dataset.module
            || "";
        show(current);
    });
    document.querySelectorAll("[data-help-show]").forEach((button) => {
        button.addEventListener("click", () => show(button.dataset.helpShow));
    });
}
