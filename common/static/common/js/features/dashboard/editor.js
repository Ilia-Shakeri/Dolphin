import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {showError} from "dolphin/core/messages.js";
import {GRID_COLUMNS, SIZE_FOR_SPAN, WIDE_GRID, boxRows, boxSpan, boxSpot, collidesWithOthers, compactUpward, dashboardLayoutState, fitDashboardRows, freezeBoxes, gridMetrics, placedBoxes, pushDownAround, setBoxSpot} from "dolphin/features/dashboard/grid.js";
import {panelCard} from "dolphin/features/dashboard/widget-cards.js";
import {renderGaugeChart, renderMixedChart, renderMultiGaugeChart} from "dolphin/features/dashboard/widget-charts.js";
import {liveCharts, renderDonutChart} from "dolphin/ui/charts.js";

/**
 * One widget's preview for the "افزودن ویجت" dialog, drawn from its own
 * real payload — the same figure the widget shows on the dashboard.
 *
 * Until 2.18.2 every preview here was an invented sample
 * (`DASHBOARD_ADD_WIDGET_META`, with a «نمونه» badge), because the page
 * had no real figure for a widget it had not rendered. The server now
 * sends those (`hidden_available`, `dashboard-tile-catalog`), so a
 * preview is simply the widget, small. `host` must already be in an open
 * dialog: Apex measures a real element's width, and a closed `<dialog>`
 * measures zero — the same rule `placeDashboardWidget` documents for the
 * grid itself.
 */
function renderWidgetPreview(host, entry) {
    const data = entry.data || {};
    if (entry.family === "kpi" || entry.family === "tile") {
        const symbol = document.createElement("span");
        symbol.className = "symbol symbol-40px flex-shrink-0";
        const symbolLabel = document.createElement("span");
        symbolLabel.className = `symbol-label bg-light-${data.accent || "primary"}`;
        const icon = document.createElement("i");
        icon.className = `di-duotone ${data.icon || "di-element-11"} fs-2 text-${data.accent || "primary"}`;
        for (let index = 1; index <= (data.icon_paths || 2); index += 1) {
            icon.appendChild(document.createElement("span")).className = `path${index}`;
        }
        symbolLabel.appendChild(icon);
        symbol.appendChild(symbolLabel);
        const figure = document.createElement("span");
        // Wraps rather than truncates: a month's sales in toman is a
        // long figure, and a preview that hides its own number is not
        // a preview.
        figure.className = "text-gray-900 fw-bolder fs-3 lh-sm text-break";
        figure.textContent = entry.family === "tile"
            ? toPersianDigits(String(data.value ?? 0))
            : (data.display || "—");
        host.append(symbol, figure);
        return;
    }
    if (entry.family === "performance") {
        const icon = document.createElement("i");
        icon.className = "di-duotone di-chart-simple fs-2tx text-primary";
        for (let index = 1; index <= 4; index += 1) icon.appendChild(document.createElement("span")).className = `path${index}`;
        const text = document.createElement("span");
        text.className = "text-gray-700 fs-8";
        text.textContent = data.summary || "";
        host.append(icon, text);
        return;
    }
    if (entry.family === "panel") {
        const wrap = document.createElement("div");
        wrap.className = "w-100";
        wrap.appendChild(panelCard({...data, url: null}).querySelector(".card-body"));
        host.appendChild(wrap);
        return;
    }
    const chart = document.createElement("div");
    chart.className = "dashboard-add-widget-chart";
    const empty = document.createElement("p");
    empty.className = "text-muted fs-8 mb-0";
    empty.textContent = "هنوز داده‌ای برای این ویجت نیست.";
    empty.hidden = true;
    host.append(chart, empty);
    if (entry.family === "gauge") {
        renderGaugeChart(chart, empty, data.value, {accent: data.accent, label: data.label});
    } else if (entry.family === "trend") {
        renderMixedChart(chart, empty, data.points || [], data.counts || [], {seriesNames: ["مبلغ فروش", "تعداد فروش"]});
    } else if (entry.family === "breakdown") {
        renderDonutChart(chart, empty, data.items || []);
    } else if (entry.family === "agent_share") {
        renderMultiGaugeChart(chart, empty, data.items || []);
    }
}

/**
 * In-place dashboard customisation: drag to reorder, resize from a
 * corner, a hide control on each box, and one "back to the default".
 *
 * Replaces the deployment-wide settings page retired in 2.8.0 (product
 * owner: «صفحهٔ چیدمان داشبورد را حذف کن و خود داشبورد را قابل
 * شخصی‌سازی کن»). What it saves is this reader's own overlay, through
 * `/api/v1/dashboard-layout/` — which takes no user parameter, so no
 * amount of tampering here reaches anybody else's arrangement.
 *
 * Reordering uses the platform's own drag-and-drop rather than a new
 * dependency: jKanban, the one drag library this product already ships,
 * is a board of columns and lists, not a responsive grid, and adapting
 * it here would be more code than `dragstart`/`dragover`/`drop`.
 *
 * 2.11.0 widened it in three ways the product owner asked for on
 * 2026-09-20. It now edits *every* grid on the page marked
 * `[data-dashboard-grid]` — the capability tiles at the top as well as
 * the insight widgets — rather than only the one it was handed. The
 * six-dot handle is gone and a box is dragged from anywhere on itself.
 * And the size `<select>` became a corner grip that is dragged, which
 * is what "resize" means everywhere else on a screen.
 */
export function setupDashboardEditor({grid, widgets, layout, hiddenAvailable}, {refresh}) {
    const bar = document.getElementById("dashboard-editor-bar");
    const toggle = document.getElementById("dashboard-edit-toggle");
    const done = document.getElementById("dashboard-edit-done");
    const reset = document.getElementById("dashboard-edit-reset");
    const hint = document.getElementById("dashboard-edit-hint");
    const addWidgetOpen = document.getElementById("dashboard-add-widget-open");
    const addWidgetDialog = document.getElementById("dashboard-add-widget-dialog");
    const addWidgetGrid = document.getElementById("dashboard-add-widget-grid");
    const addWidgetEmpty = document.getElementById("dashboard-add-widget-empty");
    const addWidgetPlaced = document.getElementById("dashboard-add-widget-placed");
    if (!bar || !toggle || !grid) return;

    // Every editable grid on the page, in document order. `grid` is the
    // insight one and is always among them; the capability tiles declare
    // themselves the same way, and a page that ever grows a third row
    // needs one attribute rather than a change here.
    const grids = Array.from(document.querySelectorAll("[data-dashboard-grid]"));
    if (!grids.includes(grid)) grids.push(grid);

    bar.hidden = false;
    let editing = false;
    let sizes = {...(layout.sizes || {})};
    let heights = {...(layout.heights || {})};
    // The steps a border drag snaps to, rendered into the page with the
    // rest of the editor's state (`dashboard-layout-state`) since 2.18.4.
    const pageState = dashboardLayoutState() || {};
    let sizeChoices = pageState.size_choices || [];
    const heightChoices = pageState.height_choices || [];
    // The smallest box each widget reads at (2.40.2, `WIDGET_MIN_SIZES` /
    // `WIDGET_MIN_ROWS`); the server raises anything smaller as well.
    const minimums = pageState.minimums || {};
    // Arranging needs the twelve-column grid; on a phone the boxes are one
    // column in saved order and there is nothing to place (2.40.2).
    const narrowScreen = window.matchMedia("(max-width: 767.98px)");
    const narrowNote = document.getElementById("dashboard-edit-narrow");
    // Changes are a draft until «ذخیره» (2.40.2): Escape or «انصراف»
    // throws the draft away, so trying an arrangement costs nothing.
    let draft = null;
    const saveButton = document.getElementById("dashboard-edit-done");
    const cancelButton = document.getElementById("dashboard-edit-cancel");
    const compactButton = document.getElementById("dashboard-edit-compact");
    // Only what this reader hid themselves can be put back. A widget
    // this deployment's default hides never reached the payload, so it
    // is not in `widgets` and cannot be listed here either.
    let hidden = (layout.hidden || []).filter((key) => !(layout.locked_hidden || []).includes(key));
    // Opt-in widgets (2.40.35, `OPT_IN_WIDGETS`) are on the page only while
    // they are in this list; adding or removing one edits it.
    const optIn = new Set(layout.opt_in || pageState.opt_in || []);
    let shown = [...(layout.shown || pageState.shown || [])];
    // The default page arranges itself (`shelfLayout`) until the reader
    // arranges it; while editing it holds still.
    const tidyHosts = grids.filter((host) => host.dataset.tidy);
    let dragged = null;

    /** Every box on the page, both grids, in the order they are drawn. */
    function allBoxes() {
        return grids.flatMap((host) => Array.from(host.children));
    }

    /** What a box calls itself in the hidden bar and in its controls'
     * accessible names. */
    function boxLabel(key) {
        const known = widgets.get(key);
        if (known) return known.label;
        const listed = catalogLabel(key);
        if (listed) return listed;
        const column = boxColumn(key);
        return (column && column.dataset.widgetLabel) || key;
    }

    function currentOrder() {
        // One list across both grids. The server orders each row against
        // the same array and ignores the keys that are not in it
        // (`_ordered`), so the two rows never need separate orders.
        return allBoxes()
            .map((column) => column.dataset.widgetKey)
            .filter(Boolean);
    }

    function save(body) {
        // While editing, a change only joins the draft; `flush` sends it.
        // `widget_positions` merges on the server, so the draft merges too.
        draft = {
            ...(draft || {}),
            ...body,
            ...(body.widget_positions ? {widget_positions: {...((draft || {}).widget_positions || {}), ...body.widget_positions}} : {}),
        };
        if (saveButton) saveButton.disabled = false;
        return Promise.resolve();
    }

    async function flush() {
        if (!draft) return true;
        const body = draft;
        try {
            const saved = await apiRequest("/api/v1/dashboard-layout/", {method: "POST", body});
            draft = null;
            // Only shown or hidden boxes, nothing placed: the page is still the
            // default and goes on arranging itself; once a place is saved, the
            // reader's arrangement is what stands.
            if (body.widget_positions) tidyHosts.length = 0;
            else tidyHosts.forEach((host) => { host.dataset.tidy = "1"; });
            if (saved && Array.isArray(saved.sizes) && saved.sizes.length) sizeChoices = saved.sizes;
            if (reset) reset.hidden = !editing || !saved || !saved.is_customised;
            return true;
        } catch (error) {
            // The draft stays on screen and unsent, so «ذخیره» can be tried
            // again; nothing snaps back under the reader.
            showError(error);
            return false;
        }
    }

    function belowMinimumWidth(key, token) {
        const minimum = minimums[key] && minimums[key][0];
        if (!minimum) return false;
        const steps = sizeChoices.map((choice) => choice.value);
        return steps.indexOf(token) < steps.indexOf(minimum);
    }

    function minimumRows(key) {
        return (minimums[key] && minimums[key][1]) || 6;
    }

    /** A short pulse on the box and a spoken note: this is as small as it goes. */
    function flagMinimum(column) {
        column.classList.remove("at-minimum");
        void column.offsetWidth;
        column.classList.add("at-minimum");
        if (hint) hint.querySelector("[data-edit-status]")?.replaceChildren("این باکس کوچک‌تر از این خوانا نیست.");
    }

    // "افزودن ویجت" — every widget this reader can have, each with a
    // preview of its own real figure, in two groups: the ones they hid
    // (addable) and the ones already on the dashboard (removable).
    // Product owner, 2026-09-27: «در مودال افزودن ویجت باید همهٔ
    // ویجت‌های موجود نمایش داده شود و پیش‌نمایش داشته باشد». Until
    // 2.18.2 it listed only hidden widgets, from the static catalog,
    // over invented samples — including widgets this deployment or role
    // would never render, which put back a box that then never appeared.
    //
    // Built at most once per page load (`addWidgetBuilt`), the first time
    // the reader opens it, and after that each card only moves between
    // the two groups — a chart is mounted once, never per open.
    // `addWidgetAdded` records that a widget absent from the page came
    // back, the one case a reload is needed for (see the `close` handler).
    let addWidgetBuilt = false;
    let addWidgetAdded = false;
    const addWidgetCards = new Map();

    /** Every widget this reader may have, keyed: the tiles row (rendered
     * into the page, hidden ones included), the insight parts on screen,
     * and the insight parts they hid (`hidden_available`). Deployment-
     * hidden widgets are in none of the three sources. */
    function widgetCatalog() {
        const entries = new Map();
        let tiles = [];
        try {
            const node = document.getElementById("dashboard-tile-catalog");
            tiles = node ? JSON.parse(node.textContent) : [];
        } catch (error) {
            tiles = [];
        }
        tiles.forEach((tile) => entries.set(tile.key, {key: tile.key, family: "tile", label: tile.label, data: tile}));
        widgets.forEach((widget) => {
            if (widget.family) entries.set(widget.key, {key: widget.key, family: widget.family, label: widget.label, data: widget.data});
        });
        (hiddenAvailable || []).forEach((part) => {
            entries.set(part.key, {key: part.key, family: part.family, label: part.label || part.title, data: part});
        });
        return entries;
    }
    const catalog = widgetCatalog();

    /** A box's catalog label — the one source that also knows boxes
     * hidden before the page loaded, which are not in the DOM to ask
     * (until 2.18.2 those showed their raw key, e.g. `capability:audit.all`). */
    function catalogLabel(key) {
        const entry = catalog.get(key);
        return entry ? entry.label : null;
    }

    function boxColumn(key) {
        return grids.map((host) => host.querySelector(`:scope > [data-widget-key="${key}"]`)).find(Boolean) || null;
    }

    function hideWidget(key) {
        if (!hidden.includes(key)) hidden = [...hidden, key];
        const column = boxColumn(key);
        if (column) column.hidden = true;
        refreshAddWidgetGrid();
        if (optIn.has(key)) shown = shown.filter((item) => item !== key);
        return save({hidden_widgets: hidden.filter((item) => !optIn.has(item)), shown_widgets: shown});
    }

    function addBackWidget(key) {
        hidden = hidden.filter((item) => item !== key);
        const column = boxColumn(key);
        // Hidden earlier on this same page: its column (and any chart in
        // it) is still in the DOM, so it simply comes back. Hidden before
        // the page loaded: the page never drew it, so the dialog's close
        // handler reloads to let the server draw it in its saved place.
        if (column) column.hidden = false;
        else addWidgetAdded = true;
        refreshAddWidgetGrid();
        if (optIn.has(key) && !shown.includes(key)) shown = [...shown, key];
        return save({hidden_widgets: hidden.filter((item) => !optIn.has(item)), shown_widgets: shown});
    }

    function buildAddWidgetGrid() {
        if (!addWidgetGrid || addWidgetBuilt) return;
        addWidgetBuilt = true;
        addWidgetGrid.replaceChildren();
        if (addWidgetPlaced) addWidgetPlaced.replaceChildren();
        catalog.forEach((entry) => {
            const card = document.createElement("div");
            card.className = "dashboard-add-widget-card";
            // Not `data-widget-key`: that attribute is how every lookup in
            // this editor finds a box on the dashboard, and the dialog sits
            // before both grids in the document.
            card.dataset.addWidgetKey = entry.key;
            card.dataset.addWidgetFamily = entry.family;
            card.setAttribute("role", "listitem");

            const head = document.createElement("span");
            head.className = "d-flex align-items-center justify-content-between gap-2 w-100";
            const label = document.createElement("span");
            label.className = "fw-semibold fs-7 text-gray-900";
            label.textContent = entry.label;
            const badge = document.createElement("span");
            badge.className = "badge badge-light-success fs-9 flex-shrink-0";
            badge.textContent = "روی داشبورد";
            badge.dataset.addWidgetPlacedBadge = "";
            head.append(label, badge);

            const preview = document.createElement("span");
            preview.className = "dashboard-add-widget-preview";

            const action = document.createElement("button");
            action.type = "button";
            action.className = "btn btn-sm w-100";
            action.dataset.addWidgetAction = entry.key;
            action.addEventListener("click", () => {
                if (hidden.includes(entry.key)) addBackWidget(entry.key);
                else hideWidget(entry.key);
            });

            card.append(head, preview, action);
            addWidgetCards.set(entry.key, {card, label: entry.label});
            refreshCard(entry.key);
            // Mounted after the card is in the (open) dialog — see
            // `renderWidgetPreview`.
            renderWidgetPreview(preview, entry);
        });
    }

    function refreshCard(key) {
        const {card, label} = addWidgetCards.get(key);
        const placed = !hidden.includes(key);
        const target = placed ? addWidgetPlaced : addWidgetGrid;
        if (target && card.parentElement !== target) target.appendChild(card);
        const badge = card.querySelector("[data-add-widget-placed-badge]");
        if (badge) badge.hidden = !placed;
        const action = card.querySelector("[data-add-widget-action]");
        action.classList.toggle("btn-light-primary", !placed);
        action.classList.toggle("btn-light-danger", placed);
        action.innerHTML = placed
            ? '<i class="di-outline di-minus fs-4 me-1"></i>برداشتن از داشبورد'
            : '<i class="di-outline di-plus fs-4 me-1"></i>افزودن به داشبورد';
        action.setAttribute("aria-label", `${placed ? "برداشتن از داشبورد" : "افزودن به داشبورد"}: ${label}`);
    }

    function refreshAddWidgetGrid() {
        if (!addWidgetGrid || !addWidgetBuilt) return;
        addWidgetCards.forEach((_entry, key) => refreshCard(key));
        if (addWidgetEmpty) addWidgetEmpty.classList.toggle("d-none", addWidgetGrid.children.length > 0);
    }

    if (addWidgetOpen && addWidgetDialog) {
        addWidgetDialog.querySelectorAll("[data-close-dialog]")
            .forEach((button) => button.addEventListener("click", () => addWidgetDialog.close()));
        addWidgetOpen.addEventListener("click", () => {
            // Open first, build after: a chart mounted into a closed
            // `<dialog>` (`display: none`, so every descendant computes
            // to zero width) is exactly the "Apex measures a real
            // element's width" trap `placeDashboardWidget` already
            // documents for the real grid.
            addWidgetAdded = false;
            addWidgetDialog.showModal();
            buildAddWidgetGrid();
            refreshAddWidgetGrid();
        });
        addWidgetDialog.addEventListener("close", () => {
            // A widget that was not on the page when it loaded carries
            // real, per-reader data the page never drew — a full reload
            // is the same "ask the server again" the reset button
            // already uses, not a special case.
            if (addWidgetAdded) flush().then((ok) => { if (ok) window.location.reload(); });
        });
    }

    /** Apply a width token to a box on screen and remember it. */
    function applySize(column, key, token) {
        if (belowMinimumWidth(key, token)) { flagMinimum(column); return false; }
        if (sizes[key] === token) return false;
        const classes = (sizeChoices.find((choice) => choice.value === token) || {}).classes;
        if (!classes) return false;
        const before = {sizes, className: column.className, spot: boxSpot(column)};
        sizes = {...sizes, [key]: token};
        const keep = ["editing", "resizing", "dragging"].filter((name) => column.classList.contains(name));
        column.className = ["dashboard-widget", ...keep, classes].join(" ");
        if (WIDE_GRID.matches) {
            const host = column.parentElement;
            freezeBoxes(host);
            const spot = boxSpot(column);
            // A box wider than the room to its end slides back toward the start…
            if (spot && spot.x + boxSpan(column) - 1 > GRID_COLUMNS) setBoxSpot(column, GRID_COLUMNS - boxSpan(column) + 1, spot.y);
            // …and one that would land on a neighbour simply does not grow.
            if (collidesWithOthers(host, column)) {
                sizes = before.sizes;
                column.className = before.className;
                if (before.spot) setBoxSpot(column, before.spot.x, before.spot.y);
                return false;
            }
        }
        return true;
    }

    /** Apply a row-count token to a box on screen and remember it. */
    function applyHeight(column, key, token) {
        if (!token || (heights[key] || null) === token) return false;
        const rows = (heightChoices.find((choice) => choice.value === token) || {}).rows;
        if (!rows) return false;
        if (rows < minimumRows(key)) { flagMinimum(column); return false; }
        const before = {heights, rows: column.style.getPropertyValue("--dashboard-rows")};
        heights = {...heights, [key]: token};
        column.style.setProperty("--dashboard-rows", String(rows));
        column.dataset.heightChosen = "1";
        if (WIDE_GRID.matches) {
            const host = column.parentElement;
            freezeBoxes(host);
            if (collidesWithOthers(host, column)) {
                heights = before.heights;
                column.style.setProperty("--dashboard-rows", before.rows);
                return false;
            }
        }
        fitAllCharts();
        return true;
    }

    /** What to save after a move or a resize: sizes and heights, and — on a
     * wide screen — where every box sits, with its rows kept as chosen so the
     * next paint reproduces exactly this arrangement. */
    function layoutBody() {
        const body = {widget_sizes: sizes, widget_heights: heights};
        if (!WIDE_GRID.matches) return body;
        const positions = {};
        const keptHeights = {...heights};
        const keptSizes = {...sizes};
        grids.forEach((host) => placedBoxes(host).forEach((column) => {
            const key = column.dataset.widgetKey;
            const spot = boxSpot(column);
            if (spot) positions[key] = [spot.x, spot.y];
            keptHeights[key] = `r${boxRows(column)}`;
            column.dataset.heightChosen = "1";
            // The width it is drawn at — on the default page the shelves may
            // have widened it, and a saved place needs its saved width.
            if (SIZE_FOR_SPAN[boxSpan(column)]) keptSizes[key] = SIZE_FOR_SPAN[boxSpan(column)];
        }));
        heights = keptHeights;
        sizes = keptSizes;
        return {widget_sizes: sizes, widget_heights: heights, widget_positions: positions};
    }

    //: How much of the row each width step takes, for snapping a dragged
    //: width to the nearest one the server accepts.
    const WIDTH_SHARES = {quarter: 1 / 4, third: 1 / 3, half: 1 / 2, two_thirds: 2 / 3, three_quarters: 3 / 4, full: 1};

    function widthTokenAt(column, width) {
        const row = column.parentElement.getBoundingClientRect().width || 1;
        const share = width / row;
        let best = sizeChoices[0] && sizeChoices[0].value;
        let distance = Infinity;
        sizeChoices.forEach((choice) => {
            const gap = Math.abs((WIDTH_SHARES[choice.value] ?? 0.25) - share);
            if (gap < distance) { distance = gap; best = choice.value; }
        });
        return best;
    }

    function remPixels() {
        return parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
    }

    /** The nearest row step to `px`, never one too short for what the box
     * has to show — a cell smaller than its content would clip it. */
    function heightTokenAt(px, naturalPx) {
        const rem = remPixels();
        let best = null;
        let distance = Infinity;
        heightChoices.forEach((choice) => {
            const candidate = parseFloat(choice.length) * rem;
            if (candidate < naturalPx - 4) return;
            const gap = Math.abs(candidate - px);
            if (gap < distance) { distance = gap; best = choice.value; }
        });
        // Nothing tall enough: the tallest step is the closest honest answer.
        return best || (heightChoices.length ? heightChoices[heightChoices.length - 1].value : null);
    }

    /** The charts drawn inside one box, as `[element, instance]` pairs.
     * Found through the DOM — every Apex chart draws its own
     * `.apexcharts-canvas` inside the element it was mounted on — because
     * `liveCharts` is a WeakMap and cannot be walked. */
    function chartsIn(column) {
        const found = [];
        column.querySelectorAll(".apexcharts-canvas").forEach((canvas) => {
            const element = canvas.parentElement;
            const instance = element && liveCharts.get(element);
            if (instance && !element.hidden) found.push([element, instance]);
        });
        return found;
    }

    /** How tall a box would be at its content's own height — with its
     * minimum lifted and any chart this editor stretched counted at its
     * original height. */
    function naturalHeight(column) {
        const card = column.querySelector(":scope > .card") || column;
        // The box is a fixed cell now, so what it needs is its height less the
        // room it has to spare (negative when it is already clipping).
        let height = card.getBoundingClientRect().height - (card.querySelector(":scope > .card-body") ? slackIn(column) : 0);
        chartsIn(column).forEach(([element]) => {
            const base = Number(element.dataset.dashboardBaseHeight || 0);
            if (base) height -= Math.max(0, element.offsetHeight - base);
        });
        return height;
    }

    /** A box's main chart — its tallest — with the height it was first
     * drawn at, remembered the first time this sees it. */
    function mainChart(column) {
        const charts = chartsIn(column);
        if (!charts.length || !column.querySelector(":scope > .card")) return null;
        const [element, instance] = charts.reduce((a, b) => (b[0].offsetHeight > a[0].offsetHeight ? b : a));
        // Not drawn yet (Apex finishes a render a tick after it starts):
        // there is no honest base height to remember, so leave it for
        // the next pass rather than remembering zero.
        if (!element.dataset.dashboardBaseHeight && !element.offsetHeight) return null;
        if (!element.dataset.dashboardBaseHeight) {
            element.dataset.dashboardBaseHeight = String(element.offsetHeight);
            // What the container holds beyond the plot Apex was asked
            // for (a legend row drawn outside the SVG), so a target
            // height for the container converts to the one Apex takes.
            const svg = element.querySelector("svg.apexcharts-svg");
            const plot = svg ? svg.getBoundingClientRect().height : element.offsetHeight;
            element.dataset.dashboardChrome = String(Math.max(0, Math.round(element.offsetHeight - plot)));
        }
        return {
            column, element, instance,
            base: Number(element.dataset.dashboardBaseHeight),
            chrome: Number(element.dataset.dashboardChrome || 0),
        };
    }

    /** How much taller a box's body is than what it holds. */
    function slackIn(column) {
        const card = column.querySelector(":scope > .card");
        const body = card.querySelector(":scope > .card-body") || card;
        const bodyStyle = getComputedStyle(body);
        const inner = body.clientHeight - parseFloat(bodyStyle.paddingTop) - parseFloat(bodyStyle.paddingBottom);
        const used = Array.from(body.children).reduce((sum, child) => {
            if (child.hidden) return sum;
            const style = getComputedStyle(child);
            return sum + child.offsetHeight + parseFloat(style.marginTop) + parseFloat(style.marginBottom);
        }, 0);
        return inner - used;
    }

    /**
     * A taller box gives its main chart the room, rather than leaving an
     * empty band under a plot drawn at its old height — so dragging a
     * chart box's bottom border makes the chart itself bigger, and
     * dragging it back makes it smaller again. A chart never drops below
     * the height it was first drawn at.
     *
     * Every box at once, in three passes, because a Bootstrap row
     * stretches each box to the tallest in it: every chart is first held
     * at its original height, *then* every box's spare room is measured
     * (so no box measures against a neighbour's chart that is about to
     * shrink), and only then is each chart redrawn at its new height.
     */
    function fitAllCharts() {
        const charts = allBoxes().filter((column) => !column.hidden).map(mainChart).filter(Boolean);
        charts.forEach((chart) => {
            // Apex pins its own container with an inline `min-height`
            // at the height it last drew, so that has to be held too.
            chart.minHeight = chart.element.style.minHeight;
            chart.element.style.minHeight = `${chart.base}px`;
            chart.element.style.height = `${chart.base}px`;
            chart.element.style.overflow = "hidden";
        });
        charts.forEach((chart) => { chart.target = chart.base + Math.max(0, Math.round(slackIn(chart.column))); });
        charts.forEach((chart) => {
            chart.element.style.minHeight = chart.minHeight;
            chart.element.style.height = "";
            chart.element.style.overflow = "";
            if (Math.abs(chart.target - chart.element.offsetHeight) < 3) return;
            // Apex's container ends up a little taller than the plot it
            // was asked for, and not by the same amount on a first
            // render as on a redraw — so ask, measure, and correct once
            // rather than predict.
            const asked = chart.target - chart.chrome;
            Promise.resolve(chart.instance.updateOptions({chart: {height: asked}}, false, false)).then(() => {
                const miss = chart.target - chart.element.offsetHeight;
                if (Math.abs(miss) >= 3) chart.instance.updateOptions({chart: {height: asked + miss}}, false, false);
            });
        });
    }

    //: The eight places a box can be taken by its border: four edges and
    //: four corners, named in logical terms so the one list is right on
    //: an RTL and an LTR page alike (the cursors live in the panel stylesheet).
    const RESIZE_EDGES = [
        "inline-start", "inline-end", "block-start", "block-end",
        "block-start inline-start", "block-start inline-end",
        "block-end inline-start", "block-end inline-end",
    ];

    //: Widths only mean something where the grid has columns to give:
    //: below the theme's `xl` breakpoint every box is already full width
    //: (or half, on `sm`), so a horizontal drag there would save a width
    //: nobody could see. Heights work at every size.
    const wideLayout = window.matchMedia("(min-width: 1200px)");

    /**
     * Resizing by the box's own border — product owner, 2026-09-27:
     * «این دکمه حذف شود و کاربر با گرفتن لبه‌ها اندازه را تغییر دهد» and
     * «همهٔ باکس‌ها باید از لبه‌ها به‌صورت افقی و عمودی بزرگ و کوچک شوند».
     * Until 2.18.4 a box had one corner button (`di-arrow-two-diagonals`)
     * that changed only its width.
     *
     * Snapped, never free pixels: widths to the steps of the theme's
     * twelve-column grid (`WIDGET_SIZES`), heights to `WIDGET_HEIGHTS` —
     * a box keeps lining up with every other card and still collapses on
     * a phone. Dragged in *visual* terms: whichever physical side the
     * taken edge is on, moving it away from the box grows the box.
     */
    function resizeHandles(column, key) {
        return RESIZE_EDGES.map((edge) => {
            const handle = document.createElement("span");
            handle.className = "dashboard-resize-handle";
            handle.dataset.widgetResize = key;
            handle.dataset.edge = edge;
            handle.setAttribute("aria-hidden", "true");
            handle.addEventListener("pointerdown", (event) => {
                if (event.button !== 0) return;
                event.preventDefault();
                event.stopPropagation();
                const rtl = getComputedStyle(column).direction === "rtl";
                const horizontal = edge.includes("inline-") && wideLayout.matches;
                const vertical = edge.includes("block-");
                // The taken edge is on the physical left when it is the
                // inline-end of an RTL box or the inline-start of an LTR one.
                const onLeft = edge.includes("inline-end") === rtl;
                const fromTop = edge.includes("block-start");
                const startX = event.clientX;
                const startY = event.clientY;
                const startWidth = column.getBoundingClientRect().width;
                const card = column.querySelector(":scope > .card") || column;
                const startHeight = card.getBoundingClientRect().height;
                const natural = vertical ? naturalHeight(column) : 0;
                let changed = false;
                column.classList.add("resizing");
                handle.classList.add("active");
                try { handle.setPointerCapture(event.pointerId); } catch (error) { /* capture is a nicety */ }

                function onMove(moveEvent) {
                    if (horizontal) {
                        const dx = onLeft ? startX - moveEvent.clientX : moveEvent.clientX - startX;
                        const token = widthTokenAt(column, Math.max(60, startWidth + dx));
                        if (token && applySize(column, key, token)) changed = true;
                    }
                    if (vertical) {
                        const dy = fromTop ? startY - moveEvent.clientY : moveEvent.clientY - startY;
                        if (applyHeight(column, key, heightTokenAt(startHeight + dy, natural))) changed = true;
                    }
                }
                function onUp() {
                    document.removeEventListener("pointermove", onMove);
                    document.removeEventListener("pointerup", onUp);
                    document.removeEventListener("pointercancel", onUp);
                    column.classList.remove("resizing");
                    handle.classList.remove("active");
                    if (changed) {
                        fitAllCharts();
                        save(layoutBody());
                    }
                }
                document.addEventListener("pointermove", onMove);
                document.addEventListener("pointerup", onUp);
                document.addEventListener("pointercancel", onUp);
            });
            return handle;
        });
    }

    /**
     * The keyboard's way to the same sizes. The border handles are
     * pointer-only affordances; while editing, the box itself takes focus
     * and the arrow keys step through the same widths and heights the
     * border snaps to — left/right in the visual direction of the page,
     * down for taller.
     */
    function onBoxKeydown(event) {
        const column = event.currentTarget;
        if (event.target !== column) return;
        const key = column.dataset.widgetKey;
        const rtl = getComputedStyle(column).direction === "rtl";
        let handled = false;
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            const steps = sizeChoices.map((choice) => choice.value);
            const current = sizes[key] || widthTokenAt(column, column.getBoundingClientRect().width);
            const at = Math.max(0, steps.indexOf(current));
            const wider = (event.key === "ArrowLeft") === rtl;
            const next = Math.min(steps.length - 1, Math.max(0, at + (wider ? 1 : -1)));
            handled = applySize(column, key, steps[next]);
        } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            const steps = heightChoices.map((choice) => choice.value);
            const natural = naturalHeight(column);
            const rem = remPixels();
            const usable = steps.filter((step) => parseFloat((heightChoices.find((choice) => choice.value === step) || {}).length) * rem >= natural - 4);
            const current = column.style.getPropertyValue("--dashboard-rows");
            const currentToken = (heightChoices.find((choice) => String(choice.rows) === current) || {}).value;
            const at = Math.max(0, usable.indexOf(heights[key] || currentToken));
            const next = Math.min(usable.length - 1, Math.max(0, at + (event.key === "ArrowDown" ? 1 : -1)));
            handled = applyHeight(column, key, usable[next]);
        } else {
            return;
        }
        event.preventDefault();
        if (handled) save(layoutBody());
    }

    function widgetControls(column, key) {
        const controls = document.createElement("div");
        controls.className = "dashboard-widget-controls";
        controls.dataset.widgetControls = key;

        // No drag handle. The whole box is the handle now (product owner:
        // «جابه‌جایی با کل ویجت انجام شود و دستگیرهٔ شش‌نقطه حذف شود») —
        // `column.draggable` was already true, so the six dots were only
        // ever a picture of a thing that was not needed.
        const hide = document.createElement("button");
        hide.type = "button";
        hide.className = "btn btn-icon btn-sm btn-danger dashboard-widget-hide";
        hide.title = "پنهان کردن";
        hide.setAttribute("aria-label", `پنهان کردن ${boxLabel(key)}`);
        hide.innerHTML = '<i class="di-outline di-cross fs-4"></i>';
        hide.addEventListener("click", () => hideWidget(key));
        controls.appendChild(hide);
        return controls;
    }

    /**
     * Every box in the first row is a link (`<a class="card">`, one per
     * capability), and so are the KPI cards below it. A browser starts
     * its own native *link* drag the moment a pressed link moves a few
     * pixels, and that native drag cancels the pointer stream this
     * editor's own drag runs on (`pointercancel`) — which is why the
     * first row could not be rearranged with a real mouse (product
     * owner, 2026-09-27). While editing, every link and image inside a
     * box is marked not-draggable, and restored exactly on the way out.
     */
    function suppressNativeDrag(column) {
        column.querySelectorAll("a[href], img").forEach((node) => {
            if (node.hasAttribute("draggable")) return;
            node.setAttribute("draggable", "false");
            node.dataset.dashboardDragSuppressed = "";
        });
    }

    function restoreNativeDrag(column) {
        column.querySelectorAll("[data-dashboard-drag-suppressed]").forEach((node) => {
            node.removeAttribute("draggable");
            delete node.dataset.dashboardDragSuppressed;
        });
    }

    function enterEditing() {
        allBoxes().forEach((column) => {
            const key = column.dataset.widgetKey;
            if (!key || column.querySelector("[data-widget-controls]")) return;
            column.classList.add("editing");
            suppressNativeDrag(column);
            column.appendChild(widgetControls(column, key));
            column.append(...resizeHandles(column, key));
            column.tabIndex = 0;
            column.setAttribute("role", "group");
            column.setAttribute("aria-label", `${boxLabel(key)} — کلیدهای جهت اندازه را تغییر می‌دهند`);
            column.addEventListener("keydown", onBoxKeydown);
        });
        grids.forEach((host) => host.classList.add("dashboard-widgets-editing"));
    }

    function leaveEditing() {
        allBoxes().forEach((column) => {
            column.classList.remove("editing", "dragging", "resizing");
            column.style.transform = "";
            column.style.zIndex = "";
            restoreNativeDrag(column);
            const controls = column.querySelector("[data-widget-controls]");
            if (controls) controls.remove();
            column.querySelectorAll("[data-widget-resize]").forEach((handle) => handle.remove());
            column.removeAttribute("tabindex");
            column.removeAttribute("role");
            column.removeAttribute("aria-label");
            column.removeEventListener("keydown", onBoxKeydown);
        });
        grids.forEach((host) => host.classList.remove("dashboard-widgets-editing"));
    }

    grids.forEach((host) => {
        bindGridDrag(host);
        // A box is something to arrange while editing, not somewhere to
        // go: releasing a dragged tile over its own link would otherwise
        // navigate away mid-edit. Capture phase, so it runs before any
        // link's own handler.
        host.addEventListener("click", (event) => {
            if (editing && event.target.closest("a[href]")) event.preventDefault();
        }, true);
    });

    /**
     * Dragging a widget, redone 2026-09-21 on Pointer Events instead of
     * HTML5 drag-and-drop (product owner: «کار با ویجت‌ها ... مثل ویجت
     * های apple و اندروید روان و پرکاربرد باشد»).
     *
     * Two real problems with the HTML5 version, not just a look: it
     * never fires on a touch screen at all (`dragstart`/`dragover` are a
     * desktop-mouse-only contract in every mobile browser this panel
     * ships to), and its own drag image — a browser-drawn ghost that
     * trails the pointer with no control over its look — is what made
     * the old picture read as "opacity: 0.45 and hope", not a lifted
     * card. Pointer Events unify mouse, touch and pen behind one API, so
     * the same code now drags on a phone, and the element itself is
     * moved with a CSS transform this code owns end to end.
     *
     * Reordering is *live*, the way a home-screen icon grid moves other
     * icons out from under a finger before it lands: every time the
     * dragged card crosses another one, they swap in the DOM
     * immediately, and every card the swap displaced animates from
     * where it used to be to where it now is (the FLIP technique —
     * First: read the old rect; Last: let the DOM change land; Invert:
     * transform back to where it was; Play: transition to identity).
     * The dragged card itself is excluded from that animation — it is
     * already being moved by the pointer, one frame at a time, and
     * animating it too would fight that.
     */
    function bindGridDrag(host) {
        let grabOffsetX = 0;
        let grabOffsetY = 0;
        let startClientX = 0;
        let startClientY = 0;
        let moved = false;
        // The widget last swapped with, this drag only — see the guard
        // in `onPointerMove` for why it exists.
        let lastSwapTarget = null;
        // Free placement (wide screens): where the box would land, and the
        // outline that shows it.
        let dropSpot = null;
        let hint = null;

        function updateDropHint() {
            const metrics = gridMetrics(host);
            const rect = dragged.getBoundingClientRect();
            const start = metrics.rtl ? metrics.rect.right - rect.right : rect.left - metrics.rect.left;
            const w = boxSpan(dragged);
            const h = boxRows(dragged);
            const x = Math.min(GRID_COLUMNS - w + 1, Math.max(1, Math.round(start / metrics.col) + 1));
            const y = Math.max(1, Math.round((rect.top - metrics.rect.top) / metrics.row) + 1);
            dropSpot = {x, y};
            if (!hint) {
                hint = document.createElement("div");
                hint.className = "dashboard-drop-hint";
                host.appendChild(hint);
            }
            hint.style.gridColumn = `${x} / span ${w}`;
            hint.style.gridRow = `${y} / span ${h}`;
            // Never blocked any more: whatever is there moves down on drop.
            hint.classList.toggle("will-push", collidesWithOthers(host, dragged, {x, y, w, h}));
        }

        /** Re-anchors the dragged card under the pointer at its current
         * grab point, measured against wherever the card's own layout
         * (untransformed) box is right now — which may have just moved,
         * if a swap put it in a different slot. Self-correcting on every
         * call, so it never needs to know how many swaps happened. */
        function followPointer(clientX, clientY) {
            dragged.style.transform = "";
            const rect = dragged.getBoundingClientRect();
            const dx = clientX - grabOffsetX - rect.left;
            const dy = clientY - grabOffsetY - rect.top;
            dragged.style.transform = `translate(${dx}px, ${dy}px)`;
        }

        /** Moves `dragged` into `target`'s slot and slides every other
         * card displaced by that move from its old position to its new
         * one — nothing snaps. */
        function swapWithAnimation(target) {
            const others = Array.from(host.children).filter(
                (el) => el !== dragged && el.dataset && el.dataset.widgetKey,
            );
            const before = new Map(others.map((el) => [el, el.getBoundingClientRect()]));

            const anchor = document.createComment("");
            host.insertBefore(anchor, dragged);
            host.insertBefore(dragged, target);
            host.insertBefore(target, anchor);
            anchor.remove();

            others.forEach((el) => {
                const from = before.get(el);
                const to = el.getBoundingClientRect();
                const dx = from.left - to.left;
                const dy = from.top - to.top;
                if (!dx && !dy) return;
                el.style.transition = "none";
                el.style.transform = `translate(${dx}px, ${dy}px)`;
                // Forces the browser to paint the inverted position
                // before the next line switches the transition back on
                // — without this the two style writes coalesce into one
                // frame and there is nothing to animate from.
                el.getBoundingClientRect();
                el.style.transition = "transform 0.2s ease";
                el.style.transform = "";
            });
        }

        function onPointerMove(event) {
            if (!dragged) return;
            if (!moved) {
                // A few pixels of slack before a press counts as a drag,
                // so a plain click still reads as a click.
                if (Math.abs(event.clientX - startClientX) < 4 && Math.abs(event.clientY - startClientY) < 4) return;
                moved = true;
                dragged.classList.add("dragging");
            }
            event.preventDefault();
            // Excluded from hit-testing for the one instant it takes to
            // ask what is under the pointer, so the answer is never
            // "the card being dragged" — the same reason `letCard
            // DetailsLinkThrough` (kanban boards, above) has to reason
            // about event targets rather than assuming one.
            if (WIDE_GRID.matches) {
                followPointer(event.clientX, event.clientY);
                updateDropHint();
                return;
            }
            dragged.style.pointerEvents = "none";
            const target = document.elementFromPoint(event.clientX, event.clientY)
                ?.closest("[data-widget-key]");
            dragged.style.pointerEvents = "";
            // Only within one grid: the two rows are different shapes —
            // one is a capped, scrolling strip of tiles and the other a
            // free grid of cards — and a card dropped into the strip
            // would be cut off by its own cap.
            if (target && target !== dragged && target.parentElement === host) {
                // Without `lastSwapTarget`, every single move event fired
                // while the pointer sits anywhere within the same target
                // widget re-ran the swap — and a swap is its own inverse,
                // so an even number of them (the common case: a widget is
                // ~235px wide and steps land inside it several times in a
                // row) landed back where it started, looking like
                // dragging did nothing. Swapping only on the move that
                // *changes* which widget is under the pointer is what
                // every other drag-to-reorder surface actually does.
                if (target !== lastSwapTarget) {
                    swapWithAnimation(target);
                    lastSwapTarget = target;
                }
            } else {
                lastSwapTarget = null;
            }
            followPointer(event.clientX, event.clientY);
        }

        function onPointerUp() {
            document.removeEventListener("pointermove", onPointerMove);
            document.removeEventListener("pointerup", onPointerUp);
            document.removeEventListener("pointercancel", onPointerUp);
            if (dragged) {
                dragged.classList.remove("dragging");
                dragged.style.transform = "";
                dragged.style.zIndex = "";
                // A swap, not an insert — the product owner's original
                // request («جابه‌جا کردن جای ویجت‌ها»), and with widgets
                // of four different widths a swap is also the only move
                // whose result is predictable from where the card
                // landed. `moved` guards a plain click (opening the hide
                // button, say) from being recorded as a no-op reorder.
                if (moved && WIDE_GRID.matches && dropSpot) {
                    // Exactly where it was dropped; whatever was there moves
                    // down, and nothing moves up until «مرتب‌سازی».
                    setBoxSpot(dragged, dropSpot.x, dropSpot.y);
                    pushDownAround(host, dragged);
                    save({widget_order: currentOrder(), ...layoutBody()});
                } else if (moved) {
                    save({widget_order: currentOrder()});
                }
            }
            if (hint) { hint.remove(); hint = null; }
            dropSpot = null;
            dragged = null;
            moved = false;
        }

        host.addEventListener("pointerdown", (event) => {
            if (!editing || event.button !== 0) return;
            // The hide button and the resize grip each own their own
            // pointer handling and must not also start a card drag.
            if (event.target.closest("[data-widget-controls], [data-widget-resize]")) return;
            const column = event.target.closest("[data-widget-key]");
            if (!column || column.parentElement !== host) return;
            dragged = column;
            moved = false;
            lastSwapTarget = null;
            // Every box needs numbers before one can be moved among them.
            freezeBoxes(host);
            startClientX = event.clientX;
            startClientY = event.clientY;
            const rect = column.getBoundingClientRect();
            grabOffsetX = event.clientX - rect.left;
            grabOffsetY = event.clientY - rect.top;
            dragged.style.zIndex = "10";
            document.addEventListener("pointermove", onPointerMove);
            document.addEventListener("pointerup", onPointerUp);
            document.addEventListener("pointercancel", onPointerUp);
        });
    }

    function setEditing(next) {
        if (next && narrowScreen.matches) {
            if (narrowNote) narrowNote.hidden = false;
            return;
        }
        if (narrowNote) narrowNote.hidden = true;
        editing = next;
        toggle.setAttribute("aria-pressed", String(editing));
        // Solid while editing, not the light tint it used to take — the
        // pencil is the one control that says which mode the page is in.
        toggle.classList.toggle("btn-primary", editing);
        toggle.classList.toggle("btn-light", !editing);
        // The page-level half of the edit-mode look (the panel stylesheet §9):
        // everything that is not being arranged steps back.
        document.body.classList.toggle("dashboard-editing", editing);
        // A change that arrived while arranging was held back; catch up now.
        if (!editing) refresh();
        if (hint) hint.hidden = !editing;
        if (done) { done.hidden = !editing; done.disabled = !draft; }
        if (cancelButton) cancelButton.hidden = !editing;
        if (compactButton) compactButton.hidden = !editing || !WIDE_GRID.matches;
        if (reset) reset.hidden = !editing || !layout.is_customised;
        if (addWidgetOpen) addWidgetOpen.hidden = !editing;
        if (editing) tidyHosts.forEach((host) => { delete host.dataset.tidy; });
        if (editing) enterEditing(); else leaveEditing();
        // Edit controls change nothing a box needs, but leaving edit mode is a
        // good moment to make sure every box is exactly as tall as it should be.
        if (!editing) fitDashboardRows();
    }

    /** Leave edit mode without the draft: the page is redrawn from what the
     * server holds, which is exactly the arrangement before this edit. */
    function discard() {
        // Cleared first, so the leave-page guard below does not ask about it.
        if (draft) { draft = null; window.location.reload(); return; }
        // Nothing was changed: the default page goes back to arranging itself.
        tidyHosts.forEach((host) => { host.dataset.tidy = "1"; });
        setEditing(false);
    }

    toggle.addEventListener("click", () => (editing ? discard() : setEditing(true)));
    if (done) {
        done.addEventListener("click", async () => {
            if (await flush()) setEditing(false);
        });
    }
    if (cancelButton) cancelButton.addEventListener("click", discard);
    if (compactButton) {
        compactButton.addEventListener("click", () => {
            grids.forEach((host) => { freezeBoxes(host); compactUpward(host); });
            save({widget_order: currentOrder(), ...layoutBody()});
        });
    }
    // Escape throws the draft away and leaves edit mode, as it leaves every
    // other mode in this panel — unless a dialog is open, which Escape
    // closes first.
    document.addEventListener("keydown", (event) => {
        if (editing && event.key === "Escape" && !document.querySelector("dialog[open]")) discard();
    });
    // A draft is not lost silently by leaving the page.
    window.addEventListener("beforeunload", (event) => {
        if (draft && editing) { event.preventDefault(); event.returnValue = ""; }
    });
    if (reset) {
        reset.addEventListener("click", async () => {
            draft = null;
            try {
                await apiRequest("/api/v1/dashboard-layout/", {method: "DELETE"});
            } catch (error) {
                showError(error);
                return;
            }
            // Reload rather than un-apply in place: "back to the
            // default" means the deployment's own order, widths and
            // hidden set, and the page already knows how to render
            // exactly that from a fresh payload.
            window.location.reload();
        });
    }

    // Boxes restored at a saved height: their charts were drawn at their
    // own height before the minimum applied, so give them the room now
    // — and again whenever the window's width moves what a row holds.
    setTimeout(fitAllCharts, 60);
    let fitTimer = null;
    window.addEventListener("resize", () => {
        clearTimeout(fitTimer);
        fitTimer = setTimeout(fitAllCharts, 150);
    });
}
