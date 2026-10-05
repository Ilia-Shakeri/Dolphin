import {dispatchUserEvent} from "dolphin/core/events.js";
import {toLatinDigits, toPersianDigits} from "dolphin/core/digits.js";
import {fillSelect, loadAllPages} from "dolphin/ui/lists.js";

/**
 * Make one `[data-searchable-select]` block usable by typing.
 *
 * The real `<select>` stays in the DOM, keeps the value, and is what
 * submits — this only filters what is offered and writes the choice back to
 * it. Nothing downstream needs to know the search box exists: `FormData`,
 * the tests, and every `.value` read in this file all keep working, and if
 * this function never ran the select is still a usable control.
 *
 * That is the whole reason it is built this way. A widget that *replaced*
 * the select would have to keep a copy of the value, and a copy that drifts
 * shows the operator a name that is not what will be recorded.
 *
 * The options are re-read from the select on every open, so the list that
 * `fillSelect` writes after the API returns is picked up without this
 * needing to be told about it.
 */
function setupSearchableSelect(root) {
    const input = root.querySelector("[data-searchable-input]");
    const select = root.querySelector("[data-searchable-source]");
    const list = root.querySelector(".searchable-select-options");
    if (!input || !select || !list) return;

    let active = -1;

    // The swap happens here rather than in the markup, and that is the
    // whole point of building it this way: until this line runs the page
    // carries a working `<select>`, so a script that fails to load leaves a
    // usable control behind instead of an invisible one.
    input.hidden = false;
    select.hidden = true;

    const options = () =>
        Array.from(select.options).filter((option) => option.value !== "");

    function close() {
        list.hidden = true;
        input.setAttribute("aria-expanded", "false");
        active = -1;
    }

    function choose(option) {
        select.value = option.value;
        // Only the name, once chosen — not "name — id" or the raw row.
        input.value = option.textContent;
        // Anything listening to the select (a dependent field, a reload)
        // hears the same event it would from a real selection.
        dispatchUserEvent(select, "change");
        close();
    }

    // What is compared, on both sides (2.25.1): Latin digits, no case, no
    // grouping or spaces. An option reads «INV-000042 — مانده ۷۳۰،۲۲۴،۰۰۰»
    // — Latin in the number, Persian and grouped in the amount — so a
    // raw substring match found neither «۴۲» nor «730224000».
    const searchKey = (text) => toLatinDigits(String(text)).toLowerCase().replace(/[،,٬\s]/g, "");
    const matching = (term) => {
        const needle = searchKey(term);
        return options().filter((option) => searchKey(option.textContent).includes(needle));
    };
    // `data-searchable-limit="0"` lists every match; the default keeps a
    // long customer book from drawing thousands of rows on focus.
    const limit = Number(select.dataset.searchableLimit ?? 50) || Infinity;

    function render(term) {
        const matches = matching(term);
        list.replaceChildren();
        if (!matches.length) {
            const empty = document.createElement("li");
            empty.className = "searchable-select-empty";
            // «در حال دریافت…» only while nothing has arrived yet. A list
            // that loaded empty says so — in its own words when the page
            // gave it some (`data-searchable-empty`) — instead of looking
            // as if it were still loading forever.
            empty.textContent = options().length
                ? "چیزی پیدا نشد."
                : (select.dataset.searchableEmpty || "در حال دریافت…");
            list.append(empty);
        } else {
            if (matches.length > limit) {
                const more = document.createElement("li");
                more.className = "searchable-select-empty";
                more.textContent = `${toPersianDigits(String(matches.length - limit))} مورد دیگر؛ برای یافتن، بنویسید.`;
                list.append(more);
            }
            matches.slice(0, limit).forEach((option, index) => {
                const row = document.createElement("li");
                row.textContent = option.textContent;
                row.setAttribute("role", "option");
                row.setAttribute("aria-selected", String(index === active));
                // `mousedown`, not `click`: the input's `blur` fires first
                // and would close the list before a click ever landed.
                row.addEventListener("mousedown", (event) => {
                    event.preventDefault();
                    choose(option);
                });
                list.append(row);
            });
        }
        list.hidden = false;
        input.setAttribute("aria-expanded", "true");
    }

    input.addEventListener("input", () => {
        // Typing after a choice means the choice is being changed, so the
        // stale value must not survive into the submission.
        select.value = "";
        active = -1;
        render(input.value);
    });
    input.addEventListener("focus", () => render(input.value));
    input.addEventListener("blur", () => window.setTimeout(close, 120));

    input.addEventListener("keydown", (event) => {
        const rows = Array.from(list.querySelectorAll("li[role='option']"));
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            if (list.hidden) render(input.value);
            active += event.key === "ArrowDown" ? 1 : -1;
            if (active < 0) active = rows.length - 1;
            if (active >= rows.length) active = 0;
            rows.forEach((row, index) => {
                row.setAttribute("aria-selected", String(index === active));
                if (index === active) row.scrollIntoView({block: "nearest"});
            });
        } else if (event.key === "Enter") {
            if (!list.hidden && rows[active]) {
                event.preventDefault();
                const matches = matching(input.value);
                if (matches[active]) choose(matches[active]);
            }
        } else if (event.key === "Escape") {
            close();
        }
    });

    // A value already on the select (a preselected party) shows as its name.
    const preselected = select.selectedOptions[0];
    if (preselected && preselected.value) input.value = preselected.textContent;
}

export function setupSearchableSelects(root = document) {
    root.querySelectorAll("[data-searchable-select]").forEach((block) => {
        if (block.dataset.searchableBound === "1") return;
        block.dataset.searchableBound = "1";
        setupSearchableSelect(block);
    });
}

export async function loadWarehouseOptions(select, emptyLabel) {
    if (!select) return [];
    const rows = await loadAllPages("/api/v1/warehouses/?is_active=true&ordering=name");
    fillSelect(select, rows, (row) => row.name, emptyLabel);
    return rows;
}
