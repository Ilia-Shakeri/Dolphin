import {toPersianDigits} from "dolphin/core/digits.js";
import {dispatchUserEvent} from "dolphin/core/events.js";

/**
 * Turns a `<select multiple>` into a searchable checklist (2.39.7).
 *
 * The select stays in the DOM as the form's single source of truth (so every
 * reader of `selectedOptions` keeps working); the checklist only mirrors it.
 * Nobody has to know about holding Ctrl.
 */
export function enhanceChecklistSelect(select) {
    if (!select || select.dataset.checklistReady) return;
    select.dataset.checklistReady = "1";
    select.hidden = true;
    select.setAttribute("aria-hidden", "true");

    const wrap = document.createElement("div");
    wrap.className = "dolphin-checklist border rounded p-3";
    const tools = document.createElement("div");
    tools.className = "d-flex flex-wrap align-items-center gap-2 mb-2";
    const search = document.createElement("input");
    search.type = "search";
    search.className = "form-control form-control-sm form-control-solid w-200px";
    search.placeholder = "جست‌وجو";
    search.autocomplete = "off";
    const all = document.createElement("button");
    all.type = "button";
    all.className = "btn btn-sm btn-light";
    all.textContent = "انتخاب همه";
    const none = document.createElement("button");
    none.type = "button";
    none.className = "btn btn-sm btn-light";
    none.textContent = "پاک‌کردن";
    const counter = document.createElement("span");
    counter.className = "text-muted fs-8 ms-auto";
    counter.setAttribute("aria-live", "polite");
    tools.append(search, all, none, counter);
    const list = document.createElement("div");
    list.className = "mh-200px overflow-auto";
    list.setAttribute("role", "group");
    const label = select.id ? document.querySelector(`label[for="${select.id}"]`) : null;
    if (label) list.setAttribute("aria-label", label.textContent.trim());
    wrap.append(tools, list);
    select.after(wrap);

    const boxes = [];
    const refresh = () => {
        const n = Array.from(select.options).filter((option) => option.selected).length;
        counter.textContent = n ? `${toPersianDigits(String(n))} مورد انتخاب شد` : "هیچ‌کدام (یعنی همه)";
    };
    const filter = () => {
        const term = search.value.trim();
        boxes.forEach(({row, option}) => { row.hidden = Boolean(term) && !option.text.includes(term); });
    };
    const build = () => {
        boxes.length = 0;
        list.replaceChildren();
        if (!select.options.length) {
            list.textContent = "موردی یافت نشد.";
            refresh();
            return;
        }
        Array.from(select.options).forEach((option) => {
            const row = document.createElement("label");
            row.className = "form-check form-check-custom form-check-solid d-flex align-items-center gap-3 py-2";
            const box = document.createElement("input");
            box.type = "checkbox";
            box.className = "form-check-input";
            box.checked = option.selected;
            box.addEventListener("change", () => {
                option.selected = box.checked;
                refresh();
                dispatchUserEvent(select, "change");
            });
            const text = document.createElement("span");
            text.className = "form-check-label";
            text.textContent = option.text;
            row.append(box, text);
            list.append(row);
            boxes.push({row, option, box});
        });
        filter();
        refresh();
    };
    const setAll = (value) => {
        boxes.forEach(({row, option, box}) => {
            if (row.hidden) return;
            option.selected = value;
            box.checked = value;
        });
        refresh();
        dispatchUserEvent(select, "change");
    };
    all.addEventListener("click", () => setAll(true));
    none.addEventListener("click", () => setAll(false));
    search.addEventListener("input", filter);
    new MutationObserver(build).observe(select, {childList: true});
    // Options selected from code (a form being filled in for editing) show
    // as ticked too (2.40.0); the checklist's own changes are user events.
    select.addEventListener("change", (event) => {
        if (event.userInitiated) return;
        boxes.forEach(({option, box}) => { box.checked = option.selected; });
        refresh();
    });
    select.form?.addEventListener("reset", () => setTimeout(build));
    build();
}
