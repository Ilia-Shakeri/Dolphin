import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {clearMessages, globalMessage, showError} from "dolphin/core/messages.js";
import {enhanceChecklistSelect} from "dolphin/ui/checklist-select.js";

/**
 * Work back from a deactivated account (2.40.48, BIZ-013): one notice per
 * person on the leads page, with the decision in a dialog — split among the
 * other responsibles of each campaign, or hand it all to one person. The rule
 * and every check are `sales.returned_work`; this only asks and shows.
 *
 * `?returned_from=<id>` (the reminder's link) narrows the list below to that
 * person's waiting leads; `onFilter` tells the list.
 */
export function setupReturnedWork({onFilter, onResolved} = {}) {
    const area = document.getElementById("returned-work");
    const dialog = document.getElementById("returned-work-dialog");
    if (!area || !dialog) return {returnedFrom: null};
    const form = document.getElementById("returned-work-form");
    const summary = document.getElementById("returned-work-summary");
    const fallbackField = dialog.querySelector('[data-returned-field="fallback"]');
    const assignField = dialog.querySelector('[data-returned-field="assign"]');
    const filterBar = document.getElementById("returned-work-filter");
    const filterLabel = document.getElementById("returned-work-filter-label");
    enhanceChecklistSelect(document.getElementById("returned-work-fallback"));

    const params = new URLSearchParams(window.location.search);
    const returnedFrom = /^\d+$/.test(params.get("returned_from") || "") ? params.get("returned_from") : null;
    let current = null;

    function countText(row) {
        const parts = [];
        if (row.lead_count) parts.push(`${toPersianDigits(String(row.lead_count))} سرنخ`);
        if (row.member_count) parts.push(`${toPersianDigits(String(row.member_count))} مخاطب کمپین`);
        return parts.join(" و ");
    }

    function notice(row) {
        const box = document.createElement("div");
        box.className = "notice d-flex flex-wrap align-items-center gap-3 bg-light-warning rounded border-warning border border-dashed p-4";
        const icon = document.createElement("i");
        icon.className = "di-duotone di-arrows-circle fs-2x text-warning flex-shrink-0";
        icon.setAttribute("aria-hidden", "true");
        icon.append(...["path1", "path2"].map((name) => Object.assign(document.createElement("span"), {className: name})));
        const text = document.createElement("div");
        text.className = "flex-grow-1 min-w-0";
        const title = document.createElement("span");
        title.className = "d-block fw-bold text-gray-900";
        title.textContent = `کارهای «${row.from_user_display}» برگشت`;
        const detail = document.createElement("span");
        detail.className = "d-block text-gray-700 fs-7";
        detail.textContent = `${countText(row)} بی‌مسئول مانده و منتظر تصمیم شماست.`;
        text.append(title, detail);
        const actions = document.createElement("div");
        actions.className = "d-flex gap-2 flex-shrink-0";
        if (row.lead_count) {
            const show = document.createElement("a");
            show.className = "btn btn-sm btn-light";
            show.href = `/leads/?returned_from=${row.from_user}`;
            show.textContent = "دیدن سرنخ‌ها";
            actions.append(show);
        }
        const decide = document.createElement("button");
        decide.type = "button";
        decide.className = "btn btn-sm btn-primary";
        decide.textContent = "تصمیم";
        decide.addEventListener("click", () => open(row));
        actions.append(decide);
        box.append(icon, text, actions);
        return box;
    }

    function syncFields() {
        const action = form.elements.action.value;
        fallbackField.hidden = action !== "split";
        assignField.hidden = action !== "assign";
    }
    form.addEventListener("change", (event) => {
        if (event.target.name === "action") syncFields();
    });

    function open(row) {
        current = row;
        form.reset();
        clearMessages(form);
        syncFields();
        summary.textContent = `${countText(row)} از «${row.from_user_display}» پس از غیرفعال شدن حسابش برگشته است.`;
        dialog.showModal();
    }
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!current) return;
        clearMessages(form);
        const action = form.elements.action.value;
        const body = {from_user: current.from_user, action};
        if (action === "assign") {
            const to = form.elements.to_user.value;
            if (!to) {
                form.querySelector('[data-error-for="to_user"]').textContent = "یک نفر را انتخاب کنید.";
                return;
            }
            body.to_user = Number(to);
        } else {
            body.fallback_users = [...document.getElementById("returned-work-fallback").selectedOptions].map((option) => Number(option.value));
        }
        const submit = form.querySelector('button[type="submit"]');
        submit.disabled = true;
        try {
            const result = await apiRequest("/api/v1/returned-work/resolve/", {method: "POST", body});
            dialog.close();
            const shares = result.by_user.map((entry) => `${entry.display}: ${toPersianDigits(String(entry.count))}`).join("، ");
            globalMessage(`${toPersianDigits(String(result.assigned_count))} مورد واگذار شد (${shares}).`, true);
            await load();
            onResolved?.();
        } catch (error) {
            showError(error, form);
        } finally {
            submit.disabled = false;
        }
    });

    async function load() {
        try {
            const rows = await apiRequest("/api/v1/returned-work/");
            area.replaceChildren(...rows.map(notice));
            area.hidden = rows.length === 0;
            if (returnedFrom) {
                const row = rows.find((item) => String(item.from_user) === returnedFrom);
                filterLabel.textContent = row
                    ? `فقط سرنخ‌های برگشتی از «${row.from_user_display}»`
                    : "کارهای برگشتی این کاربر تصمیم گرفته شده‌اند.";
                filterBar.hidden = false;
            }
        } catch (error) {
            showError(error);
        }
    }
    load();
    if (returnedFrom) onFilter?.(returnedFrom);
    return {returnedFrom};
}
