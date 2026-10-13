import {toPersianDigits} from "dolphin/core/digits.js";

/**
 * One list or calendar widget (`common.dashboard_panels`): a card with a
 * header, and either a short list of real rows, a Jalali day, or a month
 * grid. Same card shell as `kpiCard`, so it sizes, moves and hides with
 * the rest; the row count it shows follows the box's height through
 * `--dashboard-min-height`, and the text scales with its width through
 * the container query in the panel stylesheet.
 */
export function panelCard(panel) {
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
export function kpiCard(kpi) {
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
    // And only beside a comparison (2.40.38): with no earlier period to compare
    // (`delta` absent) the caption says there was nothing before, and a line
    // with a peak in it contradicted it.
    const history = Array.isArray(kpi.spark) ? kpi.spark.slice(0, -1) : [];
    if (Array.isArray(kpi.spark) && kpi.spark.length >= 3 && kpi.delta && history.some((value) => Number(value) !== 0)) {
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
export function gaugeCard(gauge) {
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
