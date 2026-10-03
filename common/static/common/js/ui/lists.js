import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {clearMessages, globalMessage, showError} from "dolphin/core/messages.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {LIVE_KINDS, onRealtime} from "dolphin/ui/realtime.js";
import {pageRangeLabel} from "dolphin/ui/table.js";

export async function loadAllPages(url, limit = 20) {
    const rows = [];
    let next = url;
    let pages = 0;
    while (next && pages < limit) {
        const data = await apiRequest(next);
        rows.push(...data.results);
        next = data.next;
        pages += 1;
    }
    if (next) throw new Error("نتایج بیش از حد مجاز این فرم است.");
    return rows;
}

export function fillSelect(select, rows, label, emptyLabel) {
    const options = [];
    if (emptyLabel !== null) {
        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = emptyLabel;
        options.push(empty);
    }
    rows.forEach((row) => {
        const option = document.createElement("option");
        option.value = String(row.id);
        option.textContent = label(row);
        options.push(option);
    });
    select.replaceChildren(...options);
}

/**
 * Row selection + real, bulk deletion for one `setupPagedList` table.
 *
 * 2026-09-02: every list page gets a checkbox column and a Delete
 * action, but only for a Platform Admin — `common.ui_views.ActiveCrmView`
 * sets `can_hard_delete` once for every page, and each list template
 * renders this whole block (the header checkbox, the selected-count
 * toolbar) only under `{% if can_hard_delete %}`. That template
 * condition is the only gate this function reads: if the checkbox column
 * is not in the DOM, nothing here does anything — no role is read in
 * JavaScript, and the actual boundary is `common.viewsets.HardDeleteMixin`
 * on the server regardless of what got rendered.
 *
 * `key` doubles as the REST resource name for every page that uses this
 * (`/api/v1/customers/`, `/api/v1/leads/`, …), so the bulk-delete
 * endpoint is derived from it rather than threaded through every one of
 * `setupPagedList`'s dozen call sites.
 */
/**
 * The rows just deleted slide out and fade before the list reloads, so the
 * removal is seen rather than the table silently changing. Skipped for users
 * who ask for reduced motion.
 */
async function playRemoval(body, deletedIds) {
    if (!deletedIds?.length || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const ids = new Set(deletedIds.map(String));
    const rows = Array.from(body.querySelectorAll("[data-row-select]"))
        .filter((box) => ids.has(box.dataset.rowSelect))
        .map((box) => box.closest("tr"))
        .filter(Boolean);
    rows.forEach((row) => row.classList.add("is-removing"));
    if (rows.length) await new Promise((resolve) => setTimeout(resolve, 320));
}

export function setupRowSelection({key, body, reload}) {
    const selectAll = document.querySelector(`[data-${key}-select="all"]`);
    if (!selectAll) return {decorateRow: (item, row) => row, resetSelection() {}};
    const toolbar = document.querySelector(`[data-${key}-toolbar="selected"]`);
    const countNode = document.querySelector(`[data-${key}-select="selected_count"]`);
    const deleteButton = document.querySelector(`[data-${key}-select="delete_selected"]`);
    let selected = new Set();

    function resetSelection() {
        selected = new Set();
        updateToolbar();
    }

    function updateToolbar() {
        const boxes = Array.from(body.querySelectorAll("[data-row-select]"));
        if (toolbar) toolbar.hidden = selected.size === 0;
        if (countNode) countNode.textContent = toPersianDigits(String(selected.size));
        const shown = boxes.filter((box) => box.checked).length;
        selectAll.checked = boxes.length > 0 && shown === boxes.length;
        selectAll.indeterminate = shown > 0 && shown < boxes.length;
    }

    selectAll.addEventListener("change", () => {
        const boxes = Array.from(body.querySelectorAll("[data-row-select]"));
        selected = new Set(selectAll.checked ? boxes.map((box) => Number(box.dataset.rowSelect)) : []);
        boxes.forEach((box) => { box.checked = selectAll.checked; });
        updateToolbar();
    });

    deleteButton?.addEventListener("click", async () => {
        const ids = Array.from(selected);
        if (!ids.length) return;
        const count = toPersianDigits(String(ids.length));
        // Spelled out every time, not just "مطمئنید؟": this is the one
        // control in the panel that does not deactivate — it is asked
        // for by name (nothing here should surprise the admin clicking
        // it), so the warning names the alternative right where the
        // decision is made rather than only in documentation.
        if (!await confirmDialog(
            `${count} مورد برای همیشه حذف شود؟ این کار قابل بازگشت نیست. رکوردی که سابقهٔ دیگری به آن وابسته است حذف نخواهد شد. اگر مطمئن نیستید، به‌جای حذف، از غیرفعال‌سازی در همان صفحهٔ رکورد استفاده کنید.`
        )) return;
        deleteButton.disabled = true;
        try {
            const result = await apiRequest(`/api/v1/${key}/bulk-delete/`, {method: "POST", body: {ids}});
            const deletedCount = result.deleted?.length || 0;
            const blockedCount = (result.protected?.length || 0) + (result.denied?.length || 0);
            const parts = [];
            if (deletedCount) parts.push(`${toPersianDigits(String(deletedCount))} مورد حذف شد`);
            if (result.protected?.length) parts.push(`${toPersianDigits(String(result.protected.length))} مورد سابقهٔ وابسته داشت و حذف نشد`);
            if (result.denied?.length) parts.push(`${toPersianDigits(String(result.denied.length))} مورد مجاز به حذف نبود`);
            resetSelection();
            await playRemoval(body, result.deleted);
            // `reload()` starts with `clearMessages()` (same as every
            // other `load()` in this file) — called first so it cannot
            // erase the very message it is about to show.
            await reload();
            globalMessage(parts.join(" — ") || "موردی حذف نشد.", deletedCount > 0 && blockedCount === 0);
        } catch (error) {
            showError(error);
        } finally {
            deleteButton.disabled = false;
        }
    });

    function decorateRow(item, row) {
        const cell = document.createElement("td");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "form-check-input";
        checkbox.dataset.rowSelect = String(item.id);
        checkbox.setAttribute("aria-label", "انتخاب ردیف");
        // A row redrawn after a refresh keeps the choice the reader already made.
        checkbox.checked = selected.has(item.id);
        checkbox.addEventListener("change", () => {
            if (checkbox.checked) selected.add(item.id); else selected.delete(item.id);
            updateToolbar();
        });
        cell.appendChild(checkbox);
        row.insertBefore(cell, row.firstChild);
        return row;
    }

    return {decorateRow, resetSelection};
}

/**
 * Wires one search input to reload live, in place, as the reader types —
 * product-owner decision 2026-09-09: every list search goes live, no
 * "اعمال" button needed for the search term itself (the field's own
 * `endpoint()` reads its `.value` fresh on every call, so nothing here
 * needs to know what the field is *for*).
 *
 * Debounced (350ms) so a fast typist does not fire a request per
 * keystroke; Enter bypasses the debounce and searches immediately, since
 * a reader who pressed it is explicitly done typing. `input`, not
 * `keyup`: also fires on paste and on the field's own native "×" clear
 * button, neither of which is a keystroke.
 */
export function bindLiveSearch(input, onSearch) {
    if (!input) return;
    let timer;
    input.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(onSearch, 350);
    });
    input.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        clearTimeout(timer);
        onSearch();
    });
}

export function setupPagedList({key, form, search, endpoint, renderRow}) {
    const loading = document.getElementById(`${key}-loading`);
    if (!loading) return null;
    const empty = document.getElementById(`${key}-empty`);
    const wrap = document.getElementById(`${key}-table-wrap`);
    const body = document.getElementById(`${key}-table-body`);
    const pagination = document.getElementById(`${key}-pagination`);
    const previous = document.getElementById(`${key}-prev`);
    const next = document.getElementById(`${key}-next`);
    let currentPage = 1;
    const selection = setupRowSelection({key, body, reload: () => load(currentPage)});

    async function load(page = 1, {quiet = false} = {}) {
        // A live refresh (`quiet`) swaps the rows in place: no spinner, no
        // cleared message, the selection kept — and a failure is not shown,
        // because nobody asked for it.
        if (!quiet) {
            loading.hidden = false;
            empty.hidden = true;
            wrap.hidden = true;
            pagination.hidden = true;
            clearMessages();
            selection.resetSelection();
        }
        try {
            const data = await apiRequest(endpoint(page));
            if (quiet) { empty.hidden = true; wrap.hidden = true; }
            body.replaceChildren(...data.results.map((item) => selection.decorateRow(item, renderRow(item))));
            loading.hidden = true;
            if (!data.results.length) { empty.hidden = false; return; }
            wrap.hidden = false;
            currentPage = page;
            previous.disabled = !data.previous;
            next.disabled = !data.next;
            document.getElementById(`${key}-page-label`).textContent = pageRangeLabel(data, page);
            pagination.hidden = !data.previous && !data.next;
        } catch (error) {
            if (quiet) return;
            loading.hidden = true;
            showError(error);
        }
    }
    // Live updates (2.38.0): the list re-reads its current page when a record of
    // its kind changes, through the same endpoint and scope as any other load.
    const liveKinds = LIVE_KINDS[key];
    if (liveKinds) onRealtime(liveKinds, () => load(currentPage, {quiet: true}));
    // A paged list embedded in a detail page (payment allocations, ledger
    // entries) has no filter form of its own; the caller passes null.
    form?.addEventListener("submit", (event) => { event.preventDefault(); load(1); });
    // The search box lives outside `form` now (`card-title`, not the
    // filter panel) and reloads live — see `bindLiveSearch`.
    bindLiveSearch(search, () => load(1));
    previous.addEventListener("click", () => load(currentPage - 1));
    next.addEventListener("click", () => load(currentPage + 1));
    return {load};
}
