import {apiRequest} from "dolphin/core/api.js";
import {displayDay} from "dolphin/core/jalali.js";
import {showError} from "dolphin/core/messages.js";
import {setupDashboardEditor} from "dolphin/features/dashboard/editor.js";
import {GRID_COLUMNS, WIDGET_BANDS, boxRect, boxRows, boxSpan, boxSpot, dashboardLayoutState, fitDashboardRows, placeDashboardWidget, placedBoxes, rectsOverlap, scheduleFitRows, setBoxSpot} from "dolphin/features/dashboard/grid.js";
import {gaugeCard, kpiCard, panelCard} from "dolphin/features/dashboard/widget-cards.js";
import {fitWidgetChart, renderGaugeChart, renderMixedChart, renderMultiGaugeChart, renderSparkline} from "dolphin/features/dashboard/widget-charts.js";
import {chartResetButton, renderDonutChart} from "dolphin/ui/charts.js";
import {setupPerformancePanel} from "dolphin/ui/performance.js";
import {ALL_BUSINESS_KINDS, onRealtime} from "dolphin/ui/realtime.js";
import {appendCell, pageRangeLabel} from "dolphin/ui/table.js";

function workQueueRow(lead) {
    const row = document.createElement("tr");
    // A campaign may name no customer, so the row leads with the campaign
    // itself and falls back to it wherever a customer would have gone.
    appendCell(row, lead.customer_name || lead.campaign_or_batch || lead.source || `#${lead.id}`);
    appendCell(row, lead.source);
    appendCell(row, displayDay(lead.next_follow_up_at));
    const actions = document.createElement("td");
    actions.className = "row-actions";
    const links = [
        [`/leads/${lead.id}/`, "سرنخ"],
        [`/interactions/?lead=${lead.id}`, "ثبت تماس"],
        [`/invoices/`, "فاکتور"],
    ];
    // The customer link exists only when there is a customer to open.
    if (lead.customer) links.unshift([`/customers/${lead.customer}/`, "مشتری"]);
    links.forEach(([href, label]) => {
        const link = document.createElement("a");
        link.className = "btn btn-sm btn-light";
        link.href = href;
        link.textContent = label;
        actions.appendChild(link);
    });
    row.appendChild(actions);
    return row;
}

async function setupWorkQueue() {
    const loading = document.getElementById("agent-work-queue-loading");
    if (!loading) return;
    const empty = document.getElementById("agent-work-queue-empty");
    const wrap = document.getElementById("agent-work-queue-table-wrap");
    const body = document.getElementById("agent-work-queue-body");
    const pager = document.getElementById("agent-work-queue-pagination");
    const previous = document.getElementById("agent-work-queue-prev");
    const next = document.getElementById("agent-work-queue-next");
    let currentPage = 1;
    async function load(page = 1) {
        loading.hidden = false; empty.hidden = true; wrap.hidden = true; pager.hidden = true;
        try {
            const data = await apiRequest(`/api/v1/leads/work-queue/?page=${page}`);
            body.replaceChildren(...data.results.map(workQueueRow));
            loading.hidden = true;
            if (!data.results.length) { empty.hidden = false; return; }
            wrap.hidden = false; currentPage = page;
            previous.disabled = !data.previous; next.disabled = !data.next;
            document.getElementById("agent-work-queue-page-label").textContent = pageRangeLabel(data, page);
            pager.hidden = !data.previous && !data.next;
        } catch (error) { loading.hidden = true; showError(error); }
    }
    previous.addEventListener("click", () => load(currentPage - 1));
    next.addEventListener("click", () => load(currentPage + 1));
    reloadWorkQueue = () => load(currentPage);
    await load();
}

let reloadWorkQueue = null;
/** The performance widget's first load, when it is on the dashboard. */
let performanceReady = null;
/** How long the page waits for every box before showing what it has. */
const REVEAL_DEADLINE_MS = 6000;

/**
 * Show every box at once (2.40.35, product owner: «وقتی وارد داشبورد می‌شویم
 * تمامی ویجت‌ها باید همزمان لود شوند»). The stage (`#dashboard-stage`,
 * home.html) stays invisible behind one loader until the boxes are placed,
 * their charts drawn and their heights fitted, then fades in as one.
 */
function revealDashboard() {
    const stage = document.getElementById("dashboard-stage");
    if (!stage || !stage.hasAttribute("data-booting")) return;
    stage.removeAttribute("data-booting");
    stage.classList.add("is-revealed");
}

export async function setupDashboard() {
    // The editor starts once the insight grid has been placed — it
    // needs those boxes in the DOM to arrange them — but it no longer
    // depends on that grid having anything in it (2.18.1, see
    // `setupDashboardInsights`' return value).
    const insights = setupDashboardInsights().then((grid) => {
        if (grid) setupDashboardEditor(grid, {refresh: refreshDashboard});
    });
    const workQueue = setupWorkQueue();
    const everything = insights.then(() => performanceReady).catch(() => {});
    await Promise.race([everything, new Promise((resolve) => { setTimeout(resolve, REVEAL_DEADLINE_MS); })]);
    fitDashboardRows();
    revealDashboard();
    await Promise.all([workQueue, everything]);
    // Live (2.40.34, product owner: «کل پنل، مخصوصاً داشبورد، باید لایو باشد»):
    // a change anywhere the dashboard counts is redrawn in place.
    onRealtime(ALL_BUSINESS_KINDS, refreshDashboard, {delay: 1200});
    // Every box takes the rows its content needs; again when the page's width,
    // the fonts or the charts change what that is.
    fitDashboardRows();
    window.addEventListener("resize", scheduleFitRows);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(scheduleFitRows);
    window.addEventListener("load", scheduleFitRows);
}


/**
 * The role's own KPI strip, gauges, sales trend, status breakdown and
 * agent share — as one arrangeable grid.
 *
 * Every part is optional and the server decides which parts exist: a
 * reader who may not see sales gets no trend, and this draws nothing
 * rather than an empty card promising a chart that will never arrive.
 * The whole section stays hidden until at least one part came back, so
 * a deployment with none of the sources looks exactly as it did before
 * this was added.
 *
 * Since 2.8.0 the order and the width of each part come from the server
 * (`common.dashboard_layout.apply_layout` — this deployment's default
 * with this reader's own overlay on top) rather than from the markup,
 * and `setupDashboardEditor` below lets the reader change them in
 * place. Nothing here decides *which* parts a reader may receive; that
 * was already settled before the payload was built.
 *
 * Charts reuse the shared helpers, so they take their colours from the
 * theme's own CSS variables and redraw themselves on a light/dark
 * switch like every other chart in the panel.
 *
 * Resolves to what `setupDashboardEditor` needs — `{grid, widgets,
 * layout}` — whenever this deployment offers personal arrangement at
 * all, *including* when the insight grid ends up empty or its request
 * failed. Until 2.18.1 both of those returned early before the editor
 * was ever set up, so a reader with no insight widgets had no pencil
 * and the capability tiles — the first row of the page — could not be
 * moved (product owner, 2026-09-27: «ردیف اول داشبورد باید قابل
 * ویرایش باشد و جایشان قابل تغییر باشد»). `null` only when there is
 * genuinely nothing to arrange: the feature is off.
 */
async function setupDashboardInsights() {
    const section = document.getElementById("dashboard-insights");
    const pageState = dashboardLayoutState();
    const emptyEditorState = () => (pageState ? {
        grid: document.getElementById("dashboard-widgets") || document.getElementById("dashboard-capability-tiles"),
        widgets: new Map(),
        layout: pageState,
        hiddenAvailable: [],
    } : null);
    if (!section) return emptyEditorState();
    let data;
    try {
        data = await apiRequest("/api/v1/dashboard/");
    } catch (error) {
        // The tiles, the work queue and the performance panel above are
        // what this page is; a failed side panel must not replace them
        // with an error card. The tile row above is still arrangeable.
        return emptyEditorState();
    }

    // Unhidden *before* any chart mounts, not after. ApexCharts measures
    // its container at render time, and a container inside a
    // `display: none` ancestor measures zero — the chart then draws at
    // zero width and never recovers on its own. This project has already
    // paid for that once (1.7.19, "chart mounts at zero width"); the
    // section is revealed first and the parts fill in behind it.
    section.hidden = false;

    const grid = document.getElementById("dashboard-widgets");
    const layout = data.layout || pageState || {order: [], hidden: [], sizes: {}, locked_hidden: []};
    // The parts this reader hid themselves, with their real figures, for
    // the "افزودن ویجت" dialog (`_hidden_available`, dashboard_layout.py).
    const hiddenAvailable = data.hidden_available || [];

    // Every widget this reader actually received, keyed, each with the
    // column element it will occupy and the chart work that has to run
    // once that element is in the DOM. Collected first and placed
    // second, because the server's order interleaves KPIs, gauges and
    // charts and there is no single loop that produces them in it.
    const widgets = new Map();

    data.kpis.forEach((kpi) => {
        const {column, spark} = kpiCard(kpi);
        widgets.set(kpi.key, {
            key: kpi.key,
            label: kpi.label,
            family: "kpi",
            data: kpi,
            column,
            size: kpi.size,
            height: kpi.height,
            height_chosen: kpi.height_chosen,
            position: kpi.position,
            mount: () => { if (spark && kpi.spark) renderSparkline(spark, kpi.spark, {accent: kpi.accent}); },
        });
    });

    (data.gauges || []).forEach((gauge) => {
        const {column, canvas, empty} = gaugeCard(gauge);
        widgets.set(gauge.key, {
            key: gauge.key,
            label: gauge.label,
            family: "gauge",
            data: gauge,
            column,
            size: gauge.size,
            height: gauge.height,
            height_chosen: gauge.height_chosen,
            position: gauge.position,
            mount: () => renderGaugeChart(canvas, empty, gauge.value, {
                ariaLabel: `${gauge.label}: ${gauge.display}`,
                accent: gauge.accent,
                label: gauge.label,
            }),
        });
    });

    (data.panels || []).forEach((panel) => {
        widgets.set(panel.key, {
            key: panel.key,
            label: panel.title,
            family: "panel",
            data: panel,
            column: panelCard(panel),
            size: panel.size,
            height: panel.height,
            height_chosen: panel.height_chosen,
            position: panel.position,
            mount: () => {},
        });
    });

    // «عملکرد عملیاتی» (2.40.35): the report panel as a widget, on the
    // dashboard only when the reader added it (`OPT_IN_WIDGETS`). Its markup
    // is the shared include parked in the store; its figures load once it is
    // placed, and the reveal waits for that first load.
    const performanceCard = document.getElementById("dashboard-performance-card");
    if (data.performance && performanceCard) {
        performanceCard.hidden = false;
        widgets.set("performance", {
            key: "performance",
            label: data.performance.title,
            family: "performance",
            data: data.performance,
            column: performanceCard,
            size: data.performance.size,
            height: data.performance.height,
            height_chosen: data.performance.height_chosen,
            position: data.performance.position,
            mount: () => {
                performanceReady = setupPerformancePanel("dashboard");
                // Its details table opens and closes inside the box; the box
                // follows its content's height.
                if (typeof ResizeObserver === "function") {
                    const content = performanceCard.querySelector(".card-body");
                    if (content) new ResizeObserver(scheduleFitRows).observe(content);
                }
            },
        });
    }

    if (data.trend) {
        const card = document.getElementById("dashboard-trend-card");
        document.getElementById("dashboard-trend-title").textContent = data.trend.title;
        document.getElementById("dashboard-trend-summary").textContent = data.trend.summary;
        card.hidden = false;
        widgets.set("trend", {
            key: "trend",
            label: data.trend.title,
            family: "trend",
            data: data.trend,
            column: card,
            size: data.trend.size,
            height: data.trend.height,
            height_chosen: data.trend.height_chosen,
            position: data.trend.position,
            // Mixed rather than a bare area: `_sales_trend` (common/
            // dashboard.py) returns the same twelve weeks' order count
            // alongside the amount, and a reader asking "how is sales
            // doing" usually means both.
            mount: () => {
                // Zoomable, so it needs the way back — and it is the one
                // line chart in the panel with no range filter beside it
                // to carry one (see `chartResetButton`).
                const slot = document.getElementById("dashboard-trend-controls");
                let reset = slot && slot.querySelector(".dolphin-chart-reset");
                if (slot && !reset) {
                    reset = chartResetButton();
                    slot.append(reset);
                }
                renderMixedChart(
                    document.getElementById("dashboard-trend-chart"),
                    document.getElementById("dashboard-trend-empty"),
                    data.trend.points,
                    data.trend.counts,
                    {
                        seriesNames: ["مبلغ فروش", "تعداد فروش"],
                        summary: data.trend.summary,
                        ariaLabel: data.trend.title,
                        resetButton: reset,
                    },
                );
            },
        });
    }

    if (data.agent_share) {
        const card = document.getElementById("dashboard-agent-share-card");
        document.getElementById("dashboard-agent-share-title").textContent = data.agent_share.title;
        document.getElementById("dashboard-agent-share-summary").textContent =
            `مجموع فروش این ماه: ${data.agent_share.total_display}`;
        const slot = document.getElementById("dashboard-agent-share-link-slot");
        slot.replaceChildren();
        const link = document.createElement("a");
        link.className = "dashboard-card-all text-primary fw-semibold fs-8 text-decoration-none";
        link.id = "dashboard-agent-share-link";
        link.href = data.agent_share.url;
        link.textContent = "همه";
        slot.appendChild(link);
        card.hidden = false;
        widgets.set("agent_share", {
            key: "agent_share",
            label: data.agent_share.title,
            family: "agent_share",
            data: data.agent_share,
            column: card,
            size: data.agent_share.size,
            height: data.agent_share.height,
            height_chosen: data.agent_share.height_chosen,
            position: data.agent_share.position,
            mount: () => renderMultiGaugeChart(
                document.getElementById("dashboard-agent-share-chart"),
                document.getElementById("dashboard-agent-share-empty"),
                data.agent_share.items,
                {ariaLabel: data.agent_share.title},
            ),
        });
    }

    if (data.breakdown) {
        const card = document.getElementById("dashboard-breakdown-card");
        document.getElementById("dashboard-breakdown-title").textContent = data.breakdown.title;
        const slot = document.getElementById("dashboard-breakdown-link-slot");
        slot.replaceChildren();
        const link = document.createElement("a");
        link.className = "dashboard-card-all text-primary fw-semibold fs-8 text-decoration-none";
        link.id = "dashboard-breakdown-link";
        link.href = data.breakdown.url;
        link.textContent = "همه";
        slot.appendChild(link);
        card.hidden = false;
        widgets.set("breakdown", {
            key: "breakdown",
            label: data.breakdown.title,
            family: "breakdown",
            data: data.breakdown,
            column: card,
            size: data.breakdown.size,
            height: data.breakdown.height,
            height_chosen: data.breakdown.height_chosen,
            position: data.breakdown.position,
            mount: () => renderDonutChart(
                document.getElementById("dashboard-breakdown-chart"),
                document.getElementById("dashboard-breakdown-empty"),
                data.breakdown.items,
                {ariaLabel: data.breakdown.title},
            ),
        });
    }

    // Nothing to show after all: leave it hidden, so a deployment with
    // none of the sources renders exactly the page it rendered before
    // this section existed.
    if (!widgets.size) {
        section.hidden = true;
        return pageState ? {grid, widgets, layout, hiddenAvailable} : null;
    }

    // Placed in the server's order. `widgets` is a Map, so its own
    // insertion order is the fallback for anything the saved order does
    // not mention — the same "an unlisted widget keeps its position"
    // rule `_ordered` applies on the Python side.
    //
    // One grid for every box (2.40.19, product owner: «تمامی ویجت ها باید
    // بتوانند هرجا قرار بگیرند»). The capability tiles are rendered by the
    // server in their own row above; they move into this grid here, so a
    // tile and a chart can share a row in any order. The tiles' own section
    // is left empty and stops being a grid.
    const tilesHost = document.getElementById("dashboard-capability-tiles");
    const tiles = new Map(
        tilesHost ? [...tilesHost.querySelectorAll(":scope > [data-widget-key]")].map((column) => [column.dataset.widgetKey, column]) : [],
    );
    tiles.forEach((column) => { column.dataset.band = String(WIDGET_BANDS.tile); });
    // Nobody placed anything yet — the default dashboard: laid out in tidy
    // shelves (`shelfLayout`), every family in its own band, rather than
    // left to the browser's packing (2.40.35, product owner: «داشبورد باید
    // به صورت دیفالت مرتب و تمیز باشد»).
    const tidy = ![...tiles.values()].some(boxSpot) && ![...widgets.values()].some((widget) => widget.position);
    if (tidy) grid.dataset.tidy = "1";
    // An arrangement the reader saved keeps its columns and order, but the
    // holes between its boxes close upward on every visit (2.40.36, product
    // owner: «جاهای خالی خودکار بسته شوند») — what «مرتب‌سازی» does in the
    // editor. While the page is being arranged nothing moves on its own.
    else grid.dataset.compact = "1";
    const placed = new Set();
    const order = tidy && !(layout.order || []).length
        ? [...tiles.keys(), ...[...widgets.values()].sort((a, b) => WIDGET_BANDS[a.family] - WIDGET_BANDS[b.family]).map((widget) => widget.key)]
        : (layout.order || []);
    order.forEach((key) => {
        if (placed.has(key)) return;
        if (tiles.has(key)) {
            placed.add(key);
            grid.appendChild(tiles.get(key));
            return;
        }
        const widget = widgets.get(key);
        if (!widget) return;
        placed.add(key);
        placeDashboardWidget(grid, widget);
    });
    tiles.forEach((column, key) => {
        if (placed.has(key)) return;
        placed.add(key);
        grid.appendChild(column);
    });
    widgets.forEach((widget, key) => {
        if (placed.has(key)) return;
        placed.add(key);
        placeDashboardWidget(grid, widget);
    });
    if (tilesHost && tiles.size) {
        tilesHost.removeAttribute("data-dashboard-grid");
        tilesHost.hidden = true;
        if (!tidy) liftLegacyPositions(grid, tiles);
    }

    // Mounted after every column is in the DOM, same rule as every other
    // chart here — Apex measures a real element's width, and a freshly
    // created node not yet attached has none.
    widgets.forEach((widget) => widget.mount());
    widgets.forEach((widget) => fitWidgetChart(widget.column));
    liveWidgets = widgets;

    return pageState ? {grid, widgets, layout, hiddenAvailable} : null;
}

/** The boxes on the page, for `refreshDashboard`. */
let liveWidgets = null;
let refreshing = false;

/**
 * Redraws every box's figures where it stands (2.40.34). The boxes stay
 * where the reader put them: each one's content is rebuilt from the fresh
 * payload with the same builder that drew it and swapped inside its own
 * column, then its chart is drawn again. The capability tiles are the
 * server's own markup, so their figures are read from a fresh render of the
 * page. Never while the layout is being edited, and never two at once.
 */
async function refreshDashboard() {
    if (refreshing || document.body.classList.contains("dashboard-editing")) return;
    refreshing = true;
    try {
        await Promise.all([refreshInsights(), refreshTiles(), reloadWorkQueue?.()]);
        scheduleFitRows();
    } catch (error) {
        // A missed refresh needs no message: the next change, or the next
        // visit, draws the page again.
    } finally {
        refreshing = false;
    }
}

async function refreshInsights() {
    if (!liveWidgets) return;
    const data = await apiRequest("/api/v1/dashboard/");
    const swap = (key, column, payload) => {
        const current = liveWidgets.get(key);
        if (!current) return false;
        // A figure that changed eases in (2.40.38); one that did not stays still.
        const before = current.column.querySelector(".dashboard-kpi-value")?.textContent;
        const after = column.querySelector(".dashboard-kpi-value");
        if (after && before !== undefined && before !== after.textContent) after.classList.add("is-updated");
        current.column.replaceChildren(...column.children);
        current.data = payload;
        return true;
    };
    data.kpis.forEach((kpi) => {
        const built = kpiCard(kpi);
        if (swap(kpi.key, built.column, kpi) && built.spark && kpi.spark) {
            renderSparkline(built.spark, kpi.spark, {accent: kpi.accent});
        }
    });
    (data.gauges || []).forEach((gauge) => {
        const built = gaugeCard(gauge);
        if (swap(gauge.key, built.column, gauge)) {
            renderGaugeChart(built.canvas, built.empty, gauge.value, {
                ariaLabel: `${gauge.label}: ${gauge.display}`, accent: gauge.accent, label: gauge.label,
            });
        }
    });
    (data.panels || []).forEach((panel) => swap(panel.key, panelCard(panel), panel));
    if (data.trend && liveWidgets.has("trend")) {
        document.getElementById("dashboard-trend-summary").textContent = data.trend.summary;
        renderMixedChart(
            document.getElementById("dashboard-trend-chart"),
            document.getElementById("dashboard-trend-empty"),
            data.trend.points,
            data.trend.counts,
            {
                seriesNames: ["مبلغ فروش", "تعداد فروش"],
                summary: data.trend.summary,
                ariaLabel: data.trend.title,
                resetButton: document.querySelector("#dashboard-trend-controls .dolphin-chart-reset"),
            },
        );
    }
    if (data.agent_share && liveWidgets.has("agent_share")) {
        document.getElementById("dashboard-agent-share-summary").textContent =
            `مجموع فروش این ماه: ${data.agent_share.total_display}`;
        renderMultiGaugeChart(
            document.getElementById("dashboard-agent-share-chart"),
            document.getElementById("dashboard-agent-share-empty"),
            data.agent_share.items,
            {ariaLabel: data.agent_share.title},
        );
    }
    if (data.breakdown && liveWidgets.has("breakdown")) {
        renderDonutChart(
            document.getElementById("dashboard-breakdown-chart"),
            document.getElementById("dashboard-breakdown-empty"),
            data.breakdown.items,
            {ariaLabel: data.breakdown.title},
        );
    }
}

async function refreshTiles() {
    const tiles = document.querySelectorAll('[data-widget-key^="capability:"]');
    if (!tiles.length) return;
    const response = await fetch(window.location.pathname, {credentials: "same-origin", headers: {Accept: "text/html"}});
    if (!response.ok) return;
    const fresh = new DOMParser().parseFromString(await response.text(), "text/html");
    tiles.forEach((tile) => {
        const source = fresh.querySelector(`[data-widget-key="${CSS.escape(tile.dataset.widgetKey)}"] .dashboard-kpi-value`);
        const target = tile.querySelector(".dashboard-kpi-value");
        if (source && target && target.textContent !== source.textContent) {
            target.textContent = source.textContent;
            target.classList.remove("is-updated");
            void target.offsetWidth;
            target.classList.add("is-updated");
        }
    });
}

/**
 * A layout saved before the two rows became one grid (2.40.19) placed the
 * tiles and the insight boxes each from row 1 of its own grid (or left the
 * tiles to flow), so in the one grid they would sit on or among each other.
 * Here, once: tiles with no saved place are laid across the top rows in
 * order, and when a saved insight box would then share cells with a tile,
 * every saved insight box moves down below the tiles. The next save stores
 * the merged arrangement, which never overlaps (`pushDownAround`).
 */
function liftLegacyPositions(grid, tiles) {
    const tileColumns = [...tiles.values()];
    if (tileColumns.every((column) => !boxSpot(column))) {
        let x = 1;
        let y = 1;
        let rowHeight = 0;
        tileColumns.forEach((column) => {
            const w = boxSpan(column);
            if (x + w - 1 > GRID_COLUMNS) { x = 1; y += rowHeight; rowHeight = 0; }
            setBoxSpot(column, x, y);
            x += w;
            rowHeight = Math.max(rowHeight, boxRows(column));
        });
    }
    const tileRects = tileColumns.map(boxRect).filter(Boolean);
    if (!tileRects.length) return;
    const others = placedBoxes(grid).filter((column) => !tiles.has(column.dataset.widgetKey) && boxSpot(column));
    const overlapping = others.some((column) => tileRects.some((rect) => rectsOverlap(rect, boxRect(column))));
    if (!overlapping) return;
    const below = Math.max(...tileRects.map((rect) => rect.y + rect.h));
    const top = Math.min(...others.map((column) => boxSpot(column).y));
    others.forEach((column) => {
        const spot = boxSpot(column);
        setBoxSpot(column, spot.x, spot.y + below - top);
    });
}
