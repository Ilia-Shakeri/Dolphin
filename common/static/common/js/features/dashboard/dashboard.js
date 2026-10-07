import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDay} from "dolphin/core/jalali.js";
import {showError} from "dolphin/core/messages.js";
import {apexBase, chartFontFamily, compactAmount, chartInk, chartPalette, chartRedraws, chartResetButton, chartResetEvents, liveCharts, mountApex, renderDonutChart, showEmptyChart, thinningFormatter} from "dolphin/ui/charts.js";
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
        if (grid) setupDashboardEditor(grid);
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

/** The editor's starting state rendered into the page itself
 * (`dashboard-layout-state`, home.html), or `null` on a deployment that
 * does not offer personal arrangement at all. */
function dashboardLayoutState() {
    const node = document.getElementById("dashboard-layout-state");
    if (!node) return null;
    try {
        return JSON.parse(node.textContent);
    } catch (error) {
        return null;
    }
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
        link.className = "text-primary fw-semibold fs-8 text-decoration-none";
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
        link.className = "text-primary fw-semibold fs-8 text-decoration-none";
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
        if (source && target && target.textContent !== source.textContent) target.textContent = source.textContent;
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

/**
 * Make a widget's chart use the room its box has been given.
 *
 * A chart is drawn at one fixed height, so a box dragged taller (or
 * shorter) left the plot the same size with empty card around it (product
 * owner, 2026-09-29: «وقتی سایزشون عوض میشه اطلاعات توشون هم همراه باهاش
 * تغییر سایز بدن»). Width already followed: Apex redraws on its parent's
 * width. Height is worked out here from the box's own minimum height minus
 * everything in the card that is *not* the chart, so the card stays
 * exactly as tall as the reader made it and nothing is pushed out.
 * Observed rather than triggered by the editor, so it also holds after a
 * reload, a theme switch and a phone rotation.
 */
function fitWidgetChart(column) {
    const card = column.querySelector(":scope > .card");
    const host = card && card.querySelector("[id$='-chart'], .dashboard-gauge-canvas");
    if (!host || column.dataset.chartFit || column.dataset.widgetKey === "performance") return;
    column.dataset.chartFit = "1";
    let base = null;
    let frame = 0;
    const usedAround = () => {
        let used = 0;
        let node = host;
        while (node && node !== card.parentElement) {
            const parent = node.parentElement;
            if (!parent) break;
            for (const sibling of parent.children) {
                if (sibling === node) continue;
                const style = getComputedStyle(sibling);
                if (style.display === "none" || style.position === "absolute") continue;
                used += sibling.offsetHeight + parseFloat(style.marginTop) + parseFloat(style.marginBottom);
            }
            const box = getComputedStyle(parent);
            used += parseFloat(box.paddingTop) + parseFloat(box.paddingBottom)
                + parseFloat(box.borderTopWidth) + parseFloat(box.borderBottomWidth);
            if (parent === card) break;
            node = parent;
        }
        const hostStyle = getComputedStyle(host);
        return used + parseFloat(hostStyle.marginTop) + parseFloat(hostStyle.marginBottom);
    };
    const apply = () => {
        frame = 0;
        const instance = liveCharts.get(host);
        if (!instance) return;
        if (base === null) base = Number(instance.w.config.chart.height) || host.offsetHeight;
        const minimum = parseFloat(getComputedStyle(card).minHeight) || 0;
        const target = Math.max(base, Math.floor(minimum - usedAround()));
        if (Math.abs(target - Number(instance.w.config.chart.height)) < 4) return;
        instance.updateOptions({chart: {height: target}}, false, false);
    };
    const schedule = () => {
        if (!frame) frame = requestAnimationFrame(apply);
    };
    if (typeof ResizeObserver === "function") new ResizeObserver(schedule).observe(card);
    new MutationObserver(schedule).observe(column, {attributes: true, attributeFilter: ["style"]});
    schedule();
}

/**
 * One list or calendar widget (`common.dashboard_panels`): a card with a
 * header, and either a short list of real rows, a Jalali day, or a month
 * grid. Same card shell as `kpiCard`, so it sizes, moves and hides with
 * the rest; the row count it shows follows the box's height through
 * `--dashboard-min-height`, and the text scales with its width through
 * the container query in dolphin.css.
 */
function panelCard(panel) {
    const column = document.createElement("div");
    column.className = "col-12 col-sm-6 col-xl-4";
    const card = document.createElement("div");
    card.className = "card card-flush h-100 dashboard-panel";
    card.dataset.dashboardPanel = panel.key;
    const body = document.createElement("div");
    body.className = "card-body d-flex flex-column py-6";

    const head = document.createElement("div");
    head.className = "d-flex align-items-center justify-content-between gap-3 mb-4";
    const titleWrap = document.createElement("div");
    titleWrap.className = "d-flex align-items-center gap-3 min-w-0";
    const symbol = document.createElement("span");
    symbol.className = "symbol symbol-40px flex-shrink-0";
    const symbolLabel = document.createElement("span");
    symbolLabel.className = `symbol-label bg-light-${panel.accent}`;
    const icon = document.createElement("i");
    icon.className = `di-duotone ${panel.icon} fs-2 text-${panel.accent}`;
    for (let index = 1; index <= (panel.icon_paths || 2); index += 1) {
        icon.appendChild(document.createElement("span")).className = `path${index}`;
    }
    symbolLabel.appendChild(icon);
    symbol.appendChild(symbolLabel);
    const title = document.createElement("h2");
    title.className = "dashboard-panel-title fw-bold text-gray-900 mb-0 text-truncate";
    title.textContent = panel.title;
    titleWrap.append(symbol, title);
    head.appendChild(titleWrap);
    if (panel.kind !== "calendar" && panel.count) {
        const badge = document.createElement("span");
        badge.className = `badge badge-light-${panel.accent} flex-shrink-0`;
        badge.textContent = `${toPersianDigits(String(panel.count))} ${panel.count_label}`;
        head.appendChild(badge);
    } else if (panel.kind === "calendar") {
        const month = document.createElement("span");
        month.className = "text-muted fw-semibold fs-7 flex-shrink-0";
        month.textContent = `${panel.month_name} ${panel.year}`;
        head.appendChild(month);
    }
    body.appendChild(head);

    if (panel.kind === "calendar") {
        body.appendChild(calendarGrid(panel));
    } else {
        if (panel.kind === "agenda") {
            const today = document.createElement("div");
            today.className = "dashboard-agenda-date d-flex align-items-baseline gap-2 mb-3";
            const day = document.createElement("span");
            day.className = "dashboard-agenda-day fw-bolder text-gray-900 lh-1";
            day.textContent = panel.day;
            const rest = document.createElement("span");
            rest.className = "text-gray-700 fw-semibold";
            rest.textContent = `${panel.weekday}، ${panel.month_name} ${panel.year}`;
            today.append(day, rest);
            body.appendChild(today);
        }
        body.appendChild(panelList(panel));
    }
    if (panel.url && panel.kind !== "calendar") {
        const more = document.createElement("a");
        more.className = "text-primary fw-semibold fs-8 text-decoration-none mt-auto pt-3";
        more.href = panel.url;
        more.textContent = "همه";
        body.appendChild(more);
    }
    card.appendChild(body);
    column.appendChild(card);
    return column;
}

function panelList(panel) {
    if (!panel.items.length) {
        const empty = document.createElement("p");
        empty.className = "text-center text-gray-600 fs-7 py-8 mb-0";
        empty.textContent = panel.empty;
        return empty;
    }
    const list = document.createElement("ul");
    list.className = "dashboard-panel-list list-unstyled mb-0";
    panel.items.forEach((item) => {
        const row = document.createElement("li");
        row.className = "dashboard-panel-row d-flex align-items-center justify-content-between gap-3";
        const text = document.createElement(item.url ? "a" : "div");
        text.className = "min-w-0 flex-grow-1 text-decoration-none";
        if (item.url) text.href = item.url;
        if (item.time) {
            const time = document.createElement("span");
            time.className = "text-muted fs-8 d-block";
            time.textContent = item.time;
            text.appendChild(time);
        }
        const name = document.createElement("span");
        name.className = `fw-semibold text-gray-900 d-block text-truncate${item.url ? " text-hover-primary" : ""}`;
        name.textContent = item.title;
        const meta = document.createElement("span");
        meta.className = "text-muted fs-8 d-block text-truncate";
        meta.textContent = item.meta || "";
        text.append(name, meta);
        row.appendChild(text);
        if (item.badge) {
            const badge = document.createElement("span");
            badge.className = `badge badge-light-${item.tone || "primary"} flex-shrink-0`;
            badge.textContent = item.badge;
            row.appendChild(badge);
        }
        list.appendChild(row);
    });
    return list;
}

function calendarGrid(panel) {
    const grid = document.createElement("div");
    grid.className = "dashboard-calendar";
    grid.setAttribute("role", "grid");
    grid.setAttribute("aria-label", `${panel.month_name} ${panel.year}`);
    panel.weekdays.forEach((name) => {
        const cell = document.createElement("span");
        cell.className = "dashboard-calendar-weekday text-muted fw-semibold";
        cell.textContent = name;
        grid.appendChild(cell);
    });
    for (let blank = 0; blank < panel.offset; blank += 1) {
        grid.appendChild(document.createElement("span"));
    }
    const marked = new Set(panel.marked);
    for (let day = 1; day <= panel.days_in_month; day += 1) {
        const cell = document.createElement("span");
        cell.className = "dashboard-calendar-day";
        cell.textContent = toPersianDigits(String(day));
        if (marked.has(day)) {
            cell.classList.add("has-task");
            cell.title = "وظیفهٔ باز دارد";
        }
        if (day === panel.today) {
            cell.classList.add("is-today");
            cell.setAttribute("aria-current", "date");
        }
        grid.appendChild(cell);
    }
    return grid;
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
const WIDE_GRID = window.matchMedia("(min-width: 1200px)");
const GRID_COLUMNS = 12;
/** The most rows a box is fitted to (`ROW_STEPS`' last step, dashboard_layout.py). */
const MAX_FIT_ROWS = 400;
/** The default dashboard's bands, top to bottom: what a reader scans first. */
const WIDGET_BANDS = {tile: 0, kpi: 1, gauge: 2, trend: 3, breakdown: 3, panel: 4, agent_share: 5, performance: 6};
/** The widths the server knows (`WIDGET_SIZES`), in columns. */
const SPAN_STEPS = [3, 4, 6, 8, 9, 12];
const SIZE_FOR_SPAN = {3: "quarter", 4: "third", 6: "half", 8: "two_thirds", 9: "three_quarters", 12: "full"};

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

function boxSpan(column) {
    const match = /dashboard-span-(\d+)/.exec(column.className);
    return match ? Number(match[1]) : 3;
}

function boxRows(column) {
    return Number(column.style.getPropertyValue("--dashboard-rows")) || 1;
}

function boxSpot(column) {
    const x = Number(column.style.getPropertyValue("--dashboard-x"));
    const y = Number(column.style.getPropertyValue("--dashboard-y"));
    return x && y ? {x, y} : null;
}

function setBoxSpot(column, x, y) {
    column.style.setProperty("--dashboard-x", String(x));
    column.style.setProperty("--dashboard-y", String(y));
}

function boxRect(column) {
    const spot = boxSpot(column);
    return spot ? {x: spot.x, y: spot.y, w: boxSpan(column), h: boxRows(column)} : null;
}

function rectsOverlap(a, b) {
    return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

function placedBoxes(host) {
    return Array.from(host.children).filter((node) => node.dataset && node.dataset.widgetKey && !node.hidden);
}

/** What the grid is made of, in pixels. */
function gridMetrics(host) {
    const style = getComputedStyle(host);
    const rect = host.getBoundingClientRect();
    const row = parseFloat(style.gridAutoRows) || 8;
    return {rect, row, col: rect.width / GRID_COLUMNS, rtl: style.direction === "rtl"};
}

/** Pin every box that is still placed automatically to where it is drawn now,
 * so each has numbers to compare. Only on a wide screen. */
function freezeBoxes(host) {
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
function collidesWithOthers(host, column, rect = boxRect(column)) {
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
function pushDownAround(host, pinned) {
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
function compactUpward(host) {
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
function scheduleFitRows() {
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
function placeDashboardWidget(grid, widget) {
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
function setupDashboardEditor({grid, widgets, layout, hiddenAvailable}) {
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
    //: an RTL and an LTR page alike (the cursors live in dolphin.css).
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
        // The page-level half of the edit-mode look (dolphin.css §9):
        // everything that is not being arranged steps back.
        document.body.classList.toggle("dashboard-editing", editing);
        // A change that arrived while arranging was held back; catch up now.
        if (!editing) refreshDashboard();
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

/**
 * One KPI card (2.40.3): the icon in a tinted tile and the title beside it
 * at the inline start; at the inline end a chip with the change and a
 * sparkline in the icon's hue; the big figure below, and one muted caption.
 * In RTL that puts the icon and title on the right and the chip on the left.
 *
 * Contract, all from the server (`common.dashboard._kpi`): `icon`,
 * `accent` (the tone), `label`, `display` (the shortened figure, unit
 * included) and `full_display`, `delta` (`{text, direction, tone}` or
 * `null` — a chip only when there is a real comparison or count), `spark`
 * (a real series or `null`), `caption`, `url`. Nothing is invented: no
 * chip without a base, no line under three points.
 */
function kpiCard(kpi) {
    const column = document.createElement("div");
    column.className = "col-sm-6 col-xl-3";

    // A link when the figure has somewhere to go, a plain card when it
    // does not — rather than an anchor with a dead href.
    const card = document.createElement(kpi.url ? "a" : "div");
    card.className = "card card-flush h-100 text-decoration-none kpi-card";
    if (kpi.url) card.href = kpi.url;
    // Deliberately not `data-kpi`: the performance panel further down
    // this same page already owns that attribute for its own four
    // figures, and one selector meaning two different things is a trap
    // for the next reader (and for a test that queries it).
    card.dataset.dashboardKpi = kpi.key;

    const body = document.createElement("div");
    body.className = "card-body kpi-card-body";

    const head = document.createElement("div");
    head.className = "kpi-card-head";
    const titleRow = document.createElement("div");
    titleRow.className = "kpi-card-title-row";
    const tile = document.createElement("span");
    tile.className = "kpi-card-icon";
    tile.setAttribute("aria-hidden", "true");
    const icon = document.createElement("i");
    icon.className = `di-duotone ${kpi.icon}`;
    // Per-glyph path count, sent by the server for the same reason the
    // reminder bell and the timeline take it from there.
    for (let index = 1; index <= (kpi.icon_paths || 2); index += 1) {
        const path = document.createElement("span");
        path.className = `path${index}`;
        icon.appendChild(path);
    }
    tile.appendChild(icon);
    const title = document.createElement("span");
    title.className = "kpi-card-title dashboard-kpi-label";
    title.textContent = kpi.label;
    titleRow.append(tile, title);
    head.appendChild(titleRow);

    let spark = null;
    const trailing = document.createElement("div");
    trailing.className = "kpi-card-trailing";
    if (kpi.delta) trailing.appendChild(kpiChip(kpi.delta));
    // A line needs at least three points to be a shape; fewer is no line.
    // A line only when there is a history to draw (2.40.36): a series that is
    // zero until its last point drew a cliff from nothing — a jump the figure
    // and its caption («در ماه گذشته چیزی ثبت نشده بود») already say plainly.
    const history = Array.isArray(kpi.spark) ? kpi.spark.slice(0, -1) : [];
    if (Array.isArray(kpi.spark) && kpi.spark.length >= 3 && history.some((value) => Number(value) !== 0)) {
        spark = document.createElement("div");
        spark.className = "kpi-sparkline";
        spark.setAttribute("role", "img");
        spark.setAttribute("aria-label", `روند ${kpi.label}: ${kpi.spark.length} دورهٔ اخیر`);
        trailing.appendChild(spark);
    }
    if (trailing.childElementCount) head.appendChild(trailing);

    const value = document.createElement("span");
    value.className = "dashboard-kpi-value";
    value.textContent = kpi.display;
    // A shortened amount keeps its exact figure one hover away, and a
    // screen reader hears the exact one.
    if (kpi.full_display) {
        value.title = kpi.full_display;
        value.setAttribute("aria-label", kpi.full_display);
    }

    body.append(head, value);
    if (kpi.caption) {
        const caption = document.createElement("span");
        caption.className = "kpi-card-caption";
        caption.textContent = kpi.caption;
        body.appendChild(caption);
    }

    card.appendChild(body);
    column.appendChild(card);
    return {column, spark};
}

/** The change chip: an arrow and a sign as well as the colour, so the
 * direction never rests on colour alone. */
function kpiChip(delta) {
    const chip = document.createElement("span");
    chip.className = "kpi-chip";
    chip.dataset.tone = delta.tone || "primary";
    if (delta.direction === "up" || delta.direction === "down") {
        const arrow = document.createElement("i");
        arrow.className = `di-duotone di-arrow-${delta.direction === "up" ? "up" : "down"}`;
        arrow.setAttribute("aria-hidden", "true");
        arrow.appendChild(document.createElement("span")).className = "path1";
        arrow.appendChild(document.createElement("span")).className = "path2";
        chip.appendChild(arrow);
    }
    const text = document.createElement("bdi");
    text.textContent = delta.text;
    chip.appendChild(text);
    return chip;
}

/**
 * One radial-gauge card, the dashboard's own counterpart to `kpiCard`
 * above — same card shell and column width, a ring instead of a bare
 * figure. Returns the pieces `setupDashboardInsights` needs rather than
 * rendering the chart itself, because `renderGaugeChart` has to run
 * *after* the card is in the DOM (ApexCharts measures a real element).
 */
function gaugeCard(gauge) {
    const column = document.createElement("div");
    column.className = "col-sm-6 col-xl-4";

    const card = document.createElement(gauge.url ? "a" : "div");
    card.className = "card card-flush h-100 text-decoration-none"
        + (gauge.url ? " border-hover-primary" : "");
    if (gauge.url) card.href = gauge.url;
    card.dataset.dashboardGauge = gauge.key;

    const body = document.createElement("div");
    body.className = "card-body d-flex flex-column align-items-center text-center py-6";

    const label = document.createElement("span");
    label.className = "text-gray-700 fw-semibold fs-7 mb-2";
    label.textContent = gauge.label;

    const canvas = document.createElement("div");
    canvas.className = "w-100 dashboard-gauge-canvas";
    canvas.setAttribute("role", "img");

    const empty = document.createElement("p");
    empty.className = "text-center text-gray-600 fs-8 py-6 mb-0";
    empty.textContent = "داده‌ای برای این گیج نیست.";
    empty.hidden = true;

    const hint = document.createElement("span");
    hint.className = "text-muted fs-8 mt-1";
    hint.textContent = gauge.hint;

    body.append(label, canvas, empty, hint);
    card.appendChild(body);
    column.appendChild(card);
    return {column, canvas, empty};
}

/**
 * An amount as a smooth area with a count overlaid as bars — one series
 * answering "how much", the other "how many", read together. Apex's own
 * combo-chart mode (the purchased theme's own mixed-chart widgets page): two
 * series, each naming its own `type`, sharing one x-axis.
 *
 * `points` carries the area series exactly as `renderAreaChart` reads it
 * (`{label, value, display}`); `counts` is the bar series, one integer
 * per point, same order — `_sales_trend` (common/dashboard.py) is the one
 * caller today and already returns the two aligned.
 */
function renderMixedChart(chart, empty, points, counts, options = {}) {
    const {ariaLabel = null, summary = "", maxLabels = 8, seriesNames = ["مقدار", "تعداد"]} = options;
    if (!chart || !empty) return;
    chartRedraws.set(chart, () => renderMixedChart(chart, empty, points, counts, options));

    const usable = points.filter((point) => Number.isFinite(point.value));
    if (usable.length < 2) {
        showEmptyChart(chart, empty);
        return;
    }

    const palette = chartPalette();
    const amountColor = options.amountColor || palette[0];
    const countColor = options.countColor || palette[1];
    const displays = usable.map((point) => point.display ?? String(point.value));
    const base = apexBase(300);

    // Apex's own per-series `fill.type` array (`["gradient","solid"]`) is
    // the documented way to gradient-shade one series and leave another
    // solid — and does exactly that for a single area's own fill
    // (`renderAreaChart`, same `gradient` object, above). Combined with a
    // second `bar` series on the same chart it does not: measured live,
    // the bar's own `<path fill>` still points at the area's
    // black-to-transparent gradient def rather than a solid `countColor`,
    // rendering "تعداد فروش" as a near-invisible smudge instead of a
    // green bar (design review, 2026-09-12). Rather than chase which
    // Apex internal combo triggers that, the bar's own fill is set
    // directly once the chart (and every redraw/theme switch) has drawn
    // it — the same "fix what the vendor library gets wrong at the
    // point it's wrong" this codebase already does for FullCalendar and
    // the theme's own broken box-shadow declarations.
    const forceSolidBars = (chartCtx) => {
        chartCtx.el.querySelectorAll(".apexcharts-bar-series path").forEach((bar) => {
            bar.setAttribute("fill", countColor);
            bar.setAttribute("fill-opacity", "1");
        });
    };

    mountApex(chart, empty, {
        ...base,
        chart: {
            ...base.chart,
            type: "line",
            // Apex's drag-to-zoom is on by default for a line/area
            // series, so a reader can already narrow the range and needs
            // a way back (design review, 2026-09-12). Until 2.11.0 that
            // way back was Apex's own toolbar, which could not show the
            // reset icon without also showing a magnifier for the gesture
            // the plot already had. The toolbar is off now and the way
            // back lives in the card header beside the range filter —
            // see `chartResetEvents` and `renderAreaChart`'s copy of this.
            zoom: {enabled: true, type: "x", autoScaleYaxis: true},
            events: {
                mounted: (ctx) => forceSolidBars(ctx),
                updated: (ctx) => forceSolidBars(ctx),
                ...chartResetEvents(options.resetButton, chart),
            },
        },
        series: [
            {name: seriesNames[0], type: "area", data: usable.map((point) => point.value)},
            {name: seriesNames[1], type: "bar", data: counts},
        ],
        colors: [amountColor, countColor],
        dataLabels: {enabled: false},
        stroke: {curve: "smooth", width: [3, 0]},
        fill: {
            type: ["gradient", "solid"],
            gradient: {shadeIntensity: 1, opacityFrom: 0.45, opacityTo: 0, stops: [0, 80, 100]},
            opacity: [1, 1],
        },
        plotOptions: {
            bar: {columnWidth: "35%", borderRadius: 4},
        },
        markers: {size: 0, strokeWidth: 3, hover: {size: 7}},
        legend: {...base.legend, show: true, position: "top", horizontalAlign: "center"},
        xaxis: {
            categories: usable.map((point) => point.label),
            tickAmount: Math.min(maxLabels, usable.length),
            labels: {
                style: {fontFamily: chartFontFamily(), fontSize: "12px"},
                hideOverlappingLabels: true,
                // Deliberately no `trim` option — see the identical
                // comment in `renderAreaChart`'s own copy of this block,
                // above.
                formatter: thinningFormatter(usable.map((point) => point.label), maxLabels),
            },
            axisBorder: {show: false},
            axisTicks: {show: false},
        },
        // Two y-axes, one per series: an amount in the millions and a
        // count in the single digits would otherwise share one scale and
        // flatten the bar series to an invisible sliver at the bottom.
        yaxis: [
            {
                seriesName: seriesNames[0],
                labels: {
                    style: {fontFamily: chartFontFamily(), fontSize: "12px", colors: amountColor},
                    formatter: compactAmount,
                },
            },
            {
                seriesName: seriesNames[1],
                opposite: true,
                forceNiceScale: true,
                labels: {
                    style: {fontFamily: chartFontFamily(), fontSize: "12px", colors: countColor},
                    formatter: (value) => toPersianDigits(String(Math.round(value))),
                },
            },
        ],
        tooltip: {
            ...base.tooltip,
            shared: true,
            y: {
                formatter: (value, {seriesIndex, dataPointIndex}) =>
                    seriesIndex === 0 ? displays[dataPointIndex] : toPersianDigits(String(value)),
            },
        },
    }, ariaLabel);

    if (summary) {
        const note = document.createElement("p");
        note.className = "text-muted fs-7 mt-3 mb-0 text-center";
        note.textContent = summary;
        chart.append(note);
    }
}

/**
 * A radial gauge — one 0–100 figure as a filled ring with the number in
 * its own hollow centre, ApexCharts' `radialBar` type. Product-owner
 * request 2026-09-11: the purchased theme uses this for exactly this
 * shape of number (a rate, a quota, a completion percentage — see
 * `custom/widgets.js`'s "mixed widget 5"/"mixed widget 11" and
 * `widgets/sliders/widget-1.js`) and this panel had never actually drawn
 * one, despite having several numbers of exactly that shape on the
 * dashboard already.
 *
 * `value` is a plain 0–100 number, already computed by the caller from a
 * real ratio — this function only draws it, it invents no rate of its
 * own.
 */
function renderGaugeChart(chart, empty, value, options = {}) {
    const {ariaLabel = null, accent = "primary", label = ""} = options;
    if (!chart || !empty) return;
    chartRedraws.set(chart, () => renderGaugeChart(chart, empty, value, options));

    if (!Number.isFinite(value)) {
        showEmptyChart(chart, empty);
        return;
    }
    const clamped = Math.max(0, Math.min(100, value));

    const style = getComputedStyle(document.documentElement);
    const base = style.getPropertyValue(`--bs-${accent}`).trim() || chartPalette()[0];
    const track = style.getPropertyValue(`--bs-${accent}-light`).trim();
    const ink = chartInk();
    const base320 = apexBase(220);

    mountApex(chart, empty, {
        ...base320,
        chart: {
            ...base320.chart,
            type: "radialBar",
            // The theme's own gauges are sparklines — no axis, no grid,
            // just the ring — and `apexBase`'s grid/tooltip settings mean
            // nothing on a chart with one data point and no plot area.
            sparkline: {enabled: true},
        },
        series: [Math.round(clamped * 10) / 10],
        colors: [base],
        stroke: {lineCap: "round"},
        plotOptions: {
            radialBar: {
                hollow: {margin: 0, size: "65%"},
                track: {background: track, strokeWidth: "100%"},
                dataLabels: {
                    show: true,
                    name: {show: false},
                    value: {
                        show: true,
                        offsetY: 10,
                        fontSize: "28px",
                        fontWeight: 700,
                        color: ink.text,
                        fontFamily: chartFontFamily(),
                        formatter: (raw) => toPersianDigits(String(Math.round(raw))) + "٪",
                    },
                },
            },
        },
        labels: [label],
    }, ariaLabel);
}

/**
 * A tiny trend line inside a KPI tile — no axis, no grid, no tooltip
 * text beyond the raw values, exactly ApexCharts' own `sparkline` mode.
 * Product-owner request 2026-09-11: the tile's own number and the
 * one-line comparison next to it both say "more or less than before";
 * this is the shape of that story, at a glance, before the reader has
 * even read the comparison.
 *
 * Never shown empty: `kpiCard` only calls this when the KPI carried a
 * `spark` array at all, so there is no empty-state to draw here — a
 * missing series is a tile with no spark slot, not a slot with nothing
 * in it.
 */
function renderSparkline(el, values, options = {}) {
    if (!el || !Array.isArray(values) || values.length < 3) return;
    const {accent = "primary"} = options;
    const color = getComputedStyle(document.documentElement).getPropertyValue(`--bs-${accent}`).trim()
        || chartPalette()[0];
    const existing = liveCharts.get(el);
    if (existing) {
        existing.destroy();
        liveCharts.delete(el);
    }
    el.replaceChildren();
    // One smooth stroke over a very soft fill of the same hue, no axes, no
    // shadow, and a dot on the latest point — the figure below is that
    // point (2.40.3). Not animated: a tile redraws on every theme switch.
    const instance = new ApexCharts(el, {
        chart: {height: 36, type: "area", sparkline: {enabled: true}, animations: {enabled: false}, dropShadow: {enabled: false}},
        series: [{data: values}],
        colors: [color],
        stroke: {curve: "smooth", width: 2},
        fill: {type: "solid", opacity: 0.08},
        markers: {
            size: 0,
            discrete: [{seriesIndex: 0, dataPointIndex: values.length - 1, size: 3, fillColor: color, strokeColor: color}],
        },
        tooltip: {enabled: false},
    });
    instance.render();
    liveCharts.set(el, instance);
}

/**
 * Several 0–100 figures as concentric rings in one drawing — ApexCharts'
 * own multi-series `radialBar`, the theme's own pattern for "several
 * shares that together read as one whole"
 * (`src/js/widgets/charts/widget-30.js`). `renderGaugeChart` above draws
 * one ratio; this is its many-ring sibling, for the one place on this
 * panel several ratios are meant to be compared at once — each seller's
 * share of the same month (product-owner request 2026-09-11).
 *
 * `items` is `[{label, value, amount_display}]`, values already 0–100 and
 * already summing to (at most) 100 — this draws what it is given, it
 * does not normalise or invent a remainder ring.
 */
function renderMultiGaugeChart(chart, empty, items, options = {}) {
    const {ariaLabel = null} = options;
    if (!chart || !empty) return;
    chartRedraws.set(chart, () => renderMultiGaugeChart(chart, empty, items, options));

    const usable = items.filter((item) => Number.isFinite(item.value) && item.value > 0);
    if (!usable.length) {
        showEmptyChart(chart, empty);
        return;
    }

    const palette = chartPalette();
    const ink = chartInk();
    const base340 = apexBase(340);

    mountApex(chart, empty, {
        ...base340,
        chart: {...base340.chart, type: "radialBar"},
        series: usable.map((item) => item.value),
        labels: usable.map((item) => item.label),
        colors: usable.map((item, index) => item.color || palette[index % palette.length]),
        stroke: {lineCap: "round"},
        plotOptions: {
            radialBar: {
                // Measured live at the old 18%: the innermost ring's own
                // radius came out to 19.5px, while the two-line total
                // label ("مجموع" + "۱۰۰٪") it sits inside is ~58px tall —
                // three times too small a hollow for what has to fit in
                // it, so the total overlapped the innermost ring's own
                // arc (design review, 2026-09-12). Widened, and the total
                // value's own font shrunk a step, so both lines clear the
                // ring at up to six sellers.
                hollow: {size: "34%"},
                track: {strokeWidth: "88%"},
                dataLabels: {
                    name: {fontSize: "13px", fontFamily: chartFontFamily()},
                    value: {
                        fontSize: "16px",
                        fontWeight: 700,
                        color: ink.text,
                        fontFamily: chartFontFamily(),
                        formatter: (raw) => toPersianDigits(String(Math.round(raw))) + "٪",
                    },
                    total: {
                        show: true,
                        label: "مجموع",
                        color: ink.muted,
                        fontSize: "13px",
                        fontFamily: chartFontFamily(),
                        formatter: () =>
                            toPersianDigits(String(Math.round(usable.reduce((sum, item) => sum + item.value, 0)))) + "٪",
                    },
                },
            },
        },
        legend: {
            ...base340.legend,
            show: true,
            position: "bottom",
            formatter: (label, opts) => {
                const item = usable[opts.seriesIndex];
                return `${label} — ${item.amount_display ?? ""}`;
            },
        },
    }, ariaLabel);
}
