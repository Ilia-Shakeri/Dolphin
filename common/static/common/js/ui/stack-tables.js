/**
 * List tables as cards on a phone (2.40.36).
 *
 * Until now a list table kept a 40rem minimum width on a phone and scrolled
 * sideways inside its card, and the row's first column — usually its name or
 * number — was the only thing in view. Each row now becomes a card of
 * «label: value» lines below 576px, the way the postal workspace already lists
 * its shipments; the table itself is unchanged, so every list module, its
 * selection, sorting and actions keep working as they are.
 *
 * Each cell is given the text of its column's header (`data-label`), which the
 * phone stylesheet prints before the value. Rows are labelled whenever a list
 * draws new ones, so paging, filtering and live refreshes are covered.
 */

const STACKED = "dolphin-stack";

function headersOf(table) {
    const head = table.tHead && table.tHead.rows[table.tHead.rows.length - 1];
    return head ? Array.from(head.cells).map((cell) => cell.textContent.trim()) : [];
}

function labelRows(table) {
    const headers = headersOf(table);
    if (headers.length < 3) return;
    table.classList.add(STACKED);
    Array.from(table.tBodies).forEach((body) => {
        Array.from(body.rows).forEach((row) => {
            let column = 0;
            Array.from(row.cells).forEach((cell) => {
                // A cell spanning the row (an empty-state line) is not a field.
                if (cell.colSpan > 1) { cell.dataset.stackFull = ""; column += cell.colSpan; return; }
                const label = headers[column] || "";
                if (cell.dataset.label !== label) cell.dataset.label = label;
                column += 1;
            });
        });
    });
}

export function setupStackedTables(root = document.getElementById("main-content")) {
    if (!root) return;
    const tables = () => root.querySelectorAll(".table-responsive > table.table");
    tables().forEach(labelRows);
    let pending = false;
    new MutationObserver((mutations) => {
        if (pending || !mutations.some((mutation) => mutation.addedNodes.length)) return;
        pending = true;
        requestAnimationFrame(() => {
            pending = false;
            tables().forEach(labelRows);
        });
    }).observe(root, {childList: true, subtree: true});
}
