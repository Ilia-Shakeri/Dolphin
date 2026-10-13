

/** The editor's starting state rendered into the page itself
 * (`dashboard-layout-state`, home.html), or `null` on a deployment that
 * does not offer personal arrangement at all. */
export function dashboardLayoutState() {
    const node = document.getElementById("dashboard-layout-state");
    if (!node) return null;
    try {
        return JSON.parse(node.textContent);
    } catch (error) {
        return null;
    }
}
/**
 * The dashboard's cell grid, as numbers (2.38.2).
 *
 * Twelve columns and rows of half a rem, no grid gap — a box keeps its own
 * margin, so two boxes are a rem apart and a box is as tall as its content to
 * within half a rem. A box has a size in cells and, once placed by hand, a
 * position in cells (`--dashboard-x` / `--dashboard-y`, both from 1, counted
 * from the grid's start corner so the same numbers are right on an RTL and an
 * LTR page). Positions apply on a wide screen only; below `xl` the boxes flow
 * in order, so a phone never shows a layout that needs a desktop's width.
 */
export const WIDE_GRID = window.matchMedia("(min-width: 1200px)");
export const GRID_COLUMNS = 12;
/** The most rows a box is fitted to (`ROW_STEPS`' last step, dashboard_layout.py). */
const MAX_FIT_ROWS = 400;
/** The default dashboard's bands, top to bottom: what a reader scans first. */
export const WIDGET_BANDS = {tile: 0, kpi: 1, gauge: 2, trend: 3, breakdown: 3, panel: 4, agent_share: 5, performance: 6};
/** The widths the server knows (`WIDGET_SIZES`), in columns. */
const SPAN_STEPS = [3, 4, 6, 8, 9, 12];
export const SIZE_FOR_SPAN = {3: "quarter", 4: "third", 6: "half", 8: "two_thirds", 9: "three_quarters", 12: "full"};

function setBoxSpan(column, span) {
    column.className = column.className.replace(/dashboard-span-\d+/, `dashboard-span-${span}`);
}

/**
 * The default dashboard (2.40.35): boxes in shelves. Each shelf is one row of
 * boxes from one band, as many as fit across; a shelf that does not fill the
 * row shares the room out (equal boxes split it evenly, otherwise the last box
 * takes the rest), and every box on a shelf is as tall as the tallest — no
 * ragged bottoms, no holes. Run on every fit until the reader arranges the
 * page themselves; their first save keeps exactly this as their own.
 */
function shelfLayout(host, rows) {
    let shelf = [];
    let used = 0;
    let band = null;
    let y = 1;
    const close = () => {
        if (!shelf.length) return;
        const room = GRID_COLUMNS - used;
        if (room > 0) {
            const spans = shelf.map(boxSpan);
            if (spans.every((span) => span === spans[0]) && GRID_COLUMNS % shelf.length === 0) {
                shelf.forEach((column) => setBoxSpan(column, GRID_COLUMNS / shelf.length));
            } else {
                const last = shelf[shelf.length - 1];
                if (SPAN_STEPS.includes(boxSpan(last) + room)) setBoxSpan(last, boxSpan(last) + room);
            }
        }
        const height = Math.max(...shelf.map((column) => rows.get(column)));
        let x = 1;
        shelf.forEach((column) => {
            setBoxSpot(column, x, y);
            column.style.setProperty("--dashboard-rows", String(height));
            x += boxSpan(column);
        });
        y += height;
        shelf = [];
        used = 0;
    };
    placedBoxes(host).forEach((column) => {
        const own = Number(column.dataset.band ?? 9);
        const span = Math.min(boxSpan(column), GRID_COLUMNS);
        if (shelf.length && (own !== band || used + span > GRID_COLUMNS)) close();
        band = own;
        shelf.push(column);
        used += span;
    });
    close();
}

export function boxSpan(column) {
    const match = /dashboard-span-(\d+)/.exec(column.className);
    return match ? Number(match[1]) : 3;
}

export function boxRows(column) {
    return Number(column.style.getPropertyValue("--dashboard-rows")) || 1;
}

export function boxSpot(column) {
    const x = Number(column.style.getPropertyValue("--dashboard-x"));
    const y = Number(column.style.getPropertyValue("--dashboard-y"));
    return x && y ? {x, y} : null;
}

export function setBoxSpot(column, x, y) {
    column.style.setProperty("--dashboard-x", String(x));
    column.style.setProperty("--dashboard-y", String(y));
}

export function boxRect(column) {
    const spot = boxSpot(column);
    return spot ? {x: spot.x, y: spot.y, w: boxSpan(column), h: boxRows(column)} : null;
}

export function rectsOverlap(a, b) {
    return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

export function placedBoxes(host) {
    return Array.from(host.children).filter((node) => node.dataset && node.dataset.widgetKey && !node.hidden);
}

/** What the grid is made of, in pixels. */
export function gridMetrics(host) {
    const style = getComputedStyle(host);
    const rect = host.getBoundingClientRect();
    const row = parseFloat(style.gridAutoRows) || 8;
    return {rect, row, col: rect.width / GRID_COLUMNS, rtl: style.direction === "rtl"};
}

/** Pin every box that is still placed automatically to where it is drawn now,
 * so each has numbers to compare. Only on a wide screen. */
export function freezeBoxes(host) {
    if (!WIDE_GRID.matches) return;
    const metrics = gridMetrics(host);
    placedBoxes(host).forEach((column) => {
        if (boxSpot(column)) return;
        const rect = column.getBoundingClientRect();
        const start = metrics.rtl ? metrics.rect.right - rect.right : rect.left - metrics.rect.left;
        const x = Math.min(GRID_COLUMNS - boxSpan(column) + 1, Math.max(1, Math.round(start / metrics.col) + 1));
        const y = Math.max(1, Math.round((rect.top - metrics.rect.top) / metrics.row) + 1);
        setBoxSpot(column, x, y);
    });
}

/** Whether `column` sits on another box's cells. */
export function collidesWithOthers(host, column, rect = boxRect(column)) {
    if (!rect) return false;
    return placedBoxes(host).some((other) => {
        if (other === column) return false;
        const otherRect = boxRect(other);
        return otherRect && rectsOverlap(rect, otherRect);
    });
}

/** After a box grew (content, a resize, a new font), push down whatever it now
 * sits on, top to bottom, so nothing is ever drawn over anything else. */
function resolveOverlaps(host) {
    if (!WIDE_GRID.matches) return;
    const items = placedBoxes(host).filter((column) => boxSpot(column))
        .sort((a, b) => boxSpot(a).y - boxSpot(b).y || boxSpot(a).x - boxSpot(b).x);
    const settled = [];
    items.forEach((column) => {
        let rect = boxRect(column);
        let clash = settled.find((other) => rectsOverlap(rect, other));
        while (clash) {
            rect = {...rect, y: clash.y + clash.h};
            clash = settled.find((other) => rectsOverlap(rect, other));
        }
        if (rect.y !== boxSpot(column).y) setBoxSpot(column, rect.x, rect.y);
        settled.push(rect);
    });
}

/** Put `pinned` where it is and push every box it now sits on — and every
 * box those then sit on — straight down (2.40.2, product-owner decision: a
 * drop never lands on a "nearest free place" the reader did not choose). */
export function pushDownAround(host, pinned) {
    if (!WIDE_GRID.matches) return;
    const settled = [boxRect(pinned)];
    placedBoxes(host).filter((column) => column !== pinned && boxSpot(column))
        .sort((a, b) => boxSpot(a).y - boxSpot(b).y || boxSpot(a).x - boxSpot(b).x)
        .forEach((column) => {
            let rect = boxRect(column);
            let clash = settled.find((other) => rectsOverlap(rect, other));
            while (clash) {
                rect = {...rect, y: clash.y + clash.h};
                clash = settled.find((other) => rectsOverlap(rect, other));
            }
            if (rect.y !== boxSpot(column).y) setBoxSpot(column, rect.x, rect.y);
            settled.push(rect);
        });
}

/** «مرتب‌سازی»: lift every box as high as it goes without touching another,
 * top to bottom, keeping its column. The only way the grid closes its gaps —
 * a drop never moves anything up behind the reader's back. */
export function compactUpward(host) {
    if (!WIDE_GRID.matches) return;
    const settled = [];
    placedBoxes(host).filter((column) => boxSpot(column))
        .sort((a, b) => boxSpot(a).y - boxSpot(b).y || boxSpot(a).x - boxSpot(b).x)
        .forEach((column) => {
            let rect = {...boxRect(column), y: 1};
            let clash = settled.find((other) => rectsOverlap(rect, other));
            while (clash) {
                rect = {...rect, y: clash.y + clash.h};
                clash = settled.find((other) => rectsOverlap(rect, other));
            }
            setBoxSpot(column, rect.x, rect.y);
            settled.push(rect);
        });
}

/**
 * Give every box exactly the rows its content needs — no empty band under it
 * and nothing that scrolls. A box whose height the reader chose keeps it, but
 * never below its content. Measured with the card at its natural height; the
 * smallest number of rows that holds it is set.
 */
export function fitDashboardRows() {
    const hosts = Array.from(document.querySelectorAll("[data-dashboard-grid]"));
    hosts.forEach((host) => {
        const style = getComputedStyle(host);
        const row = parseFloat(style.gridAutoRows) || 8;
        const boxes = placedBoxes(host);
        boxes.forEach((column) => column.classList.add("is-measuring"));
        const needs = boxes.map((column) => {
            const card = column.querySelector(":scope > .card") || column;
            const margin = parseFloat(getComputedStyle(column).marginTop) + parseFloat(getComputedStyle(column).marginBottom);
            return Math.ceil((card.getBoundingClientRect().height + margin) / row);
        });
        boxes.forEach((column) => column.classList.remove("is-measuring"));
        const rows = new Map();
        boxes.forEach((column, index) => {
            const chosen = column.dataset.heightChosen === "1" ? boxRows(column) : 0;
            const floor = Number(column.dataset.minRows) || 6;
            const value = Math.min(MAX_FIT_ROWS, Math.max(floor, needs[index], chosen));
            rows.set(column, value);
            column.style.setProperty("--dashboard-rows", String(value));
        });
        if (host.dataset.tidy && WIDE_GRID.matches) shelfLayout(host, rows);
        else {
            resolveOverlaps(host);
            if (host.dataset.compact && !document.body.classList.contains("dashboard-editing")) compactUpward(host);
        }
    });
}

let fitTimer = null;
export function scheduleFitRows() {
    clearTimeout(fitTimer);
    fitTimer = setTimeout(fitDashboardRows, 120);
}

/**
 * Put one widget's column into the grid at its chosen width.
 *
 * The width is the Bootstrap column classes the server resolved from
 * `WIDGET_SIZES` (common/dashboard_layout.py), so the browser never
 * holds a second copy of that mapping — a size added on the Python side
 * needs no change here.
 */
export function placeDashboardWidget(grid, widget) {
    const column = widget.column;
    column.className = `dashboard-widget ${widget.size || "dashboard-span-3"}`;
    column.dataset.widgetKey = widget.key;
    // How many grid rows the box spans (2.38.1): the reader's choice or the
    // widget's own default, resolved by the server (`height_for`).
    if (widget.height) column.style.setProperty("--dashboard-rows", String(widget.height));
    column.dataset.heightChosen = widget.height_chosen ? "1" : "";
    column.dataset.band = String(WIDGET_BANDS[widget.family] ?? 9);
    const minimum = (dashboardLayoutState()?.minimums || {})[widget.key];
    if (minimum) column.dataset.minRows = String(minimum[1]);
    // The box's accent colour (its top edge and icon tile) is the one its icon wears.
    column.dataset.accent = (widget.data && widget.data.accent) || "primary";
    if (widget.position) setBoxSpot(column, widget.position[0], widget.position[1]);
    grid.appendChild(column);
}
