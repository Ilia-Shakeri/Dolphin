import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDay} from "dolphin/core/jalali.js";
import {showError} from "dolphin/core/messages.js";
import {apexBase, chartFontFamily, chartInk, chartPalette, chartRedraws, chartResetButton, chartResetEvents, liveCharts, mountApex, renderDonutChart, showEmptyChart, thinningFormatter} from "dolphin/ui/charts.js";
import {setupPerformancePanel} from "dolphin/ui/performance.js";
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
        [`/sales/?lead=${lead.id}`, "ثبت فروش"],
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
    await load();
}

export async function setupDashboard() {
    // The editor starts once the insight grid has been placed — it
    // needs those boxes in the DOM to arrange them — but it no longer
    // depends on that grid having anything in it (2.18.1, see
    // `setupDashboardInsights`' return value).
    const insights = setupDashboardInsights().then((grid) => {
        if (grid) setupDashboardEditor(grid);
    });
    await Promise.all([setupWorkQueue(), setupPerformancePanel("dashboard"), insights]);
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
            mount: () => {},
        });
    });

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
    const placed = new Set();
    (layout.order || []).forEach((key) => {
        const widget = widgets.get(key);
        if (!widget || placed.has(key)) return;
        placed.add(key);
        placeDashboardWidget(grid, widget);
    });
    widgets.forEach((widget, key) => {
        if (placed.has(key)) return;
        placed.add(key);
        placeDashboardWidget(grid, widget);
    });

    // Mounted after every column is in the DOM, same rule as every other
    // chart here — Apex measures a real element's width, and a freshly
    // created node not yet attached has none.
    widgets.forEach((widget) => widget.mount());
    widgets.forEach((widget) => fitWidgetChart(widget.column));

    return pageState ? {grid, widgets, layout, hiddenAvailable} : null;
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
    if (!host || column.dataset.chartFit) return;
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
 * Put one widget's column into the grid at its chosen width.
 *
 * The width is the Bootstrap column classes the server resolved from
 * `WIDGET_SIZES` (common/dashboard_layout.py), so the browser never
 * holds a second copy of that mapping — a size added on the Python side
 * needs no change here.
 */
function placeDashboardWidget(grid, widget) {
    const column = widget.column;
    column.className = `dashboard-widget ${widget.size || "col-12 col-sm-6 col-xl-3"}`;
    column.dataset.widgetKey = widget.key;
    // A reader-chosen minimum height (2.18.4, `WIDGET_HEIGHTS`), or none.
    if (widget.height) column.style.setProperty("--dashboard-min-height", widget.height);
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
    // Only what this reader hid themselves can be put back. A widget
    // this deployment's default hides never reached the payload, so it
    // is not in `widgets` and cannot be listed here either.
    let hidden = (layout.hidden || []).filter((key) => !(layout.locked_hidden || []).includes(key));
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

    async function save(body) {
        try {
            const saved = await apiRequest("/api/v1/dashboard-layout/", {method: "POST", body});
            if (saved && Array.isArray(saved.sizes) && saved.sizes.length) sizeChoices = saved.sizes;
            if (reset) reset.hidden = !editing || !saved || !saved.is_customised;
        } catch (error) {
            // The arrangement is already applied on screen; saying so
            // and leaving it is better than snapping every widget back
            // while the reader is mid-edit. The next page load shows
            // whatever the server actually holds.
            showError(error);
        }
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
        return save({hidden_widgets: hidden});
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
        return save({hidden_widgets: hidden});
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
            if (addWidgetAdded) window.location.reload();
        });
    }

    /** Apply a width token to a box on screen and remember it. */
    function applySize(column, key, token) {
        if (sizes[key] === token) return false;
        const classes = (sizeChoices.find((choice) => choice.value === token) || {}).classes;
        if (!classes) return false;
        sizes = {...sizes, [key]: token};
        const keep = ["editing", "resizing", "dragging"].filter((name) => column.classList.contains(name));
        column.className = ["dashboard-widget", ...keep, classes].join(" ");
        return true;
    }

    /** Apply a height token — or `null`, the box's own content height —
     * to a box on screen and remember it. */
    function applyHeight(column, key, token) {
        if ((heights[key] || null) === token) return false;
        const next = {...heights};
        if (token) next[key] = token; else delete next[key];
        heights = next;
        const length = token ? (heightChoices.find((choice) => choice.value === token) || {}).length : null;
        if (length) column.style.setProperty("--dashboard-min-height", length);
        else column.style.removeProperty("--dashboard-min-height");
        fitAllCharts();
        return true;
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

    /** The nearest height step to `px` — or `null` when that is not
     * taller than the box's own content. A minimum height below what the
     * box already holds would be a size in name only. */
    function heightTokenAt(px, naturalPx) {
        if (px <= naturalPx + 4) return null;
        const rem = remPixels();
        let best = null;
        let distance = Infinity;
        heightChoices.forEach((choice) => {
            const candidate = parseFloat(choice.length) * rem;
            if (candidate <= naturalPx) return;
            const gap = Math.abs(candidate - px);
            if (gap < distance) { distance = gap; best = choice.value; }
        });
        return best;
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
        const saved = column.style.getPropertyValue("--dashboard-min-height");
        column.style.removeProperty("--dashboard-min-height");
        let height = card.getBoundingClientRect().height;
        if (saved) column.style.setProperty("--dashboard-min-height", saved);
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
                        save({widget_sizes: sizes, widget_heights: heights});
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
            const steps = [null, ...heightChoices.map((choice) => choice.value)];
            const natural = naturalHeight(column);
            const rem = remPixels();
            const usable = steps.filter((step) => step === null
                || parseFloat((heightChoices.find((choice) => choice.value === step) || {}).length) * rem > natural);
            const at = Math.max(0, usable.indexOf(heights[key] || null));
            const next = Math.min(usable.length - 1, Math.max(0, at + (event.key === "ArrowDown" ? 1 : -1)));
            handled = applyHeight(column, key, usable[next]);
        } else {
            return;
        }
        event.preventDefault();
        if (handled) save({widget_sizes: sizes, widget_heights: heights});
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
                if (moved) save({widget_order: currentOrder()});
            }
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
        editing = next;
        toggle.setAttribute("aria-pressed", String(editing));
        // Solid while editing, not the light tint it used to take — the
        // pencil is the one control that says which mode the page is in.
        toggle.classList.toggle("btn-primary", editing);
        toggle.classList.toggle("btn-light", !editing);
        // The page-level half of the edit-mode look (dolphin.css §9):
        // everything that is not being arranged steps back.
        document.body.classList.toggle("dashboard-editing", editing);
        if (hint) hint.hidden = !editing;
        if (done) done.hidden = !editing;
        if (reset) reset.hidden = !editing || !layout.is_customised;
        if (addWidgetOpen) addWidgetOpen.hidden = !editing;
        if (editing) enterEditing(); else leaveEditing();
    }

    toggle.addEventListener("click", () => setEditing(!editing));
    if (done) done.addEventListener("click", () => setEditing(false));
    // Escape leaves edit mode, as it leaves every other mode in this
    // panel — unless a dialog is open, which Escape closes first.
    document.addEventListener("keydown", (event) => {
        if (editing && event.key === "Escape" && !document.querySelector("dialog[open]")) setEditing(false);
    });
    if (reset) {
        reset.addEventListener("click", async () => {
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

function kpiCard(kpi) {
    const column = document.createElement("div");
    column.className = "col-sm-6 col-xl-3";

    // A link when the figure has somewhere to go, a plain card when it
    // does not — rather than an anchor with a dead href.
    const card = document.createElement(kpi.url ? "a" : "div");
    card.className = "card card-flush h-100 text-decoration-none"
        + (kpi.url ? " border-hover-primary" : "");
    if (kpi.url) card.href = kpi.url;
    // Deliberately not `data-kpi`: the performance panel further down
    // this same page already owns that attribute for its own four
    // figures, and one selector meaning two different things is a trap
    // for the next reader (and for a test that queries it).
    card.dataset.dashboardKpi = kpi.key;

    const body = document.createElement("div");
    body.className = "card-body d-flex flex-column justify-content-between py-6";

    const top = document.createElement("div");
    top.className = "d-flex align-items-center justify-content-between mb-4";
    const symbol = document.createElement("span");
    // Bigger and bolder than before (product-owner request 2026-09-11,
    // "رنگی و جذاب" — colourful and eye-catching): 50px/fs-1 rather than
    // 40px/fs-2, the theme's own next size step up, not an arbitrary one.
    symbol.className = "symbol symbol-50px";
    const symbolLabel = document.createElement("span");
    symbolLabel.className = `symbol-label bg-light-${kpi.accent}`;
    const icon = document.createElement("i");
    icon.className = `di-duotone ${kpi.icon} fs-1 text-${kpi.accent}`;
    // Per-glyph path count, sent by the server for the same reason the
    // reminder bell and the timeline take it from there.
    for (let index = 1; index <= (kpi.icon_paths || 2); index += 1) {
        const path = document.createElement("span");
        path.className = `path${index}`;
        icon.appendChild(path);
    }
    symbolLabel.appendChild(icon);
    symbol.appendChild(symbolLabel);
    top.appendChild(symbol);

    const value = document.createElement("span");
    value.className = "dashboard-kpi-value text-gray-900 fw-bolder lh-1";
    value.textContent = kpi.display;

    const label = document.createElement("span");
    label.className = "dashboard-kpi-label text-gray-700 fw-semibold mt-2";
    label.textContent = kpi.label;

    // A month/week-over-month change reads its direction from a sentence
    // ("۱۲٪ کمتر از...") alone otherwise — the theme's own stat widgets
    // (widgets/statistics.html) pair that sentence with an arrow colour
    // so the direction reads before the words do. Only drawn when the
    // backend actually computed one (`_change_direction`, common/
    // dashboard.py) — a KPI with no month-over-month base (e.g. مطالبات
    // باز) keeps its plain hint rather than a fabricated arrow.
    const hint = document.createElement("span");
    hint.className = "d-flex align-items-center gap-1 fs-8 mt-1";
    if (kpi.direction === "up" || kpi.direction === "down") {
        const isUp = kpi.direction === "up";
        const arrow = document.createElement("i");
        arrow.className = `di-duotone di-arrow-${isUp ? "up" : "down"} fs-7 text-${isUp ? "success" : "danger"}`;
        arrow.appendChild(document.createElement("span")).className = "path1";
        arrow.appendChild(document.createElement("span")).className = "path2";
        const text = document.createElement("span");
        text.className = "text-muted";
        text.textContent = kpi.hint;
        hint.append(arrow, text);
    } else {
        hint.classList.add("text-muted");
        hint.textContent = kpi.hint;
    }

    body.append(top, value, label, hint);

    // The spark slot only exists when there is something to put in it —
    // an empty 36px strip under every tile, spark or not, would be a
    // blank gap on the three-quarters of KPIs that have no cheap series
    // to draw one from.
    let spark = null;
    if (kpi.spark) {
        spark = document.createElement("div");
        spark.className = "kpi-sparkline mt-3";
        body.appendChild(spark);
    }

    card.appendChild(body);
    column.appendChild(card);
    return {column, spark};
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
                    formatter: (value) => toPersianDigits(String(Math.round(value))),
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
    if (!el || !Array.isArray(values) || values.length < 2) return;
    const {accent = "primary"} = options;
    const color = getComputedStyle(document.documentElement).getPropertyValue(`--bs-${accent}`).trim()
        || chartPalette()[0];
    const existing = liveCharts.get(el);
    if (existing) {
        existing.destroy();
        liveCharts.delete(el);
    }
    el.replaceChildren();
    const instance = new ApexCharts(el, {
        chart: {height: 36, type: "line", sparkline: {enabled: true}, animations: {enabled: false}},
        series: [{data: values}],
        colors: [color],
        stroke: {curve: "smooth", width: 2},
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
