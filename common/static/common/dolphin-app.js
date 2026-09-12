(() => {
    "use strict";

    const ROLE_LABELS = Object.freeze({
        sales_agent: "بازاریاب (کال سنتر)",
        sales_manager: "مدیر فروشگاه",
        company_it: "مدیر فنی مشتری",
        platform_admin: "مدیر پلتفرم",
    });
    const STATUS_MESSAGES = Object.freeze({
        400: "داده‌های واردشده درست نیست. موارد مشخص‌شده را اصلاح کنید.",
        403: "اجازه انجام این کار را ندارید.",
        404: "مورد درخواستی پیدا نشد.",
        409: "این تغییر با وضعیت فعلی سامانه سازگار نیست.",
        429: "درخواست‌ها بیش از حد مجاز است. کمی بعد دوباره تلاش کنید.",
    });

    class ApiError extends Error {
        constructor(status, payload) {
            super(STATUS_MESSAGES[status] || "خطایی رخ داد. دوباره تلاش کنید.");
            this.status = status;
            this.payload = payload || {};
        }
    }

    function csrfToken() {
        const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    async function apiRequest(url, options = {}) {
        const method = (options.method || "GET").toUpperCase();
        const headers = {Accept: "application/json", ...(options.headers || {})};
        if (!(["GET", "HEAD", "OPTIONS"].includes(method))) {
            headers["X-CSRFToken"] = csrfToken();
        }
        if (options.body !== undefined) {
            if (options.raw) {
                // A FormData body carries its own multipart boundary. Setting
                // Content-Type by hand here would omit that boundary and the
                // upload would arrive unparseable.
                delete options.raw;
            } else {
                headers["Content-Type"] = "application/json";
                options.body = JSON.stringify(options.body);
            }
        }
        const response = await fetch(url, {...options, method, headers, credentials: "same-origin"});
        let payload = null;
        if (response.status !== 204) {
            try { payload = await response.json(); } catch (_) { payload = null; }
        }
        if (!response.ok) throw new ApiError(response.status, payload);
        return payload;
    }

    function globalMessage(message, success = false) {
        const node = document.getElementById("global-message");
        if (!node) return;
        node.textContent = message;
        // The markup ships hard-coded `alert-danger` — right for the far more
        // common error case, wrong for a success message with no matching CSS
        // of its own. `alert-success` is the theme's own real class (`style.
        // bundle.rtl.css` styles it already); this swaps the two rather than
        // toggling a bare `.success` modifier that nothing in the stylesheet
        // has ever answered, which is why every past success message here —
        // "کاربر ذخیره شد" and the rest — still painted the danger red.
        node.classList.toggle("alert-success", success);
        node.classList.toggle("alert-danger", !success);
        node.hidden = false;
        node.focus?.();
    }

    function clearMessages(form) {
        document.getElementById("global-message")?.setAttribute("hidden", "");
        form?.querySelectorAll("[data-error-for]").forEach((node) => { node.textContent = ""; });
    }

    function errorText(error) {
        if (!(error instanceof ApiError)) return "ارتباط با سامانه برقرار نشد. دوباره تلاش کنید.";
        return STATUS_MESSAGES[error.status] || "خطایی رخ داد. دوباره تلاش کنید.";
    }

    /**
     * Turn one field's error payload into a sentence a reader can act on.
     *
     * DRF nests. A plain field gives `["..."]`, but a nested serializer used
     * with `many=True` — the split-allocation form is one — gives a list of
     * per-row objects like `[{invoice: ["..."]}]`. Joining that list directly
     * printed the literal text `[object Object]` where the reason should be,
     * which told the operator nothing and looked like a crash.
     *
     * Walking the structure instead means any shape DRF produces comes out as
     * readable text, and a shape nobody anticipated degrades to its own values
     * rather than to a stringified object.
     */
    function flattenErrorValue(value) {
        if (value === null || value === undefined) return "";
        if (Array.isArray(value)) {
            return value.map(flattenErrorValue).filter(Boolean).join(" ");
        }
        if (typeof value === "object") {
            return Object.values(value).map(flattenErrorValue).filter(Boolean).join(" ");
        }
        return String(value);
    }

    function showError(error, form = null) {
        if (error instanceof ApiError && error.payload?.error?.code === "authentication_failed") {
            window.location.assign("/login/");
            return;
        }
        let hasFieldError = false;
        if (form && error instanceof ApiError && error.payload && typeof error.payload === "object") {
            form.querySelectorAll("[data-error-for]").forEach((node) => {
                const value = error.payload[node.dataset.errorFor];
                if (value !== undefined) {
                    node.textContent = flattenErrorValue(value);
                    hasFieldError = true;
                }
            });
        }
        globalMessage(hasFieldError && error.status === 400 ? STATUS_MESSAGES[400] : errorText(error));
    }

    function formPayload(form, names) {
        const data = new FormData(form);
        return Object.fromEntries(names.map((name) => [name, String(data.get(name) || "")]));
    }

    async function withSubmit(form, task) {
        clearMessages(form);
        const button = form.querySelector("button[type='submit']");
        button.disabled = true;
        try { await task(); } catch (error) { showError(error, form); } finally { button.disabled = false; }
    }

    /**
     * Keep `aria-expanded` truthful on the sidebar toggle.
     *
     * Opening and closing the sidebar itself is the theme's drawer
     * (`data-kt-drawer-toggle="#nav-toggle"`); this only mirrors that state
     * into the attribute a screen reader reads, which the drawer does not set.
     */
    function setupNav() {
        const toggle = document.getElementById("nav-toggle");
        const sidebar = document.getElementById("app-sidebar");
        if (!toggle || !sidebar) return;
        const sync = () => toggle.setAttribute("aria-expanded", String(sidebar.classList.contains("drawer-on")));
        new MutationObserver(sync).observe(sidebar, {attributes: true, attributeFilter: ["class"]});
        sync();
    }

    /**
     * Mark the sidebar entry the current page belongs to.
     *
     * The theme's own classes do the work: `.menu-link.active` colours the
     * entry, and `.here.show` on a parent `.menu-accordion` both opens it and
     * colours its title — so an entry inside a group lights up together with
     * its group, which is what the product asks for.
     *
     * Matching is by longest URL prefix rather than by an id per page, so a
     * detail route (`/customers/12/`) lights up the list entry it came from and
     * a page added later needs nothing here. Exactly one group is ever open:
     * the one containing the current page, or none on the dashboard.
     */
    function setupNavActiveState() {
        const sidebar = document.getElementById("app-sidebar");
        if (!sidebar) return;
        // Normally the current URL, but a page may name the entry it belongs to
        // instead. Receipts and disbursements are one document behind one detail
        // route, so `/payments/12/` prefix-matches «دریافت‌ها» whichever desk it
        // was opened from — and a disbursement lit the wrong entry. The page
        // knows its own direction server-side; this lets it say so.
        const path = document.body.dataset.navMatch || window.location.pathname;

        let best = null;
        let bestLength = -1;
        for (const link of sidebar.querySelectorAll(".menu-link[href]")) {
            const href = new URL(link.getAttribute("href"), window.location.origin).pathname;
            // "/" would otherwise prefix-match every page, so the dashboard
            // matches only itself.
            const matches = href === "/" ? path === "/" : path.startsWith(href);
            if (matches && href.length > bestLength) {
                best = link;
                bestLength = href.length;
            }
        }
        if (!best) return;

        for (const item of sidebar.querySelectorAll(".menu-item.menu-accordion")) {
            item.classList.remove("here", "show");
        }
        for (const link of sidebar.querySelectorAll(".menu-link.active")) {
            link.classList.remove("active");
        }

        best.classList.add("active");
        best.setAttribute("aria-current", "page");
        const group = best.closest(".menu-item.menu-accordion");
        if (group) {
            group.classList.add("here", "show");
        }
    }

    /**
     * Scroll a sidebar accordion group into view once it opens.
     *
     * `.menu-item.menu-accordion` groups (`base.html`) toggle open/closed
     * through the theme's own KTMenu (`data-kt-menu-trigger="click"`), which
     * animates `.show`/height but never scrolls the sidebar's own KTScroll
     * viewport (`#kt_app_sidebar_menu_scroll`) to follow it — so a group near
     * the bottom of a long menu (e.g. «مدیریت سامانه») opens its submenu
     * mostly or entirely below the fold, and reaching it means scrolling by
     * hand every time (product-owner request 2026-09-12).
     *
     * A fixed delay rather than a transitionend listener: KTMenu animates
     * height via its own timing, not a CSS transition this code can attach
     * to, and 300ms comfortably covers it without waiting on an event that
     * never fires.
     */
    function setupSidebarAccordionScroll() {
        const sidebar = document.getElementById("app-sidebar");
        const scroller = document.getElementById("kt_app_sidebar_menu_scroll");
        if (!sidebar || !scroller) return;

        sidebar.addEventListener("click", (event) => {
            const link = event.target.closest(".menu-item.menu-accordion > .menu-link");
            if (!link || !scroller.contains(link)) return;
            const group = link.closest(".menu-item.menu-accordion");
            window.setTimeout(() => {
                if (group.classList.contains("show")) {
                    group.scrollIntoView({behavior: "smooth", block: "nearest"});
                }
            }, 300);
        });
    }

    /**
     * Open and close the header user menu.
     *
     * The theme owns how the panel looks and its `.show` rule; KTMenu would
     * normally toggle that class and position the panel with Popper, which
     * lives in the plugins bundle this deployment does not load. Toggling the
     * class here is the whole of what was missing — placement is two CSS lines
     * in dolphin.css.
     */
    function setupUserMenu() {
        const toggle = document.getElementById("user-menu-toggle");
        const menu = document.getElementById("user-menu");
        if (!toggle || !menu) return;

        const setOpen = (open) => {
            menu.classList.toggle("show", open);
            toggle.setAttribute("aria-expanded", String(open));
        };

        toggle.addEventListener("click", (event) => {
            event.stopPropagation();
            setOpen(!menu.classList.contains("show"));
        });
        // A menu that stays open after the pointer moves on is a menu in the
        // way, so anywhere outside it closes it, and Escape returns focus.
        document.addEventListener("click", (event) => {
            if (!menu.contains(event.target)) setOpen(false);
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && menu.classList.contains("show")) {
                setOpen(false);
                toggle.focus();
            }
        });
    }

    /**
     * A list card's own "فیلتر" panel — same open/close shape as
     * `setupUserMenu` right above (manual `[hidden]` toggle, close on an
     * outside click or Escape, placement in CSS) for the same reason: no
     * Popper in this build. `toggle` carries `aria-expanded`; `.list-filter-
     * toggle[aria-expanded="true"]` in dolphin.css gives it the pressed look
     * KTMenu's own `.show` would have.
     *
     * The panel's own form still submits normally (`setupPagedList`'s own
     * `form.addEventListener("submit", ...)` above) — only the search box
     * beside this button went live; everything in here stays an explicit
     * "اعمال" the reader chooses, since these are heavier filters (a status,
     * a date window) a reader is still composing keystroke by keystroke.
     */
    function setupListFilter(key) {
        const toggle = document.getElementById(`${key}-filter-toggle`);
        const panel = document.getElementById(`${key}-filter-panel`);
        if (!toggle || !panel) return;

        const setOpen = (open) => {
            panel.hidden = !open;
            toggle.setAttribute("aria-expanded", String(open));
        };

        toggle.addEventListener("click", (event) => {
            event.stopPropagation();
            setOpen(panel.hidden);
        });
        document.addEventListener("click", (event) => {
            if (!panel.hidden && !panel.contains(event.target) && event.target !== toggle) setOpen(false);
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && !panel.hidden) {
                setOpen(false);
                toggle.focus();
            }
        });
        // Applying a filter closes the panel — the reader chose one, no
        // reason to keep it open over the now-refreshed list.
        panel.querySelector("form")?.addEventListener("submit", () => setOpen(false));
    }

    /**
     * The signed-in user's own sessions, opened from the header user menu.
     *
     * Every row is identified by the opaque reference the server sends; the
     * session key never reaches the browser, so nothing here could be replayed
     * as a credential even if the page were captured. The user's current
     * session is marked and cannot be ended from this dialog — signing yourself
     * out of the page you are using is never what "end this session" means.
     */
    function setupSessionsDialog() {
        const dialog = document.getElementById("sessions-dialog");
        const open = document.getElementById("open-sessions");
        if (!dialog || !open) return;
        const body = document.getElementById("sessions-table-body");
        const wrap = document.getElementById("sessions-table-wrap");
        const loading = document.getElementById("sessions-loading");
        const empty = document.getElementById("sessions-empty");
        const revokeOthers = document.getElementById("revoke-other-sessions");
        const close = document.getElementById("close-sessions");

        async function load() {
            loading.hidden = false;
            wrap.hidden = true;
            empty.hidden = true;
            try {
                const data = await apiRequest("/api/v1/auth/me/sessions/");
                const others = data.results.filter((item) => !item.is_current);
                body.replaceChildren(...data.results.map((item) => {
                    const row = document.createElement("tr");
                    appendCell(row, describeDevice(item.user_agent));
                    appendCell(row, item.ip_address || "—").dir = "ltr";
                    appendCell(row, item.started_at ? displayDate(item.started_at) : "—");
                    appendCell(row, displayDate(item.expires_at));
                    const actions = document.createElement("td");
                    if (item.is_current) {
                        const badge = document.createElement("span");
                        badge.className = "badge badge-light-success";
                        badge.textContent = "نشست فعلی";
                        actions.append(badge);
                    } else {
                        const button = document.createElement("button");
                        button.className = "btn btn-sm btn-light-danger";
                        button.type = "button";
                        button.textContent = "پایان";
                        button.addEventListener("click", () => revoke(item.reference, button));
                        actions.append(button);
                    }
                    row.append(actions);
                    return row;
                }));
                loading.hidden = true;
                empty.hidden = data.results.length > 0;
                wrap.hidden = data.results.length === 0;
                revokeOthers.disabled = others.length === 0;
            } catch (error) {
                loading.hidden = true;
                showError(error);
            }
        }

        async function revoke(reference, button) {
            button.disabled = true;
            clearMessages();
            try {
                await apiRequest("/api/v1/auth/me/sessions/", {method: "POST", body: {reference}});
                globalMessage("نشست پایان یافت.", true);
                await load();
            } catch (error) {
                button.disabled = false;
                showError(error);
            }
        }

        revokeOthers.addEventListener("click", async () => {
            if (!window.confirm("همه نشست‌های دیگر شما پایان یابد؟")) return;
            revokeOthers.disabled = true;
            clearMessages();
            try {
                const result = await apiRequest("/api/v1/auth/me/sessions/", {method: "POST", body: {}});
                globalMessage(`${result.ended} نشست پایان یافت.`, true);
                await load();
            } catch (error) {
                revokeOthers.disabled = false;
                showError(error);
            }
        });

        open.addEventListener("click", () => {
            dialog.showModal();
            load();
        });
        close.addEventListener("click", () => dialog.close());
    }

    /**
     * A user agent string reduced to something a person recognises.
     *
     * Deliberately coarse: the point is "is this me on my own machine", not
     * device fingerprinting, and a full user agent string on screen tells the
     * reader nothing they can act on.
     */
    function describeDevice(userAgent) {
        const text = String(userAgent || "");
        if (!text) return "—";
        const platform =
            /Windows/i.test(text) ? "ویندوز"
            : /Android/i.test(text) ? "اندروید"
            : /(iPhone|iPad|iOS)/i.test(text) ? "iOS"
            : /Mac OS X/i.test(text) ? "مک"
            : /Linux/i.test(text) ? "لینوکس"
            : "نامشخص";
        const browser =
            /Edg\//i.test(text) ? "Edge"
            : /OPR\//i.test(text) ? "Opera"
            : /Chrome\//i.test(text) ? "Chrome"
            : /Firefox\//i.test(text) ? "Firefox"
            : /Safari\//i.test(text) ? "Safari"
            : "مرورگر";
        return `${browser} — ${platform}`;
    }

    function setupLogout() {
        const form = document.getElementById("logout-form");
        if (!form) return;
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                await apiRequest(form.action, {method: "POST"});
                window.location.assign("/login/");
            });
        });
    }

    function setupLogin() {
        const form = document.getElementById("login-form");
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                await apiRequest(form.action, {method: "POST", body: formPayload(form, ["username", "password"])});
                window.location.assign("/");
            });
        });
    }

    async function setupProfile() {
        const form = document.getElementById("profile-form");
        const loading = document.getElementById("profile-loading");
        try {
            const user = await apiRequest("/api/v1/auth/me/");
            document.getElementById("profile-username").value = user.username;
            document.getElementById("profile-role").value = ROLE_LABELS[user.role];
            ["first_name", "last_name", "email", "phone"].forEach((name) => {
                document.getElementById(`profile-${name.replaceAll("_", "-")}`).value = user[name] || "";
            });
            loading.hidden = true;
            form.hidden = false;
        } catch (error) {
            loading.hidden = true;
            showError(error);
            return;
        }
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                await apiRequest(form.action, {method: "PATCH", body: formPayload(form, ["first_name", "last_name", "email", "phone"])});
                globalMessage("پروفایل ذخیره شد.", true);
            });
        });
    }

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

    async function setupDashboard() {
        await Promise.all([setupWorkQueue(), setupPerformancePanel("dashboard"), setupDashboardInsights()]);
    }

    /**
     * The role's own KPI strip, sales trend and status breakdown.
     *
     * Every part is optional and the server decides which parts exist: a
     * reader who may not see sales gets no trend, and this draws nothing
     * rather than an empty card promising a chart that will never arrive.
     * The whole section stays hidden until at least one part came back, so
     * a deployment with none of the sources looks exactly as it did before
     * this was added.
     *
     * Charts reuse the shared helpers, so they take their colours from the
     * theme's own CSS variables and redraw themselves on a light/dark
     * switch like every other chart in the panel.
     */
    async function setupDashboardInsights() {
        const section = document.getElementById("dashboard-insights");
        if (!section) return;
        let data;
        try {
            data = await apiRequest("/api/v1/dashboard/");
        } catch (error) {
            // The tiles, the work queue and the performance panel above are
            // what this page is; a failed side panel must not replace them
            // with an error card.
            return;
        }

        // Unhidden *before* any chart mounts, not after. ApexCharts measures
        // its container at render time, and a container inside a
        // `display: none` ancestor measures zero — the chart then draws at
        // zero width and never recovers on its own. This project has already
        // paid for that once (1.7.19, "chart mounts at zero width"); the
        // section is revealed first and the parts fill in behind it.
        section.hidden = false;

        const strip = document.getElementById("dashboard-kpis");
        data.kpis.forEach((kpi) => {
            const {column, spark} = kpiCard(kpi);
            strip.appendChild(column);
            // Mounted after the column is in the DOM, same rule as every
            // other chart here — Apex measures a real element's width, and a
            // freshly created node not yet attached has none.
            if (spark && kpi.spark) renderSparkline(spark, kpi.spark, {accent: kpi.accent});
        });

        const gaugeRow = document.getElementById("dashboard-gauges");
        (data.gauges || []).forEach((gauge) => {
            const {column, canvas, empty} = gaugeCard(gauge);
            gaugeRow.appendChild(column);
            renderGaugeChart(canvas, empty, gauge.value, {
                ariaLabel: `${gauge.label}: ${gauge.display}`,
                accent: gauge.accent,
                label: gauge.label,
            });
        });

        if (data.trend) {
            const card = document.getElementById("dashboard-trend-card");
            document.getElementById("dashboard-trend-title").textContent = data.trend.title;
            document.getElementById("dashboard-trend-summary").textContent = data.trend.summary;
            card.hidden = false;
            // Mixed rather than a bare area: `_sales_trend` (common/
            // dashboard.py) now returns the same twelve weeks' order count
            // alongside the amount, and a reader asking "how is sales doing"
            // usually means both.
            renderMixedChart(
                document.getElementById("dashboard-trend-chart"),
                document.getElementById("dashboard-trend-empty"),
                data.trend.points,
                data.trend.counts,
                {seriesNames: ["مبلغ فروش", "تعداد فروش"], summary: data.trend.summary, ariaLabel: data.trend.title},
            );
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
            renderMultiGaugeChart(
                document.getElementById("dashboard-agent-share-chart"),
                document.getElementById("dashboard-agent-share-empty"),
                data.agent_share.items,
                {ariaLabel: data.agent_share.title},
            );
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
            renderDonutChart(
                document.getElementById("dashboard-breakdown-chart"),
                document.getElementById("dashboard-breakdown-empty"),
                data.breakdown.items,
                {ariaLabel: data.breakdown.title},
            );
        }

        // Nothing to show after all: put it back, so a deployment with none
        // of the sources renders exactly the page it rendered before this
        // section existed.
        if (
            !data.kpis.length && !data.trend && !data.breakdown
            && !(data.gauges || []).length && !data.agent_share
        ) {
            section.hidden = true;
        }
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
        icon.className = `ki-duotone ${kpi.icon} fs-1 text-${kpi.accent}`;
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
        value.className = "text-gray-900 fw-bolder fs-2hx lh-1";
        value.textContent = kpi.display;

        const label = document.createElement("span");
        label.className = "text-gray-700 fw-semibold fs-7 mt-2";
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
            arrow.className = `ki-duotone ki-arrow-${isUp ? "up" : "down"} fs-7 text-${isUp ? "success" : "danger"}`;
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
        canvas.className = "w-100";
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

    function userRow(user) {
        const row = document.createElement("tr");
        const displayName = [user.first_name, user.last_name].filter(Boolean).join(" ") || "—";
        const workstream = user.workstream === "after_sales" ? "خدمات پس از فروش" : "فروش و مرکز تماس";
        const cells = [user.username, displayName, `${ROLE_LABELS[user.role] || "—"} — ${workstream}`];
        cells.forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.appendChild(cell); });
        const statusCell = document.createElement("td");
        const status = document.createElement("span");
        status.className = `status${user.is_active ? " status-active" : ""}`;
        status.textContent = user.is_active ? "فعال" : "غیرفعال";
        statusCell.appendChild(status);
        row.appendChild(statusCell);
        const actionCell = document.createElement("td");
        actionCell.className = "row-actions";
        const profileLink = document.createElement("a");
        profileLink.className = "btn btn-sm btn-light";
        profileLink.href = `/users/${user.id}/profile/`;
        profileLink.textContent = "پروفایل";
        actionCell.appendChild(profileLink);
        const link = document.createElement("a");
        link.className = "btn btn-sm btn-light";
        link.href = `/users/${user.id}/`;
        link.textContent = "جزئیات";
        actionCell.appendChild(link);
        const permissionsButton = document.createElement("button");
        permissionsButton.className = "btn btn-sm btn-light";
        permissionsButton.type = "button";
        permissionsButton.dataset.permissionsButton = "";
        permissionsButton.dataset.userId = String(user.id);
        permissionsButton.dataset.userName = displayName === "—" ? user.username : displayName;
        permissionsButton.textContent = "مجوزها";
        actionCell.appendChild(permissionsButton);
        row.appendChild(actionCell);
        return row;
    }

    function setupUsers() {
        const searchInput = document.getElementById("user-search");
        const tableWrap = document.getElementById("users-table-wrap");
        const tableBody = document.getElementById("users-table-body");
        const loading = document.getElementById("users-loading");
        const empty = document.getElementById("users-empty");
        const pagination = document.getElementById("users-pagination");
        const prev = document.getElementById("users-prev");
        const next = document.getElementById("users-next");
        let currentPage = 1;
        let search = "";
        const selection = setupRowSelection({key: "users", body: tableBody, reload: () => loadUsers(currentPage)});

        async function loadUsers(page = 1) {
            loading.hidden = false;
            empty.hidden = true;
            tableWrap.hidden = true;
            pagination.hidden = true;
            clearMessages();
            selection.resetSelection();
            try {
                const query = new URLSearchParams({page: String(page)});
                if (search) query.set("search", search);
                const data = await apiRequest(`/api/v1/users/?${query}`);
                tableBody.replaceChildren(...data.results.map((item) => selection.decorateRow(item, userRow(item))));
                loading.hidden = true;
                if (!data.results.length) { empty.hidden = false; return; }
                tableWrap.hidden = false;
                currentPage = page;
                prev.disabled = !data.previous;
                next.disabled = !data.next;
                document.getElementById("users-page-label").textContent = pageRangeLabel(data, page);
                pagination.hidden = !data.previous && !data.next;
            } catch (error) {
                loading.hidden = true;
                showError(error);
            }
        }

        bindLiveSearch(searchInput, () => {
            search = searchInput.value.trim();
            loadUsers(1);
        });
        prev.addEventListener("click", () => loadUsers(currentPage - 1));
        next.addEventListener("click", () => loadUsers(currentPage + 1));

        const dialog = document.getElementById("create-user-dialog");
        const createForm = document.getElementById("create-user-form");
        function renderCreateUserReview() {
            renderWizardReview(document.getElementById("create-user-review"), [
                ["نام کاربری", document.getElementById("create-username").value],
                ["گذرواژه", "•".repeat(Math.min(document.getElementById("create-password").value.length, 12)) || "—"],
                ["نام", document.getElementById("create-first-name").value || "—"],
                ["نام خانوادگی", document.getElementById("create-last-name").value || "—"],
                ["ایمیل", document.getElementById("create-email").value || "—"],
                ["تلفن", document.getElementById("create-phone").value || "—"],
                ["نقش", selectedOptionText(document.getElementById("create-role"))],
                ["حوزه کاری", selectedOptionText(document.getElementById("create-workstream"))],
            ]);
        }
        const createUserWizard = setupWizard(dialog, {onReachLastStep: renderCreateUserReview});
        document.getElementById("open-create-user").addEventListener("click", () => {
            createForm.reset();
            clearMessages(createForm);
            syncCreateWorkstream();
            createUserWizard?.goFirst();
            dialog.showModal();
        });
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));

        // Only a Sales Agent may run the after-sales workstream — the same
        // rule `fillUser` enforces on the edit form, applied here so picking
        // any other role locks the field back to the ordinary sales queue
        // instead of letting the create call fail on it.
        const createRole = document.getElementById("create-role");
        const createWorkstream = document.getElementById("create-workstream");
        function syncCreateWorkstream() {
            const afterSalesOption = createWorkstream.querySelector('option[value="after_sales"]');
            const isAgent = createRole.value === "sales_agent";
            afterSalesOption.disabled = !isAgent;
            if (!isAgent) createWorkstream.value = "sales";
        }
        createRole.addEventListener("change", syncCreateWorkstream);
        syncCreateWorkstream();

        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const user = await apiRequest(createForm.action, {
                    method: "POST",
                    body: formPayload(createForm, ["username", "password", "first_name", "last_name", "email", "phone", "role", "workstream"]),
                });
                window.location.assign(`/users/${user.id}/`);
            });
        });

        setupPermissionsDialog();
        tableBody.addEventListener("click", (event) => {
            const button = event.target.closest("[data-permissions-button]");
            if (!button) return;
            openPermissionsDialog(button.dataset.userId, button.dataset.userName);
        });

        loadUsers();
    }

    /**
     * The "Permissions" modal: view mode first, an explicit "Edit
     * Permissions" step before anything becomes editable, and the
     * edit-implies-read rule enforced live as the two checkboxes on a row
     * are ticked — matching the server-side rule in
     * `accounts.module_permissions.validate_matrix` so nothing the UI
     * allows can ever be rejected by the save call for that reason.
     */
    function setupPermissionsDialog() {
        const dialog = document.getElementById("permissions-dialog");
        if (!dialog) return;
        const loading = document.getElementById("permissions-loading");
        const body = document.getElementById("permissions-body");
        const errorBox = document.getElementById("permissions-error");
        const tableBody = document.getElementById("permissions-table-body");
        const customNote = document.getElementById("permissions-custom-note");
        const nameField = document.getElementById("permissions-user-name");
        const roleField = document.getElementById("permissions-user-role");
        const editButton = document.getElementById("permissions-edit");
        const saveButton = document.getElementById("permissions-save");
        const cancelEditButton = document.getElementById("permissions-cancel-edit");
        const resetButton = document.getElementById("permissions-reset");

        let userId = null;
        let current = null; // last server-confirmed {role, matrix, has_custom_permissions}
        let editing = false;

        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => {
            button.addEventListener("click", () => dialog.close());
        });

        function showError(message) {
            errorBox.textContent = message;
            errorBox.hidden = false;
        }

        function renderRows() {
            const rows = Object.entries(current.matrix).map(([key, entry]) => {
                const row = document.createElement("tr");

                const labelCell = document.createElement("td");
                labelCell.textContent = entry.is_custom ? `${entry.label} *` : entry.label;
                row.appendChild(labelCell);

                const readCell = document.createElement("td");
                readCell.className = "text-center";
                const readInput = document.createElement("input");
                readInput.type = "checkbox";
                readInput.className = "form-check-input";
                readInput.checked = entry.read;
                readInput.disabled = !editing;
                readInput.dataset.module = key;
                readInput.dataset.axis = "read";
                readInput.setAttribute("aria-label", `خواندن — ${entry.label}`);
                readCell.appendChild(readInput);
                row.appendChild(readCell);

                const writeCell = document.createElement("td");
                writeCell.className = "text-center";
                if (entry.supports_write) {
                    const writeInput = document.createElement("input");
                    writeInput.type = "checkbox";
                    writeInput.className = "form-check-input";
                    writeInput.checked = entry.write;
                    writeInput.disabled = !editing;
                    writeInput.dataset.module = key;
                    writeInput.dataset.axis = "write";
                    writeInput.setAttribute("aria-label", `ویرایش — ${entry.label}`);
                    writeCell.appendChild(writeInput);
                } else {
                    writeCell.textContent = "—";
                }
                row.appendChild(writeCell);
                return row;
            });
            tableBody.replaceChildren(...rows);
        }

        function render() {
            nameField.textContent = dialog.dataset.userName || "";
            roleField.textContent = ROLE_LABELS[current.role] || current.role;
            customNote.hidden = !current.has_custom_permissions;
            editButton.hidden = editing;
            saveButton.hidden = !editing;
            cancelEditButton.hidden = !editing;
            renderRows();
        }

        // Edit always implies Read; unchecking Read while Edit is on turns
        // Edit off too — the same rule the server enforces, applied live so
        // the checkboxes never sit in a state the save call would reject.
        tableBody.addEventListener("change", (event) => {
            const input = event.target.closest('input[type="checkbox"]');
            if (!input) return;
            const moduleKey = input.dataset.module;
            const readInput = tableBody.querySelector(`input[data-module="${moduleKey}"][data-axis="read"]`);
            const writeInput = tableBody.querySelector(`input[data-module="${moduleKey}"][data-axis="write"]`);
            if (input.dataset.axis === "write" && input.checked && readInput) {
                readInput.checked = true;
            } else if (input.dataset.axis === "read" && !input.checked && writeInput) {
                writeInput.checked = false;
            }
        });

        function collectMatrix() {
            const matrix = {};
            tableBody.querySelectorAll("tr").forEach((row) => {
                const readInput = row.querySelector('input[data-axis="read"]');
                const writeInput = row.querySelector('input[data-axis="write"]');
                if (!readInput) return;
                matrix[readInput.dataset.module] = {
                    read: readInput.checked,
                    write: writeInput ? writeInput.checked : false,
                };
            });
            return matrix;
        }

        async function load() {
            loading.hidden = false;
            body.hidden = true;
            errorBox.hidden = true;
            editing = false;
            try {
                current = await apiRequest(`/api/v1/users/${userId}/permissions/`);
                loading.hidden = true;
                body.hidden = false;
                render();
            } catch (error) {
                loading.hidden = true;
                showError(errorText(error));
            }
        }

        editButton.addEventListener("click", () => {
            editing = true;
            render();
        });

        cancelEditButton.addEventListener("click", () => {
            editing = false;
            render();
        });

        saveButton.addEventListener("click", async () => {
            errorBox.hidden = true;
            saveButton.disabled = true;
            try {
                current = await apiRequest(`/api/v1/users/${userId}/permissions/`, {
                    method: "PATCH",
                    body: {matrix: collectMatrix()},
                });
                editing = false;
                render();
                globalMessage("مجوزهای کاربر ذخیره شد.", true);
            } catch (error) {
                showError(errorText(error));
            } finally {
                saveButton.disabled = false;
            }
        });

        resetButton.addEventListener("click", async () => {
            if (!window.confirm("مجوزهای اختصاصی این کاربر حذف و به پیش‌فرض نقشش بازگردانده شود؟")) return;
            resetButton.disabled = true;
            try {
                current = await apiRequest(`/api/v1/users/${userId}/permissions/reset/`, {method: "POST", body: {}});
                editing = false;
                render();
                globalMessage("مجوزهای کاربر به پیش‌فرض نقش بازنشانی شد.", true);
            } catch (error) {
                showError(errorText(error));
            } finally {
                resetButton.disabled = false;
            }
        });

        permissionsDialogOpener = (id, name) => {
            userId = id;
            dialog.dataset.userName = name;
            dialog.showModal();
            load();
        };
    }

    let permissionsDialogOpener = null;

    function openPermissionsDialog(id, name) {
        if (permissionsDialogOpener) permissionsDialogOpener(id, name);
    }

    function fillUser(user) {
        ["username", "first_name", "last_name", "email", "phone"].forEach((name) => {
            document.getElementById(`edit-${name.replaceAll("_", "-")}`).value = user[name] || "";
        });
        const role = document.getElementById("edit-role");
        if (role) role.value = user.role;
        const workstream = document.getElementById("edit-workstream");
        const afterSalesOption = workstream.querySelector('option[value="after_sales"]');
        afterSalesOption.disabled = user.role !== "sales_agent";
        workstream.value = user.role === "sales_agent" ? (user.workstream || "sales") : "sales";
        const toggle = document.getElementById("toggle-user-active");
        toggle.disabled = false;
        toggle.dataset.nextActive = String(!user.is_active);
        toggle.classList.toggle("btn-danger", user.is_active);
        toggle.textContent = user.is_active ? "غیرفعال کردن کاربر" : "فعال کردن دوباره کاربر";
    }

    async function setupUserDetail() {
        const userId = document.body.dataset.userId;
        const endpoint = `/api/v1/users/${userId}/`;
        const content = document.getElementById("user-detail-content");
        const loading = document.getElementById("user-detail-loading");
        if (!loading || !content) return;
        let user;
        try {
            user = await apiRequest(endpoint);
            fillUser(user);
            loading.hidden = true;
            content.hidden = false;
        } catch (error) {
            loading.hidden = true;
            showError(error);
            return;
        }

        const editForm = document.getElementById("edit-user-form");
        editForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(editForm, async () => {
                // No password field: changing an existing account's password is
                // not offered anywhere in this interface, and the API refuses it.
                const payload = formPayload(editForm, ["username", "first_name", "last_name", "email", "phone", "workstream"]);
                user = await apiRequest(endpoint, {method: "PATCH", body: payload});
                fillUser(user);
                globalMessage("مشخصات کاربر ذخیره شد.", true);
            });
        });

        const roleForm = document.getElementById("change-role-form");
        if (roleForm) {
            const permissionsDialog = document.getElementById("role-change-access-dialog");
            permissionsDialog.querySelectorAll("[data-close-dialog]").forEach((button) => {
                button.addEventListener("click", () => permissionsDialog.close());
            });

            // Resolves to `true`/`false` for keep/reset once the admin picks
            // one of the dialog's two decision buttons, or to `null` if they
            // close it any other way — cancelling the role change entirely,
            // never silently picking one of the two for them.
            function askKeepCustomPermissions() {
                return new Promise((resolve) => {
                    let decided = false;
                    const keepButton = document.getElementById("role-change-keep");
                    const resetButton = document.getElementById("role-change-reset");
                    const onKeep = () => { decided = true; permissionsDialog.close(); resolve(true); };
                    const onReset = () => { decided = true; permissionsDialog.close(); resolve(false); };
                    const onClose = () => {
                        keepButton.removeEventListener("click", onKeep);
                        resetButton.removeEventListener("click", onReset);
                        permissionsDialog.removeEventListener("close", onClose);
                        if (!decided) resolve(null);
                    };
                    keepButton.addEventListener("click", onKeep);
                    resetButton.addEventListener("click", onReset);
                    permissionsDialog.addEventListener("close", onClose);
                    permissionsDialog.showModal();
                });
            }

            roleForm.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(roleForm, async () => {
                    const nextRole = new FormData(roleForm).get("role");
                    let keepCustomPermissions = true;
                    if (user.has_custom_permissions && nextRole !== user.role) {
                        const choice = await askKeepCustomPermissions();
                        if (choice === null) return; // admin backed out; role stays as it was
                        keepCustomPermissions = choice;
                    }
                    user = await apiRequest(roleForm.action, {
                        method: "POST",
                        body: {...formPayload(roleForm, ["role"]), keep_custom_permissions: keepCustomPermissions},
                    });
                    fillUser(user);
                    globalMessage("نقش کاربر تغییر کرد.", true);
                });
            });
        }

        const toggle = document.getElementById("toggle-user-active");
        toggle.addEventListener("click", async () => {
            const nextActive = toggle.dataset.nextActive === "true";
            if (!window.confirm(nextActive ? "این کاربر دوباره فعال شود؟" : "این کاربر غیرفعال شود؟")) return;
            clearMessages();
            toggle.disabled = true;
            try {
                user = await apiRequest(endpoint, {method: "PATCH", body: {is_active: nextActive}});
                fillUser(user);
                globalMessage(nextActive ? "کاربر دوباره فعال شد." : "کاربر غیرفعال شد.", true);
            } catch (error) {
                toggle.disabled = false;
                showError(error);
            }
        });

        setupUserSessions(userId);
    }

    /**
     * The active sessions of one user, with the option to end them.
     *
     * The panel exists only for a user administrator, so it is absent rather
     * than disabled for anyone else. Ending sessions signs the person out; it
     * does not disable the account, which is the separate control above.
     */
    async function setupUserSessions(userId) {
        const wrap = document.getElementById("user-sessions-table-wrap");
        const body = document.getElementById("user-sessions-table-body");
        const loading = document.getElementById("user-sessions-loading");
        const empty = document.getElementById("user-sessions-empty");
        const revoke = document.getElementById("revoke-user-sessions");
        if (!wrap || !body || !loading || !empty || !revoke) return;

        async function load() {
            loading.hidden = false;
            wrap.hidden = true;
            empty.hidden = true;
            try {
                const data = await apiRequest(`/api/v1/users/${userId}/sessions/`);
                body.replaceChildren(...data.results.map((item) => {
                    const row = document.createElement("tr");
                    // The server sends an opaque reference, never the session
                    // key. A short prefix of it is enough to tell rows apart.
                    appendCell(row, `${String(item.reference || "").slice(0, 8)}…`).dir = "ltr";
                    appendCell(row, displayDate(item.expires_at));
                    return row;
                }));
                loading.hidden = true;
                empty.hidden = data.results.length > 0;
                wrap.hidden = data.results.length === 0;
                revoke.disabled = data.results.length === 0;
            } catch (error) {
                loading.hidden = true;
                showError(error);
            }
        }

        revoke.addEventListener("click", async () => {
            if (!window.confirm("همه نشست‌های فعال این کاربر پایان یابد؟")) return;
            revoke.disabled = true;
            clearMessages();
            try {
                const result = await apiRequest(`/api/v1/users/${userId}/revoke-sessions/`, {method: "POST", body: {}});
                globalMessage(`${result.ended} نشست پایان یافت.`, true);
                await load();
            } catch (error) {
                revoke.disabled = false;
                showError(error);
            }
        });

        await load();
    }

    function appendCell(row, value) {
        const cell = document.createElement("td");
        cell.textContent = value === null || value === undefined || value === "" ? "—" : String(value);
        row.appendChild(cell);
        return cell;
    }

    function appendDetailLink(row, href) {
        const cell = document.createElement("td");
        const link = document.createElement("a");
        link.className = "btn btn-sm btn-light";
        link.href = href;
        link.textContent = "جزئیات";
        cell.appendChild(link);
        row.appendChild(cell);
    }

    function statusText(active) {
        return active ? "فعال" : "غیرفعال";
    }

    /** An active/inactive cell as the theme's badge rather than bare text. */
    function appendStatusCell(row, active) {
        const cell = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = active ? "badge badge-light-success" : "badge badge-light-danger";
        badge.textContent = statusText(active);
        cell.appendChild(badge);
        row.appendChild(cell);
        return cell;
    }

    function directionText(direction) {
        return direction === "inbound" ? "ورودی" : direction === "outbound" ? "خروجی" : direction;
    }

    // --- Jalali dates (BIZ-007) ----------------------------------------------
    // What the user reads and types is Jalali; what crosses /api/v1/ stays
    // Gregorian ISO-8601. The conversion below is the same arithmetic as
    // common/jalali.py and is held to the same ICU reference vectors, so the
    // two halves of the product can never disagree about a date.
    //
    // Intl can format Jalali but cannot parse it, and typing is half the job
    // here, so both directions are implemented rather than half-borrowed.

    const OPERATIONAL_TIME_ZONE = "Asia/Tehran";
    const JALALI_EPOCH_UTC = Date.UTC(622, 2, 21); // 1 Farvardin 1
    const DAY_MS = 86400000;
    const JALALI_MONTH_OFFSETS = [0, 31, 62, 93, 124, 155, 186, 216, 246, 276, 306, 336];
    const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
    //: Matches `JALALI_MONTHS` in `common/jalali.py` exactly — the one other
    //: place this product spells out a Jalali month by name.
    const JALALI_MONTH_NAMES = [
        "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
        "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
    ];
    //: Indexed like `Date.prototype.getDay()` (0 = Sunday .. 6 = Saturday) —
    //: the Gregorian and Jalali calendars share the same seven weekdays, only
    //: the month names differ, so this is not Jalali-specific like the array
    //: above. Spelled out in full rather than the single-letter abbreviation
    //: (ی/د/س/چ/پ/ج/ش) the lead-follow-up calendar used before: several of
    //: those letters are one or two dots apart in the Persian script (چ/ج/ح,
    //: پ/ب/ت) and read as near-identical at a calendar header's font size.
    const PERSIAN_WEEKDAY_NAMES = [
        "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه",
    ];

    function isJalaliLeap(year) {
        return (((year + 12) % 33) % 4) === 1;
    }

    function jalaliYearLength(year) {
        return isJalaliLeap(year) ? 366 : 365;
    }

    function toPersianDigits(text) {
        return String(text).replace(/[0-9]/g, (digit) => PERSIAN_DIGITS[Number(digit)]);
    }

    function toLatinDigits(text) {
        // Persian ۰-۹ and Arabic-Indic ٠-٩ both normalise to Latin.
        return String(text)
            .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06F0))
            .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660));
    }

    function gregorianToJalali(year, month, day) {
        let days = Math.round((Date.UTC(year, month - 1, day) - JALALI_EPOCH_UTC) / DAY_MS);
        if (days < 0) throw new RangeError("Date precedes the Jalali epoch.");
        let jalaliYear = 1;
        for (;;) {
            const length = jalaliYearLength(jalaliYear);
            if (days < length) break;
            days -= length;
            jalaliYear += 1;
        }
        for (let index = 11; index >= 0; index -= 1) {
            if (days >= JALALI_MONTH_OFFSETS[index]) {
                return [jalaliYear, index + 1, days - JALALI_MONTH_OFFSETS[index] + 1];
            }
        }
        throw new RangeError("Unreachable: month offsets are exhaustive.");
    }

    function jalaliToGregorian(year, month, day) {
        let days = 0;
        for (let each = 1; each < year; each += 1) days += jalaliYearLength(each);
        days += JALALI_MONTH_OFFSETS[month - 1] + day - 1;
        const utc = new Date(JALALI_EPOCH_UTC + days * DAY_MS);
        return [utc.getUTCFullYear(), utc.getUTCMonth() + 1, utc.getUTCDate()];
    }

    function jalaliMonthLength(year, month) {
        if (month <= 6) return 31;
        if (month <= 11) return 30;
        return isJalaliLeap(year) ? 30 : 29;
    }

    /** The wall-clock parts of an instant in the operational time zone. */
    function tehranParts(value) {
        const date = value instanceof Date ? value : new Date(value);
        if (Number.isNaN(date.getTime())) return null;
        const parts = new Intl.DateTimeFormat("en-CA", {
            timeZone: OPERATIONAL_TIME_ZONE,
            year: "numeric", month: "2-digit", day: "2-digit",
            hour: "2-digit", minute: "2-digit", hour12: false,
        }).formatToParts(date).reduce((all, part) => {
            if (part.type !== "literal") all[part.type] = part.value;
            return all;
        }, {});
        return {
            year: Number(parts.year),
            month: Number(parts.month),
            day: Number(parts.day),
            hour: Number(parts.hour === "24" ? "0" : parts.hour),
            minute: Number(parts.minute),
        };
    }

    /** The operational zone's UTC offset in minutes on a given instant. */
    function tehranOffsetMinutes(utcMillis) {
        const parts = tehranParts(new Date(utcMillis));
        const asUtc = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute);
        return Math.round((asUtc - utcMillis) / 60000);
    }

    /** Tehran wall-clock parts -> the exact instant they name. */
    function tehranToInstant(year, month, day, hour, minute) {
        const naive = Date.UTC(year, month - 1, day, hour, minute);
        // Two passes settle the offset even across a DST transition.
        let guess = naive - tehranOffsetMinutes(naive) * 60000;
        guess = naive - tehranOffsetMinutes(guess) * 60000;
        return new Date(guess);
    }

    /** A stored value as `۱۴۰۵/۰۵/۲۵` (date only). */
    function displayDay(value) {
        if (!value) return "—";
        // A bare `YYYY-MM-DD` is a calendar day, not an instant: read it as
        // written rather than shifting it through a time zone.
        const plain = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value));
        if (plain) {
            const [year, month, day] = gregorianToJalali(+plain[1], +plain[2], +plain[3]);
            return toPersianDigits(`${pad4(year)}/${pad2(month)}/${pad2(day)}`);
        }
        const parts = tehranParts(value);
        if (!parts) return value;
        const [year, month, day] = gregorianToJalali(parts.year, parts.month, parts.day);
        return toPersianDigits(`${pad4(year)}/${pad2(month)}/${pad2(day)}`);
    }

    /** A stored instant as `۱۴۰۵/۰۵/۲۵ ۱۴:۳۰` in Tehran local time. */
    function displayDate(value) {
        if (!value) return "—";
        const parts = tehranParts(value);
        if (!parts) return value;
        const [year, month, day] = gregorianToJalali(parts.year, parts.month, parts.day);
        return toPersianDigits(
            `${pad4(year)}/${pad2(month)}/${pad2(day)} ${pad2(parts.hour)}:${pad2(parts.minute)}`
        );
    }

    function pad2(value) { return String(value).padStart(2, "0"); }
    function pad4(value) { return String(value).padStart(4, "0"); }

    /** Fill a Jalali date-time input from a stored value. */
    function localDateTimeValue(value) {
        if (!value) return "";
        const shown = displayDate(value);
        return shown === "—" ? "" : shown;
    }

    /**
     * A stored calendar day, for a `data-jalali="date"` input.
     *
     * `localDateValue` below reads an instant and drops its clock. This reads a
     * day that never had one — `document_date` is a `DateField` and arrives as a
     * bare `YYYY-MM-DD`. Putting that through the instant path would send it
     * through a time zone and could land on the day before.
     */
    function localDayValue(value) {
        const shown = displayDay(value);
        return shown === "—" ? "" : shown;
    }

    /** The same, for a `data-jalali="date"` input: the day without the time. */
    function localDateValue(value) {
        const shown = localDateTimeValue(value);
        // `displayDate` renders "۱۴۰۵/۰۵/۲۷ ۰۱:۰۳"; a date input wants the day.
        return shown ? shown.split(" ")[0] : "";
    }

    /**
     * Read a typed Jalali value.
     *
     * Returns `{date, hour, minute}` or throws with a Persian message, so every
     * caller reports the same thing for the same mistake.
     */
    function parseJalaliInput(text, {requireTime = false} = {}) {
        const raw = toLatinDigits(String(text || "")).trim();
        if (!raw) return null;
        const match = /^(\d{3,4})[/\-.](\d{1,2})[/\-.](\d{1,2})(?:[\sT]+(\d{1,2}):(\d{2}))?$/.exec(raw);
        if (!match) throw new Error("تاریخ باید به شکل ۱۴۰۵/۰۵/۲۵ باشد.");
        const year = Number(match[1]);
        const month = Number(match[2]);
        const day = Number(match[3]);
        // Catches a Gregorian value typed into a Jalali field: 2026 is a valid
        // Jalali year arithmetically, but it means 2647 CE.
        if (year < 1200 || year > 1700) throw new Error("سال باید یک سال شمسی معتبر باشد (مثلا ۱۴۰۵).");
        if (month < 1 || month > 12) throw new Error("ماه باید بین ۱ تا ۱۲ باشد.");
        if (day < 1 || day > jalaliMonthLength(year, month)) throw new Error("روز در این ماه معتبر نیست.");
        const hour = match[4] === undefined ? (requireTime ? 0 : 0) : Number(match[4]);
        const minute = match[5] === undefined ? 0 : Number(match[5]);
        if (hour > 23 || minute > 59) throw new Error("ساعت معتبر نیست.");
        return {jalali: [year, month, day], hour, minute};
    }

    // The two converters below return null rather than throwing on a value they
    // cannot read. They run on every keystroke (the export link rebuilds live),
    // so throwing would break the handler on a half-typed date. The field's own
    // blur handler reports the mistake and `setCustomValidity` blocks submit,
    // so an unreadable date is still never silently sent.

    /** Typed Jalali date-time -> the ISO instant the API stores, or null. */
    function apiDateTime(value) {
        let parsed;
        try { parsed = parseJalaliInput(value); } catch { return null; }
        if (!parsed) return null;
        const [year, month, day] = jalaliToGregorian(...parsed.jalali);
        return tehranToInstant(year, month, day, parsed.hour, parsed.minute).toISOString();
    }

    /** Typed Jalali date -> the `YYYY-MM-DD` calendar day the API stores, or null. */
    function apiDate(value) {
        let parsed;
        try { parsed = parseJalaliInput(value); } catch { return null; }
        if (!parsed) return null;
        const [year, month, day] = jalaliToGregorian(...parsed.jalali);
        return `${pad4(year)}-${pad2(month)}-${pad2(day)}`;
    }

    //: Standard Iranian week, شنبه first — the same order the lead and
    //: after-sales calendars already render (`setupLeadCalendar`,
    //: `setupAfterSalesCalendar`, both driven by FullCalendar's own
    //: `firstDay: 6`).
    const JALALI_WEEKDAY_LETTERS = ["ش", "ی", "د", "س", "چ", "پ", "ج"];

    /** Gregorian day-of-week (0=Saturday..6=Friday) for a Jalali calendar day. */
    function jalaliWeekday(year, month, day) {
        const [gy, gm, gd] = jalaliToGregorian(year, month, day);
        const sunday0 = new Date(Date.UTC(gy, gm - 1, gd)).getUTCDay(); // 0=Sun..6=Sat
        return (sunday0 + 1) % 7; // 0=Sat..6=Fri
    }

    let closeOpenJalaliPicker = null; // the open picker's own teardown, or null
    let openJalaliPickerField = null; // which field it belongs to

    /**
     * A small popup calendar for a `data-jalali` field, opened on focus/click.
     *
     * Built in-house rather than adapted from a vendor picker: the theme
     * bundles flatpickr (`assets/plugins/global/plugins.bundle.js`), but it
     * draws its grid straight from JS `Date` with no hook for a different
     * calendar system — there is no Jalali build of it in this bundle, and
     * retrofitting one would mean fighting its internals rather than using
     * them. This project already carries a complete, tested Jalali <->
     * Gregorian conversion layer (`jalaliToGregorian`, `gregorianToJalali`,
     * `jalaliMonthLength` — the same functions every `apiDate`/`apiDateTime`
     * call already runs through), so the grid is drawn from that instead.
     *
     * The popup's shell is still entirely the theme's own:
     * `.menu.menu-sub.menu-sub-dropdown`, the exact classes `#user-menu` and
     * `setupListFilterPopovers()`'s own panel already use, so it inherits the
     * theme's light/dark background, box-shadow, border-radius and
     * fade/move-in animation for free — no separate design system, and no
     * dark-mode work of its own to get wrong. Only the day grid itself is
     * custom CSS (`.jalali-picker-*` in dolphin.css), because the purchased
     * theme has no component for a Jalali calendar to adapt.
     *
     * Typing the date directly keeps working exactly as it always did
     * (`parseJalaliInput` on blur, below) — this only adds a second way to
     * fill the same field, not a replacement for the first.
     */
    function openJalaliPicker(field) {
        if (openJalaliPickerField === field) return;
        if (closeOpenJalaliPicker) closeOpenJalaliPicker();

        const wantsTime = field.dataset.jalali === "datetime";
        let parsed;
        try { parsed = parseJalaliInput(field.value, {requireTime: wantsTime}); } catch { parsed = null; }
        const nowParts = tehranParts(new Date());
        const [todayYear, todayMonth, todayDay] = gregorianToJalali(nowParts.year, nowParts.month, nowParts.day);

        let viewYear = parsed ? parsed.jalali[0] : todayYear;
        let viewMonth = parsed ? parsed.jalali[1] : todayMonth;
        let selected = parsed ? {year: parsed.jalali[0], month: parsed.jalali[1], day: parsed.jalali[2]} : null;
        let hour = parsed ? parsed.hour : nowParts.hour;
        let minute = parsed ? parsed.minute : nowParts.minute;

        const panel = document.createElement("div");
        panel.className = "menu menu-sub menu-sub-dropdown menu-column jalali-picker";
        panel.dir = "rtl";
        panel.setAttribute("role", "dialog");
        panel.setAttribute("aria-label", wantsTime ? "انتخاب تاریخ و زمان" : "انتخاب تاریخ");

        function navButton(glyph, label) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-icon btn-sm btn-color-muted btn-active-color-primary";
            button.setAttribute("aria-label", label);
            button.textContent = glyph;
            return button;
        }

        const header = document.createElement("div");
        header.className = "jalali-picker-header";
        // Each arrow points *outward*, towards its own edge of the row (the
        // direction moving further prev/next actually travels once the row
        // below is reordered to put prev on the right) — not towards the
        // title, which is what the glyphs originally paired with the old,
        // reversed order would now point.
        const nextYearBtn = navButton("«", "سال بعد");
        const nextMonthBtn = navButton("‹", "ماه بعد");
        const title = document.createElement("span");
        title.className = "jalali-picker-title";
        const prevMonthBtn = navButton("›", "ماه قبل");
        const prevYearBtn = navButton("»", "سال قبل");
        // DOM order is visual order in this `dir="rtl"` row: first child sits
        // rightmost. Right holds "prev", left holds "next" — matching the
        // lead/after-sales calendars' own toolbar (`prev,next` in
        // `headerToolbar`, which renders prev rightmost the same way under
        // `direction: "rtl"`) and every "قبلی"/"بعدی" pagination pair
        // elsewhere in the app (e.g. `leads/list.html`). A previous version
        // of this comment claimed the opposite order matched that same
        // convention; it did not — measured live, this picker's own arrows
        // sat backwards from every other prev/next control in the app
        // (design review, 2026-09-12).
        header.append(prevYearBtn, prevMonthBtn, title, nextMonthBtn, nextYearBtn);

        const weekdays = document.createElement("div");
        weekdays.className = "jalali-picker-weekdays";
        JALALI_WEEKDAY_LETTERS.forEach((letter) => {
            const cell = document.createElement("span");
            cell.textContent = letter;
            weekdays.append(cell);
        });

        const days = document.createElement("div");
        days.className = "jalali-picker-days";

        let timeRow = null;
        let hourSelect = null;
        let minuteSelect = null;
        if (wantsTime) {
            timeRow = document.createElement("div");
            timeRow.className = "jalali-picker-time";
            hourSelect = document.createElement("select");
            hourSelect.className = "form-select form-select-solid form-select-sm";
            hourSelect.setAttribute("aria-label", "ساعت");
            for (let h = 0; h <= 23; h += 1) {
                const option = document.createElement("option");
                option.value = String(h);
                option.textContent = toPersianDigits(pad2(h));
                hourSelect.append(option);
            }
            const separator = document.createElement("span");
            separator.textContent = ":";
            minuteSelect = document.createElement("select");
            minuteSelect.className = "form-select form-select-solid form-select-sm";
            minuteSelect.setAttribute("aria-label", "دقیقه");
            // Five-minute steps cover the ordinary case; the field's own
            // exact minute (typed by hand, or already stored) is added too
            // so opening the picker on an existing value never rounds it
            // away silently.
            const minuteOptions = new Set([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, minute]);
            Array.from(minuteOptions).sort((a, b) => a - b).forEach((m) => {
                const option = document.createElement("option");
                option.value = String(m);
                option.textContent = toPersianDigits(pad2(m));
                minuteSelect.append(option);
            });
            hourSelect.value = String(hour);
            minuteSelect.value = String(minute);
            timeRow.append(hourSelect, separator, minuteSelect);
        }

        const footer = document.createElement("div");
        footer.className = "jalali-picker-footer";
        const clearBtn = document.createElement("button");
        clearBtn.type = "button";
        clearBtn.className = "btn btn-sm btn-light";
        clearBtn.textContent = "پاک‌کردن";
        const todayBtn = document.createElement("button");
        todayBtn.type = "button";
        todayBtn.className = "btn btn-sm btn-light-primary";
        todayBtn.textContent = "امروز";
        footer.append(clearBtn, todayBtn);
        let confirmBtn = null;
        if (wantsTime) {
            confirmBtn = document.createElement("button");
            confirmBtn.type = "button";
            confirmBtn.className = "btn btn-sm btn-primary";
            confirmBtn.textContent = "تأیید";
            footer.append(confirmBtn);
        }

        panel.append(header, weekdays, days, ...(timeRow ? [timeRow] : []), footer);

        function updateTitle() {
            title.textContent = `${JALALI_MONTH_NAMES[viewMonth - 1]} ${toPersianDigits(String(viewYear))}`;
        }

        function renderDays() {
            days.replaceChildren();
            const leading = jalaliWeekday(viewYear, viewMonth, 1);
            const length = jalaliMonthLength(viewYear, viewMonth);
            const totalCells = 42; // 6 full weeks, so the popup never resizes month to month.
            for (let cellIndex = 0; cellIndex < totalCells; cellIndex += 1) {
                const day = cellIndex - leading + 1;
                if (day < 1 || day > length) {
                    days.append(document.createElement("span"));
                    continue;
                }
                const isToday = viewYear === todayYear && viewMonth === todayMonth && day === todayDay;
                const isSelected = !!selected && selected.year === viewYear && selected.month === viewMonth && selected.day === day;
                const cell = document.createElement("button");
                cell.type = "button";
                cell.textContent = toPersianDigits(String(day));
                cell.className = "btn btn-icon jalali-picker-day " + (
                    isSelected ? "btn-primary"
                    : isToday ? "btn-active-light-primary border border-primary text-primary"
                    : "btn-color-gray-700 btn-active-light-primary"
                );
                if (isSelected) cell.setAttribute("aria-current", "date");
                cell.addEventListener("click", () => {
                    selected = {year: viewYear, month: viewMonth, day};
                    commit();
                    if (wantsTime) {
                        renderDays();
                    } else {
                        close();
                    }
                });
                days.append(cell);
            }
        }

        function commit() {
            if (!selected) return;
            const text = wantsTime
                ? toPersianDigits(`${pad4(selected.year)}/${pad2(selected.month)}/${pad2(selected.day)} ${pad2(hour)}:${pad2(minute)}`)
                : toPersianDigits(`${pad4(selected.year)}/${pad2(selected.month)}/${pad2(selected.day)}`);
            field.value = text;
            field.dispatchEvent(new Event("input", {bubbles: true}));
            field.dispatchEvent(new Event("change", {bubbles: true}));
            field.dispatchEvent(new Event("blur"));
        }

        function shiftMonth(delta) {
            let year = viewYear;
            let month = viewMonth + delta;
            while (month < 1) { month += 12; year -= 1; }
            while (month > 12) { month -= 12; year += 1; }
            viewYear = year;
            viewMonth = month;
            updateTitle();
            renderDays();
        }

        prevMonthBtn.addEventListener("click", () => shiftMonth(-1));
        nextMonthBtn.addEventListener("click", () => shiftMonth(1));
        prevYearBtn.addEventListener("click", () => { viewYear -= 1; updateTitle(); renderDays(); });
        nextYearBtn.addEventListener("click", () => { viewYear += 1; updateTitle(); renderDays(); });

        if (hourSelect) {
            hourSelect.addEventListener("change", () => { hour = Number(hourSelect.value); if (selected) commit(); });
            minuteSelect.addEventListener("change", () => { minute = Number(minuteSelect.value); if (selected) commit(); });
        }
        clearBtn.addEventListener("click", () => {
            field.value = "";
            field.dispatchEvent(new Event("input", {bubbles: true}));
            field.dispatchEvent(new Event("change", {bubbles: true}));
            field.dispatchEvent(new Event("blur"));
            close();
        });
        todayBtn.addEventListener("click", () => {
            viewYear = todayYear;
            viewMonth = todayMonth;
            selected = {year: todayYear, month: todayMonth, day: todayDay};
            if (wantsTime) {
                hour = nowParts.hour;
                minute = nowParts.minute;
                hourSelect.value = String(hour);
                minuteSelect.value = String(minute);
            }
            updateTitle();
            renderDays();
            commit();
            if (!wantsTime) close();
        });
        confirmBtn?.addEventListener("click", () => close());

        function position() {
            const anchor = field.getBoundingClientRect();
            const panelRect = panel.getBoundingClientRect();
            const margin = 8;
            let top = anchor.bottom + margin;
            if (top + panelRect.height > window.innerHeight - margin) {
                top = Math.max(margin, anchor.top - panelRect.height - margin);
            }
            let left = anchor.right - panelRect.width;
            left = Math.min(Math.max(left, margin), window.innerWidth - margin - panelRect.width);
            panel.style.top = `${top}px`;
            panel.style.left = `${left}px`;
        }

        function onDocumentMouseDown(event) {
            if (panel.contains(event.target) || event.target === field) return;
            close();
        }
        function onKeyDown(event) {
            if (event.key === "Escape") {
                event.stopPropagation();
                close();
                field.focus();
            }
        }

        function close() {
            if (openJalaliPickerField !== field) return;
            document.removeEventListener("mousedown", onDocumentMouseDown, true);
            document.removeEventListener("keydown", onKeyDown, true);
            panel.remove();
            openJalaliPickerField = null;
            closeOpenJalaliPicker = null;
        }

        // A field inside a native <dialog> renders in the browser's own top
        // layer; a picker appended to <body> would paint *behind* the open
        // dialog's backdrop and be unreachable. Appending inside the dialog
        // keeps it in that same promoted stacking context. Neither this nor
        // <body> is `position: relative`, which is fine — the panel is
        // `position: fixed` (dolphin.css) and positioned in viewport
        // coordinates below, not relative to its parent.
        (field.closest("dialog") || document.body).appendChild(panel);
        updateTitle();
        renderDays();
        // Measured before it is shown: `.jalali-picker` has no size of its
        // own to reason about until its content exists, and `position()`
        // needs that real size to decide whether it fits below the field.
        panel.style.visibility = "hidden";
        panel.style.display = "flex";
        position();
        panel.style.visibility = "";
        panel.style.display = "";
        // `.show` added only now, after the panel already has its final
        // position — the theme's own fade/move-in animation
        // (`.menu-sub-dropdown.show`) plays from there, not from wherever
        // the hidden measurement pass happened to leave it.
        panel.classList.add("show");

        document.addEventListener("mousedown", onDocumentMouseDown, true);
        document.addEventListener("keydown", onKeyDown, true);

        openJalaliPickerField = field;
        closeOpenJalaliPicker = close;
    }

    /**
     * Give every Jalali input the same behaviour once, at start-up.
     *
     * Persian digits are accepted as typed and the field reports its own error
     * on blur, so a bad date is caught where it was entered rather than as a
     * 400 from the server after submit. `openJalaliPicker` above is a second,
     * additive way to fill the same field — typing still works exactly as it
     * did before that function existed.
     */
    function setupJalaliInputs(root = document) {
        root.querySelectorAll("input[data-jalali]").forEach((field) => {
            if (field.dataset.jalaliReady === "1") return;
            field.dataset.jalaliReady = "1";
            const wantsTime = field.dataset.jalali === "datetime";
            field.setAttribute("dir", "ltr");
            field.setAttribute("inputmode", "numeric");
            field.setAttribute("autocomplete", "off");
            if (!field.placeholder) {
                field.placeholder = wantsTime ? "۱۴۰۵/۰۵/۲۵ ۱۴:۳۰" : "۱۴۰۵/۰۵/۲۵";
            }
            field.addEventListener("focus", () => openJalaliPicker(field));
            field.addEventListener("click", () => openJalaliPicker(field));
            field.addEventListener("blur", () => {
                const target = document.querySelector(`[data-error-for="${field.name}"]`);
                if (!field.value.trim()) {
                    if (target) target.textContent = "";
                    field.setCustomValidity("");
                    return;
                }
                try {
                    parseJalaliInput(field.value, {requireTime: wantsTime});
                    field.setCustomValidity("");
                    if (target) target.textContent = "";
                } catch (error) {
                    field.setCustomValidity(error.message);
                    if (target) target.textContent = error.message;
                }
            });
        });
    }

    async function loadAllPages(url, limit = 20) {
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

    function fillSelect(select, rows, label, emptyLabel) {
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
    function setupRowSelection({key, body, reload}) {
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
            selectAll.checked = boxes.length > 0 && selected.size === boxes.length;
            selectAll.indeterminate = selected.size > 0 && selected.size < boxes.length;
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
            if (!window.confirm(
                `${count} مورد برای همیشه حذف شود؟ این کار قابل بازگشت نیست. رکوردی که سابقهٔ دیگری به آن وابسته است حذف نخواهد شد. اگر مطمئن نیستید، به‌جای حذف، از غیرفعال‌سازی در همان صفحهٔ رکورد استفاده کنید.`
            )) return;
            try {
                const result = await apiRequest(`/api/v1/${key}/bulk-delete/`, {method: "POST", body: {ids}});
                const deletedCount = result.deleted?.length || 0;
                const blockedCount = (result.protected?.length || 0) + (result.denied?.length || 0);
                const parts = [];
                if (deletedCount) parts.push(`${toPersianDigits(String(deletedCount))} مورد حذف شد`);
                if (result.protected?.length) parts.push(`${toPersianDigits(String(result.protected.length))} مورد سابقهٔ وابسته داشت و حذف نشد`);
                if (result.denied?.length) parts.push(`${toPersianDigits(String(result.denied.length))} مورد مجاز به حذف نبود`);
                resetSelection();
                // `reload()` starts with `clearMessages()` (same as every
                // other `load()` in this file) — called first so it cannot
                // erase the very message it is about to show.
                await reload();
                globalMessage(parts.join(" — ") || "موردی حذف نشد.", deletedCount > 0 && blockedCount === 0);
            } catch (error) {
                showError(error);
            }
        });

        function decorateRow(item, row) {
            const cell = document.createElement("td");
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.className = "form-check-input";
            checkbox.dataset.rowSelect = String(item.id);
            checkbox.setAttribute("aria-label", "انتخاب ردیف");
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
    function bindLiveSearch(input, onSearch) {
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

    function setupPagedList({key, form, search, endpoint, renderRow}) {
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

        async function load(page = 1) {
            loading.hidden = false;
            empty.hidden = true;
            wrap.hidden = true;
            pagination.hidden = true;
            clearMessages();
            selection.resetSelection();
            try {
                const data = await apiRequest(endpoint(page));
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
                loading.hidden = true;
                showError(error);
            }
        }
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

    function customerRow(customer) {
        const row = document.createElement("tr");
        appendCell(row, customer.full_name);
        appendCell(row, customer.primary_phone?.normalized_phone || customer.primary_phone?.raw_phone || "—");
        appendCell(row, customer.category);
        appendCell(row, customer.postal_code);
        appendCell(row, customer.city);
        appendStatusCell(row, (customer.is_active));
        appendCell(row, customer.created_by_display || customer.created_by);
        appendCell(row, displayDay(customer.created_at));
        appendDetailLink(row, `/customers/${customer.id}/`);
        return row;
    }

    function setupCustomers() {
        const form = document.getElementById("customer-search-form");
        setupListFilter("customer");
        // Which of the two books is on screen. A marketer never sees the
        // switch, and `customers_for` confines them to this book in the
        // database regardless of what the page asks for.
        let kind = "individual";
        const controller = setupPagedList({
            key: "customers",
            form,
            search: document.getElementById("customer-search"),
            endpoint(page) {
                const ordering = document.getElementById("customer-ordering").value;
                // "registered" is a UI-only choice that means "sort by
                // registration date and let me pick a window"; the API knows
                // only its own ordering fields.
                const query = new URLSearchParams({
                    page: String(page),
                    ordering: ordering === "registered" ? "-created_at" : ordering,
                });
                const search = document.getElementById("customer-search").value.trim();
                if (search) query.set("search", search);
                if (ordering === "registered") {
                    const from = apiDate(document.getElementById("customer-created-from").value);
                    const to = apiDate(document.getElementById("customer-created-to").value);
                    if (from) query.set("created_from", from);
                    if (to) query.set("created_to", to);
                }
                query.set("kind", kind);
                return `/api/v1/customers/?${query}`;
            },
            renderRow: customerRow,
        });
        // The window controls only make sense under the registration sort, so
        // they appear with it and stay out of the way otherwise.
        const orderingSelect = document.getElementById("customer-ordering");
        const dateRange = document.getElementById("customer-date-range");
        const syncDateRange = () => {
            const active = orderingSelect.value === "registered";
            dateRange.hidden = !active;
        };
        orderingSelect.addEventListener("change", syncDateRange);
        syncDateRange();

        /**
         * The حقیقی / حقوقی switch.
         *
         * One table, two books: the same columns and the same filters read a
         * different list, rather than a second page duplicating all of it. The
         * pressed state is carried on `aria-pressed` as well as the class, so
         * the switch is not colour-only.
         */
        const kindButtons = Array.from(document.querySelectorAll("[data-customer-kind]"));
        kindButtons.forEach((button) => {
            button.addEventListener("click", () => {
                const chosen = button.dataset.customerKind;
                if (chosen === kind) return;
                kind = chosen;
                kindButtons.forEach((other) => {
                    const active = other === button;
                    other.classList.toggle("btn-primary", active);
                    other.classList.toggle("btn-light", !active);
                    other.setAttribute("aria-pressed", String(active));
                });
                clearMessages();
                controller.load(1);
            });
        });

        setupCustomerListTransfer(() => kind);
        setupCustomerCharts();
        controller.load();
        const dialog = document.getElementById("create-customer-dialog");
        const createForm = document.getElementById("create-customer-form");
        function renderCustomerReview() {
            const kindField = document.getElementById("create-customer-kind");
            const phoneRaw = document.getElementById("create-customer-phone").value.trim();
            renderWizardReview(document.getElementById("create-customer-review"), [
                ["نام کامل", createForm.full_name.value || "—"],
                ...(kindField ? [["نوع مشتری", selectedOptionText(kindField)]] : []),
                ["کد ملی", createForm.national_id.value || "—"],
                ["شماره اقتصادی", createForm.economic_code.value || "—"],
                ["ایمیل", createForm.email.value || "—"],
                ["دسته‌بندی", createForm.category.value || "—"],
                ["استان", createForm.province.value || "—"],
                ["شهر", createForm.city.value || "—"],
                ["کد پستی", createForm.postal_code.value || "—"],
                ["تلفن آغازین", phoneRaw || "—"],
                ["برچسب تلفن", createForm.phone_label.value || "—"],
                ["شماره اصلی", document.getElementById("create-customer-phone-primary").checked ? "بله" : "خیر"],
                ["نشانی", createForm.address.value || "—"],
                ["یادداشت", createForm.notes.value || "—"],
            ]);
        }
        const wizard = setupWizard(dialog, {onReachLastStep: renderCustomerReview});
        document.getElementById("open-create-customer").addEventListener("click", () => {
            createForm.reset();
            clearMessages(createForm);
            wizard?.goFirst();
            dialog.showModal();
        });
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const payload = formPayload(createForm, ["full_name", "national_id", "economic_code", "email", "province", "city", "postal_code", "category", "address", "notes"]);
                // Absent for a marketer, who has no such selector and whose
                // customers are individuals by the model's own default.
                const kindField = document.getElementById("create-customer-kind");
                if (kindField) payload.kind = kindField.value;
                const rawPhone = String(new FormData(createForm).get("phone_raw") || "").trim();
                if (rawPhone) payload.phone = {
                    raw_phone: rawPhone,
                    label: String(new FormData(createForm).get("phone_label") || ""),
                    is_primary: document.getElementById("create-customer-phone-primary").checked,
                };
                const customer = await apiRequest(createForm.action, {method: "POST", body: payload});
                dialog.close();
                controller.load(1);
                window.location.assign(`/customers/${customer.id}/`);
            });
        });
    }

    /**
     * The «خروجی لیست» and «ورودی لیست» dialogs.
     *
     * Both ask the same first question — which list — because both act on one
     * book at a time. Export then offers a download; import offers a file and a
     * upload button. The export columns and the import columns are the same row,
     * so the operator exports a list, writes on that file, and returns it.
     *
     * `currentKind` seeds each dialog with the book already on screen, which is
     * almost always the one meant.
     */
    function setupCustomerListTransfer(currentKind) {
        const exportDialog = document.getElementById("export-customers-dialog");
        const exportOpen = document.getElementById("open-export-customers");
        const exportKind = document.getElementById("export-customers-kind");
        const download = document.getElementById("download-customers");

        function bindClose(dialog) {
            dialog?.querySelectorAll("[data-close-dialog]").forEach((button) =>
                button.addEventListener("click", () => dialog.close()),
            );
        }

        if (exportDialog && exportOpen) {
            bindClose(exportDialog);
            exportOpen.addEventListener("click", () => {
                // Seed with the book on screen, but only if this reader has
                // that option at all.
                if (Array.from(exportKind.options).some((option) => option.value === currentKind())) {
                    exportKind.value = currentKind();
                }
                exportDialog.showModal();
            });
            download.addEventListener("click", () => {
                // A plain navigation: the browser's own download, with the
                // session cookie attached, and no blob held in memory.
                window.location.assign(
                    `/api/v1/exports/customers.xlsx?kind=${encodeURIComponent(exportKind.value)}`,
                );
                exportDialog.close();
            });
        }

        const importDialog = document.getElementById("import-customers-dialog");
        const importOpen = document.getElementById("open-import-customers");
        if (!importDialog || !importOpen) return;
        const importKind = document.getElementById("import-customers-kind");
        const picker = document.getElementById("import-customers-file");
        const upload = document.getElementById("upload-customers");

        bindClose(importDialog);
        importOpen.addEventListener("click", () => {
            importKind.value = currentKind();
            picker.value = "";
            clearMessages(importDialog);
            importDialog.showModal();
        });
        upload.addEventListener("click", async () => {
            const file = picker.files && picker.files[0];
            if (!file) {
                const slot = importDialog.querySelector('[data-error-for="file"]');
                if (slot) slot.textContent = "یک فایل اکسل انتخاب کنید.";
                return;
            }
            const body = new FormData();
            body.append("file", file);
            body.append("kind", importKind.value);
            upload.disabled = true;
            clearMessages(importDialog);
            try {
                const result = await apiRequest("/api/v1/customers/import-xlsx/", {
                    method: "POST", body, raw: true,
                });
                importDialog.close();
                const parts = [`${toPersianDigits(String(result.created))} مشتری ثبت شد.`];
                if (result.duplicates) {
                    parts.push(`${toPersianDigits(String(result.duplicates))} مشتری تکراری بود و اضافه نشد.`);
                }
                if (result.invalid) {
                    parts.push(`${toPersianDigits(String(result.invalid))} ردیف نامعتبر بود و رد شد.`);
                }
                // A run that created nothing is not a success message.
                globalMessage(parts.join(" "), result.created > 0);
            } catch (error) {
                showError(error, importDialog);
            } finally {
                upload.disabled = false;
            }
        });
    }

    /**
     * The customer province map (product-owner request 2026-09-09): a
     * choropleth of Iran's thirty-one provinces, each shaded by how many of
     * this reader's customers sit in it, naming the province and its count on
     * hover.
     *
     * Drawn as plain inline SVG from a vendored path file rather than with a
     * mapping library. The purchased theme's own map widget
     * (`src/js/widgets/maps/widget-1.js`) uses amCharts 5, which this
     * deployment cannot have: amCharts and its geodata are served from the
     * vendor's own content-delivery host, and nothing in this panel is
     * fetched from an external origin — the base layout links none at all,
     * and
     * the runbook's offline install has no route to one. The geometry instead comes from Natural
     * Earth's public-domain admin-1 layer, projected once at build time into
     * `common/static/common/iran-provinces.json` (see the note in this
     * release's CHANGELOG for how that file is regenerated).
     *
     * The scale is five steps of the theme's own primary colour rather than a
     * continuous ramp: five bands are readable side by side and comparable
     * against the legend, which a continuous ramp is not.
     */
    const IRAN_MAP_URL = document.body?.dataset.iranMapUrl || "";
    let iranMapPromise = null;

    function loadIranMap() {
        if (!iranMapPromise) {
            iranMapPromise = fetch(IRAN_MAP_URL, {credentials: "same-origin"}).then((response) => {
                if (!response.ok) throw new Error("نقشه بارگذاری نشد.");
                return response.json();
            });
        }
        return iranMapPromise;
    }

    /** Which of the five bands a count falls in, 0 meaning "no customers". */
    function choroplethStep(count, max) {
        if (!count) return 0;
        if (max <= 1) return 5;
        // Ceil so any non-zero count lands in band 1 or above — a province
        // with one customer must never be shaded as though it had none.
        return Math.min(5, Math.max(1, Math.ceil((count / max) * 5)));
    }

    async function renderProvinceMap(host, empty, report) {
        if (!host) return;
        let map;
        try {
            map = await loadIranMap();
        } catch (error) {
            host.hidden = true;
            if (empty) {
                empty.textContent = "نقشهٔ استان‌ها بارگذاری نشد.";
                empty.hidden = false;
            }
            return;
        }

        const counts = new Map(report.results.map((row) => [row.key, row]));
        const max = report.results.reduce((top, row) => Math.max(top, row.count), 0);

        const svgNS = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(svgNS, "svg");
        svg.setAttribute("viewBox", map.viewBox);
        svg.setAttribute("class", "province-map-canvas");
        svg.setAttribute("role", "img");
        svg.setAttribute(
            "aria-label",
            `نقشهٔ پراکندگی ${toPersianDigits(String(report.placed))} مشتری در ${toPersianDigits(String(report.distinct_provinces))} استان`,
        );

        Object.entries(map.provinces).forEach(([key, province]) => {
            const row = counts.get(key);
            const count = row ? row.count : 0;
            const path = document.createElementNS(svgNS, "path");
            path.setAttribute("d", province.path);
            path.setAttribute("class", `province-map-region province-map-step-${choroplethStep(count, max)}`);
            path.dataset.province = key;
            path.dataset.count = String(count);
            path.dataset.name = province.name;
            path.setAttribute("tabindex", "0");
            // The accessible name carries the same two facts the tooltip shows,
            // so a keyboard or screen-reader user is not left with a shape.
            const title = document.createElementNS(svgNS, "title");
            title.textContent = `${province.name}: ${toPersianDigits(String(count))} مشتری`;
            path.append(title);
            svg.append(path);
        });

        const tooltip = document.createElement("div");
        tooltip.className = "province-map-tooltip";
        tooltip.hidden = true;

        function showTooltip(region) {
            const count = Number(region.dataset.count);
            const share = report.placed ? Math.round((count / report.placed) * 1000) / 10 : 0;
            tooltip.replaceChildren();
            const name = document.createElement("span");
            name.className = "province-map-tooltip-name";
            name.textContent = region.dataset.name;
            const value = document.createElement("span");
            value.className = "province-map-tooltip-value";
            value.textContent = count
                ? `${toPersianDigits(String(count))} مشتری (${toPersianDigits(String(share))}٪)`
                : "بدون مشتری";
            tooltip.append(name, value);
            tooltip.hidden = false;
        }

        function positionTooltip(event) {
            const box = host.getBoundingClientRect();
            // Clamped to the card so a province near the edge does not push the
            // tooltip outside it and trigger a horizontal scrollbar.
            const x = Math.min(Math.max(event.clientX - box.left, 8), box.width - 8);
            const y = Math.min(Math.max(event.clientY - box.top, 8), box.height - 8);
            tooltip.style.insetInlineStart = `${x}px`;
            tooltip.style.top = `${y}px`;
        }

        svg.addEventListener("pointermove", (event) => {
            const region = event.target.closest?.(".province-map-region");
            if (!region) {
                tooltip.hidden = true;
                return;
            }
            showTooltip(region);
            positionTooltip(event);
        });
        svg.addEventListener("pointerleave", () => {
            tooltip.hidden = true;
        });
        // Focus, not just hover: the regions are tabbable above, so the same
        // reading has to be available without a pointer.
        svg.addEventListener("focusin", (event) => {
            const region = event.target.closest?.(".province-map-region");
            if (!region) return;
            showTooltip(region);
            const box = host.getBoundingClientRect();
            const spot = region.getBoundingClientRect();
            tooltip.style.insetInlineStart = `${spot.left + spot.width / 2 - box.left}px`;
            tooltip.style.top = `${spot.top + spot.height / 2 - box.top}px`;
        });
        svg.addEventListener("focusout", () => {
            tooltip.hidden = true;
        });

        const legend = document.createElement("div");
        legend.className = "province-map-legend";
        const legendLabel = document.createElement("span");
        legendLabel.className = "fs-8 text-muted";
        legendLabel.textContent = "کمتر";
        legend.append(legendLabel);
        [1, 2, 3, 4, 5].forEach((step) => {
            const swatch = document.createElement("span");
            swatch.className = `province-map-swatch province-map-step-${step}`;
            legend.append(swatch);
        });
        const legendMax = document.createElement("span");
        legendMax.className = "fs-8 text-muted";
        legendMax.textContent = `بیشتر (${toPersianDigits(String(max))})`;
        legend.append(legendMax);

        host.replaceChildren(svg, tooltip, legend);
        host.hidden = false;
        if (empty) empty.hidden = true;
    }

    /**
     * The two charts under the customers table.
     *
     * Both read endpoints built on `customers_for`, so what they count is
     * exactly what the table above lists. Neither is fatal: a deployment whose
     * role cannot reach the reports still gets its customer list, and the chart
     * simply reports that it has nothing rather than taking the page down.
     */
    function setupCustomerCharts() {
        const cityChart = document.getElementById("customer-city-chart");
        const growthChart = document.getElementById("customer-growth-chart");
        if (!cityChart && !growthChart) return;

        async function loadCities() {
            const empty = document.getElementById("customer-city-chart-empty");
            try {
                // The map first — it is what this card is now — falling back to
                // the old ranking only where the map cannot say anything,
                // which is a book whose provinces were never filled in.
                const provinces = await apiRequest("/api/v1/reports/customer-provinces/");
                if (provinces.placed > 0) {
                    await renderProvinceMap(cityChart, empty, provinces);
                    const note = document.getElementById("customer-city-chart-note");
                    if (note) {
                        note.textContent = provinces.unmatched
                            ? `${toPersianDigits(String(provinces.unmatched))} مشتری استان ثبت‌شده‌ای ندارند و روی نقشه نیامده‌اند.`
                            : "";
                        note.hidden = !provinces.unmatched;
                    }
                    return;
                }
                const report = await apiRequest("/api/v1/reports/customer-cities/");
                const rows = report.results.map((row) => ({
                    label: row.label,
                    value: row.count,
                    // Count and share together: the count is the fact, the
                    // share is what makes two cities comparable.
                    display: `${toPersianDigits(String(row.count))} (${toPersianDigits(String(row.percent))}٪)`,
                }));
                const ariaLabel = `نمودار پراکندگی ${toPersianDigits(String(report.total))} مشتری در ${toPersianDigits(String(report.distinct_cities))} شهر`;
                // A few cities are parts of one customer book, which is what a
                // ring shows; many are a ranking, which is what bars show. Same
                // rule as the list charts, so the two never disagree about the
                // same shape of data.
                const populated = rows.filter((row) => row.value > 0);
                if (populated.length && populated.length <= 6) {
                    renderDonutChart(cityChart, empty, rows, {
                        ariaLabel,
                        total: toPersianDigits(String(report.total)),
                        totalLabel: "مشتری",
                    });
                } else {
                    renderBarChart(cityChart, empty, rows, {
                        // Already ordered largest-first by the endpoint, with
                        // its two aggregate rows deliberately last. Re-sorting
                        // here would lift "سایر شهرها" into the middle of the
                        // real cities.
                        sort: false,
                        ariaLabel,
                    });
                }
            } catch (error) {
                if (cityChart) cityChart.hidden = true;
                if (empty) {
                    empty.textContent = "نمودار پراکندگی شهری در دسترس نیست.";
                    empty.hidden = false;
                }
            }
        }

        let granularity = "month";
        const rangeForm = document.getElementById("customer-growth-range");

        async function loadGrowth() {
            const empty = document.getElementById("customer-growth-chart-empty");
            const query = new URLSearchParams();
            // "custom" is a window, not a bucket width. A bucket has to be a
            // fixed size for the slope between two points to mean anything, so
            // a custom range is still bucketed monthly.
            query.set("granularity", granularity === "custom" ? "month" : granularity);
            if (granularity === "custom") {
                const from = apiDateTime(textOrNull(document.getElementById("customer-growth-from").value));
                const to = apiDateTime(textOrNull(document.getElementById("customer-growth-to").value));
                if (from) query.set("period_start", from);
                if (to) query.set("period_end", to);
            }
            try {
                const report = await apiRequest(`/api/v1/reports/customer-growth/?${query}`);
                const points = report.results.map((row) => ({
                    label: displayDay(row.bucket),
                    value: row.cumulative,
                    display: `${toPersianDigits(String(row.cumulative))} مشتری (${toPersianDigits(String(row.count))} تازه)`,
                }));
                const added = report.closing_total - report.opening_total;
                renderAreaChart(growthChart, empty, points, {
                    ariaLabel: `نمودار رشد مشتریان از ${toPersianDigits(String(report.opening_total))} به ${toPersianDigits(String(report.closing_total))}`,
                    summary: `در این بازه ${toPersianDigits(String(added))} مشتری تازه ثبت شد؛ مجموع از ${toPersianDigits(String(report.opening_total))} به ${toPersianDigits(String(report.closing_total))} رسید.`,
                });
            } catch (error) {
                if (growthChart) growthChart.hidden = true;
                if (empty) {
                    empty.textContent = "نمودار رشد در دسترس نیست.";
                    empty.hidden = false;
                }
            }
        }

        document.querySelectorAll("[data-growth-range]").forEach((button) => {
            button.addEventListener("click", () => {
                granularity = button.dataset.growthRange;
                document.querySelectorAll("[data-growth-range]").forEach((other) => {
                    const active = other === button;
                    other.classList.toggle("btn-primary", active);
                    other.classList.toggle("btn-light", !active);
                    other.setAttribute("aria-pressed", String(active));
                });
                if (rangeForm) rangeForm.hidden = granularity !== "custom";
                // A custom range waits for the operator to name one; the two
                // fixed granularities redraw immediately.
                if (granularity !== "custom") loadGrowth();
            });
        });
        rangeForm?.addEventListener("submit", (event) => {
            event.preventDefault();
            loadGrowth();
        });

        loadCities();
        loadGrowth();
    }

    /**
     * The chart card beneath a list page, wherever one is declared.
     *
     * Driven by `data-list-chart` in the markup rather than by a per-page
     * function, so a twelfth page needs a template card and a registry entry
     * and no JavaScript at all.
     *
     * Every failure is contained to the card. A role without the capability, or
     * a deployment without the module, leaves the list above it working and
     * says so in the space the chart would have taken - a chart is never worth
     * taking a page down for.
     */
    /**
     * The attachments panel (common/includes/attachments_panel.inc), reused
     * on all five detail pages that carry one: customer, lead, invoice,
     * sales-document, after-sales. One generic function rather than five
     * near-duplicates — the only thing that varies per page is which parent
     * field the panel names and which of `document.body.dataset` already
     * carries that record's id.
     */
    const ATTACHMENTS_PARENT_ID_KEY = {
        customer: "customerId",
        lead: "leadId",
        invoice: "invoiceId",
        sales_document: "salesDocumentId",
        after_sales_request: "afterSalesId",
    };

    function humanFileSize(bytes) {
        const value = Number(bytes) || 0;
        if (value < 1024) return `${toPersianDigits(String(value))} بایت`;
        const kb = value / 1024;
        if (kb < 1024) return `${toPersianDigits(kb.toFixed(1))} کیلوبایت`;
        return `${toPersianDigits((kb / 1024).toFixed(1))} مگابایت`;
    }

    function attachmentRow(panel, item) {
        const row = document.createElement("tr");
        const nameCell = document.createElement("td");
        const link = document.createElement("a");
        link.href = `/api/v1/attachments/${item.id}/download/`;
        link.textContent = item.original_filename;
        link.target = "_blank";
        link.rel = "noopener";
        nameCell.appendChild(link);
        row.appendChild(nameCell);
        [item.content_type, humanFileSize(item.size_bytes), item.uploaded_by_name, displayDate(item.uploaded_at)]
            .forEach((value) => appendCell(row, value));
        const actions = document.createElement("td");
        if (panel.dataset.canDelete === "true") {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-sm btn-light-danger";
            button.textContent = "حذف";
            button.addEventListener("click", async () => {
                if (!window.confirm("این پیوست برای همیشه حذف شود؟")) return;
                try {
                    await apiRequest(`/api/v1/attachments/${item.id}/delete/`, {method: "POST"});
                    await loadAttachments(panel);
                } catch (error) {
                    showError(error);
                }
            });
            actions.appendChild(button);
        }
        row.appendChild(actions);
        return row;
    }

    async function loadAttachments(panel) {
        const field = panel.dataset.attachmentsField;
        const parentId = document.body.dataset[ATTACHMENTS_PARENT_ID_KEY[field]];
        const empty = panel.querySelector("[data-attachments-empty]");
        const wrap = panel.querySelector("[data-attachments-table-wrap]");
        const body = panel.querySelector("[data-attachments-table-body]");
        try {
            const items = await apiRequest(`/api/v1/attachments/?${new URLSearchParams({[field]: parentId})}`);
            const rows = items.map((item) => attachmentRow(panel, item));
            body.replaceChildren(...rows);
            empty.hidden = Boolean(rows.length);
            wrap.hidden = !rows.length;
        } catch (error) {
            showError(error);
        }
    }

    function setupAttachmentsPanel() {
        document.querySelectorAll("[data-attachments-panel]").forEach((panel) => {
            loadAttachments(panel);
            const form = panel.querySelector("[data-attachments-upload-form]");
            if (!form) return;
            form.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(form, async () => {
                    const field = panel.dataset.attachmentsField;
                    const parentId = document.body.dataset[ATTACHMENTS_PARENT_ID_KEY[field]];
                    const file = form.querySelector("[data-attachments-file]").files[0];
                    if (!file) return;
                    const payload = new FormData();
                    payload.set("file", file);
                    payload.set(field, parentId);
                    await apiRequest("/api/v1/attachments/", {method: "POST", body: payload, raw: true});
                    form.reset();
                    await loadAttachments(panel);
                });
            });
        });
    }

    async function setupListCharts() {
        const cards = Array.from(document.querySelectorAll("[data-list-chart]"));
        await Promise.all(cards.map(async (card) => {
            const key = card.dataset.listChart;
            const canvas = card.querySelector("[data-list-chart-canvas]");
            const empty = card.querySelector("[data-list-chart-empty]");
            const heading = card.querySelector("[data-list-chart-title]");
            if (!canvas || !empty) return;
            try {
                const report = await apiRequest(`/api/v1/reports/list-chart/${key}/`);
                if (heading && report.title) heading.textContent = report.title;
                // Every one of these is a breakdown of a total, so the shape is
                // chosen by how many parts there are rather than by which page
                // it is. Up to six, a ring compares the parts and names the
                // whole in its middle. Past that the arcs get too small to
                // compare and bars read better — the server caps the list at
                // twelve plus a grouped «سایر», so both cases really occur.
                const slices = report.results.filter((row) => Number(row.value) > 0);
                if (slices.length && slices.length <= 6) {
                    renderDonutChart(canvas, empty, report.results, {
                        ariaLabel: report.title,
                        total: report.total_display || null,
                        totalLabel: report.total_label || "",
                    });
                } else {
                    renderBarChart(canvas, empty, report.results, {
                        // The builder already ordered them and put its grouped
                        // tail last; re-sorting here would lift "سایر" into the
                        // middle.
                        sort: false,
                        ariaLabel: report.title,
                    });
                }
            } catch (error) {
                canvas.hidden = true;
                empty.textContent = "نمودار این فهرست در دسترس نیست.";
                empty.hidden = false;
            }
        }));
    }

    function phoneRow(phone, edit, deactivate) {
        const row = document.createElement("tr");
        appendCell(row, phone.raw_phone);
        appendCell(row, phone.normalized_phone);
        appendCell(row, phone.label);
        appendCell(row, phone.is_primary ? "بله" : "خیر");
        appendStatusCell(row, (phone.is_active));
        const actions = document.createElement("td");
        const editButton = document.createElement("button");
        editButton.className = "btn btn-sm btn-light";
        editButton.type = "button";
        editButton.textContent = "ویرایش";
        editButton.addEventListener("click", () => edit(phone));
        actions.appendChild(editButton);
        const deactivateButton = document.createElement("button");
        deactivateButton.className = "btn btn-sm btn-light-danger";
        deactivateButton.type = "button";
        deactivateButton.textContent = phone.is_active ? "غیرفعال" : "غیرفعال است";
        deactivateButton.disabled = !phone.is_active;
        deactivateButton.addEventListener("click", () => deactivate(phone, deactivateButton));
        actions.appendChild(deactivateButton);
        row.appendChild(actions);
        return row;
    }

    async function setupCustomerDetail() {
        const customerId = document.body.dataset.customerId;
        const endpoint = `/api/v1/customers/${customerId}/`;
        const loading = document.getElementById("customer-detail-loading");
        const content = document.getElementById("customer-detail-content");
        const editForm = document.getElementById("edit-customer-form");
        let customer;
        let editingPhoneId = null;

        function fillCustomer(value) {
            ["full_name", "national_id", "economic_code", "email", "province", "city", "postal_code", "category", "address", "notes"].forEach((name) => {
                document.getElementById(`edit-customer-${name.replaceAll("_", "-").replace("full-name", "name")}`).value = value[name] || "";
            });
            document.getElementById("customer-created-by").value = value.created_by_display || value.created_by;
            // A Platform Admin gets a select; everyone else the read-only text.
            const activeSelect = document.getElementById("customer-active-select");
            if (activeSelect) {
                activeSelect.value = String(Boolean(value.is_active));
            } else {
                document.getElementById("customer-active").value = statusText(value.is_active);
            }
        }

        async function loadCustomer() {
            customer = await apiRequest(endpoint);
            fillCustomer(customer);
        }

        const phoneLoading = document.getElementById("phones-loading");
        const phoneEmpty = document.getElementById("phones-empty");
        const phoneWrap = document.getElementById("phones-table-wrap");
        const phoneBody = document.getElementById("phones-table-body");
        const phoneDialog = document.getElementById("phone-dialog");
        const phoneForm = document.getElementById("phone-form");

        function openPhone(phone = null) {
            editingPhoneId = phone?.id || null;
            document.getElementById("phone-dialog-title").textContent = phone ? "ویرایش تلفن" : "تلفن جدید";
            document.getElementById("phone-raw").value = phone?.raw_phone || "";
            document.getElementById("phone-label").value = phone?.label || "";
            document.getElementById("phone-primary").checked = Boolean(phone?.is_primary);
            clearMessages(phoneForm);
            phoneDialog.showModal();
        }

        async function deactivatePhone(phone, button) {
            if (!window.confirm("این تلفن غیرفعال شود؟")) return;
            button.disabled = true;
            clearMessages();
            try {
                await apiRequest(`/api/v1/customer-phones/${phone.id}/deactivate/`, {method: "POST"});
                globalMessage("تلفن غیرفعال شد.", true);
                await loadPhones();
            } catch (error) {
                button.disabled = false;
                showError(error);
            }
        }

        async function loadPhones() {
            phoneLoading.hidden = false;
            phoneEmpty.hidden = true;
            phoneWrap.hidden = true;
            try {
                const phones = await loadAllPages(`/api/v1/customer-phones/?customer=${customerId}&ordering=-is_primary`);
                phoneBody.replaceChildren(...phones.map((phone) => phoneRow(phone, openPhone, deactivatePhone)));
                phoneLoading.hidden = true;
                if (!phones.length) { phoneEmpty.hidden = false; return; }
                phoneWrap.hidden = false;
            } catch (error) {
                phoneLoading.hidden = true;
                showError(error);
            }
        }

        function setupCustomerRelatedList(key, path, renderRow, {absolute = false} = {}) {
            const listLoading = document.getElementById(`customer-${key}-loading`);
            const listEmpty = document.getElementById(`customer-${key}-empty`);
            const listWrap = document.getElementById(`customer-${key}-table-wrap`);
            const listBody = document.getElementById(`customer-${key}-table-body`);
            const listPagination = document.getElementById(`customer-${key}-pagination`);
            const previous = document.getElementById(`customer-${key}-prev`);
            const next = document.getElementById(`customer-${key}-next`);
            let currentPage = 1;

            async function load(page = 1) {
                listLoading.hidden = false;
                listEmpty.hidden = true;
                listWrap.hidden = true;
                listPagination.hidden = true;
                try {
                    // Most related lists are sub-resources of the customer; the
                    // orders panel reads the orders endpoint filtered by this
                    // customer, because that is where orders actually live.
                    const url = absolute
                        ? `${path}${path.includes("?") ? "&" : "?"}page=${page}`
                        : `${endpoint}${path}/?page=${page}`;
                    const data = await apiRequest(url);
                    // A renderer may expand one record into several rows — the
                    // orders panel lists a row per line — so results are
                    // flattened rather than assumed one-to-one.
                    listBody.replaceChildren(...data.results.flatMap(renderRow));
                    listLoading.hidden = true;
                    if (!data.results.length) { listEmpty.hidden = false; return; }
                    listWrap.hidden = false;
                    currentPage = page;
                    previous.disabled = !data.previous;
                    next.disabled = !data.next;
                    document.getElementById(`customer-${key}-page-label`).textContent = pageRangeLabel(data, page);
                    listPagination.hidden = !data.previous && !data.next;
                } catch (error) {
                    listLoading.hidden = true;
                    showError(error);
                }
            }

            previous.addEventListener("click", () => load(currentPage - 1));
            next.addEventListener("click", () => load(currentPage + 1));
            return {load};
        }

        /**
         * One row per invoice this customer has.
         *
         * The panel answers "where does this customer's account stand", which
         * is a question about documents rather than goods, so each row is one
         * invoice: its number, where it is, what it came to and what is still
         * owed. Both settlement columns are shown because they can disagree —
         * a manually settled invoice reads as paid while its canonical balance
         * is untouched, and hiding one of the two would make the page lie.
         */
        function customerInvoiceRow(invoice) {
            const row = document.createElement("tr");
            appendCell(row, invoice.number).dir = "ltr";
            appendStatusBadgeCell(row, DOCUMENT_STATUS_TEXT, invoice.status);
            appendCell(row, labelled(SETTLEMENT_TEXT, invoice.settlement_status));
            appendMoneyCell(row, invoice.total_amount);
            appendMoneyCell(row, invoice.balance_due);
            appendCell(row, displayDay(invoice.issued_at));
            appendActionLinks(row, [[`/invoices/${invoice.id}/`, "مشاهده"]]);
            return row;
        }

        const relatedLists = [
            setupCustomerRelatedList("leads", "leads", leadRow),
            setupCustomerRelatedList("interactions", "interactions", interactionRow),
        ];
        // Related orders became related invoices. The box is only rendered for
        // a reader whose deployment has invoices at all, so its absence is not
        // an error — the endpoint checks scope again regardless.
        if (document.getElementById("customer-invoices-table-wrap")) {
            relatedLists.push(setupCustomerRelatedList(
                "invoices",
                `/api/v1/invoices/?customer=${customerId}`,
                customerInvoiceRow,
                {absolute: true},
            ));
        }

        /**
         * The 360° history strip.
         *
         * Loaded after the page is already usable and outside the `try`
         * that gates it, deliberately: the boxes above are what this page
         * *is*, and a timeline that failed to load must not blank the
         * customer's own record behind an error card. It reports its own
         * failure in its own section and leaves everything else standing.
         */
        async function loadTimeline() {
            const list = document.getElementById("customer-timeline-list");
            if (!list) return;
            const timelineLoading = document.getElementById("customer-timeline-loading");
            const empty = document.getElementById("customer-timeline-empty");
            const failed = document.getElementById("customer-timeline-error");
            const more = document.getElementById("customer-timeline-more");
            try {
                const data = await apiRequest(`/api/v1/customers/${customerId}/timeline/`);
                list.replaceChildren();
                data.events.forEach((event) => list.appendChild(timelineEntry(event)));
                timelineLoading.hidden = true;
                list.hidden = data.events.length === 0;
                empty.hidden = data.events.length > 0;
                // `count` is everything found; `events` is the page shown.
                if (data.count > data.events.length) {
                    more.textContent = `${toPersianDigits(String(data.count - data.events.length))} رویداد قدیمی‌تر نشان داده نشده است.`;
                    more.hidden = false;
                }
            } catch (error) {
                timelineLoading.hidden = true;
                failed.hidden = false;
            }
        }

        function timelineEntry(event) {
            const item = document.createElement("li");
            item.className = "customer-timeline-entry";

            const marker = document.createElement("span");
            marker.className = `customer-timeline-marker bg-light-${event.accent}`;
            const icon = document.createElement("i");
            icon.className = `ki-duotone ${event.icon} fs-5 text-${event.accent}`;
            for (let index = 1; index <= (event.icon_paths || 2); index += 1) {
                icon.append(timelinePath(index));
            }
            marker.appendChild(icon);

            const box = document.createElement("div");
            box.className = "customer-timeline-body";

            const head = document.createElement("div");
            head.className = "d-flex flex-wrap align-items-center justify-content-between gap-2";
            const kind = document.createElement("span");
            kind.className = `badge badge-light-${event.accent} fs-8`;
            kind.textContent = event.label;
            const when = document.createElement("span");
            when.className = "text-muted fs-8";
            when.textContent = displayDate(event.at);
            head.append(kind, when);

            const title = document.createElement("a");
            title.className = "d-block text-gray-900 fw-semibold fs-6 mt-1 text-decoration-none";
            title.href = event.url;
            title.textContent = event.title;

            const subtitle = document.createElement("span");
            subtitle.className = "d-block text-muted fs-7";
            subtitle.textContent = event.subtitle;

            box.append(head, title, subtitle);
            item.append(marker, box);
            return item;
        }

        function timelinePath(index) {
            const span = document.createElement("span");
            span.className = `path${index}`;
            return span;
        }

        try {
            await loadCustomer();
            await loadPhones();
            for (const list of relatedLists) await list.load();
            loading.hidden = true;
            content.hidden = false;
        } catch (error) {
            loading.hidden = true;
            showError(error);
            return;
        }
        loadTimeline();
        editForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(editForm, async () => {
                customer = await apiRequest(endpoint, {method: "PATCH", body: formPayload(editForm, ["full_name", "national_id", "economic_code", "email", "province", "city", "postal_code", "category", "address", "notes"])});
                fillCustomer(customer);
                globalMessage("مشخصات مشتری ذخیره شد.", true);
            });
        });
        document.getElementById("open-create-phone").addEventListener("click", () => openPhone());
        phoneDialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => phoneDialog.close()));
        phoneForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(phoneForm, async () => {
                const payload = formPayload(phoneForm, ["raw_phone", "label"]);
                payload.is_primary = document.getElementById("phone-primary").checked;
                if (!editingPhoneId) payload.customer = Number(customerId);
                const url = editingPhoneId ? `/api/v1/customer-phones/${editingPhoneId}/` : phoneForm.action;
                await apiRequest(url, {method: editingPhoneId ? "PATCH" : "POST", body: payload});
                phoneDialog.close();
                globalMessage("تلفن ذخیره شد.", true);
                await loadPhones();
            });
        });
        // Activation state. Reversible on purpose: it hides the customer from
        // day-to-day work and removes nothing, so switching back restores them.
        const activeSelect = document.getElementById("customer-active-select");
        activeSelect?.addEventListener("change", async () => {
            const nextActive = activeSelect.value === "true";
            if (nextActive === Boolean(customer.is_active)) return;
            const question = nextActive ? "این مشتری دوباره فعال شود؟" : "این مشتری غیرفعال شود؟";
            if (!window.confirm(question)) {
                activeSelect.value = String(Boolean(customer.is_active));
                return;
            }
            activeSelect.disabled = true;
            clearMessages();
            try {
                customer = await apiRequest(`${endpoint}set-active/`, {
                    method: "POST", body: {is_active: nextActive},
                });
                fillCustomer(customer);
                globalMessage(
                    nextActive ? "مشتری دوباره فعال شد." : "مشتری بدون حذف سابقه غیرفعال شد.",
                    true,
                );
            } catch (error) {
                activeSelect.value = String(Boolean(customer.is_active));
                showError(error);
            } finally {
                activeSelect.disabled = false;
            }
        });
    }

    /** The three states a campaign is tracked in, as the theme's badges. */
    const LEAD_STATUS_LABELS = {
        pending: ["در انتظار تکمیل", "badge-light-warning"],
        completed: ["تکمیل", "badge-light-success"],
        cancelled: ["کنسل شده", "badge-light-danger"],
    };

    function leadRow(lead) {
        const row = document.createElement("tr");
        // The customer column is gone: a campaign is worked from its target
        // audience rather than from one customer.
        appendCell(row, lead.source);
        appendCell(row, lead.campaign_or_batch);
        const [label, badgeClass] = LEAD_STATUS_LABELS[lead.status] || [lead.status || "—", "badge-light"];
        const statusCell = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = `badge ${badgeClass}`;
        badge.textContent = label;
        statusCell.append(badge);
        row.append(statusCell);
        appendCell(row, lead.assigned_to_display || lead.assigned_to);
        // Follow-up and registration are both days; the time of day was never
        // acted on and only made the column harder to scan.
        appendCell(row, displayDay(lead.next_follow_up_at));
        appendCell(row, displayDay(lead.created_at));
        appendDetailLink(row, `/leads/${lead.id}/`);
        return row;
    }

    async function setupLeads() {
        const form = document.getElementById("lead-search-form");
        setupListFilter("lead");
        const controller = setupPagedList({
            key: "leads", form,
            search: document.getElementById("lead-search"),
            endpoint(page) {
                const query = new URLSearchParams({page: String(page), ordering: document.getElementById("lead-ordering").value});
                const search = document.getElementById("lead-search").value.trim();
                const status = document.getElementById("lead-status-filter").value.trim();
                if (search) query.set("search", search);
                if (status) query.set("status", status);
                return `/api/v1/leads/?${query}`;
            }, renderRow: leadRow,
        });
        const dialog = document.getElementById("create-lead-dialog");
        const createForm = document.getElementById("create-lead-form");
        function renderLeadReview() {
            renderWizardReview(document.getElementById("create-lead-review"), [
                ["منبع", document.getElementById("create-lead-source").value || "—"],
                ["کمپین یا نوبت", document.getElementById("create-lead-campaign").value || "—"],
                ["وضعیت", selectedOptionText(document.getElementById("create-lead-status"))],
                ["پیگیری بعدی", document.getElementById("create-lead-follow-up").value || "—"],
                ["یادداشت", document.getElementById("create-lead-notes").value || "—"],
            ]);
        }
        const leadWizard = setupWizard(dialog, {onReachLastStep: renderLeadReview});
        document.getElementById("open-create-lead").addEventListener("click", () => {
            createForm.reset();
            clearMessages(createForm);
            leadWizard?.goFirst();
            dialog.showModal();
        });
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        try {
            await controller.load();
        } catch (error) { showError(error); }
        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const data = new FormData(createForm);
                // No customer and no interested product: a campaign is worked
                // from its target audience.
                const payload = formPayload(createForm, ["source", "campaign_or_batch", "status", "notes"]);
                if (data.get("next_follow_up_at")) payload.next_follow_up_at = apiDateTime(data.get("next_follow_up_at"));
                const lead = await apiRequest(createForm.action, {method: "POST", body: payload});
                window.location.assign(`/leads/${lead.id}/`);
            });
        });
    }

    /**
     * The lead follow-up calendar.
     *
     * FullCalendar draws a Gregorian grid — the theme's own bundled build
     * carries no Jalali locale — so every label a reader actually reads (the
     * day-of-month number, the month/year title) is overwritten with its
     * Jalali equivalent after render. The grid's own navigation stays
     * Gregorian internally; only what it says on screen is not.
     *
     * Events come from `leads_for(user)` through the ordinary `/api/v1/leads/`
     * endpoint, narrowed to the visible range by `follow_up_from`/`follow_up_to`
     * — the same scope and the same rows the leads list page would show for
     * the same reader, just laid out by date instead of in a table.
     */
    /**
     * The clock labels both calendars draw, and the fix-up the format options
     * cannot express on their own.
     *
     * The bundle carries no Jalali/Persian locale, so FullCalendar formatted
     * every clock label through its English default: a grid whose day numbers,
     * month title and weekday names were all deliberately localised was still
     * labelling each event `8:50p`, and the week/day hour axis `12am, 1am, …`.
     * The format below settles the shape — 24 hour, the Iranian convention,
     * zero-padded — and the two helpers settle the digits, which no format
     * option covers.
     */
    const CALENDAR_TIME_FORMAT = {hour: "2-digit", minute: "2-digit", hour12: false};

    function persianiseEventTime(info) {
        const node = info.el.querySelector(".fc-event-time");
        if (node) node.textContent = toPersianDigits(node.textContent);
    }

    /** The week/day view's hour axis, in Persian digits. */
    function persianSlotLabel(arg) {
        return toPersianDigits(arg.text);
    }

    async function setupLeadCalendar() {
        const container = document.getElementById("lead-calendar");
        if (!container || typeof FullCalendar === "undefined") return;
        const loading = document.getElementById("lead-calendar-loading");
        const errorNode = document.getElementById("lead-calendar-error");

        function jalaliDayLabel(date) {
            const [, , day] = gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
            return toPersianDigits(String(day));
        }

        function jalaliTitle(date, exact) {
            const [year, month, day] = gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
            const monthYear = `${JALALI_MONTH_NAMES[month - 1]} ${toPersianDigits(String(year))}`;
            // `exact`: the day view has only one date on screen and nothing
            // else naming it, unlike month view (numbered cells) or week view
            // (a date under each column's own header) — so its title is the
            // one place that has to carry the day-of-month too.
            return exact ? `${toPersianDigits(String(day))} ${monthYear}` : monthYear;
        }

        const palette = chartPalette();
        // pending/completed/cancelled — the three backend-owned Lead statuses,
        // same order and same colours `sales_by_agent`-style charts already use
        // for "needs attention" (primary), "done" (success), "closed out, no
        // action" (danger) — and the same three the legend above already shows.
        const STATUS_META = {
            pending: {label: "در انتظار تکمیل", color: palette[0], badgeClass: "badge-light-primary"},
            completed: {label: "تکمیل", color: palette[1], badgeClass: "badge-light-success"},
            cancelled: {label: "کنسل شده", color: palette[4], badgeClass: "badge-light-danger"},
        };

        /**
         * A hover preview richer than one title-attribute line: who it's for,
         * status, agent, source/campaign, and a notes preview — everything a
         * follow-up needs to be actioned without leaving the calendar.
         *
         * Every piece of text below goes through `textContent`, never through
         * an HTML string built by hand — a customer name, note, or source is
         * free text someone typed, and this file never assigns to `innerHTML`
         * from a template literal anywhere. `content.innerHTML` is read once,
         * at the very end, only to hand Bootstrap's Popover the markup it
         * requires — by then every value in it was already escaped by the
         * browser itself when each `textContent` assignment above ran.
         */
        function buildEventPopoverContent(lead, meta, overdue, when) {
            const wrap = document.createElement("div");

            const nameLine = document.createElement("div");
            nameLine.className = "fw-bold fs-6 mb-1";
            nameLine.textContent = lead.customer_name || "سرنخ بدون مشتری";
            wrap.append(nameLine);

            const badgeRow = document.createElement("div");
            badgeRow.className = "d-flex flex-wrap gap-2 mb-2";
            const statusBadge = document.createElement("span");
            statusBadge.className = `badge ${meta.badgeClass}`;
            statusBadge.textContent = meta.label;
            badgeRow.append(statusBadge);
            if (overdue) {
                const overdueBadge = document.createElement("span");
                overdueBadge.className = "badge badge-light-danger";
                overdueBadge.textContent = "دیرکرد";
                badgeRow.append(overdueBadge);
            }
            wrap.append(badgeRow);

            [
                ["کارشناس", lead.assigned_to_display],
                ["منبع", lead.source],
                ["کمپین", lead.campaign_or_batch],
                ["زمان پیگیری", when],
            ].forEach(([label, value]) => {
                if (!value) return;
                const row = document.createElement("div");
                row.className = "fs-8 text-gray-600 mb-1";
                const strong = document.createElement("span");
                strong.className = "text-gray-800 fw-semibold";
                strong.textContent = `${label}: `;
                row.append(strong, document.createTextNode(value));
                wrap.append(row);
            });

            if (lead.notes) {
                const notes = document.createElement("div");
                notes.className = "fs-8 text-gray-600 mt-2 pt-2 border-top border-gray-300";
                notes.textContent = lead.notes.length > 100 ? `${lead.notes.slice(0, 100)}…` : lead.notes;
                wrap.append(notes);
            }
            return wrap;
        }

        const calendar = new FullCalendar.Calendar(container, {
            direction: "rtl",
            height: "auto",
            firstDay: 6, // Saturday — the Iranian week start.
            // Otherwise the trailing/leading days of the *adjacent* Gregorian
            // month fill out the grid's first/last week — and because every
            // cell's own number is re-labelled in Jalali (`dayCellContent`
            // below), those spillover cells show Jalali day numbers that
            // belong to neither the month in the title nor a full week of
            // their own, reading as numbers with no calendar around them
            // (design review, 2026-09-12).
            showNonCurrentDates: false,
            headerToolbar: {start: "prev,next today", center: "title", end: "dayGridMonth,timeGridWeek,timeGridDay"},
            buttonText: {today: "امروز", month: "ماه", week: "هفته", day: "روز"},
            dayHeaderContent: (arg) => {
                const weekday = PERSIAN_WEEKDAY_NAMES[arg.date.getDay()];
                // Month view names the column once, above every date in it —
                // the date itself is each cell's own number (`dayCellContent`
                // below), so the header needs only the name.
                if (arg.view.type === "dayGridMonth") return weekday;
                // Week/day views have one column per date, so the header is
                // the only place that date appears — stacked on two lines,
                // not one, so a wide name like "چهارشنبه" never has to shrink
                // to fit next to a day number in a week view's seven columns.
                const wrap = document.createElement("div");
                const nameLine = document.createElement("div");
                nameLine.textContent = weekday;
                const dayLine = document.createElement("div");
                dayLine.className = "fs-4 fw-bold";
                dayLine.textContent = jalaliDayLabel(arg.date);
                wrap.append(nameLine, dayLine);
                return {domNodes: [wrap]};
            },
            dayCellContent: (arg) => jalaliDayLabel(arg.date),
            datesSet: (info) => {
                if (info.view.type === "timeGridDay") {
                    const titleEl = container.querySelector(".fc-toolbar-title");
                    if (titleEl) titleEl.textContent = jalaliTitle(info.view.currentStart, true);
                    return;
                }
                // The visible grid's own centre, not `currentStart` — a month
                // view's first cell is often still the tail of the previous
                // Jalali month, which would title "شهریور" a grid that reads
                // as "مهر" to anyone looking at it.
                const middle = new Date((info.view.currentStart.getTime() + info.view.currentEnd.getTime()) / 2);
                const titleEl = container.querySelector(".fc-toolbar-title");
                if (titleEl) titleEl.textContent = jalaliTitle(middle, false);
            },
            editable: true,
            eventStartEditable: true,
            eventDurationEditable: false,
            dayMaxEvents: true,
            // Without this, a timed follow-up (most of them — only a
            // date-only one is all-day) renders in month view as FullCalendar's
            // default small dot + text, and the status colour all but
            // disappears into a single-pixel dot. Block display gives every
            // follow-up the same full-colour chip regardless of view, so
            // status is readable at a glance everywhere, not just in week/day.
            eventDisplay: "block",
            eventTimeFormat: CALENDAR_TIME_FORMAT,
            slotLabelFormat: CALENDAR_TIME_FORMAT,
            slotLabelContent: persianSlotLabel,
            allDayText: "تمام‌روز",
            moreLinkText: (count) => `+${toPersianDigits(String(count))} مورد دیگر`,
            events: async (fetchInfo, successCallback, failureCallback) => {
                try {
                    const query = new URLSearchParams({
                        follow_up_from: fetchInfo.startStr,
                        follow_up_to: fetchInfo.endStr,
                    });
                    const leads = await loadAllPages(`/api/v1/leads/?${query}`);
                    loading.hidden = true;
                    errorNode.hidden = true;
                    container.hidden = false;
                    const now = new Date();
                    successCallback(leads.map((lead) => {
                        // A follow-up set from the date-only picker lands on
                        // Tehran midnight; that is what "all day" means here —
                        // a time-precise one (set from an interaction's own
                        // datetime field) keeps its clock.
                        const parts = tehranParts(lead.next_follow_up_at);
                        const allDay = Boolean(parts && parts.hour === 0 && parts.minute === 0);
                        const meta = STATUS_META[lead.status] || STATUS_META.pending;
                        // Only a still-pending follow-up can be "late" — a
                        // completed or cancelled one has nothing left to act on,
                        // so a past date on those is expected, not a warning.
                        const overdue = lead.status === "pending" && new Date(lead.next_follow_up_at) < now;
                        return {
                            id: String(lead.id),
                            title: lead.customer_name
                                ? `${lead.customer_name}${lead.assigned_to_display ? " — " + lead.assigned_to_display : ""}`
                                : `سرنخ بدون مشتری${lead.assigned_to_display ? " — " + lead.assigned_to_display : ""}`,
                            start: lead.next_follow_up_at,
                            allDay,
                            backgroundColor: meta.color,
                            borderColor: meta.color,
                            classNames: overdue ? ["fc-event-overdue"] : [],
                            extendedProps: {lead, meta, overdue},
                        };
                    }));
                } catch (error) {
                    loading.hidden = true;
                    errorNode.textContent = errorText(error);
                    errorNode.hidden = false;
                    failureCallback(error);
                }
            },
            eventClick: (info) => {
                window.location.href = `/leads/${info.event.id}/`;
            },
            eventDrop: async (info) => {
                try {
                    await apiRequest(`/api/v1/leads/${info.event.id}/`, {
                        method: "PATCH",
                        body: {next_follow_up_at: info.event.start.toISOString()},
                    });
                    globalMessage("تاریخ پیگیری به‌روزرسانی شد.", true);
                } catch (error) {
                    info.revert();
                    showError(error);
                }
            },
            eventDidMount: (info) => {
                persianiseEventTime(info);
                const {lead, meta, overdue} = info.event.extendedProps;
                // FullCalendar's day-limit ("+N more") layout pass mounts an
                // event element to measure it before every event is known to
                // carry the custom props this file attaches — a mount with no
                // `lead` yet is that measurement pass, not a real one, and
                // gets no popover; the later real mount for the same event
                // still gets one normally.
                if (!lead) return;
                const when = info.event.allDay
                    ? displayDay(info.event.startStr)
                    : displayDate(info.event.startStr);
                const content = buildEventPopoverContent(lead, meta, overdue, when);
                // eslint-disable-next-line -- see buildEventPopoverContent's own
                // comment: every value in `content` was already escaped by
                // `textContent` before this line ever runs.
                new bootstrap.Popover(info.el, {
                    trigger: "hover focus",
                    placement: "top",
                    html: true,
                    customClass: "lead-calendar-popover",
                    content: content.innerHTML,
                });
            },
            eventWillUnmount: (info) => {
                bootstrap.Popover.getInstance(info.el)?.dispose();
            },
        });
        calendar.render();
    }

    /**
     * One board column's own search, collapsed behind a small icon button in
     * that column's header (product-owner decision 2026-09-09).
     *
     * Shared by both boards below because the shape is identical: a toggle
     * appended into jKanban's own `.kanban-title-board`, and one input
     * revealed between that header and the column's card list. `onSearch`
     * receives the trimmed term and refetches that column alone; the term
     * goes to the same DRF `search=` the list page's own box already uses, so
     * a column searches exactly the fields its list searches (leads:
     * customer name, source, campaign, notes — orders: number, customer,
     * notes, and each line's product name) with no new backend surface.
     *
     * Collapsed by default on purpose: four permanently-open search boxes
     * across a four-column board would crowd out the cards they filter.
     */
    function setupBoardColumnSearch(container, status, onSearch) {
        const board = container.querySelector(`.kanban-board[data-id="${status}"]`);
        const title = board?.querySelector(".kanban-title-board");
        const drag = board?.querySelector(".kanban-drag");
        if (!board || !title || !drag) return;

        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "btn btn-icon btn-sm btn-active-light-primary board-search-toggle";
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "جست‌وجو در این ستون");
        const icon = document.createElement("i");
        icon.className = "ki-duotone ki-magnifier fs-5";
        ["path1", "path2"].forEach((name) => {
            const path = document.createElement("span");
            path.className = name;
            icon.append(path);
        });
        toggle.append(icon);
        title.append(toggle);

        const wrap = document.createElement("div");
        wrap.className = "board-search";
        wrap.hidden = true;
        const input = document.createElement("input");
        input.type = "search";
        input.className = "form-control form-control-solid";
        input.placeholder = "جست‌وجو در این ستون…";
        input.setAttribute("aria-label", "جست‌وجو در این ستون");
        wrap.append(input);
        board.insertBefore(wrap, drag);

        toggle.addEventListener("click", () => {
            const opening = wrap.hidden;
            wrap.hidden = !opening;
            toggle.setAttribute("aria-expanded", String(opening));
            if (opening) {
                input.focus();
                return;
            }
            // Closing the box clears the filter: leaving a column silently
            // filtered by a term nobody can see any more is the one way this
            // control could lie about what the board contains.
            if (input.value) {
                input.value = "";
                onSearch("");
            }
        });

        bindLiveSearch(input, () => onSearch(input.value.trim()));
    }

    /**
     * The leads Kanban board — the same three real `Lead.status` values
     * (`LEAD_STATUS_LABELS` above, the ordinary list's own badge map) as
     * fixed columns, drawn with the theme's own `jkanban` bundle (dragula
     * under it) rather than a hand-rolled drag-and-drop implementation.
     *
     * Every card comes from `leads_for(user)` through the ordinary
     * `/api/v1/leads/?status=` endpoint, one paginated request per column —
     * the same scope and the same rows the list page and the calendar would
     * show for the same reader. Dropping a card into another column PATCHes
     * that same lead through `/api/v1/leads/<id>/`, the very endpoint the
     * calendar's own drag already uses for a different field, so this adds
     * no new mutation path: `LeadSerializer.update` -> `sales.services.
     * update_lead` still validates the status, still locks the actor, still
     * refuses a sales agent a lead outside their own scope.
     */
    async function setupLeadBoard() {
        const container = document.getElementById("lead-board");
        if (!container || typeof jKanban === "undefined") return;
        const loading = document.getElementById("lead-board-loading");
        const errorNode = document.getElementById("lead-board-error");
        const canManage = container.dataset.canManageLeads === "true";

        // pending/completed/cancelled, same order `LEAD_STATUS_LABELS` and
        // the calendar legend already use.
        const STATUSES = Object.keys(LEAD_STATUS_LABELS);
        // Where the next page for each column's own "load more" comes from,
        // and whether that column has anything at all — kept outside jKanban
        // itself, which has no paging concept of its own.
        const pageState = {};

        function boardTitle(status, count) {
            const [label] = LEAD_STATUS_LABELS[status];
            const wrap = document.createElement("div");
            wrap.className = "d-flex align-items-center gap-2";
            const text = document.createElement("span");
            text.textContent = label;
            const badge = document.createElement("span");
            badge.className = "badge badge-light-secondary";
            badge.textContent = toPersianDigits(String(count));
            wrap.append(text, badge);
            return wrap.innerHTML;
        }

        /**
         * Every piece of text below goes through `textContent`; `innerHTML`
         * is read once, at the end, only because jKanban's own API takes an
         * item's content as an HTML string — the same escape-then-serialise
         * pattern `buildEventPopoverContent` above already uses for the same
         * reason with Bootstrap's Popover.
         */
        function cardContent(lead) {
            const wrap = document.createElement("div");

            const title = document.createElement("div");
            title.className = "fw-bold fs-6 mb-2 text-gray-900";
            title.textContent = lead.customer_name || lead.source || `سرنخ #${toPersianDigits(String(lead.id))}`;
            wrap.append(title);

            if (lead.assigned_to_display) {
                const row = document.createElement("div");
                row.className = "d-flex align-items-center gap-2 mb-2";
                const symbol = document.createElement("span");
                symbol.className = "symbol symbol-25px symbol-circle";
                const symbolLabel = document.createElement("span");
                const colors = ["primary", "success", "info", "warning", "danger"];
                const color = colors[Math.abs(Number(lead.assigned_to)) % colors.length];
                symbolLabel.className = `symbol-label bg-light-${color} text-${color} fw-bold fs-8`;
                symbolLabel.textContent = lead.assigned_to_display.trim().charAt(0);
                symbol.append(symbolLabel);
                const name = document.createElement("span");
                name.className = "fs-8 text-gray-700";
                name.textContent = lead.assigned_to_display;
                row.append(symbol, name);
                wrap.append(row);
            }

            [
                ["منبع", lead.source],
                ["کمپین", lead.campaign_or_batch],
            ].forEach(([label, value]) => {
                if (!value) return;
                const row = document.createElement("div");
                row.className = "fs-8 text-gray-600 mb-1";
                row.textContent = `${label}: ${value}`;
                wrap.append(row);
            });

            if (lead.next_follow_up_at) {
                const row = document.createElement("div");
                row.className = "fs-8 text-gray-600 mb-1";
                row.textContent = `پیگیری بعدی: ${displayDay(lead.next_follow_up_at)}`;
                wrap.append(row);
            }

            const link = document.createElement("a");
            link.className = "fs-8 fw-semibold mt-1 d-inline-block";
            link.href = `/leads/${lead.id}/`;
            link.textContent = "مشاهدهٔ جزئیات";
            wrap.append(link);

            return wrap.innerHTML;
        }

        function toItem(lead) {
            return {id: String(lead.id), title: cardContent(lead)};
        }

        function boardElement(status) {
            return container.querySelector(`.kanban-board[data-id="${status}"] .kanban-drag`);
        }

        // Kept alongside the DOM rather than re-read from it: the badge text
        // is Persian digits, and counting from a known number is simpler and
        // less fragile than parsing them back out on every drop.
        const counts = {};

        function updateBoardCount(status, delta) {
            counts[status] += delta;
            const badge = container.querySelector(
                `.kanban-board[data-id="${status}"] .kanban-title-board .badge`,
            );
            if (badge) badge.textContent = toPersianDigits(String(counts[status]));
        }

        function renderLoadMore(status) {
            const drag = boardElement(status);
            if (!drag) return;
            drag.querySelector(".lead-board-load-more")?.remove();
            const state = pageState[status];
            if (!state?.next) return;
            const button = document.createElement("button");
            button.type = "button";
            // `not-draggable`: jkanban.bundle.js cancels a drag started on any
            // element carrying this class, the same mechanism its own
            // add-item footer uses — not a real kanban item, so it must not
            // behave like one.
            button.className = "btn btn-sm btn-light-primary w-100 not-draggable lead-board-load-more";
            button.textContent = "بارگذاری بیشتر";
            button.addEventListener("click", () => loadMore(status));
            drag.append(button);
        }

        function renderEmptyState(status) {
            const drag = boardElement(status);
            if (!drag || drag.querySelector(".kanban-item")) return;
            const empty = document.createElement("div");
            empty.className = "not-draggable lead-board-empty text-center fs-8 py-6";
            empty.textContent = pageState[status]?.search
                ? "سرنخی با این جست‌وجو در این ستون نیست."
                : "سرنخی در این وضعیت نیست.";
            drag.append(empty);
        }

        function columnUrl(status, page) {
            const term = pageState[status]?.search;
            const search = term ? `&search=${encodeURIComponent(term)}` : "";
            return `/api/v1/leads/?status=${status}&ordering=-created_at&page=${page}${search}`;
        }

        async function loadMore(status) {
            const state = pageState[status];
            if (!state?.next) return;
            try {
                const data = await apiRequest(state.next);
                data.results.forEach((lead) => kanban.addElement(status, toItem(lead)));
                state.next = data.next;
                renderLoadMore(status);
            } catch (error) {
                showError(error);
            }
        }

        /**
         * Refetch one column from page 1 under its own search term. The card
         * list is emptied and rebuilt rather than filtered in place: the term
         * is applied by the server across the whole column, not just the page
         * already loaded, so hiding local cards would under-report every match
         * past the first page.
         */
        async function reloadColumn(status, term) {
            const drag = boardElement(status);
            if (!drag) return;
            pageState[status] = {...pageState[status], search: term};
            try {
                const data = await apiRequest(columnUrl(status, 1));
                drag.innerHTML = "";
                data.results.forEach((lead) => kanban.addElement(status, toItem(lead)));
                pageState[status] = {next: data.next, search: term};
                counts[status] = data.count;
                const badge = container.querySelector(
                    `.kanban-board[data-id="${status}"] .kanban-title-board .badge`,
                );
                if (badge) badge.textContent = toPersianDigits(String(data.count));
                renderLoadMore(status);
                renderEmptyState(status);
            } catch (error) {
                showError(error);
            }
        }

        let kanban;

        loading.hidden = false;
        errorNode.hidden = true;
        container.hidden = true;
        try {
            const pages = await Promise.all(
                STATUSES.map((status) =>
                    apiRequest(`/api/v1/leads/?status=${status}&ordering=-created_at&page=1`),
                ),
            );
            loading.hidden = true;
            container.hidden = false;

            const boards = STATUSES.map((status, index) => {
                const data = pages[index];
                pageState[status] = {next: data.next};
                counts[status] = data.count;
                // No `dragTo` restriction: nothing in `_validate_lead_status`
                // (sales/services.py) restricts which of the three statuses a
                // lead may move to from which, so every column accepts a drop
                // from every other one — jKanban's own default when `dragTo`
                // is left unset.
                return {
                    id: status,
                    title: boardTitle(status, data.count),
                    item: data.results.map(toItem),
                };
            });

            kanban = new jKanban({
                element: "#lead-board",
                gutter: "0.75rem",
                widthBoard: "300px",
                // Not `responsivePercentage`: reading jkanban.bundle.js shows
                // it unconditionally overwrites `gutter` to a hard-coded
                // `"1%"` the moment this is on, silently ignoring whatever
                // `gutter` above says — measured directly (computed
                // `margin-right` stayed a nonzero percentage no matter what
                // `gutter` was set to). Narrow-viewport stacking is handled
                // in CSS instead: `#lead-board .kanban-board`'s own
                // `max-width: 767.98px` rule in dolphin.css forces full width
                // with `!important`, the only way to beat this inline style.
                dragBoards: false,
                dragItems: canManage,
                boards,
                click: (el) => {
                    window.location.href = `/leads/${el.dataset.eid}/`;
                },
                dropEl: async (el, target, source) => {
                    const leadId = el.dataset.eid;
                    const toStatus = target.parentNode.dataset.id;
                    const fromStatus = source.parentNode.dataset.id;
                    if (toStatus === fromStatus) return;
                    try {
                        await apiRequest(`/api/v1/leads/${leadId}/`, {
                            method: "PATCH",
                            body: {status: toStatus},
                        });
                        globalMessage("وضعیت سرنخ به‌روزرسانی شد.", true);
                        updateBoardCount(fromStatus, -1);
                        updateBoardCount(toStatus, 1);
                        renderEmptyState(fromStatus);
                        renderEmptyState(toStatus);
                    } catch (error) {
                        // dragula has already moved the node into `target`
                        // by the time this fires; a rejected PATCH must move
                        // it back, the same revert `setupLeadCalendar`'s own
                        // `eventDrop` performs with `info.revert()` above —
                        // jKanban carries no equivalent, so this does the
                        // same thing by hand.
                        source.append(el);
                        renderEmptyState(fromStatus);
                        renderEmptyState(toStatus);
                        showError(error);
                    }
                },
            });

            STATUSES.forEach((status) => {
                // A fixed number of cards shows before a column scrolls
                // internally instead of stretching the whole board — see the
                // `.kanban-drag` max-height rule in dolphin.css. The class is
                // the theme's own overlay scrollbar (vendor `_scroll.scss`),
                // the same one the app sidebar itself scrolls with, not a
                // hand-rolled one — it stays invisible until hovered, so a
                // short column shows no scrollbar chrome at all.
                boardElement(status)?.classList.add("hover-scroll-overlay-y");
                renderLoadMore(status);
                renderEmptyState(status);
                setupBoardColumnSearch(container, status, (term) => reloadColumn(status, term));
            });
        } catch (error) {
            loading.hidden = true;
            errorNode.textContent = errorText(error);
            errorNode.hidden = false;
        }
    }

    /**
     * The same orders `setupOrders`' table shows, grouped into status
     * columns instead — the order-side sibling of `setupLeadBoard` above,
     * built on the same `jKanban` library. Two real differences from the
     * lead board, both driven by `billing.models.Order` actually having a
     * `TRANSITIONS` table where `sales.Lead` has none:
     *
     * - Dropping a card POSTs `/api/v1/orders/<id>/transition/` with
     *   `{to_status}` — `OrderViewSet.transition` ->
     *   `billing.services.transition_order` — the same endpoint and body
     *   `setupOrderDetail`'s own status `<select>` already uses, not a bare
     *   PATCH like the lead board's status field. That function is what
     *   reserves or releases stock and what can silently redirect a
     *   `confirmed` drop to `cancelled` on a stock shortage; this handler
     *   only has to show whatever status the response actually reports.
     * - Each column declares jKanban's own `dragTo` option from
     *   `ORDER_TRANSITIONS`, so an invalid drop (e.g. `fulfilled` back to
     *   `draft`) is refused by jKanban itself — a greyed-out target and an
     *   auto-reverted drop — before any request is sent. This is display
     *   convenience only: `ORDER_TRANSITIONS` drifting out of sync with the
     *   server's own table could only ever narrow the board's menu, never
     *   widen access, because `transition_order` re-validates independently.
     */
    async function setupOrderBoard() {
        const container = document.getElementById("order-board");
        if (!container || typeof jKanban === "undefined") return;
        const loading = document.getElementById("order-board-loading");
        const errorNode = document.getElementById("order-board-error");
        const canManage = container.dataset.canManageOrders === "true";

        // draft/confirmed/fulfilled/cancelled, the exact order
        // billing.models.Order.Status and ORDER_TRANSITIONS both use.
        const STATUSES = Object.keys(ORDER_TRANSITIONS);
        const pageState = {};

        function boardTitle(status, count) {
            const wrap = document.createElement("div");
            wrap.className = "d-flex align-items-center gap-2";
            const text = document.createElement("span");
            text.textContent = labelled(DOCUMENT_STATUS_TEXT, status);
            const badge = document.createElement("span");
            badge.className = "badge badge-light-secondary";
            badge.textContent = toPersianDigits(String(count));
            wrap.append(text, badge);
            return wrap.innerHTML;
        }

        /**
         * Every piece of text below goes through `textContent`; `innerHTML`
         * is read once, at the end, only because jKanban's own API takes an
         * item's content as an HTML string — the same escape-then-serialise
         * pattern `setupLeadBoard`'s own `cardContent` uses for the same
         * reason.
         */
        function cardContent(order) {
            const wrap = document.createElement("div");

            const title = document.createElement("div");
            title.className = "fw-bold fs-6 mb-2 text-gray-900";
            title.textContent = order.customer_name || `سفارش ${order.number || ""}`.trim();
            wrap.append(title);

            const number = document.createElement("div");
            number.className = "fs-8 text-gray-600 mb-1";
            number.dir = "ltr";
            number.textContent = order.number || "—";
            wrap.append(number);

            const amount = document.createElement("div");
            amount.className = "fs-8 text-gray-700 fw-semibold mb-1";
            amount.textContent = money(order.total_amount);
            wrap.append(amount);

            if (order.expected_delivery_at) {
                const row = document.createElement("div");
                row.className = "fs-8 text-gray-600 mb-1";
                row.textContent = `تحویل: ${displayDay(order.expected_delivery_at)}`;
                wrap.append(row);
            }

            const creator = order.created_by_display || order.created_by;
            if (creator) {
                const row = document.createElement("div");
                row.className = "fs-8 text-gray-600 mb-1";
                row.textContent = `ثبت‌شده توسط: ${creator}`;
                wrap.append(row);
            }

            const link = document.createElement("a");
            link.className = "fs-8 fw-semibold mt-1 d-inline-block";
            link.href = `/orders/${order.id}/`;
            link.textContent = "مشاهدهٔ جزئیات";
            wrap.append(link);

            return wrap.innerHTML;
        }

        function toItem(order) {
            return {id: String(order.id), title: cardContent(order)};
        }

        function boardElement(status) {
            return container.querySelector(`.kanban-board[data-id="${status}"] .kanban-drag`);
        }

        const counts = {};

        function updateBoardCount(status, delta) {
            counts[status] += delta;
            const badge = container.querySelector(
                `.kanban-board[data-id="${status}"] .kanban-title-board .badge`,
            );
            if (badge) badge.textContent = toPersianDigits(String(counts[status]));
        }

        function renderLoadMore(status) {
            const drag = boardElement(status);
            if (!drag) return;
            drag.querySelector(".lead-board-load-more")?.remove();
            const state = pageState[status];
            if (!state?.next) return;
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-sm btn-light-primary w-100 not-draggable lead-board-load-more";
            button.textContent = "بارگذاری بیشتر";
            button.addEventListener("click", () => loadMore(status));
            drag.append(button);
        }

        function renderEmptyState(status) {
            const drag = boardElement(status);
            if (!drag || drag.querySelector(".kanban-item")) return;
            const empty = document.createElement("div");
            empty.className = "not-draggable lead-board-empty text-center fs-8 py-6";
            empty.textContent = pageState[status]?.search
                ? "سفارشی با این جست‌وجو در این ستون نیست."
                : "سفارشی در این وضعیت نیست.";
            drag.append(empty);
        }

        function columnUrl(status, page) {
            const term = pageState[status]?.search;
            const search = term ? `&search=${encodeURIComponent(term)}` : "";
            return `/api/v1/orders/?status=${status}&ordering=-created_at&page=${page}${search}`;
        }

        /** The order-side twin of `setupLeadBoard`'s own `reloadColumn` — see
         *  that one for why the column is rebuilt rather than filtered. */
        async function reloadColumn(status, term) {
            const drag = boardElement(status);
            if (!drag) return;
            pageState[status] = {...pageState[status], search: term};
            try {
                const data = await apiRequest(columnUrl(status, 1));
                drag.innerHTML = "";
                data.results.forEach((order) => kanban.addElement(status, toItem(order)));
                pageState[status] = {next: data.next, search: term};
                counts[status] = data.count;
                const badge = container.querySelector(
                    `.kanban-board[data-id="${status}"] .kanban-title-board .badge`,
                );
                if (badge) badge.textContent = toPersianDigits(String(data.count));
                renderLoadMore(status);
                renderEmptyState(status);
            } catch (error) {
                showError(error);
            }
        }

        async function loadMore(status) {
            const state = pageState[status];
            if (!state?.next) return;
            try {
                const data = await apiRequest(state.next);
                data.results.forEach((order) => kanban.addElement(status, toItem(order)));
                state.next = data.next;
                renderLoadMore(status);
            } catch (error) {
                showError(error);
            }
        }

        let kanban;

        loading.hidden = false;
        errorNode.hidden = true;
        container.hidden = true;
        try {
            const pages = await Promise.all(
                STATUSES.map((status) =>
                    apiRequest(`/api/v1/orders/?status=${status}&ordering=-created_at&page=1`),
                ),
            );
            loading.hidden = true;
            container.hidden = false;

            const boards = STATUSES.map((status, index) => {
                const data = pages[index];
                pageState[status] = {next: data.next};
                counts[status] = data.count;
                return {
                    id: status,
                    title: boardTitle(status, data.count),
                    item: data.results.map(toItem),
                    // Restricts valid drop targets to ORDER_TRANSITIONS[status]
                    // via jKanban's own dragTo option (see the function
                    // docstring above) — a terminal status (fulfilled,
                    // cancelled) gets an empty array, so every other column
                    // refuses a drop from it.
                    dragTo: ORDER_TRANSITIONS[status],
                };
            });

            kanban = new jKanban({
                element: "#order-board",
                // Narrower than the lead board's own 300px: this board always
                // carries four columns (the lead board carries three), and at
                // 300px four of them plus three 0.75rem gutters (1236px) no
                // longer sit comfortably side by side once the sidebar and
                // this card's own padding are subtracted from a typical
                // laptop viewport — the fourth column fell to the next line.
                // Measured directly against this card's own available width
                // at 1440px (≈1040px, the sidebar and card padding already
                // taken out) and against jKanban's own rendered board width —
                // its per-board margin from `gutter` is not the plain value
                // passed in (`jkanban.bundle.js` splits it unevenly between
                // a board's two inline sides rather than applying it once
                // per gap), so the fit was checked against the real
                // `getBoundingClientRect()` of a rendered board, not the
                // arithmetic the option name suggests. 225px keeps four
                // boards plus their real margins inside that width with room
                // held in reserve, and an order card's own content (customer
                // name, status badge, total) still reads on one line at it.
                gutter: "0.5rem",
                widthBoard: "225px",
                dragBoards: false,
                dragItems: canManage,
                boards,
                click: (el) => {
                    window.location.href = `/orders/${el.dataset.eid}/`;
                },
                dropEl: async (el, target, source) => {
                    const orderId = el.dataset.eid;
                    const toStatus = target.parentNode.dataset.id;
                    const fromStatus = source.parentNode.dataset.id;
                    if (toStatus === fromStatus) return;
                    try {
                        const updated = await apiRequest(`/api/v1/orders/${orderId}/transition/`, {
                            method: "POST",
                            body: {to_status: toStatus},
                        });
                        // transition_order can silently redirect a shortage-hit
                        // confirm to cancelled instead — the same case
                        // setupOrderDetail's own status select reports; the
                        // board reflects whatever status actually came back
                        // rather than assuming the drop landed where dropped.
                        const landedStatus = updated.status;
                        if (landedStatus !== toStatus) {
                            el.remove();
                            kanban.addElement(landedStatus, toItem(updated));
                            globalMessage("موجودی کافی نبود؛ سفارش لغو شد.");
                        } else {
                            globalMessage("وضعیت سفارش به‌روزرسانی شد.", true);
                        }
                        updateBoardCount(fromStatus, -1);
                        updateBoardCount(landedStatus, 1);
                        renderEmptyState(fromStatus);
                        renderEmptyState(landedStatus);
                    } catch (error) {
                        source.append(el);
                        renderEmptyState(fromStatus);
                        renderEmptyState(toStatus);
                        showError(error);
                    }
                },
            });

            STATUSES.forEach((status) => {
                // Same fixed-height, hover-revealed scrollbar as the lead
                // board above — see that block's own comment.
                boardElement(status)?.classList.add("hover-scroll-overlay-y");
                renderLoadMore(status);
                renderEmptyState(status);
                setupBoardColumnSearch(container, status, (term) => reloadColumn(status, term));
            });
        } catch (error) {
            loading.hidden = true;
            errorNode.textContent = errorText(error);
            errorNode.hidden = false;
        }
    }

    /**
     * The after-sales side of the follow-up calendar
     * (DOLPHIN_FEATURE_MAP_AND_ROADMAP.md §7 phase E) — the same FullCalendar
     * setup as `setupLeadCalendar` above, adapted for two real differences:
     *
     * - after-sales `status` is free text an elevated role or the assigned
     *   technician types (`transition_after_sales_status`), not a fixed
     *   three-value enum like Lead's — so colour here comes from open/closed
     *   (`closed_at`), the one status fact every deployment shares, not from
     *   the status string itself.
     * - dragging an event PATCHes a plain field on `setupLeadCalendar`
     *   because `next_follow_up_at` is a directly writable Lead field; here
     *   it POSTs to `schedule-appointment` instead, because scheduling an
     *   after-sales appointment carries its own rules (elevated role or the
     *   assigned technician only, refused on a closed case) that a bare
     *   PATCH would bypass — `next_appointment_at` is deliberately read-only
     *   on `AfterSalesRequestSerializer` for exactly that reason.
     */
    async function setupAfterSalesCalendar() {
        const container = document.getElementById("after-sales-calendar");
        if (!container || typeof FullCalendar === "undefined") return;
        const loading = document.getElementById("after-sales-calendar-loading");
        const errorNode = document.getElementById("after-sales-calendar-error");

        function jalaliDayLabel(date) {
            const [, , day] = gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
            return toPersianDigits(String(day));
        }

        function jalaliTitle(date, exact) {
            const [year, month, day] = gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
            const monthYear = `${JALALI_MONTH_NAMES[month - 1]} ${toPersianDigits(String(year))}`;
            return exact ? `${toPersianDigits(String(day))} ${monthYear}` : monthYear;
        }

        const palette = chartPalette();
        const OPEN_COLOR = palette[0];
        const CLOSED_COLOR = palette[1];

        function buildEventPopoverContent(item, overdue, when) {
            const wrap = document.createElement("div");

            const nameLine = document.createElement("div");
            nameLine.className = "fw-bold fs-6 mb-1";
            nameLine.textContent = item.subject || item.customer_name || "پروندهٔ بدون موضوع";
            wrap.append(nameLine);

            const badgeRow = document.createElement("div");
            badgeRow.className = "d-flex flex-wrap gap-2 mb-2";
            const statusBadge = document.createElement("span");
            statusBadge.className = `badge ${item.closed_at ? "badge-light-success" : "badge-light-primary"}`;
            statusBadge.textContent = item.status || (item.closed_at ? "بسته" : "باز");
            badgeRow.append(statusBadge);
            if (overdue) {
                const overdueBadge = document.createElement("span");
                overdueBadge.className = "badge badge-light-danger";
                overdueBadge.textContent = "دیرکرد";
                badgeRow.append(overdueBadge);
            }
            wrap.append(badgeRow);

            [
                ["مشتری", item.customer_name],
                ["کارشناس", item.assigned_to_display],
                ["زمان قرار", when],
            ].forEach(([label, value]) => {
                if (!value) return;
                const row = document.createElement("div");
                row.className = "fs-8 text-gray-600 mb-1";
                const strong = document.createElement("span");
                strong.className = "text-gray-800 fw-semibold";
                strong.textContent = `${label}: `;
                row.append(strong, document.createTextNode(value));
                wrap.append(row);
            });

            if (item.description) {
                const description = document.createElement("div");
                description.className = "fs-8 text-gray-600 mt-2 pt-2 border-top border-gray-300";
                description.textContent = item.description.length > 100 ? `${item.description.slice(0, 100)}…` : item.description;
                wrap.append(description);
            }
            return wrap;
        }

        const calendar = new FullCalendar.Calendar(container, {
            direction: "rtl",
            height: "auto",
            firstDay: 6,
            // See the lead calendar's own copy of this option for the full
            // reasoning — same fix, same symptom, same cause.
            showNonCurrentDates: false,
            headerToolbar: {start: "prev,next today", center: "title", end: "dayGridMonth,timeGridWeek,timeGridDay"},
            buttonText: {today: "امروز", month: "ماه", week: "هفته", day: "روز"},
            dayHeaderContent: (arg) => {
                const weekday = PERSIAN_WEEKDAY_NAMES[arg.date.getDay()];
                if (arg.view.type === "dayGridMonth") return weekday;
                const wrap = document.createElement("div");
                const nameLine = document.createElement("div");
                nameLine.textContent = weekday;
                const dayLine = document.createElement("div");
                dayLine.className = "fs-4 fw-bold";
                dayLine.textContent = jalaliDayLabel(arg.date);
                wrap.append(nameLine, dayLine);
                return {domNodes: [wrap]};
            },
            dayCellContent: (arg) => jalaliDayLabel(arg.date),
            datesSet: (info) => {
                if (info.view.type === "timeGridDay") {
                    const titleEl = container.querySelector(".fc-toolbar-title");
                    if (titleEl) titleEl.textContent = jalaliTitle(info.view.currentStart, true);
                    return;
                }
                const middle = new Date((info.view.currentStart.getTime() + info.view.currentEnd.getTime()) / 2);
                const titleEl = container.querySelector(".fc-toolbar-title");
                if (titleEl) titleEl.textContent = jalaliTitle(middle, false);
            },
            editable: true,
            eventStartEditable: true,
            eventDurationEditable: false,
            dayMaxEvents: true,
            eventDisplay: "block",
            eventTimeFormat: CALENDAR_TIME_FORMAT,
            slotLabelFormat: CALENDAR_TIME_FORMAT,
            slotLabelContent: persianSlotLabel,
            allDayText: "تمام‌روز",
            moreLinkText: (count) => `+${toPersianDigits(String(count))} مورد دیگر`,
            events: async (fetchInfo, successCallback, failureCallback) => {
                try {
                    const query = new URLSearchParams({
                        appointment_from: fetchInfo.startStr,
                        appointment_to: fetchInfo.endStr,
                    });
                    const items = await loadAllPages(`/api/v1/after-sales/?${query}`);
                    loading.hidden = true;
                    errorNode.hidden = true;
                    container.hidden = false;
                    const now = new Date();
                    successCallback(items.map((item) => {
                        const parts = tehranParts(item.next_appointment_at);
                        const allDay = Boolean(parts && parts.hour === 0 && parts.minute === 0);
                        // Only a still-open case can be "late" — a closed one
                        // has nothing left to act on, so a past appointment on
                        // one is expected, not a warning.
                        const overdue = !item.closed_at && new Date(item.next_appointment_at) < now;
                        return {
                            id: String(item.id),
                            title: item.customer_name
                                ? `${item.customer_name}${item.assigned_to_display ? " — " + item.assigned_to_display : ""}`
                                : item.subject,
                            start: item.next_appointment_at,
                            allDay,
                            backgroundColor: item.closed_at ? CLOSED_COLOR : OPEN_COLOR,
                            borderColor: item.closed_at ? CLOSED_COLOR : OPEN_COLOR,
                            classNames: overdue ? ["fc-event-overdue"] : [],
                            extendedProps: {item, overdue},
                        };
                    }));
                } catch (error) {
                    loading.hidden = true;
                    errorNode.textContent = errorText(error);
                    errorNode.hidden = false;
                    failureCallback(error);
                }
            },
            eventClick: (info) => {
                window.location.href = `/after-sales/${info.event.id}/`;
            },
            eventDrop: async (info) => {
                try {
                    await apiRequest(`/api/v1/after-sales/${info.event.id}/schedule-appointment/`, {
                        method: "POST",
                        body: {appointment_at: info.event.start.toISOString()},
                    });
                    globalMessage("زمان قرار به‌روزرسانی شد.", true);
                } catch (error) {
                    info.revert();
                    showError(error);
                }
            },
            eventDidMount: (info) => {
                persianiseEventTime(info);
                const {item, overdue} = info.event.extendedProps;
                if (!item) return;
                const when = info.event.allDay
                    ? displayDay(info.event.startStr)
                    : displayDate(info.event.startStr);
                const content = buildEventPopoverContent(item, overdue, when);
                // eslint-disable-next-line -- see buildEventPopoverContent's own
                // comment on setupLeadCalendar: every value here was already
                // escaped by textContent before this line ever runs.
                new bootstrap.Popover(info.el, {
                    trigger: "hover focus",
                    placement: "top",
                    html: true,
                    customClass: "lead-calendar-popover",
                    content: content.innerHTML,
                });
            },
            eventWillUnmount: (info) => {
                bootstrap.Popover.getInstance(info.el)?.dispose();
            },
        });
        calendar.render();
    }

    async function setupLeadDetail() {
        const leadId = document.body.dataset.leadId;
        const endpoint = `/api/v1/leads/${leadId}/`;
        const loading = document.getElementById("lead-detail-loading");
        const content = document.getElementById("lead-detail-content");
        const editForm = document.getElementById("edit-lead-form");
        let lead;
        let historyPage = 1;
        let targetAudiencePage = 1;

        function fillLead(value) {
            // Customer, server status, creator and interested product are no
            // longer on this form: a campaign is worked from its target
            // audience rather than from a single customer.
            document.getElementById("lead-assigned-to").value = value.assigned_to_display || value.assigned_to || "تخصیص نیافته";
            document.getElementById("edit-lead-status").value = value.status || "pending";
            document.getElementById("edit-lead-source").value = value.source || "";
            document.getElementById("edit-lead-campaign").value = value.campaign_or_batch || "";
            // Follow-up is a date; the time of day was never used for anything.
            document.getElementById("edit-lead-follow-up").value = localDateValue(value.next_follow_up_at);
            document.getElementById("edit-lead-notes").value = value.notes || "";
        }

        /**
         * The campaign's target audience.
         *
         * Read-only for a marketer: the add button is absent for them and the
         * API refuses the write regardless, so this rendering never decides
         * anything on its own.
         */
        async function loadTargetAudience(page = 1) {
            const wrap = document.getElementById("target-audience-table-wrap");
            const body = document.getElementById("target-audience-table-body");
            const audienceLoading = document.getElementById("target-audience-loading");
            const empty = document.getElementById("target-audience-empty");
            const pager = document.getElementById("target-audience-pagination");
            if (!wrap || !body) return;
            audienceLoading.hidden = false; empty.hidden = true; wrap.hidden = true; pager.hidden = true;
            try {
                const data = await apiRequest(`/api/v1/target-audience/?lead=${leadId}&page=${page}`);
                body.replaceChildren(...data.results.map((item) => {
                    const row = document.createElement("tr");
                    appendCell(row, item.full_name);
                    appendCell(row, item.raw_phone).dir = "ltr";
                    const statusCell = document.createElement("td");
                    const badge = document.createElement("span");
                    badge.className = `badge ${TARGET_STATUS_BADGES[item.status] || "badge-light"}`;
                    badge.textContent = item.status_display || item.status;
                    statusCell.append(badge);
                    row.append(statusCell);
                    return row;
                }));
                audienceLoading.hidden = true;
                empty.hidden = data.results.length > 0;
                wrap.hidden = data.results.length === 0;
                targetAudiencePage = page;
                document.getElementById("target-audience-prev").disabled = !data.previous;
                document.getElementById("target-audience-next").disabled = !data.next;
                document.getElementById("target-audience-page-label").textContent =
                    pageRangeLabel(data, page);
                pager.hidden = !data.previous && !data.next;
            } catch (error) {
                audienceLoading.hidden = true;
                showError(error);
            }
        }

        async function loadHistory(page = 1) {
            const historyLoading = document.getElementById("history-loading");
            const historyEmpty = document.getElementById("history-empty");
            const historyWrap = document.getElementById("history-table-wrap");
            const historyPager = document.getElementById("history-pagination");
            historyLoading.hidden = false; historyEmpty.hidden = true; historyWrap.hidden = true; historyPager.hidden = true;
            try {
                const data = await apiRequest(`${endpoint}assignment-history/?page=${page}`);
                const rows = data.results.map((item) => {
                    const row = document.createElement("tr");
                    appendCell(row, item.from_user_display || "بدون مسئول"); appendCell(row, item.to_user_display); appendCell(row, item.changed_by_display); appendCell(row, item.reason); appendCell(row, displayDate(item.changed_at));
                    return row;
                });
                document.getElementById("history-table-body").replaceChildren(...rows);
                historyLoading.hidden = true;
                if (!rows.length) { historyEmpty.hidden = false; return; }
                historyWrap.hidden = false; historyPage = page;
                document.getElementById("history-prev").disabled = !data.previous;
                document.getElementById("history-next").disabled = !data.next;
                document.getElementById("history-page-label").textContent = pageRangeLabel(data, page);
                historyPager.hidden = !data.previous && !data.next;
            } catch (error) { historyLoading.hidden = true; showError(error); }
        }

        try {
            lead = await apiRequest(endpoint);
            // The interested-product select is gone from this form, so the
            // product catalogue is no longer fetched for it either.
            fillLead(lead);
            await loadHistory();
            const reassignForm = document.getElementById("reassign-lead-form");
            if (reassignForm) {
                const assignees = await loadAllPages("/api/v1/leads/assignees/");
                fillSelect(document.getElementById("reassign-to-user"), assignees, (item) => [item.first_name, item.last_name].filter(Boolean).join(" ") || item.username, "انتخاب بازاریاب (کال سنتر)");
            }
            loading.hidden = true; content.hidden = false;
        } catch (error) { loading.hidden = true; showError(error); return; }

        editForm.addEventListener("submit", (event) => {
            event.preventDefault();
            if (!editForm.querySelector("button[type='submit']")) return;
            withSubmit(editForm, async () => {
                const data = new FormData(editForm);
                const payload = formPayload(editForm, ["source", "campaign_or_batch", "status", "notes"]);
                payload.next_follow_up_at = apiDateTime(data.get("next_follow_up_at"));
                lead = await apiRequest(endpoint, {method: "PATCH", body: payload});
                fillLead(lead); globalMessage("سرنخ ذخیره شد.", true);
            });
        });
        const reassignForm = document.getElementById("reassign-lead-form");
        reassignForm?.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(reassignForm, async () => {
                const data = new FormData(reassignForm);
                lead = await apiRequest(reassignForm.action, {method: "POST", body: {to_user: Number(data.get("to_user")), reason: String(data.get("reason") || "")}});
                fillLead(lead); await loadHistory(1); globalMessage("تخصیص ثبت شد.", true);
            });
        });
        document.getElementById("history-prev").addEventListener("click", () => loadHistory(historyPage - 1));
        document.getElementById("history-next").addEventListener("click", () => loadHistory(historyPage + 1));

        document.getElementById("target-audience-prev")?.addEventListener(
            "click", () => loadTargetAudience(targetAudiencePage - 1)
        );
        document.getElementById("target-audience-next")?.addEventListener(
            "click", () => loadTargetAudience(targetAudiencePage + 1)
        );

        // Adding to the audience exists only for a role that may write, but the
        // API is what actually refuses a marketer.
        const addDialog = document.getElementById("add-target-member-dialog");
        const addForm = document.getElementById("add-target-member-form");
        const openAdd = document.getElementById("open-add-target-member");
        if (addDialog && addForm && openAdd) {
            openAdd.addEventListener("click", () => addDialog.showModal());
            addDialog.querySelectorAll("[data-close-dialog]").forEach(
                (button) => button.addEventListener("click", () => addDialog.close())
            );
            addForm.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(addForm, async () => {
                    // No status: the server derives it, so sending one would be refused.
                    const payload = formPayload(addForm, ["full_name", "raw_phone"]);
                    payload.lead = Number(leadId);
                    await apiRequest(addForm.action, {method: "POST", body: payload});
                    addForm.reset();
                    addDialog.close();
                    await loadTargetAudience(1);
                    globalMessage("به جامعه هدف افزوده شد.", true);
                });
            });
        }

        /**
         * Upload a filled target-audience export back as new identities.
         *
         * Same round trip as `setupProductImport`: the marketer exports first,
         * writes rows on that file, and returns it — the server matches columns
         * by name and decides what is a duplicate, what is invalid and what was
         * added. This only reports what it says and refreshes the table.
         */
        const importOpen = document.getElementById("open-import-target-audience");
        const importPicker = document.getElementById("import-target-audience-file");
        if (importOpen && importPicker) {
            importOpen.addEventListener("click", () => importPicker.click());
            importPicker.addEventListener("change", async () => {
                const file = importPicker.files && importPicker.files[0];
                if (!file) return;
                const body = new FormData();
                body.append("file", file);
                body.append("lead", leadId);
                importOpen.disabled = true;
                clearMessages();
                try {
                    const result = await apiRequest("/api/v1/target-audience/import-xlsx/", {
                        method: "POST", body, raw: true,
                    });
                    const parts = [`${toPersianDigits(String(result.created))} مورد به جامعه هدف افزوده شد.`];
                    if (result.duplicates) {
                        parts.push(`${toPersianDigits(String(result.duplicates))} مورد تکراری بود و اضافه نشد.`);
                    }
                    if (result.invalid) {
                        parts.push(`${toPersianDigits(String(result.invalid))} ردیف نامعتبر بود و رد شد.`);
                    }
                    globalMessage(parts.join(" "), result.created > 0);
                    await loadTargetAudience(1);
                } catch (error) {
                    showError(error);
                } finally {
                    importOpen.disabled = false;
                    importPicker.value = "";
                }
            });
        }

        await loadTargetAudience(1);
    }

    /** Theme badge per target-audience status, warm for progress, muted for a dead end. */
    const TARGET_STATUS_BADGES = {
        lead: "badge-light-primary",
        engaged: "badge-light-warning",
        customer: "badge-light-success",
        failed: "badge-light-danger",
    };

    function interactionRow(interaction) {
        const row = document.createElement("tr");
        appendCell(row, interaction.customer_name || interaction.customer);
        appendCell(row, interaction.phone);
        appendCell(row, directionText(interaction.direction));
        appendCell(row, interaction.outcome);
        appendCell(row, displayDate(interaction.occurred_at));
        appendCell(row, displayDate(interaction.next_follow_up_at));
        appendDetailLink(row, `/interactions/${interaction.id}/`);
        return row;
    }

    async function setupInteractions() {
        const form = document.getElementById("interaction-search-form");
        setupListFilter("interaction");
        const controller = setupPagedList({
            key: "interactions", form,
            search: document.getElementById("interaction-search"),
            endpoint(page) {
                const query = new URLSearchParams({page: String(page), ordering: document.getElementById("interaction-ordering").value});
                const search = document.getElementById("interaction-search").value.trim();
                if (search) query.set("search", search);
                return `/api/v1/interactions/?${query}`;
            }, renderRow: interactionRow,
        });
        const dialog = document.getElementById("create-interaction-dialog");
        const createForm = document.getElementById("create-interaction-form");
        let memberOptions = [];
        function renderInteractionReview() {
            renderWizardReview(document.getElementById("create-interaction-review"), [
                ["مشتری", document.getElementById("create-interaction-member").value || "—"],
                ["شماره تماس", document.getElementById("create-interaction-phone").value],
                ["جهت", selectedOptionText(document.getElementById("create-interaction-direction"))],
                ["نتیجه ثبت‌شده", document.getElementById("create-interaction-outcome").value],
                ["زمان تماس", document.getElementById("create-interaction-occurred").value],
                ["پیگیری بعدی", document.getElementById("create-interaction-follow-up").value || "—"],
                ["یادداشت", document.getElementById("create-interaction-notes").value || "—"],
            ]);
        }
        const interactionWizard = setupWizard(dialog, {onReachLastStep: renderInteractionReview});
        document.getElementById("open-create-interaction").addEventListener("click", () => {
            createForm.reset();
            clearMessages(createForm);
            document.getElementById("create-interaction-occurred").value = localDateTimeValue(new Date().toISOString());
            interactionWizard?.goFirst();
            dialog.showModal();
        });
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        try {
            await controller.load();
            // The identities this caller may call. The endpoint is already
            // scoped to their own campaigns, so a marketer searches only the
            // people on campaigns assigned to them — no client-side filtering
            // decides that.
            memberOptions = await loadAllPages("/api/v1/target-audience/?ordering=full_name");
            const list = document.getElementById("target-member-options");
            list.replaceChildren(...memberOptions.map((item) => {
                const option = document.createElement("option");
                // The label is what the user types against and what is matched
                // back to an id on submit.
                option.value = `${item.full_name} — ${item.raw_phone}`;
                return option;
            }));
        } catch (error) { showError(error); }

        /** The identity whose label the user typed, or null. */
        function chosenMember(typed) {
            const text = String(typed || "").trim();
            if (!text) return null;
            return memberOptions.find(
                (item) => `${item.full_name} — ${item.raw_phone}` === text
            ) || memberOptions.find((item) => item.full_name === text) || null;
        }

        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const data = new FormData(createForm);
                const member = chosenMember(data.get("target_member"));
                if (member === null) {
                    const slot = createForm.querySelector('[data-error-for="target_member"]');
                    if (slot) slot.textContent = "یکی از هویت‌های جامعه هدف را انتخاب کنید.";
                    return;
                }
                const payload = formPayload(createForm, ["phone", "direction", "outcome", "notes"]);
                // The campaign comes from the identity, so the two can never
                // disagree about which campaign the call belongs to.
                payload.lead = member.lead;
                payload.target_member = member.id;
                payload.occurred_at = apiDateTime(data.get("occurred_at"));
                if (data.get("next_follow_up_at")) payload.next_follow_up_at = apiDateTime(data.get("next_follow_up_at"));
                const interaction = await apiRequest(createForm.action, {method: "POST", body: payload});
                window.location.assign(`/interactions/${interaction.id}/`);
            });
        });
    }

    async function setupInteractionDetail() {
        const interactionId = document.body.dataset.interactionId;
        const loading = document.getElementById("interaction-detail-loading");
        const content = document.getElementById("interaction-detail-content");
        try {
            const interaction = await apiRequest(`/api/v1/interactions/${interactionId}/`);
            document.getElementById("interaction-lead").value = interaction.lead;
            document.getElementById("interaction-customer").value = interaction.customer_name || interaction.customer;
            document.getElementById("interaction-agent").value = interaction.agent_display || interaction.agent;
            document.getElementById("interaction-phone").value = interaction.phone;
            document.getElementById("interaction-direction").value = directionText(interaction.direction);
            document.getElementById("interaction-outcome").value = interaction.outcome;
            document.getElementById("interaction-occurred").value = displayDate(interaction.occurred_at);
            document.getElementById("interaction-follow-up").value = displayDate(interaction.next_follow_up_at);
            document.getElementById("interaction-notes").value = interaction.notes || "";
            loading.hidden = true; content.hidden = false;
        } catch (error) { loading.hidden = true; showError(error); }
    }

    function productCategoryRow(category) {
        const row = document.createElement("tr");
        appendCell(row, category.display_order);
        appendCell(row, category.code);
        appendCell(row, category.name);
        appendStatusCell(row, (category.is_active));
        appendDetailLink(row, `/product-categories/${category.id}/`);
        return row;
    }

    function setupProductCategories() {
        const form = document.getElementById("product-category-search-form");
        setupListFilter("product-category");
        const controller = setupPagedList({
            key: "product-categories",
            form,
            search: document.getElementById("product-category-search"),
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page)});
                const search = document.getElementById("product-category-search").value.trim();
                if (search) query.set("search", search);
                const isActive = document.getElementById("product-category-status-filter").value;
                if (isActive) query.set("is_active", isActive);
                query.set("ordering", document.getElementById("product-category-ordering").value);
                return `/api/v1/product-categories/?${query}`;
            },
            renderRow: productCategoryRow,
        });
        const dialog = document.getElementById("create-product-category-dialog");
        if (dialog) {
            const createForm = document.getElementById("create-product-category-form");
            function renderReview() {
                renderWizardReview(document.getElementById("create-product-category-review"), [
                    ["کد پایدار", document.getElementById("create-product-category-code").value],
                    ["نام", document.getElementById("create-product-category-name").value],
                    ["ترتیب نمایش", toPersianDigits(document.getElementById("create-product-category-order").value)],
                    ["شرح", document.getElementById("create-product-category-description").value || "—"],
                ]);
            }
            const wizard = setupWizard(dialog, {onReachLastStep: renderReview});
            document.getElementById("open-create-product-category").addEventListener("click", () => {
                createForm.reset();
                clearMessages(createForm);
                wizard?.goFirst();
                dialog.showModal();
            });
            dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
            createForm.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(createForm, async () => {
                    const payload = formPayload(createForm, ["code", "name", "description"]);
                    payload.display_order = Number(new FormData(createForm).get("display_order"));
                    const category = await apiRequest(createForm.action, {method: "POST", body: payload});
                    window.location.assign(`/product-categories/${category.id}/`);
                });
            });
        }
        controller.load();
    }

    function fillProductCategory(category) {
        document.getElementById("edit-product-category-code").value = category.code;
        document.getElementById("edit-product-category-name").value = category.name;
        document.getElementById("edit-product-category-order").value = category.display_order;
        document.getElementById("edit-product-category-description").value = category.description || "";
        document.getElementById("product-category-status").value = statusText(category.is_active);
        document.getElementById("product-category-created-by").value = category.created_by_display || category.created_by;
        document.getElementById("product-category-updated-by").value = category.updated_by_display || category.updated_by;
        const toggle = document.getElementById("toggle-product-category");
        if (toggle) {
            toggle.textContent = category.is_active ? "غیرفعال کردن دسته‌بندی" : "فعال کردن دوباره دسته‌بندی";
            toggle.classList.toggle("btn-danger", category.is_active);
        }
    }

    async function setupProductCategoryDetail() {
        const categoryId = document.body.dataset.categoryId;
        const endpoint = `/api/v1/product-categories/${categoryId}/`;
        const loading = document.getElementById("product-category-detail-loading");
        const content = document.getElementById("product-category-detail-content");
        let category;
        try {
            category = await apiRequest(endpoint);
            fillProductCategory(category);
            loading.hidden = true;
            content.hidden = false;
        } catch (error) {
            loading.hidden = true;
            showError(error);
            return;
        }
        const form = document.getElementById("edit-product-category-form");
        if (form.querySelector("button[type='submit']")) {
            form.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(form, async () => {
                    const payload = formPayload(form, ["name", "description"]);
                    payload.display_order = Number(new FormData(form).get("display_order"));
                    category = await apiRequest(endpoint, {method: "PATCH", body: payload});
                    fillProductCategory(category);
                    globalMessage("دسته‌بندی ذخیره شد.", true);
                });
            });
        }
        const toggle = document.getElementById("toggle-product-category");
        toggle?.addEventListener("click", async () => {
            const action = category.is_active ? "deactivate" : "reactivate";
            const prompt = category.is_active ? "این دسته‌بندی غیرفعال شود؟" : "این دسته‌بندی دوباره فعال شود؟";
            if (!window.confirm(prompt)) return;
            toggle.disabled = true;
            try {
                category = await apiRequest(`${endpoint}${action}/`, {method: "POST"});
                fillProductCategory(category);
                globalMessage(category.is_active ? "دسته‌بندی فعال شد." : "دسته‌بندی غیرفعال شد.", true);
            } catch (error) {
                showError(error);
            } finally {
                toggle.disabled = false;
            }
        });
    }

    function productRow(product) {
        const row = document.createElement("tr");
        appendCell(row, product.sku);
        appendCell(row, product.name);
        appendCell(row, product.category_name || "بدون دسته‌بندی");
        appendCell(row, product.brand || "—");
        appendCell(row, product.unit_display || "—");
        // The price went out raw here while every other table used `money()`,
        // so the products list was the one screen showing `12500000.00`.
        appendMoneyCell(row, product.current_price);
        appendStatusCell(row, (product.is_active));
        appendDetailLink(row, `/products/${product.id}/`);
        return row;
    }

    async function setupProducts() {
        const form = document.getElementById("product-search-form");
        setupListFilter("product");
        setupProductImport();
        // Wire the dialog before any awaited load: a click that lands while a
        // network load is still pending would otherwise be silently discarded,
        // leaving the create button inert for the first moments of the page.
        const dialog = document.getElementById("create-product-dialog");
        if (dialog) {
            const createForm = document.getElementById("create-product-form");
            function renderProductReview() {
                renderWizardReview(document.getElementById("create-product-review"), [
                    ["کد محصول", document.getElementById("create-product-sku").value],
                    ["نام", document.getElementById("create-product-name").value],
                    ["دسته‌بندی", selectedOptionText(document.getElementById("create-product-category"))],
                    ["برند", document.getElementById("create-product-brand").value || "—"],
                    ["واحد", selectedOptionText(document.getElementById("create-product-unit"))],
                    ["قیمت جاری (ریال)", document.getElementById("create-product-price").value || "—"],
                    ["شرح", document.getElementById("create-product-description").value || "—"],
                ]);
            }
            const productWizard = setupWizard(dialog, {onReachLastStep: renderProductReview});
            document.getElementById("open-create-product").addEventListener("click", () => {
                createForm.reset();
                clearMessages(createForm);
                productWizard?.goFirst();
                dialog.showModal();
            });
            dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
            createForm.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(createForm, async () => {
                    const payload = formPayload(createForm, ["sku", "name", "brand", "unit", "description"]);
                    // The field is grouped text for the operator; the API wants digits.
                    payload.current_price = moneyValue(new FormData(createForm).get("current_price"));
                    payload.category = new FormData(createForm).get("category") ? Number(new FormData(createForm).get("category")) : null;
                    const product = await apiRequest(createForm.action, {method: "POST", body: payload});
                    window.location.assign(`/products/${product.id}/`);
                });
            });
        }
        try {
            const categories = await loadAllPages("/api/v1/product-categories/?is_active=true&ordering=display_order");
            fillSelect(document.getElementById("product-category-filter"), categories, (category) => category.name, "همه دسته‌بندی‌ها");
            const createCategory = document.getElementById("create-product-category");
            if (createCategory) fillSelect(createCategory, categories, (category) => category.name, "بدون دسته‌بندی");
        } catch (error) {
            showError(error);
        }
        const controller = setupPagedList({
            key: "products",
            form,
            search: document.getElementById("product-search"),
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page)});
                const search = document.getElementById("product-search").value.trim();
                if (search) query.set("search", search);
                const isActive = document.getElementById("product-status-filter").value;
                if (isActive) query.set("is_active", isActive);
                const category = document.getElementById("product-category-filter").value;
                if (category) query.set("category", category);
                // Ordering is no longer a filter control; the list keeps the
                // model's own name ordering.
                return `/api/v1/products/?${query}`;
            },
            renderRow: productRow,
        });
        controller.load();
    }

    function fillProduct(product) {
        document.getElementById("edit-product-sku").value = product.sku;
        document.getElementById("edit-product-name").value = product.name;
        document.getElementById("edit-product-category").value = product.category || "";
        document.getElementById("edit-product-brand").value = product.brand || "";
        document.getElementById("edit-product-unit").value = product.unit || "";
        document.getElementById("edit-product-price").value = moneyDigits(product.current_price);
        document.getElementById("edit-product-description").value = product.description || "";
        document.getElementById("product-created-by").value = product.created_by_display || product.created_by;
        document.getElementById("product-updated-by").value = product.updated_by_display || product.updated_by;
        // A Platform Admin gets a select; everyone else the read-only text.
        const activeSelect = document.getElementById("product-active-select");
        if (activeSelect) {
            activeSelect.value = String(Boolean(product.is_active));
        } else {
            document.getElementById("product-status").value = statusText(product.is_active);
        }
    }

    /**
     * Upload a filled export back as new products.
     *
     * The user exports first, writes on that file, and returns it — so the
     * header row is ours and the server maps columns by name rather than by
     * position. Everything about which row is a duplicate, which is invalid and
     * which was created is decided on the server; this only reports what it
     * says.
     */
    function setupProductImport() {
        const open = document.getElementById("open-import-products");
        const picker = document.getElementById("import-products-file");
        if (!open || !picker) return;

        open.addEventListener("click", () => picker.click());
        picker.addEventListener("change", async () => {
            const file = picker.files && picker.files[0];
            if (!file) return;
            const body = new FormData();
            body.append("file", file);
            open.disabled = true;
            clearMessages();
            try {
                const result = await apiRequest("/api/v1/products/import-xlsx/", {
                    method: "POST", body, raw: true,
                });
                const parts = [`${toPersianDigits(String(result.created))} محصول ثبت شد.`];
                if (result.duplicates) {
                    parts.push(`${toPersianDigits(String(result.duplicates))} محصول تکراری بود و اضافه نشد.`);
                }
                if (result.invalid) {
                    parts.push(`${toPersianDigits(String(result.invalid))} ردیف نامعتبر بود و رد شد.`);
                }
                // A run with nothing created is not a success message.
                globalMessage(parts.join(" "), result.created > 0);
            } catch (error) {
                showError(error);
            } finally {
                open.disabled = false;
                picker.value = "";
            }
        });
    }

    async function setupProductDetail() {
        const productId = document.body.dataset.productId;
        const endpoint = `/api/v1/products/${productId}/`;
        const loading = document.getElementById("product-detail-loading");
        const content = document.getElementById("product-detail-content");
        let product;
        try {
            const [productValue, categories] = await Promise.all([
                apiRequest(endpoint),
                loadAllPages("/api/v1/product-categories/?is_active=true&ordering=display_order"),
            ]);
            product = productValue;
            if (product.category && !categories.some((category) => category.id === product.category)) {
                categories.push({id: product.category, name: `${product.category_name || "دسته‌بندی"} (غیرفعال)`});
            }
            fillSelect(document.getElementById("edit-product-category"), categories, (category) => category.name, "بدون دسته‌بندی");
            fillProduct(product);
            loading.hidden = true;
            content.hidden = false;
        } catch (error) {
            loading.hidden = true;
            showError(error);
            return;
        }
        const form = document.getElementById("edit-product-form");
        if (form.querySelector("button[type='submit']")) {
            form.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(form, async () => {
                    const payload = formPayload(form, ["sku", "name", "brand", "unit", "description"]);
                    payload.current_price = moneyValue(new FormData(form).get("current_price"));
                    payload.category = new FormData(form).get("category") ? Number(new FormData(form).get("category")) : null;
                    product = await apiRequest(endpoint, {method: "PATCH", body: payload});
                    fillProduct(product);
                    globalMessage("محصول ذخیره شد.", true);
                });
            });
        }
        // Reversible: an inactive product cannot go on a new document, but every
        // existing line keeps its snapshot, so turning it back on restores it.
        const activeSelect = document.getElementById("product-active-select");
        activeSelect?.addEventListener("change", async () => {
            const nextActive = activeSelect.value === "true";
            if (nextActive === Boolean(product.is_active)) return;
            const question = nextActive ? "این محصول دوباره فعال شود؟" : "این محصول غیرفعال شود؟";
            if (!window.confirm(question)) {
                activeSelect.value = String(Boolean(product.is_active));
                return;
            }
            activeSelect.disabled = true;
            clearMessages();
            try {
                product = await apiRequest(`${endpoint}set-active/`, {
                    method: "POST", body: {is_active: nextActive},
                });
                fillProduct(product);
                globalMessage(nextActive ? "محصول دوباره فعال شد." : "محصول غیرفعال شد.", true);
            } catch (error) {
                activeSelect.value = String(Boolean(product.is_active));
                showError(error);
            } finally {
                activeSelect.disabled = false;
            }
        });
    }

    function saleStatusText(value) {
        return value === "confirmed" ? "تأییدشده" : value === "cancelled" ? "لغوشده" : value;
    }

    function saleRow(sale) {
        const row = document.createElement("tr");
        // The campaign the result came from leads the row: these are campaign
        // outcomes, and the campaign is what the reader is scanning for.
        appendCell(row, sale.campaign_name || "—");
        appendCell(row, sale.product_name || sale.product);
        appendCell(row, sale.quantity);
        appendCell(row, sale.total_amount);
        appendCell(row, saleStatusText(sale.status));
        appendCell(row, sale.sold_by_display || sale.sold_by);
        appendDetailLink(row, `/sales/${sale.id}/`);
        return row;
    }

    async function setupSales() {
        const form = document.getElementById("sale-search-form");
        setupListFilter("sale");
        const controller = setupPagedList({
            key: "sales",
            form,
            search: document.getElementById("sale-search"),
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page), ordering: document.getElementById("sale-ordering").value});
                const search = document.getElementById("sale-search").value.trim();
                const status = document.getElementById("sale-status").value;
                if (search) query.set("search", search);
                if (status) query.set("status", status);
                return `/api/v1/sales/?${query}`;
            },
            renderRow: saleRow,
        });
        controller.load();
        const dialog = document.getElementById("create-sale-dialog");
        const createForm = document.getElementById("create-sale-form");
        function renderSaleReview() {
            renderWizardReview(document.getElementById("create-sale-review"), [
                ["سرنخ مجاز", selectedOptionText(document.getElementById("create-sale-lead"))],
                ["محصول فعال", selectedOptionText(document.getElementById("create-sale-product"))],
                ["تعداد", toPersianDigits(document.getElementById("create-sale-quantity").value)],
                ["یادداشت", document.getElementById("create-sale-notes").value || "—"],
            ]);
        }
        const saleWizard = setupWizard(dialog, {onReachLastStep: renderSaleReview});
        document.getElementById("open-create-sale").addEventListener("click", () => {
            createForm.reset();
            clearMessages(createForm);
            saleWizard?.goFirst();
            dialog.showModal();
        });
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        try {
            const me = await apiRequest("/api/v1/auth/me/");
            let leads = await loadAllPages("/api/v1/leads/?ordering=-created_at");
            const products = await loadAllPages("/api/v1/products/?ordering=name");
            if (me.role === "sales_agent") leads = leads.filter((lead) => Number(lead.assigned_to) === Number(me.id));
            const leadSelect = document.getElementById("create-sale-lead");
            fillSelect(leadSelect, leads, (lead) => `${lead.customer_name} — ${lead.source}`, "یک سرنخ انتخاب کنید");
            fillSelect(document.getElementById("create-sale-product"), products.filter((product) => product.is_active), (product) => `${product.name} — ${money(product.current_price)}`, "یک محصول انتخاب کنید");
            const requestedLead = new URLSearchParams(window.location.search).get("lead");
            if (requestedLead && leads.some((lead) => String(lead.id) === requestedLead)) {
                leadSelect.value = requestedLead;
                saleWizard?.goFirst();
                dialog.showModal();
            }
        } catch (error) {
            showError(error);
        }
        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const payload = formPayload(createForm, ["lead", "product", "quantity", "notes"]);
                const sale = await apiRequest(createForm.action, {method: "POST", body: payload});
                window.location.assign(`/sales/${sale.id}/`);
            });
        });
    }

    function fillSale(sale) {
        document.getElementById("sale-lead").value = sale.lead;
        document.getElementById("sale-customer").value = sale.customer_name || sale.customer;
        document.getElementById("sale-product").value = sale.product_name || sale.product || "—";
        document.getElementById("sale-seller").value = sale.sold_by_display || sale.sold_by;
        document.getElementById("sale-quantity").value = sale.quantity;
        // These are read-only boxes, so they get the same rial formatting as
        // every table cell rather than the raw two-decimal string.
        document.getElementById("sale-unit-price").value = money(sale.unit_price_snapshot);
        document.getElementById("sale-total").value = money(sale.total_amount);
        document.getElementById("sale-detail-status").value = saleStatusText(sale.status);
        document.getElementById("sale-time").value = displayDate(sale.sold_at);
        document.getElementById("sale-notes").value = sale.notes || "";
        const cancelSection = document.getElementById("sale-cancel-section");
        if (cancelSection) cancelSection.hidden = sale.status !== "confirmed";
    }

    async function setupSaleDetail() {
        const saleId = document.body.dataset.saleId;
        const endpoint = `/api/v1/sales/${saleId}/`;
        const loading = document.getElementById("sale-detail-loading");
        const content = document.getElementById("sale-detail-content");
        let sale;
        try {
            sale = await apiRequest(endpoint);
            fillSale(sale);
            loading.hidden = true;
            content.hidden = false;
        } catch (error) {
            loading.hidden = true;
            showError(error);
            return;
        }
        const form = document.getElementById("cancel-sale-form");
        form?.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                sale = await apiRequest(form.action, {method: "POST", body: formPayload(form, ["reason"])});
                fillSale(sale);
                globalMessage("فروش لغو شد.", true);
            });
        });
    }

    function salesDocumentRow(item) {
        const row = document.createElement("tr");
        appendCell(row, item.document_number);
        appendCell(row, item.customer_name || item.customer);
        appendCell(row, item.sale || "—");
        appendCell(row, [item.province_snapshot, item.city_snapshot].filter(Boolean).join(" / ") || "—");
        appendCell(row, item.postal_status);
        appendCell(row, item.is_active ? "فعال" : "غیرفعال");
        appendDetailLink(row, `/sales-documents/${item.id}/`);
        return row;
    }

    async function setupSalesDocuments() {
        const form = document.getElementById("sales-document-search-form");
        setupListFilter("sales-document");
        const controller = setupPagedList({
            key: "sales-documents",
            form,
            search: document.getElementById("sales-document-search"),
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page), ordering: document.getElementById("sales-document-ordering").value});
                const search = document.getElementById("sales-document-search").value.trim();
                if (search) query.set("search", search);
                [["postal_status", "sales-document-postal-status"], ["province", "sales-document-province"], ["city", "sales-document-city"], ["is_active", "sales-document-active"]].forEach(([name, id]) => {
                    const value = document.getElementById(id).value.trim();
                    if (value) query.set(name, value);
                });
                return `/api/v1/sales-documents/?${query}`;
            },
            renderRow: salesDocumentRow,
        });
        controller.load();
        const dialog = document.getElementById("create-sales-document-dialog");
        if (!dialog) return;
        const createForm = document.getElementById("create-sales-document-form");
        const customerSelect = document.getElementById("create-sales-document-customer");
        const saleSelect = document.getElementById("create-sales-document-sale");
        function renderSalesDocumentReview() {
            renderWizardReview(document.getElementById("create-sales-document-review"), [
                ["مشتری", selectedOptionText(customerSelect)],
                ["فروش مرتبط", selectedOptionText(saleSelect)],
                ["شماره داخلی سند", document.getElementById("create-sales-document-number").value],
                ["وضعیت پستی آغازین", document.getElementById("create-sales-document-status").value],
                ["یادداشت", document.getElementById("create-sales-document-notes").value || "—"],
            ]);
        }
        const salesDocumentWizard = setupWizard(dialog, {onReachLastStep: renderSalesDocumentReview});
        document.getElementById("open-create-sales-document").addEventListener("click", () => {
            createForm.reset();
            clearMessages(createForm);
            salesDocumentWizard?.goFirst();
            dialog.showModal();
        });
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        let sales = [];
        try {
            const [customers, loadedSales] = await Promise.all([
                loadAllPages("/api/v1/customers/?ordering=full_name"),
                loadAllPages("/api/v1/sales/?ordering=-sold_at"),
            ]);
            sales = loadedSales;
            fillSelect(customerSelect, customers, (customer) => customer.full_name, "یک مشتری انتخاب کنید");
        } catch (error) { showError(error); }
        function refreshSales() {
            const customerId = Number(customerSelect.value);
            fillSelect(saleSelect, sales.filter((sale) => Number(sale.customer) === customerId), (sale) => `فروش ${sale.id} — ${sale.product_name || sale.product}`, "بدون فروش مرتبط");
        }
        customerSelect.addEventListener("change", refreshSales);
        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const payload = formPayload(createForm, ["customer", "sale", "document_number", "postal_status", "notes"]);
                if (!payload.sale) delete payload.sale;
                const item = await apiRequest(createForm.action, {method: "POST", body: payload});
                window.location.assign(`/sales-documents/${item.id}/`);
            });
        });
    }

    function fillSalesDocument(item) {
        document.getElementById("sales-document-number").value = item.document_number;
        document.getElementById("sales-document-customer").value = item.customer_name || item.customer;
        document.getElementById("sales-document-sale").value = item.sale || "—";
        document.getElementById("sales-document-registered-by").value = item.registered_by_display || item.registered_by;
        document.getElementById("sales-document-province").value = item.province_snapshot || "—";
        document.getElementById("sales-document-city").value = item.city_snapshot || "—";
        document.getElementById("sales-document-postal-code").value = item.postal_code_snapshot || "—";
        document.getElementById("sales-document-address").value = item.address_snapshot || "—";
        document.getElementById("sales-document-status").value = item.postal_status;
        document.getElementById("sales-document-notes").value = item.notes || "";
        document.getElementById("sales-document-active-state").textContent = item.is_active ? "سند فعال است." : "سند غیرفعال است؛ تاریخچه حفظ شده است.";
        const section = document.getElementById("postal-transition-section");
        if (section) section.hidden = !item.is_active;
    }

    async function loadPostalHistory(id) {
        const loading = document.getElementById("postal-history-loading");
        const empty = document.getElementById("postal-history-empty");
        const wrap = document.getElementById("postal-history-table-wrap");
        const rows = await loadAllPages(`/api/v1/sales-documents/${id}/postal-history/`);
        const nodes = rows.map((item) => {
            const row = document.createElement("tr");
            [item.from_status || "آغاز", item.to_status, item.changed_by_display || item.changed_by, item.reason || "—", displayDate(item.changed_at)].forEach((value) => appendCell(row, value));
            return row;
        });
        document.getElementById("postal-history-table-body").replaceChildren(...nodes);
        loading.hidden = true; empty.hidden = Boolean(nodes.length); wrap.hidden = !nodes.length;
    }

    async function setupSalesDocumentDetail() {
        const id = document.body.dataset.salesDocumentId;
        const endpoint = `/api/v1/sales-documents/${id}/`;
        const loading = document.getElementById("sales-document-detail-loading");
        const content = document.getElementById("sales-document-detail-content");
        let item;
        try {
            [item] = await Promise.all([apiRequest(endpoint), loadPostalHistory(id)]);
            fillSalesDocument(item); loading.hidden = true; content.hidden = false;
        } catch (error) { loading.hidden = true; document.getElementById("postal-history-loading").hidden = true; showError(error); return; }
        const form = document.getElementById("postal-transition-form");
        form?.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                item = await apiRequest(form.action, {method: "POST", body: formPayload(form, ["to_status", "reason"])});
                fillSalesDocument(item); form.reset(); await loadPostalHistory(id); globalMessage("وضعیت پستی ثبت شد.", true);
            });
        });
        document.getElementById("deactivate-sales-document")?.addEventListener("click", async () => {
            if (!window.confirm("این سند غیرفعال شود؟ تاریخچه پاک نمی‌شود.")) return;
            try { item = await apiRequest(`${endpoint}deactivate/`, {method: "POST"}); fillSalesDocument(item); globalMessage("سند غیرفعال شد.", true); } catch (error) { showError(error); }
        });
    }

    function salesDocumentReportQuery(form) {
        const data = new FormData(form);
        const query = new URLSearchParams();
        query.set("period_start", apiDateTime(String(data.get("period_start") || "")) || "");
        query.set("period_end", apiDateTime(String(data.get("period_end") || "")) || "");
        ["province", "city", "postal_status", "is_active"].forEach((name) => { const value = String(data.get(name) || "").trim(); if (value) query.set(name, value); });
        return query;
    }

    /**
     * A live, client-side text filter over a report's own already-rendered
     * result table(s) — the search box every list page's own card-header
     * carries, adapted for a report page: there is no server round trip to
     * make, since the whole table is already on the page once the report is
     * built. Hiding a row rather than removing it keeps `report.total`,
     * column widths and re-search all correct without re-rendering.
     */
    function bindReportTableSearch(input, tbodies) {
        if (!input) return;
        input.addEventListener("input", () => {
            const query = input.value.trim().toLowerCase();
            tbodies.forEach((tbody) => {
                if (!tbody) return;
                Array.from(tbody.rows).forEach((row) => {
                    row.hidden = query !== "" && !row.textContent.toLowerCase().includes(query);
                });
            });
        });
    }

    async function setupSalesDocumentReport() {
        const form = document.getElementById("sales-document-report-form");
        bindReportTableSearch(document.getElementById("sales-document-report-search"), [
            document.getElementById("sales-document-geography-body"),
            document.getElementById("sales-document-status-body"),
        ]);
        const now = new Date();
        document.getElementById("document-report-start").value = localDateTimeValue(new Date(now.getFullYear(), now.getMonth(), 1));
        document.getElementById("document-report-end").value = localDateTimeValue(new Date(now.getTime() + 60000));
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const loading = document.getElementById("sales-document-report-loading");
                const empty = document.getElementById("sales-document-report-empty");
                const content = document.getElementById("sales-document-report-content");
                loading.hidden = false; empty.hidden = true; content.hidden = true;
                let report;
                try { report = await apiRequest(`/api/v1/reports/sales-documents/?${salesDocumentReportQuery(form)}`); } finally { loading.hidden = true; }
                document.getElementById("sales-document-report-total").textContent = report.total;
                document.getElementById("sales-document-geography-body").replaceChildren(...report.by_geography.map((item) => { const row = document.createElement("tr"); [item.province || "ثبت‌نشده", item.city || "ثبت‌نشده", item.count].forEach((value) => appendCell(row, value)); return row; }));
                document.getElementById("sales-document-status-body").replaceChildren(...report.by_postal_status.map((item) => { const row = document.createElement("tr"); [item.postal_status, item.count].forEach((value) => appendCell(row, value)); return row; }));
                if (report.total) content.hidden = false; else empty.hidden = false;
            });
        });
    }

    function inboundSMSReportQuery(form) {
        const data = new FormData(form);
        const query = new URLSearchParams();
        query.set("period_start", apiDateTime(String(data.get("period_start") || "")) || "");
        query.set("period_end", apiDateTime(String(data.get("period_end") || "")) || "");
        ["provider_code", "recipient_normalized", "processing_state"].forEach((name) => {
            const value = String(data.get(name) || "").trim();
            if (value) query.set(name, value);
        });
        return query;
    }

    function renderInboundSMSChart(rows) {
        // `local_date` is a DateField, so it arrives as a bare `YYYY-MM-DD`.
        // `displayDay` reads that as a calendar day rather than pushing it
        // through a time zone, and returns Jalali — this chart was the one
        // surface still showing Gregorian dates and Latin digits.
        //
        // Not sorted: the sequence is the chart. Reordering hourly counts by
        // size would destroy the only thing a time series is for.
        const items = rows.map((item) => ({
            label: `${displayDay(item.local_date)} — ساعت ${toPersianDigits(String(item.local_hour).padStart(2, "0"))}`,
            value: Number(item.inbound_sms_count),
            display: toPersianDigits(String(item.inbound_sms_count)),
        }));
        // An area rather than bars: these are consecutive hours, and the
        // question is the shape over time, not which single hour was tallest.
        // One reading has no shape, so that case falls back to a bar.
        const chart = document.getElementById("inbound-sms-chart");
        const empty = document.getElementById("inbound-sms-chart-empty");
        const ariaLabel = `نمودار تعداد پیامک ورودی در ${toPersianDigits(String(items.length))} بازه زمانی`;
        if (items.length >= 2) {
            renderAreaChart(chart, empty, items, {ariaLabel, maxLabels: 6});
        } else {
            renderBarChart(chart, empty, items, {sort: false, ariaLabel});
        }
    }

    async function showInboundSMSMessage(messageId) {
        try {
            const item = await apiRequest(`/api/v1/reports/inbound-sms/messages/${messageId}/`);
            document.getElementById("inbound-sms-detail-external").textContent = item.external_message_id;
            document.getElementById("inbound-sms-detail-system-time").textContent = displayDate(item.system_received_at);
            document.getElementById("inbound-sms-detail-lead").textContent = item.lead_label || "بدون تطبیق قطعی";
            document.getElementById("inbound-sms-detail-metadata").textContent = JSON.stringify(item.metadata, null, 2);
            const detail = document.getElementById("inbound-sms-message-detail");
            detail.hidden = false;
            detail.scrollIntoView({behavior: "smooth", block: "start"});
        } catch (error) {
            showError(error);
        }
    }

    async function loadInboundSMSDrilldown(localDate, localHour, page = 1) {
        const section = document.getElementById("inbound-sms-drilldown");
        const loading = document.getElementById("inbound-sms-drilldown-loading");
        const errorNode = document.getElementById("inbound-sms-drilldown-error");
        const empty = document.getElementById("inbound-sms-drilldown-empty");
        const wrap = document.getElementById("inbound-sms-drilldown-wrap");
        const pager = document.getElementById("inbound-sms-drilldown-pagination");
        const query = inboundSMSReportQuery(document.getElementById("inbound-sms-report-form"));
        query.set("local_date", localDate);
        query.set("local_hour", String(localHour));
        query.set("page", String(page));
        section.hidden = false;
        loading.hidden = false;
        errorNode.hidden = true;
        empty.hidden = true;
        wrap.hidden = true;
        pager.hidden = true;
        document.getElementById("inbound-sms-drilldown-title").textContent = `جزئیات ${localDate} — ساعت ${String(localHour).padStart(2, "0")}`;
        try {
            const data = await apiRequest(`/api/v1/reports/inbound-sms/drilldown/?${query}`);
            const rows = data.results.map((item) => {
                const row = document.createElement("tr");
                [
                    item.provider_code,
                    item.sender_normalized,
                    item.recipient_normalized,
                    displayDate(item.provider_received_at),
                    item.customer_name || "بدون تطبیق قطعی",
                    item.processing_state === "linked" ? "متصل" : "بدون تطبیق",
                ].forEach((value) => appendCell(row, value));
                const actions = document.createElement("td");
                const button = document.createElement("button");
                button.type = "button";
                button.className = "btn btn-sm btn-light";
                button.textContent = "نمایش";
                button.addEventListener("click", () => showInboundSMSMessage(item.id));
                actions.appendChild(button);
                row.appendChild(actions);
                return row;
            });
            document.getElementById("inbound-sms-drilldown-body").replaceChildren(...rows);
            loading.hidden = true;
            if (!rows.length) {
                empty.hidden = false;
                return;
            }
            wrap.hidden = false;
            const previous = document.getElementById("inbound-sms-drilldown-prev");
            const next = document.getElementById("inbound-sms-drilldown-next");
            previous.disabled = !data.previous;
            next.disabled = !data.next;
            previous.onclick = () => loadInboundSMSDrilldown(localDate, localHour, page - 1);
            next.onclick = () => loadInboundSMSDrilldown(localDate, localHour, page + 1);
            document.getElementById("inbound-sms-drilldown-page").textContent = `صفحه ${page}`;
            pager.hidden = !data.previous && !data.next;
        } catch (error) {
            loading.hidden = true;
            errorNode.textContent = errorText(error);
            errorNode.hidden = false;
        }
    }

    async function setupInboundSMSReport() {
        const form = document.getElementById("inbound-sms-report-form");
        bindReportTableSearch(
            document.getElementById("inbound-sms-report-search"),
            [document.getElementById("inbound-sms-table-body")],
        );
        const now = new Date();
        document.getElementById("inbound-sms-start").value = localDateTimeValue(new Date(now.getFullYear(), now.getMonth(), 1));
        document.getElementById("inbound-sms-end").value = localDateTimeValue(new Date(now.getTime() + 60000));
        const load = async () => {
            clearMessages(form);
            const loading = document.getElementById("inbound-sms-loading");
            const errorNode = document.getElementById("inbound-sms-error");
            const content = document.getElementById("inbound-sms-content");
            const empty = document.getElementById("inbound-sms-empty");
            const wrap = document.getElementById("inbound-sms-table-wrap");
            const button = form.querySelector("button[type='submit']");
            loading.hidden = false;
            errorNode.hidden = true;
            content.hidden = true;
            document.getElementById("inbound-sms-drilldown").hidden = true;
            document.getElementById("inbound-sms-message-detail").hidden = true;
            button.disabled = true;
            try {
                const report = await apiRequest(`/api/v1/reports/inbound-sms/?${inboundSMSReportQuery(form)}`);
                document.getElementById("inbound-sms-total").textContent = String(report.total);
                const rows = report.results.map((item) => {
                    const row = document.createElement("tr");
                    [item.local_date, String(item.local_hour).padStart(2, "0"), item.inbound_sms_count].forEach((value) => appendCell(row, value));
                    const actions = document.createElement("td");
                    const drill = document.createElement("button");
                    drill.type = "button";
                    drill.className = "btn btn-sm btn-light";
                    drill.textContent = "جزئیات";
                    drill.addEventListener("click", () => loadInboundSMSDrilldown(item.local_date, item.local_hour));
                    actions.appendChild(drill);
                    row.appendChild(actions);
                    return row;
                });
                document.getElementById("inbound-sms-table-body").replaceChildren(...rows);
                renderInboundSMSChart(report.results);
                empty.hidden = Boolean(rows.length);
                wrap.hidden = !rows.length;
                content.hidden = false;
            } catch (error) {
                errorNode.textContent = errorText(error);
                errorNode.hidden = false;
                showError(error, form);
            } finally {
                loading.hidden = true;
                button.disabled = false;
            }
        };
        form.addEventListener("submit", (event) => { event.preventDefault(); load(); });
        await load();
    }

    function outboundSmsRow(item) {
        const row = document.createElement("tr");
        appendCell(row, displayDate(item.sent_at));
        appendCell(row, item.recipient_normalized);
        appendCell(row, item.customer_name || item.lead_label || "—");
        const statusCell = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = `badge ${item.status === "sent" ? "badge-light-success" : "badge-light-danger"}`;
        badge.textContent = item.status === "sent" ? "ارسال شد" : "ناموفق";
        statusCell.appendChild(badge);
        row.appendChild(statusCell);
        appendCell(row, item.status_detail || "—");
        const bodyCell = document.createElement("td");
        bodyCell.textContent = item.body_text.length > 60 ? `${item.body_text.slice(0, 60)}…` : item.body_text;
        row.appendChild(bodyCell);
        return row;
    }

    async function loadOutboundSmsLog(url) {
        const empty = document.getElementById("outbound-sms-empty");
        const wrap = document.getElementById("outbound-sms-table-wrap");
        const pager = document.getElementById("outbound-sms-pagination");
        try {
            const data = await apiRequest(url);
            const rows = data.results.map(outboundSmsRow);
            document.getElementById("outbound-sms-table-body").replaceChildren(...rows);
            empty.hidden = Boolean(rows.length);
            wrap.hidden = !rows.length;
            pager.hidden = !data.previous && !data.next;
            const previous = document.getElementById("outbound-sms-prev");
            const next = document.getElementById("outbound-sms-next");
            previous.disabled = !data.previous;
            next.disabled = !data.next;
            previous.onclick = () => data.previous && loadOutboundSmsLog(data.previous);
            next.onclick = () => data.next && loadOutboundSmsLog(data.next);
        } catch (error) {
            showError(error);
        }
    }

    /**
     * How many SMS segments a body will actually cost.
     *
     * The GSM-7 alphabet carries 160 characters per segment (153 once a
     * message is concatenated, because each part spends 7 characters on a
     * user-data header); anything outside it — every Persian message — is
     * encoded UCS-2 at 70 per segment, 67 concatenated. These are the GSM
     * 03.38 / 23.038 numbers every Iranian SMS panel shows, not a guess: an
     * operator who writes 80 Persian characters is billed for two messages
     * and needs to see that before sending, not on the invoice.
     */
    const GSM7_ALPHABET = new Set(
        "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?" +
        "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà" +
        "^{}\\[~]|€",
    );

    function smsSegmentInfo(text) {
        const body = String(text || "");
        if (!body) return {characters: 0, segments: 0, encoding: "GSM-7", perSegment: 160};
        const isGsm7 = [...body].every((character) => GSM7_ALPHABET.has(character));
        const single = isGsm7 ? 160 : 70;
        const concatenated = isGsm7 ? 153 : 67;
        // `[...body]` rather than `.length`: an emoji is one character to a
        // reader and two UTF-16 code units to `.length`, and the carrier
        // counts code units — but the *limit* comparison people expect is on
        // what they typed, so count code units explicitly and say so.
        const units = body.split("").length;
        const segments = units <= single ? 1 : Math.ceil(units / concatenated);
        return {
            characters: units,
            segments,
            encoding: isGsm7 ? "GSM-7" : "فارسی",
            perSegment: segments <= 1 ? single : concatenated,
        };
    }

    /**
     * The SMS page: one composer that sends either to a single recipient or
     * to a group (now or at a stated time), the saved-template picker, the
     * campaign list, and the ordinary outbound log.
     */
    async function setupOutboundSms() {
        const form = document.getElementById("outbound-sms-send-form");
        if (!form) return;
        const bodyInput = document.getElementById("outbound-sms-body");
        const counter = document.getElementById("sms-body-counter");
        const submitLabel = document.getElementById("sms-submit-label");
        const chips = document.getElementById("sms-bulk-chips");
        const chipsNote = document.getElementById("sms-bulk-count");
        const phonesInput = document.getElementById("sms-bulk-phones");
        const scheduleInput = document.getElementById("sms-schedule-at");
        const templatePicker = document.getElementById("sms-template-picker");

        // Chosen recipients for a group send, keyed so the same person cannot
        // be added twice from the same picker. The service de-duplicates by
        // normalised number as well — this is the visible half of that.
        const chosen = {customers: new Map(), leads: new Map()};
        let mode = "single";

        function updateCounter() {
            const info = smsSegmentInfo(bodyInput.value);
            if (!info.characters) {
                counter.textContent = "";
                return;
            }
            counter.textContent =
                `${toPersianDigits(String(info.characters))} نویسه — ` +
                `${toPersianDigits(String(info.segments))} پیامک (${info.encoding}، ` +
                `${toPersianDigits(String(info.perSegment))} نویسه در هر پیامک)`;
        }

        function renderChips() {
            const nodes = [];
            [["customers", "مشتری"], ["leads", "سرنخ"]].forEach(([kind, label]) => {
                chosen[kind].forEach((name, id) => {
                    const chip = document.createElement("span");
                    chip.className = "badge badge-light-primary d-inline-flex align-items-center gap-2";
                    const text = document.createElement("span");
                    text.textContent = `${label}: ${name}`;
                    const remove = document.createElement("button");
                    remove.type = "button";
                    remove.className = "btn btn-icon btn-active-light-danger btn-sm w-15px h-15px";
                    remove.setAttribute("aria-label", `حذف ${name}`);
                    remove.textContent = "×";
                    remove.addEventListener("click", () => {
                        chosen[kind].delete(id);
                        renderChips();
                    });
                    chip.append(text, remove);
                    nodes.push(chip);
                });
            });
            chips.replaceChildren(...nodes);
            const total = chosen.customers.size + chosen.leads.size;
            chipsNote.textContent = total ? ` ${toPersianDigits(String(total))} گیرنده از فهرست انتخاب شده است.` : "";
            chipsNote.previousSibling && (chipsNote.parentElement.firstChild.textContent =
                total ? "" : "هیچ گیرنده‌ای انتخاب نشده است.");
        }

        function setMode(next) {
            mode = next;
            document.querySelectorAll("[data-sms-recipients]").forEach((node) => {
                node.hidden = node.dataset.smsRecipients !== next;
            });
            document.querySelectorAll("[data-sms-mode]").forEach((button) => {
                const active = button.dataset.smsMode === next;
                button.classList.toggle("btn-primary", active);
                button.classList.toggle("btn-light", !active);
                button.setAttribute("aria-pressed", String(active));
            });
            // The single-send fields are `required`-free but still submitted;
            // clearing them on switch stops a stale customer id riding along
            // with a group send.
            if (next === "bulk") {
                ["outbound-sms-customer", "outbound-sms-lead", "outbound-sms-phone"].forEach((id) => {
                    const node = document.getElementById(id);
                    if (node) node.value = "";
                });
            }
            submitLabel.textContent = next === "bulk" ? "ثبت ارسال گروهی" : "ارسال پیامک";
        }

        document.querySelectorAll("[data-sms-mode]").forEach((button) => {
            button.addEventListener("click", () => setMode(button.dataset.smsMode));
        });
        bindLiveSearch(bodyInput, () => {});
        bodyInput.addEventListener("input", updateCounter);
        updateCounter();

        // --- saved templates --------------------------------------------
        async function loadTemplates() {
            try {
                const templates = await apiRequest("/api/v1/outbound-sms/templates/");
                const options = [new Option("قالب آماده…", "")];
                templates.forEach((template) => {
                    const option = new Option(template.title, String(template.id));
                    option.dataset.body = template.body_text;
                    options.push(option);
                });
                templatePicker.replaceChildren(...options);
            } catch (error) {
                // A missing template list must not stop someone sending a
                // message they already typed.
                showError(error);
            }
        }

        templatePicker?.addEventListener("change", () => {
            const option = templatePicker.selectedOptions[0];
            if (!option?.dataset.body) return;
            bodyInput.value = option.dataset.body;
            updateCounter();
        });

        const templateDialog = document.getElementById("sms-template-dialog");
        document.getElementById("sms-template-save")?.addEventListener("click", () => {
            if (!bodyInput.value.trim()) {
                globalMessage("اول متن پیامک را بنویسید.");
                return;
            }
            document.getElementById("sms-template-name").value = "";
            templateDialog?.showModal();
        });
        document.getElementById("sms-template-confirm")?.addEventListener("click", async () => {
            try {
                await apiRequest("/api/v1/outbound-sms/templates/", {
                    method: "POST",
                    body: {
                        title: document.getElementById("sms-template-name").value,
                        body: bodyInput.value,
                    },
                });
                templateDialog?.close();
                globalMessage("قالب ذخیره شد.", true);
                await loadTemplates();
            } catch (error) {
                showError(error);
            }
        });

        // --- group recipient pickers -------------------------------------
        const customerSelect = document.getElementById("sms-bulk-customer");
        const leadSelect = document.getElementById("sms-bulk-lead");
        if (customerSelect) {
            try {
                const customers = await apiRequest("/api/v1/customers/?page_size=200");
                fillSelect(customerSelect, customers.results || customers, (item) => item.full_name, "افزودن مشتری…");
                customerSelect.addEventListener("change", () => {
                    const id = customerSelect.value;
                    if (!id) return;
                    chosen.customers.set(id, selectedOptionText(customerSelect));
                    customerSelect.value = "";
                    renderChips();
                });
            } catch (error) {
                showError(error);
            }
        }
        if (leadSelect) {
            try {
                const leads = await apiRequest("/api/v1/leads/?page_size=200");
                fillSelect(
                    leadSelect,
                    leads.results || leads,
                    (item) => item.customer_name || item.source || `سرنخ ${item.id}`,
                    "افزودن سرنخ…",
                );
                leadSelect.addEventListener("change", () => {
                    const id = leadSelect.value;
                    if (!id) return;
                    chosen.leads.set(id, selectedOptionText(leadSelect));
                    leadSelect.value = "";
                    renderChips();
                });
            } catch (error) {
                showError(error);
            }
        }
        setupSearchableSelects(form);
        renderChips();

        // --- campaigns ----------------------------------------------------
        const CAMPAIGN_STATUS = {
            scheduled: ["زمان‌بندی‌شده", "badge-light-info"],
            sending: ["در حال ارسال", "badge-light-primary"],
            completed: ["پایان‌یافته", "badge-light-success"],
            cancelled: ["لغوشده", "badge-light-danger"],
        };

        function campaignRow(item) {
            const row = document.createElement("tr");
            appendCell(row, displayDate(item.scheduled_for));
            const statusCell = document.createElement("td");
            const [label, badgeClass] = CAMPAIGN_STATUS[item.status] || [item.status, "badge-light"];
            const badge = document.createElement("span");
            badge.className = `badge ${badgeClass}`;
            badge.textContent = label;
            statusCell.append(badge);
            row.append(statusCell);
            appendCell(
                row,
                `${toPersianDigits(String(item.sent_count))} ارسال‌شده / ` +
                `${toPersianDigits(String(item.failed_count))} ناموفق / ` +
                `${toPersianDigits(String(item.pending_count))} در صف`,
            );
            appendCell(row, item.created_by_name || "—");
            appendCell(row, item.body_text.slice(0, 60));
            const actions = document.createElement("td");
            if (item.status === "scheduled" || item.status === "sending") {
                const cancel = document.createElement("button");
                cancel.type = "button";
                cancel.className = "btn btn-sm btn-light-danger";
                cancel.textContent = "لغو";
                cancel.addEventListener("click", async () => {
                    try {
                        await apiRequest(`/api/v1/outbound-sms/campaigns/${item.id}/cancel/`, {method: "POST"});
                        globalMessage("کارزار لغو شد.", true);
                        await loadCampaigns("/api/v1/outbound-sms/campaigns/");
                    } catch (error) {
                        showError(error);
                    }
                });
                actions.append(cancel);
            } else {
                actions.textContent = "—";
            }
            row.append(actions);
            return row;
        }

        async function loadCampaigns(url) {
            const empty = document.getElementById("sms-campaigns-empty");
            const wrap = document.getElementById("sms-campaigns-table-wrap");
            const pager = document.getElementById("sms-campaigns-pagination");
            try {
                const data = await apiRequest(url);
                const rows = data.results.map(campaignRow);
                document.getElementById("sms-campaigns-table-body").replaceChildren(...rows);
                empty.hidden = Boolean(rows.length);
                wrap.hidden = !rows.length;
                pager.hidden = !data.previous && !data.next;
                const previous = document.getElementById("sms-campaigns-prev");
                const next = document.getElementById("sms-campaigns-next");
                previous.disabled = !data.previous;
                next.disabled = !data.next;
                previous.onclick = () => data.previous && loadCampaigns(data.previous);
                next.onclick = () => data.next && loadCampaigns(data.next);
            } catch (error) {
                showError(error);
            }
        }

        // --- submit --------------------------------------------------------
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                if (mode === "single") {
                    const data = formPayload(form, ["customer", "lead", "phone", "body"]);
                    const payload = {body: data.body};
                    if (data.customer) payload.customer = data.customer;
                    if (data.lead) payload.lead = data.lead;
                    if (data.phone) payload.phone = data.phone;
                    const sent = await apiRequest("/api/v1/outbound-sms/send/", {method: "POST", body: payload});
                    form.reset();
                    updateCounter();
                    // The request itself succeeded (HTTP 200) either way — the
                    // attempt was recorded — but the provider may still have
                    // refused the message, which is a distinct outcome the
                    // operator needs to see, not a silent "sent".
                    if (sent.status === "sent") {
                        globalMessage("پیامک ارسال شد.", true);
                    } else {
                        globalMessage(`ارسال ناموفق بود: ${sent.status_detail || "دلیل نامشخص"}`);
                    }
                    await loadOutboundSmsLog("/api/v1/outbound-sms/");
                    return;
                }

                const phones = (phonesInput?.value || "")
                    .split(/[\n،,;]+/)
                    .map((value) => value.trim())
                    .filter(Boolean);
                const payload = {
                    body: bodyInput.value,
                    customers: [...chosen.customers.keys()].map(Number),
                    leads: [...chosen.leads.keys()].map(Number),
                    phones,
                };
                // The picker keeps Jalali text in `.value`; `apiDateTime`
                // is the same converter every other scheduled field uses.
                const typed = (scheduleInput?.value || "").trim();
                const when = typed ? apiDateTime(typed) : "";
                if (typed && !when) throw new Error("زمان ارسال خوانده نشد؛ قالب باید ۱۴۰۵/۰۵/۲۵ ۱۴:۳۰ باشد.");
                if (when) payload.scheduled_for = when;
                const campaign = await apiRequest("/api/v1/outbound-sms/campaigns/", {
                    method: "POST",
                    body: payload,
                });
                bodyInput.value = "";
                if (phonesInput) phonesInput.value = "";
                if (scheduleInput) scheduleInput.value = "";
                chosen.customers.clear();
                chosen.leads.clear();
                renderChips();
                updateCounter();
                globalMessage(
                    when
                        ? `ارسال گروهی برای ${toPersianDigits(String(campaign.recipient_count))} گیرنده زمان‌بندی شد.`
                        : `ارسال گروهی برای ${toPersianDigits(String(campaign.recipient_count))} گیرنده ثبت شد.`,
                    true,
                );
                await Promise.all([
                    loadCampaigns("/api/v1/outbound-sms/campaigns/"),
                    loadOutboundSmsLog("/api/v1/outbound-sms/"),
                ]);
            });
        });

        setMode("single");
        await Promise.all([
            loadOutboundSmsLog("/api/v1/outbound-sms/"),
            loadCampaigns("/api/v1/outbound-sms/campaigns/"),
            loadTemplates(),
        ]);
    }

    function afterSalesRow(item) {
        const row = document.createElement("tr");
        [item.subject, item.customer_name || item.customer, item.status, item.assigned_to_display || "تخصیص‌نیافته", item.closed_at ? "بسته" : "باز", displayDate(item.created_at)].forEach((value) => appendCell(row, value));
        appendDetailLink(row, `/after-sales/${item.id}/`);
        return row;
    }

    async function setupAfterSales() {
        const form = document.getElementById("after-sales-search-form");
        setupListFilter("after-sales");
        const controller = setupPagedList({key: "after-sales", form, search: document.getElementById("after-sales-search"), endpoint: (page) => {
            const query = new URLSearchParams({page: String(page), ordering: document.getElementById("after-sales-ordering").value});
            const search = document.getElementById("after-sales-search").value.trim(); if (search) query.set("search", search);
            [["status", "after-sales-status"], ["assigned_to", "after-sales-assignee"], ["is_closed", "after-sales-closed"]].forEach(([name, id]) => { const node = document.getElementById(id); const value = node?.value.trim(); if (value) query.set(name, value); });
            return `/api/v1/after-sales/?${query}`;
        }, renderRow: afterSalesRow});
        controller.load();
        const dialog = document.getElementById("create-after-sales-dialog");
        if (!dialog) return;
        const customerSelect = document.getElementById("create-after-sales-customer");
        const saleSelect = document.getElementById("create-after-sales-sale");
        const documentSelect = document.getElementById("create-after-sales-document");
        const assigneeSelect = document.getElementById("create-after-sales-assigned");
        let sales = [], documents = [];
        function renderAfterSalesReview() {
            renderWizardReview(document.getElementById("create-after-sales-review"), [
                ["مشتری", selectedOptionText(customerSelect)],
                ["فروش اختیاری", selectedOptionText(saleSelect)],
                ["سند عملیاتی اختیاری", selectedOptionText(documentSelect)],
                ["مسئول اختیاری", selectedOptionText(assigneeSelect)],
                ["موضوع", document.getElementById("create-after-sales-subject").value],
                ["وضعیت آغازین", document.getElementById("create-after-sales-status").value],
                ["شرح", document.getElementById("create-after-sales-description").value],
            ]);
        }
        const afterSalesWizard = setupWizard(dialog, {onReachLastStep: renderAfterSalesReview});
        // Wire the dialog before the awaited loads below, so a click during
        // them opens the dialog instead of being silently discarded.
        customerSelect.addEventListener("change", refreshRelations);
        document.getElementById("open-create-after-sales").addEventListener("click", () => {
            document.getElementById("create-after-sales-form").reset();
            clearMessages(document.getElementById("create-after-sales-form"));
            afterSalesWizard?.goFirst();
            dialog.showModal();
        });
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        try {
            const [customers, loadedSales, loadedDocuments, assignees] = await Promise.all([
                loadAllPages("/api/v1/customers/?ordering=full_name"), loadAllPages("/api/v1/sales/?ordering=-sold_at"),
                loadAllPages("/api/v1/sales-documents/?ordering=-registered_at"), loadAllPages("/api/v1/after-sales/assignees/"),
            ]);
            sales = loadedSales; documents = loadedDocuments;
            fillSelect(customerSelect, customers, (item) => item.full_name, "یک مشتری انتخاب کنید");
            fillSelect(assigneeSelect, assignees, (item) => item.display, "فعلا تخصیص ندهید");
        } catch (error) { showError(error); }
        function refreshRelations() {
            const id = Number(customerSelect.value);
            fillSelect(saleSelect, sales.filter((item) => Number(item.customer) === id), (item) => `فروش ${item.id}`, "بدون فروش");
            fillSelect(documentSelect, documents.filter((item) => Number(item.customer) === id), (item) => item.document_number, "بدون سند");
        }
        const createForm = document.getElementById("create-after-sales-form");
        createForm.addEventListener("submit", (event) => { event.preventDefault(); withSubmit(createForm, async () => {
            const payload = formPayload(createForm, ["customer", "sale", "document", "assigned_to", "subject", "description", "status"]);
            ["sale", "document", "assigned_to"].forEach((name) => { if (!payload[name]) delete payload[name]; });
            const item = await apiRequest(createForm.action, {method: "POST", body: payload}); window.location.assign(`/after-sales/${item.id}/`);
        }); });
    }

    function fillAfterSales(item) {
        document.getElementById("after-sales-subject-detail").value = item.subject;
        document.getElementById("after-sales-customer-detail").value = item.customer_name || item.customer;
        document.getElementById("after-sales-sale-detail").value = item.sale || "—";
        document.getElementById("after-sales-document-detail").value = item.document || "—";
        document.getElementById("after-sales-status-detail").value = item.status;
        document.getElementById("after-sales-assigned-detail").value = item.assigned_to_display || "تخصیص‌نیافته";
        document.getElementById("after-sales-created-by-detail").value = item.created_by_display || item.created_by;
        document.getElementById("after-sales-closed-detail").value = displayDate(item.closed_at);
        document.getElementById("after-sales-appointment-detail").value = item.next_appointment_at ? displayDate(item.next_appointment_at) : "زمان‌بندی‌نشده";
        document.getElementById("after-sales-description-detail").value = item.description;
        document.getElementById("after-sales-actions").hidden = Boolean(item.closed_at);
    }

    async function loadAfterSalesHistory(id) {
        const rows = await loadAllPages(`/api/v1/after-sales/${id}/history/`);
        const eventLabels = {created: "ایجاد", assigned: "تخصیص", status_changed: "تغییر وضعیت", closed: "بستن", appointment_scheduled: "زمان‌بندی قرار"};
        const nodes = rows.map((item) => {
            const row = document.createElement("tr");
            const fromTo = item.event === "appointment_scheduled"
                ? (item.appointment_at ? displayDate(item.appointment_at) : "لغو قرار")
                : `${item.from_status || "—"} / ${item.to_status || "—"}`;
            [eventLabels[item.event] || item.event, fromTo, `${item.from_user_display || "—"} / ${item.to_user_display || "—"}`, item.actor_display, item.reason || "—", displayDate(item.created_at)].forEach((value) => appendCell(row, value));
            return row;
        });
        document.getElementById("after-sales-history-body").replaceChildren(...nodes);
        document.getElementById("after-sales-history-loading").hidden = true;
        document.getElementById("after-sales-history-empty").hidden = Boolean(nodes.length);
        document.getElementById("after-sales-history-wrap").hidden = !nodes.length;
    }

    async function setupAfterSalesDetail() {
        const id = document.body.dataset.afterSalesId, endpoint = `/api/v1/after-sales/${id}/`;
        let item;
        try { [item] = await Promise.all([apiRequest(endpoint), loadAfterSalesHistory(id)]); fillAfterSales(item); document.getElementById("after-sales-detail-loading").hidden = true; document.getElementById("after-sales-detail-content").hidden = false; } catch (error) { document.getElementById("after-sales-detail-loading").hidden = true; showError(error); return; }
        const statusForm = document.getElementById("after-sales-status-form");
        statusForm.addEventListener("submit", (event) => { event.preventDefault(); withSubmit(statusForm, async () => { item = await apiRequest(statusForm.action, {method: "POST", body: formPayload(statusForm, ["to_status", "reason"])}); fillAfterSales(item); statusForm.reset(); await loadAfterSalesHistory(id); globalMessage("وضعیت پرونده ثبت شد.", true); }); });
        const appointmentForm = document.getElementById("after-sales-appointment-form");
        appointmentForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(appointmentForm, async () => {
                const raw = new FormData(appointmentForm).get("appointment_at");
                const body = {
                    appointment_at: apiDateTime(String(raw || "")) || null,
                    reason: String(new FormData(appointmentForm).get("reason") || ""),
                };
                item = await apiRequest(appointmentForm.action, {method: "POST", body});
                fillAfterSales(item);
                await loadAfterSalesHistory(id);
                globalMessage(body.appointment_at ? "قرار زمان‌بندی شد." : "قرار لغو شد.", true);
            });
        });
        const assignForm = document.getElementById("after-sales-assign-form");
        if (assignForm) {
            try { fillSelect(document.getElementById("after-sales-to-user"), await loadAllPages("/api/v1/after-sales/assignees/"), (user) => user.display, "مسئول را انتخاب کنید"); } catch (error) { showError(error); }
            assignForm.addEventListener("submit", (event) => { event.preventDefault(); withSubmit(assignForm, async () => { item = await apiRequest(assignForm.action, {method: "POST", body: formPayload(assignForm, ["to_user", "reason"])}); fillAfterSales(item); assignForm.reset(); await loadAfterSalesHistory(id); globalMessage("پرونده تخصیص یافت.", true); }); });
            document.getElementById("close-after-sales").addEventListener("click", async () => { if (!window.confirm("پرونده بسته شود؟ بازگشایی هنوز تصویب نشده.")) return; try { item = await apiRequest(`${endpoint}close/`, {method: "POST", body: {}}); fillAfterSales(item); await loadAfterSalesHistory(id); globalMessage("پرونده بسته شد.", true); } catch (error) { showError(error); } });
        }
    }

    function reportQuery(form) {
        const data = new FormData(form);
        const query = new URLSearchParams();
        query.set("period_start", apiDateTime(String(data.get("period_start") || "")) || "");
        query.set("period_end", apiDateTime(String(data.get("period_end") || "")) || "");
        ["user_id", "sales_product_id"].forEach((name) => {
            const value = String(data.get(name) || "").trim();
            if (value) query.set(name, value);
        });
        return query;
    }

    /**
     * One horizontal bar per item, drawn from `div`s.
     *
     * The panel deliberately ships no charting library: the theme's ApexCharts
     * lives inside a 3.5 MB bundle that `collectstatic` excludes, and every
     * chart here is a comparison across a handful of rows, which a bar answers
     * without one. See docs/frontend/CHARTS_GROUNDWORK.md.
     *
     * `items` is `[{label, value, display}]` — `value` sizes the bar, `display`
     * is what the reader sees, already formatted by the caller. Keeping those
     * apart is what stops a chart printing a raw `12500000.00` beside tables
     * reading grouped rial, which is what the two renderers this replaces had
     * each drifted into doing in their own way.
     *
     * options:
     *   ariaLabel  what the chart says to a screen reader; bars announce nothing
     *   limit      keep only the first N after sorting (a "top N" chart)
     *   sort       order by value descending; off for fixed categories such as
     *              ageing buckets or a time series, where the sequence itself
     *              carries the meaning
     *   keepZero   draw zero-valued items as empty tracks instead of dropping
     *              them — for a fixed category, an empty bucket is information
     */
    //: One offscreen canvas, reused rather than created per call — this is
    //: called once per category on every horizontal bar chart the panel
    //: draws, and a `<canvas>` is not free to allocate.
    let _measureCanvas = null;

    /**
     * How wide a string actually renders in a given font, in CSS pixels.
     *
     * Exists because ApexCharts' own automatic y-axis gutter sizing — meant
     * to reserve enough room for the longest category label before drawing
     * the plot — measured badly for this panel's Persian category names and
     * IRANSansWeb: on a live chart the gutter came out at 45px for labels
     * that render 150–160px wide, so every bar's own opening third drew
     * directly under the category name instead of the label sitting beside
     * it. Measuring the text ourselves and setting the gutter from that
     * number, rather than trusting Apex's own calculation, is what actually
     * keeps a bar chart's "keys" — its category names — outside the bars,
     * the same way its values now sit outside them too.
     */
    function measureTextWidth(text, font) {
        _measureCanvas ??= document.createElement("canvas");
        const context = _measureCanvas.getContext("2d");
        context.font = font;
        return context.measureText(text).width;
    }

    /**
     * The series colours, taken from the purchased theme rather than chosen.
     *
     * Read at draw time from the live custom properties, so a chart drawn in
     * dark mode gets the theme's dark values — `--bs-primary` is `#1B84FF` in
     * light and `#006AE6` in dark, and a hard-coded hex would be wrong in one
     * of them.
     */
    function chartPalette() {
        const style = getComputedStyle(document.documentElement);
        const read = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
        return [
            read("--bs-primary", "#1B84FF"),
            read("--bs-success", "#17C653"),
            read("--bs-info", "#7239EA"),
            read("--bs-warning", "#F6C000"),
            read("--bs-danger", "#F8285A"),
            // `--bs-dark` used to close this out. On this panel's own dark
            // theme that value sits only a few shades off the card
            // background it draws on, so a chart's sixth series all but
            // vanished — the same bug `WIDGET_STYLE`'s "dark" accents had
            // (common/ui_views.py, 2026-09-11). Orange is the same fill
            // `severityRamp` below already reaches for to widen this exact
            // palette, for the same reason.
            read("--bs-orange", "#fd7e14"),
        ];
    }

    /**
     * Five colours that escalate, for the receivables ageing buckets.
     *
     * Not decoration: the buckets run from "not yet due" to "over ninety days",
     * so the colour has to carry the same direction the reader is already
     * looking for — and it has to keep moving at every step. Built from the
     * palette's own success/primary/warning/danger with Bootstrap's `--bs-orange`
     * filling the gap between warning and danger, because the theme has no
     * colour there and repeating the yellow made buckets three and four look
     * equally bad when one is twice as old as the other.
     */
    function severityRamp() {
        const palette = chartPalette();
        const orange =
            getComputedStyle(document.documentElement).getPropertyValue("--bs-orange").trim()
            || "#fd7e14";
        return [palette[1], palette[0], palette[3], orange, palette[4]];
    }

    function chartInk() {
        const style = getComputedStyle(document.documentElement);
        return {
            grid: style.getPropertyValue("--bs-gray-300").trim() || "#DBDFE9",
            muted: style.getPropertyValue("--bs-gray-500").trim() || "#99A1B7",
            text: style.getPropertyValue("--bs-gray-800").trim() || "#252F4A",
        };
    }

    /**
     * Everything every chart on this panel shares.
     *
     * ApexCharts is the theme's own chart library and comes from its plugin
     * bundle. What is set here is the part the theme cannot know: the panel is
     * RTL and Persian, its type is IRANSansWeb, and it has a dark mode that the
     * library has to be told about because Apex renders to SVG with its own
     * colours rather than inheriting the page's.
     */
    function apexBase(height) {
        const ink = chartInk();
        const dark = document.documentElement.getAttribute("data-bs-theme") === "dark";
        return {
            chart: {
                height,
                fontFamily: "IRANSansWeb, Helvetica, sans-serif",
                // Apex flips its own axes and legend from this, so the whole
                // chart reads right-to-left like the page around it.
                defaultLocale: "en",
                toolbar: {show: false},
                // Off deliberately. Apex animates a chart from an empty state
                // to its real geometry with requestAnimationFrame, so a chart
                // that mounts where frames are not being produced — a
                // background tab, a card still hidden, a headless browser — is
                // left showing the empty first frame permanently. Measured
                // exactly that: bars stuck at `M0.101 ... L0.101`, zero width,
                // and an area path flat on its baseline below the plot.
                //
                // It also costs nothing to lose. These are dense financial
                // report charts, not a landing page, and since a theme switch
                // now redraws every chart, keeping it would replay a half-second
                // grow on all of them each time the reader toggles light/dark.
                animations: {enabled: false},
                background: "transparent",
            },
            theme: {mode: dark ? "dark" : "light"},
            grid: {
                borderColor: ink.grid,
                strokeDashArray: 4,
                padding: {top: 0, right: 8, bottom: 0, left: 8},
                // Horizontal rules only. The purchased theme's charts read
                // values off the y axis and use the x axis purely for
                // sequence, so vertical rules add ink without adding a
                // reading — the "graph paper" look that made these feel
                // heavier than the theme's own (product-owner note
                // 2026-09-09). Each chart that genuinely needs the vertical
                // set turns it back on for itself.
                xaxis: {lines: {show: false}},
                yaxis: {lines: {show: true}},
            },
            tooltip: {
                style: {fontFamily: "IRANSansWeb, Helvetica, sans-serif", fontSize: "13px"},
            },
            legend: {
                fontFamily: "IRANSansWeb, Helvetica, sans-serif",
                labels: {colors: ink.muted},
                markers: {radius: 3},
                // Measured on a live legend: the marker's own edge landed
                // exactly on the label's edge, a real 0px gap, not merely a
                // tight one. Apex's built-in item spacing (an inline
                // `margin: 2px 5px` on the whole item) puts room *between*
                // items but nothing between a marker and its own label, so
                // this is set explicitly rather than left to the default.
                itemMargin: {horizontal: 10, vertical: 6},
            },
            noData: {
                text: "داده‌ای برای نمایش نیست.",
                style: {fontFamily: "IRANSansWeb, Helvetica, sans-serif", color: ink.muted},
            },
        };
    }

    //: One live chart per container. Apex keeps its own DOM and listeners, so a
    //: redraw has to destroy the previous instance or every reload leaves one
    //: behind — on a page whose filters redraw on every submit, that is a leak
    //: that grows for as long as the tab is open.
    const liveCharts = new WeakMap();

    //: What it would take to draw each chart on the page again, keyed by its
    //: container. Apex bakes the palette into the SVG at draw time — including
    //: the text colours — so a chart drawn in light mode keeps light-mode ink
    //: after a switch to dark, where `--bs-gray-800` ink on a dark card is
    //: nearly invisible. Redrawing is the only way to re-read the palette.
    const chartRedraws = new Map();

    function mountApex(chart, empty, options, ariaLabel) {
        const existing = liveCharts.get(chart);
        if (existing) {
            existing.destroy();
            liveCharts.delete(chart);
        }
        chart.replaceChildren();
        chart.hidden = false;
        empty.hidden = true;
        const instance = new ApexCharts(chart, options);
        instance.render();
        liveCharts.set(chart, instance);
        if (ariaLabel) chart.setAttribute("aria-label", ariaLabel);
        return instance;
    }

    function showEmptyChart(chart, empty) {
        const existing = liveCharts.get(chart);
        if (existing) {
            existing.destroy();
            liveCharts.delete(chart);
        }
        chart.replaceChildren();
        chart.hidden = true;
        empty.hidden = false;
    }

    /**
     * A donut, for "what is this total made of".
     *
     * Chosen over a pie because the hole carries the total, which is the number
     * a reader wants first — and because a ring compares arc lengths, which the
     * eye reads better than the wedge areas of a pie.
     */
    function renderDonutChart(chart, empty, items, options = {}) {
        const {ariaLabel = null, total = null, totalLabel = ""} = options;
        if (!chart || !empty) return;
        chartRedraws.set(chart, () => renderDonutChart(chart, empty, items, options));

        const usable = items.filter((item) => Number.isFinite(item.value) && item.value > 0);
        if (!usable.length) {
            showEmptyChart(chart, empty);
            return;
        }

        const palette = chartPalette();
        const ink = chartInk();
        // The already-formatted strings, held beside the series so the tooltip
        // and the centre can print rial rather than the bare number Apex has.
        const displays = usable.map((item) => item.display ?? String(item.value));

        mountApex(chart, empty, {
            ...apexBase(320),
            series: usable.map((item) => item.value),
            labels: usable.map((item) => item.label),
            colors: usable.map((item, index) => item.color || palette[index % palette.length]),
            chart: {...apexBase(320).chart, type: "donut"},
            // A ring of flat fills reads as a diagram; the theme's own pie and
            // donut widgets shade each wedge slightly across its own arc, which
            // is what gives them depth. `shade: "light"` keeps every wedge the
            // colour it was assigned — the ramp only varies its own lightness,
            // so two adjacent wedges never blend into one another.
            fill: {
                type: "gradient",
                gradient: {shade: "light", shadeIntensity: 0.28, opacityFrom: 1, opacityTo: 0.92},
            },
            stroke: {width: 2, colors: ["transparent"]},
            states: {
                hover: {filter: {type: "darken", value: 0.9}},
                active: {filter: {type: "none"}},
            },
            // No text drawn on the wedges themselves. A percentage printed on a
            // thin slice either overlaps its neighbour or gets clipped outside
            // the ring — the smaller the share, the less room its own label
            // has. The legend below is already outside the chart and has all
            // the room it needs, so the percentage moves there instead of
            // living on the drawing.
            dataLabels: {enabled: false},
            legend: {
                ...apexBase(320).legend,
                position: "bottom",
                // Name and share together, entirely outside the ring: "شهر X
                // — ۴۲٪" rather than a bare label the reader has to match back
                // to a wedge by colour alone.
                formatter: (label, opts) => {
                    const value = opts.w.globals.series[opts.seriesIndex];
                    const total = opts.w.globals.series.reduce((sum, each) => sum + each, 0);
                    const percent = total > 0 ? Math.round((value / total) * 100) : 0;
                    return `${label} — ${toPersianDigits(String(percent))}٪`;
                },
            },
            tooltip: {
                ...apexBase(320).tooltip,
                y: {formatter: (_value, {seriesIndex}) => displays[seriesIndex]},
            },
            plotOptions: {
                pie: {
                    donut: {
                        size: "68%",
                        labels: {
                            show: true,
                            // Apex would print the raw number here; the total is
                            // formatted by the server, which is the only place
                            // that knows whether this series is rial or a count.
                            total: {
                                show: true,
                                showAlways: true,
                                label: totalLabel || "مجموع",
                                color: ink.muted,
                                fontFamily: "IRANSansWeb, Helvetica, sans-serif",
                                formatter: () =>
                                    total ||
                                    toPersianDigits(
                                        String(usable.reduce((carry, item) => carry + item.value, 0)),
                                    ),
                            },
                            value: {
                                color: ink.text,
                                fontFamily: "IRANSansWeb, Helvetica, sans-serif",
                                fontSize: "20px",
                                fontWeight: 700,
                                formatter: (_value, opts) =>
                                    displays[opts?.seriesIndex ?? 0] ?? _value,
                            },
                            name: {
                                color: ink.muted,
                                fontFamily: "IRANSansWeb, Helvetica, sans-serif",
                            },
                        },
                    },
                },
            },
        }, ariaLabel);
    }

    /**
     * A tick-label formatter that prints only every Nth category's own
     * label, blank otherwise, so at most `maxLabels` of them ever reach the
     * axis — the *category* array itself stays untouched, so the tooltip
     * (which reads the same array for its own title) still names every
     * point.
     *
     * Apex's own `tickAmount`/`hideOverlappingLabels` are built for
     * horizontal label text; measured live on this panel's own rotated
     * (-45°) date labels, neither actually thinned anything — every one of
     * twelve category labels still rendered, each overlapping the label
     * beside it (design review, 2026-09-12).
     */
    function thinningFormatter(labels, maxLabels) {
        const step = Math.max(1, Math.ceil(labels.length / Math.max(1, maxLabels)));
        return (value) => {
            const index = labels.indexOf(value);
            return index === -1 || index % step === 0 ? value : "";
        };
    }

    /**
     * A filled area over a line, for a quantity moving through time.
     *
     * The fill is what separates this from a plain line: it gives the series a
     * mass the eye can compare between periods, and the gradient fades it out
     * before the axis so the shape stays legible where points sit close.
     */
    /**
     * On the axis direction, so it is not re-litigated.
     *
     * The hand-drawn chart this replaced reversed its x-axis so the earliest
     * point sat on the right, which is where a reader of an RTL panel starts.
     * `xaxis.reversed: true` is the Apex equivalent and was tried here — it is
     * a no-op in the build the purchased theme ships: measured, the earliest
     * category stayed leftmost at x=66 with it set. On horizontal bars the same
     * option is worse than a no-op and collapses every bar to zero width.
     *
     * The theme's own charts set neither `reversed` nor `opposite` and read
     * left-to-right in its RTL build, so all of these do too. That is a real
     * change from the hand-drawn behaviour, not an oversight.
     */
    function renderAreaChart(chart, empty, points, options = {}) {
        const {ariaLabel = null, summary = "", maxLabels = 8} = options;
        if (!chart || !empty) return;
        chartRedraws.set(chart, () => renderAreaChart(chart, empty, points, options));

        const usable = points.filter((point) => Number.isFinite(point.value));
        // One point is not a line. Two are the fewest that can show a direction,
        // and a direction is what this chart is for.
        if (usable.length < 2) {
            showEmptyChart(chart, empty);
            return;
        }

        const palette = chartPalette();
        const accent = options.color || palette[0];
        const displays = usable.map((point) => point.display ?? String(point.value));
        const base = apexBase(300);

        mountApex(chart, empty, {
            ...base,
            chart: {...base.chart, type: "area"},
            series: [{name: options.seriesName || "مقدار", data: usable.map((p) => p.value)}],
            colors: [accent],
            dataLabels: {enabled: false},
            stroke: {curve: "smooth", width: 3},
            // The purchased theme's own area widgets fade to nothing at the
            // baseline (`opacityTo: 0`, stops 0/80/100 — src/js/widgets/charts/
            // widget-11.js). Ours stopped at 0.05, which left a visible band
            // sitting on the axis and made the fill read as a block rather
            // than as a fade.
            fill: {
                type: "gradient",
                gradient: {shadeIntensity: 1, opacityFrom: 0.45, opacityTo: 0, stops: [0, 80, 100]},
            },
            // Markers only where the pointer is. A dot on every point turns a
            // twelve-week line into a dotted rule; the line is the shape being
            // read, and the point under the cursor is the one that matters.
            markers: {size: 0, strokeWidth: 3, hover: {size: 7}},
            xaxis: {
                categories: usable.map((point) => point.label),
                tickAmount: Math.min(maxLabels, usable.length),
                labels: {
                    style: {fontFamily: "IRANSansWeb, Helvetica, sans-serif", fontSize: "12px"},
                    hideOverlappingLabels: true,
                    trim: true,
                    // See `thinningFormatter`: `tickAmount`/`hideOverlappingLabels`
                    // alone left every rotated label on screen, overlapping the
                    // next one.
                    formatter: thinningFormatter(usable.map((point) => point.label), maxLabels),
                },
                axisBorder: {show: false},
                axisTicks: {show: false},
            },
            yaxis: {
                labels: {
                    style: {fontFamily: "IRANSansWeb, Helvetica, sans-serif", fontSize: "12px"},
                    formatter: (value) => toPersianDigits(String(Math.round(value))),
                },
            },
            tooltip: {
                ...base.tooltip,
                y: {formatter: (_value, {dataPointIndex}) => displays[dataPointIndex]},
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
                events: {mounted: (ctx) => forceSolidBars(ctx), updated: (ctx) => forceSolidBars(ctx)},
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
                    style: {fontFamily: "IRANSansWeb, Helvetica, sans-serif", fontSize: "12px"},
                    hideOverlappingLabels: true,
                    trim: true,
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
                        style: {fontFamily: "IRANSansWeb, Helvetica, sans-serif", fontSize: "12px", colors: amountColor},
                        formatter: (value) => toPersianDigits(String(Math.round(value))),
                    },
                },
                {
                    seriesName: seriesNames[1],
                    opposite: true,
                    forceNiceScale: true,
                    labels: {
                        style: {fontFamily: "IRANSansWeb, Helvetica, sans-serif", fontSize: "12px", colors: countColor},
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
                            fontFamily: "IRANSansWeb, Helvetica, sans-serif",
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
                        name: {fontSize: "13px", fontFamily: "IRANSansWeb, Helvetica, sans-serif"},
                        value: {
                            fontSize: "16px",
                            fontWeight: 700,
                            color: ink.text,
                            fontFamily: "IRANSansWeb, Helvetica, sans-serif",
                            formatter: (raw) => toPersianDigits(String(Math.round(raw))) + "٪",
                        },
                        total: {
                            show: true,
                            label: "مجموع",
                            color: ink.muted,
                            fontSize: "13px",
                            fontFamily: "IRANSansWeb, Helvetica, sans-serif",
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

    /**
     * A horizontal bar chart, for comparing named things against each other.
     *
     * Horizontal rather than vertical because the labels are Persian names of
     * arbitrary length — customer names, product names, provinces — and a
     * vertical chart has one column of width for each of them.
     */
    function renderBarChart(chart, empty, items, options = {}) {
        const {ariaLabel = null, limit = 0, sort = true, keepZero = false, colorBy = null} = options;
        if (!chart || !empty) return;
        chartRedraws.set(chart, () => renderBarChart(chart, empty, items, options));

        const palette = chartPalette();
        const usable = items.filter((item) => Number.isFinite(item.value) && item.value >= 0);
        const positive = usable.filter((item) => item.value > 0);
        // A chart of nothing but zeros is an empty chart, whatever keepZero says.
        if (!positive.length) {
            showEmptyChart(chart, empty);
            return;
        }

        let shown = keepZero ? usable.slice() : positive.slice();
        if (sort) shown.sort((a, b) => b.value - a.value);
        if (limit > 0) shown = shown.slice(0, limit);

        // The server formats every value — rial with its separators, or a plain
        // count — so the axis and the tooltip print what it sent rather than
        // Apex's own idea of the number.
        const displays = shown.map((item) => item.display ?? String(item.value));
        // The bar's own "key" and its value, combined into one label drawn
        // past the bar's tip. A separate y-axis column for the category name
        // was the first cut here, and it does not work: Apex reserves that
        // column's own width from an internal text measurement that came out
        // wrong for Persian names in IRANSansWeb on a live chart — a 45px
        // gutter for labels that render 150–160px wide, so every bar's own
        // opening third drew directly *under* its own name. `grid.padding.
        // left` does not move that gutter either; measured with it set to
        // 180px, the bars had not shifted a pixel. Rather than fight an
        // internal calculation this codebase cannot see into, the name joins
        // the value as one string, drawn through the *other* label mechanism
        // — the per-bar dataLabel already proven to land outside the bar's
        // own tip (see the `offsetX`/`textAnchor` reasoning below) — and the
        // y-axis column is turned off outright rather than left half-working.
        const combined = shown.map((item) => `${item.label} — ${item.display ?? String(item.value)}`);
        const LABEL_FONT = "600 12px IRANSansWeb, Helvetica, sans-serif";
        // How far past the longest bar's own tip its label needs the axis to
        // reach — measured in real pixels against this chart's own rendered
        // width, not guessed as a flat percentage. A flat percentage was the
        // first cut here too: it happened to clear a short value-only label,
        // and would not have scaled to a name-and-value string roughly twice
        // as wide. `chart` is the actual container element already in the
        // DOM (`mountApex` below hands it straight to ApexCharts), so its
        // real width is known before a single option is decided from it.
        const CLEARANCE_PX = 56; // the 40px offset below, plus a few px of breathing room
        const widestLabelPx = Math.max(...combined.map((text) => measureTextWidth(text, LABEL_FONT)));
        const neededPx = widestLabelPx + CLEARANCE_PX;
        const plotWidthPx = chart.clientWidth - 24; // grid.padding's own left+right, roughly
        const maxValue = Math.max(...shown.map((item) => item.value));
        const axisMax =
            plotWidthPx > neededPx
                ? (maxValue * plotWidthPx) / (plotWidthPx - neededPx)
                // The container has no real width yet — mounted while still
                // hidden, the one situation `chart.clientWidth` cannot answer
                // for. A generous fixed multiple keeps the chart readable
                // rather than betting on an unmeasurable number; a chart that
                // becomes visible without a resize/redraw is an existing,
                // separate concern (`chartRedraws`), not one this guards.
                : maxValue * 3;
        const colours = shown.map(
            (item, index) =>
                item.color || (colorBy ? colorBy(item, index) : palette[index % palette.length]),
        );
        // Enough room per bar to stay readable, and a floor so a two-bar chart
        // does not become two enormous slabs.
        const height = Math.max(220, shown.length * 44 + 60);
        const base = apexBase(height);

        mountApex(chart, empty, {
            ...base,
            chart: {...base.chart, type: "bar"},
            series: [{name: options.seriesName || "مقدار", data: shown.map((item) => item.value)}],
            colors: colours,
            // Apex fills bars at 0.85 by default, which on a white card turns
            // every one of these into a paler version of the colour that was
            // chosen to mean something. The severity ramp only reads if the
            // colours are the ones it names.
            fill: {opacity: 1},
            // A bar lifts under the pointer rather than only its tooltip
            // appearing — the theme's own charts do this, and on a ranking
            // where the rows are read one after another it is what tells you
            // which row the tooltip belongs to.
            states: {
                hover: {filter: {type: "darken", value: 0.88}},
                active: {filter: {type: "none"}},
            },
            plotOptions: {
                bar: {
                    horizontal: true,
                    // Rounded at the tip only (product-owner request
                    // 2026-09-09: closer to the purchased theme). The theme's
                    // own bar widgets round 5–6px; rounding *both* ends of a
                    // horizontal bar detaches it from its own axis, which is
                    // why this names the end rather than raising the radius.
                    borderRadius: 6,
                    borderRadiusApplication: "end",
                    barHeight: "62%",
                    // Without this every bar takes the first colour, because a
                    // single series is one colour to Apex unless told otherwise.
                    distributed: true,
                    // The value used to print at the *inside* end of the bar —
                    // set in the same colour the bar was filled, on a short bar
                    // that is white-on-white and unreadable, and on a long one
                    // it sits crammed against the tip with nothing behind it
                    // but the bar's own fill. `"top"` draws it just past the
                    // bar's own end instead, outside the coloured shape
                    // entirely, so it reads the same for the shortest bar and
                    // the longest one.
                    dataLabels: {position: "top", maxItems: 100},
                },
            },
            // `distributed` gives each bar its own legend entry, which for a
            // top-ten list is ten redundant swatches beside ten labelled bars.
            legend: {show: false},
            dataLabels: {
                enabled: true,
                formatter: (_value, {dataPointIndex}) => combined[dataPointIndex],
                // 40px, not a token gesture of a few pixels: measured
                // directly against the rendered SVG, Apex places a bar's
                // dataLabel anchor a fixed ~29px *inside* the bar's own tip
                // regardless of `plotOptions.bar.dataLabels.position`, which
                // (for a plain, non-stacked horizontal bar, unlike a stacked
                // one) turned out not to move that anchor at all. 40px of
                // offset is what actually pushes the anchor past the tip
                // with a few pixels to spare, not merely past the point
                // where `position: "top"` stopped helping.
                offsetX: 40,
                // The SVG `text-anchor` axis follows the element's own
                // reading direction, inherited here as RTL from the page —
                // measured both ways rather than assumed from the property
                // name: `"start"` keeps the text's *right* edge at the
                // anchor and grows it leftward, back over the bar; `"end"`
                // keeps the *left* edge at the anchor and grows rightward,
                // away from the bar, which is the one that actually clears
                // it.
                textAnchor: "end",
                style: {
                    fontFamily: "IRANSansWeb, Helvetica, sans-serif",
                    fontSize: "12px",
                    fontWeight: 600,
                    // Drawn outside the bar now, against the card's own
                    // background — so this reads with the page's own ink
                    // colour rather than the white Apex assumes for a label
                    // sitting on top of a filled shape.
                    colors: [chartInk().text],
                },
                dropShadow: {enabled: false},
            },
            xaxis: {
                categories: shown.map((item) => item.label),
                // Deliberately NOT `reversed: true`, which is the obvious way
                // to make these read right-to-left. In the Apex build the theme
                // ships, that option collapses every horizontal bar to zero
                // width — measured: each path came out as `M0.101 ... L0.101`,
                // a vertical line at the origin. The purchased theme never sets
                // it either, and draws its own charts left-to-right in the RTL
                // build. So do these.
                labels: {show: false},
                axisBorder: {show: false},
                axisTicks: {show: false},
                max: axisMax,
            },
            // No separate label column — see the comment above `combined`.
            // The category names still reach the tooltip: Apex reads them
            // from `xaxis.categories` below regardless of whether this axis
            // draws its own text, so hovering a bar still names it.
            yaxis: {
                labels: {show: false},
                axisBorder: {show: false},
                axisTicks: {show: false},
            },
            grid: {...base.grid, xaxis: {lines: {show: true}}, yaxis: {lines: {show: false}}},
            tooltip: {
                ...base.tooltip,
                y: {formatter: (_value, {dataPointIndex}) => displays[dataPointIndex]},
            },
        }, ariaLabel);
    }


    function renderPerformanceChart(prefix, rows) {
        const items = rows.map((row) => ({
            label: row.username,
            value: Number(row.sales_amount),
            display: money(row.sales_amount),
        }));
        const drawn = items.filter((item) => Number.isFinite(item.value) && item.value > 0).length;
        renderBarChart(
            document.getElementById(`${prefix}-performance-chart`),
            document.getElementById(`${prefix}-performance-chart-empty`),
            items,
            {ariaLabel: `نمودار مبلغ فروش تأییدشده برای ${toPersianDigits(String(drawn))} کاربر مجاز`},
        );
    }

    async function loadPerformanceDetails(prefix, userId, username, metric, page = 1) {
        const form = document.getElementById(`${prefix}-performance-filter-form`);
        const section = document.getElementById(`${prefix}-performance-details`);
        const loading = document.getElementById(`${prefix}-details-loading`);
        const errorNode = document.getElementById(`${prefix}-details-error`);
        const empty = document.getElementById(`${prefix}-details-empty`);
        const wrap = document.getElementById(`${prefix}-details-table-wrap`);
        const pager = document.getElementById(`${prefix}-details-pagination`);
        const metricLabel = metric === "customers_created_count" ? "مشتری‌های ثبت‌شده" : "فروش‌های تأییدشده";
        const query = reportQuery(form);
        query.set("metric", metric);
        query.set("page", String(page));
        if (userId) query.set("user_id", String(userId));
        else query.delete("user_id");
        section.hidden = false;
        loading.hidden = false;
        errorNode.hidden = true;
        empty.hidden = true;
        wrap.hidden = true;
        pager.hidden = true;
        document.getElementById(`${prefix}-details-scope`).textContent = `${metricLabel} — ${username || "همه کاربران مجاز"}`;
        try {
            const data = await apiRequest(`/api/v1/reports/user-performance/details/?${query}`);
            const rows = data.results.map((item) => {
                const row = document.createElement("tr");
                [
                    item.record_type === "customer" ? "مشتری" : "فروش",
                    item.title,
                    item.owner,
                    item.product_name || "—",
                    item.amount === null ? "—" : item.amount,
                    displayDate(item.occurred_at),
                ].forEach((value) => appendCell(row, value));
                appendDetailLink(row, item.detail_url);
                return row;
            });
            document.getElementById(`${prefix}-details-body`).replaceChildren(...rows);
            loading.hidden = true;
            if (!rows.length) {
                empty.hidden = false;
                return;
            }
            wrap.hidden = false;
            const previous = document.getElementById(`${prefix}-details-prev`);
            const next = document.getElementById(`${prefix}-details-next`);
            previous.disabled = !data.previous;
            next.disabled = !data.next;
            previous.onclick = () => loadPerformanceDetails(prefix, userId, username, metric, page - 1);
            next.onclick = () => loadPerformanceDetails(prefix, userId, username, metric, page + 1);
            document.getElementById(`${prefix}-details-page-label`).textContent = pageRangeLabel(data, page);
            pager.hidden = !data.previous && !data.next;
        } catch (error) {
            loading.hidden = true;
            errorNode.textContent = errorText(error);
            errorNode.hidden = false;
        }
    }

    function renderPerformanceReport(prefix, report) {
        const panel = document.querySelector(`[data-performance-panel="${prefix}"]`);
        // Two of the four KPIs are amounts and the other two are counts. Sending
        // an amount through `String()` printed it exactly as the API serialises
        // a decimal — `12500000.00` — with no grouping and a fraction the panel
        // shows nowhere else.
        const MONEY_KPIS = new Set(["sales_amount", "average_sale_amount"]);
        Object.entries(report.summary).forEach(([name, value]) => {
            const node = panel.querySelector(`[data-kpi="${name}"]`);
            if (node) node.textContent = MONEY_KPIS.has(name) ? money(value) : String(value);
        });
        const rows = report.results.map((item) => {
            const row = document.createElement("tr");
            // The first three are text and counts; the last two are money and
            // need the same grouping every other table in the panel uses.
            [item.username, item.customers_created_count, item.sales_count]
                .forEach((value) => appendCell(row, value));
            appendMoneyCell(row, item.sales_amount);
            appendMoneyCell(row, item.average_sale_amount);
            const actions = document.createElement("td");
            // Three buttons in one narrow column, unlike every other
            // `row-actions` cell in the app (one or two, which the
            // `margin-inline-start` rule in dolphin.css handles fine) —
            // narrow enough that they wrapped onto their own lines with no
            // gap between them. `flex-wrap` first tried here fixed the gap
            // but not the wrapping itself: three stacked lines multiplied
            // across every `<td>` in the row (they all share one height),
            // and the whole table grew a few hundred pixels of dead space
            // per row for it. `flex-nowrap` keeps the three side by side, as
            // asked, and any overflow is exactly what `.table-responsive`
            // (this table already sits in one) is for — a horizontal
            // scrollbar the panel already uses on nine-column tables.
            actions.className = "row-actions d-flex flex-nowrap gap-2";
            const profileLink = document.createElement("a");
            profileLink.className = "btn btn-sm btn-light";
            profileLink.href = `/users/${item.user_id}/profile/`;
            profileLink.textContent = "پروفایل";
            actions.appendChild(profileLink);
            [
                ["customers_created_count", "مشتری‌ها", item.customers_created_count],
                ["sales_count", "فروش‌ها", item.sales_count],
            ].forEach(([metric, label, count]) => {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "btn btn-sm btn-light";
                button.textContent = label;
                button.disabled = Number(count) === 0;
                button.addEventListener("click", () => loadPerformanceDetails(prefix, item.user_id, item.username, metric));
                actions.appendChild(button);
            });
            row.appendChild(actions);
            return row;
        });
        document.getElementById(`${prefix}-performance-table-body`).replaceChildren(...rows);
        // The content wrapper has to become visible *before* the chart mounts
        // inside it, not after: ApexCharts measures its container's real width
        // at render time, and a container still under `hidden` (`display:none`)
        // measures zero — the chart then draws with `width: 0` and stays that
        // way forever, since `animations: {enabled: false}` (set for a
        // different, related reason above) means nothing ever retries the
        // measurement. Reproduced live: a fresh page load raced the fetch
        // against layout and mounted the chart at 0×220 while this div was
        // still hidden, leaving the whole chart panel blank with no error.
        const hasActivity = Number(report.summary.customers_created_count) > 0 || Number(report.summary.sales_count) > 0;
        document.getElementById(`${prefix}-performance-empty`).hidden = hasActivity;
        document.getElementById(`${prefix}-performance-content`).hidden = false;
        renderPerformanceChart(prefix, report.results);
        panel.querySelectorAll("[data-performance-detail]").forEach((button) => {
            const metric = button.dataset.performanceDetail;
            button.disabled = Number(report.summary[metric === "customers_created_count" ? metric : "sales_count"]) === 0;
        });
    }

    async function setupPerformancePanel(prefix) {
        const form = document.getElementById(`${prefix}-performance-filter-form`);
        if (!form) return;
        const now = new Date();
        const start = new Date(now.getFullYear(), now.getMonth(), 1);
        document.getElementById(`${prefix}-period-start`).value = localDateTimeValue(start);
        document.getElementById(`${prefix}-period-end`).value = localDateTimeValue(new Date(now.getTime() + 60000));
        const exportLink = document.getElementById(`${prefix}-performance-xlsx`);
        const updateExport = () => { exportLink.href = `/api/v1/exports/user-performance.xlsx?${reportQuery(form)}`; };
        form.addEventListener("input", updateExport);
        form.addEventListener("change", updateExport);
        updateExport();
        form.closest("[data-performance-panel]").querySelectorAll("[data-performance-detail]").forEach((button) => {
            button.addEventListener("click", () => {
                const userSelect = document.getElementById(`${prefix}-user`);
                const userId = userSelect?.value || null;
                const username = userId ? userSelect.options[userSelect.selectedIndex].textContent : "همه کاربران مجاز";
                loadPerformanceDetails(prefix, userId, username, button.dataset.performanceDetail);
            });
        });
        let userOptionsLoaded = false;
        const load = async () => {
            clearMessages(form);
            const loading = document.getElementById(`${prefix}-performance-loading`);
            const errorNode = document.getElementById(`${prefix}-performance-error`);
            const content = document.getElementById(`${prefix}-performance-content`);
            // Not `form.querySelector(...)`: the submit button moved out of
            // the form and into the panel's header (2026-09-08, "بالا سمت چپ
            // باکس" — `performance_panel.inc`), wired back only through its
            // own `form="..."` HTML attribute, so it is a sibling of `<form>`
            // now, not a descendant. Found the same way the browser itself
            // associates it with the form it submits.
            const button = document.querySelector(`button[type="submit"][form="${form.id}"]`);
            loading.hidden = false;
            errorNode.hidden = true;
            content.hidden = true;
            document.getElementById(`${prefix}-performance-details`).hidden = true;
            button.disabled = true;
            const query = reportQuery(form);
            exportLink.href = `/api/v1/exports/user-performance.xlsx?${query}`;
            try {
                const report = await apiRequest(`/api/v1/reports/user-performance/?${query}`);
                const userSelect = document.getElementById(`${prefix}-user`);
                if (userSelect && !userOptionsLoaded) {
                    fillSelect(
                        userSelect,
                        report.results.map((row) => ({id: row.user_id, username: row.username})),
                        (user) => user.username,
                        "همه کاربران مجاز",
                    );
                    userOptionsLoaded = true;
                }
                renderPerformanceReport(prefix, report);
            } catch (error) {
                errorNode.textContent = errorText(error);
                errorNode.hidden = false;
                showError(error, form);
            } finally {
                loading.hidden = true;
                button.disabled = false;
            }
        };
        // Claim the submit event before any awaited load. Without this the
        // filter button performs a native form submission during the first
        // moments of the page, which reloads instead of filtering.
        form.addEventListener("submit", (event) => { event.preventDefault(); load(); });
        try {
            const products = await loadAllPages("/api/v1/products/?ordering=name");
            fillSelect(document.getElementById(`${prefix}-product`), products, (product) => product.name, "همه محصولات مجاز");
        } catch (error) {
            showError(error);
        }
        await load();
    }

    async function setupUserPerformance() {
        await setupPerformancePanel("report");
    }

    /**
     * One seller's profile page: identity is already server-rendered — this
     * only fills the parts that come from the reports API, locked to the one
     * user the URL names via the hidden `user_id` field `reportQuery` already
     * knows to read. The backend re-checks that scope on every request this
     * makes; nothing here is the authorization, only the display.
     */
    async function setupSellerProfile() {
        const section = document.getElementById("user-profile-content");
        if (!section) return;
        const targetUserId = section.dataset.targetUserId;
        const targetUsername = section.dataset.targetUsername || "";

        const form = document.getElementById("profile-performance-filter-form");
        const now = new Date();
        const start = new Date(now.getFullYear(), now.getMonth(), 1);
        document.getElementById("profile-period-start").value = localDateTimeValue(start);
        document.getElementById("profile-period-end").value = localDateTimeValue(new Date(now.getTime() + 60000));

        async function loadPerformance() {
            clearMessages(form);
            const loading = document.getElementById("profile-performance-loading");
            const errorNode = document.getElementById("profile-performance-error");
            loading.hidden = false;
            errorNode.hidden = true;
            document.getElementById("profile-performance-details").hidden = true;
            const query = reportQuery(form);
            try {
                const report = await apiRequest(`/api/v1/reports/user-performance/?${query}`);
                const MONEY_KPIS = new Set(["sales_amount", "average_sale_amount"]);
                Object.entries(report.summary).forEach(([name, value]) => {
                    const node = section.querySelector(`[data-kpi="${name}"]`);
                    if (node) node.textContent = MONEY_KPIS.has(name) ? money(value) : toPersianDigits(String(value));
                });
                section.querySelectorAll("[data-performance-detail]").forEach((button) => {
                    const metric = button.dataset.performanceDetail;
                    const count = report.summary[metric === "customers_created_count" ? metric : "sales_count"];
                    button.disabled = Number(count) === 0;
                });
            } catch (error) {
                errorNode.textContent = errorText(error);
                errorNode.hidden = false;
                showError(error, form);
            } finally {
                loading.hidden = true;
            }
        }
        form.addEventListener("submit", (event) => { event.preventDefault(); loadPerformance(); });

        let granularity = "month";
        async function loadTrend() {
            const chart = document.getElementById("profile-trend-chart");
            const empty = document.getElementById("profile-trend-chart-empty");
            try {
                const query = new URLSearchParams({user_id: targetUserId, granularity});
                const report = await apiRequest(`/api/v1/reports/user-performance/trend/?${query}`);
                const points = report.results.map((row) => ({
                    label: displayDay(row.bucket),
                    value: Number(row.sales_amount),
                    display: money(row.sales_amount),
                }));
                renderAreaChart(chart, empty, points, {
                    ariaLabel: "نمودار روند فروش تأییدشده",
                    seriesName: "مبلغ فروش تأییدشده",
                });
            } catch (error) {
                if (chart) chart.hidden = true;
                if (empty) {
                    empty.textContent = "نمودار روند در دسترس نیست.";
                    empty.hidden = false;
                }
            }
        }
        document.querySelectorAll("[data-trend-range]").forEach((button) => {
            button.addEventListener("click", () => {
                granularity = button.dataset.trendRange;
                document.querySelectorAll("[data-trend-range]").forEach((other) => {
                    const active = other === button;
                    other.classList.toggle("btn-primary", active);
                    other.classList.toggle("btn-light", !active);
                    other.setAttribute("aria-pressed", String(active));
                });
                loadTrend();
            });
        });

        section.querySelectorAll("[data-performance-detail]").forEach((button) => {
            button.addEventListener("click", () => {
                loadPerformanceDetails("profile", targetUserId, targetUsername, button.dataset.performanceDetail);
            });
        });

        await Promise.all([loadPerformance(), loadTrend()]);
    }

    function activityLogRow(item) {
        const row = document.createElement("tr");
        appendCell(row, item.operation_display || item.operation);
        appendCell(row, item.object_type);
        appendCell(row, item.object_id);
        appendCell(row, ROLE_LABELS[item.actor_role_snapshot] || item.actor_role_snapshot);
        appendCell(row, displayDate(item.created_at));
        appendDetailLink(row, `/activity-logs/${item.id}/`);
        return row;
    }

    function setupActivityLogs() {
        const form = document.getElementById("activity-log-search-form");
        setupListFilter("activity-log");
        const controller = setupPagedList({
            key: "activity-logs",
            form,
            search: document.getElementById("activity-log-search"),
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page), ordering: document.getElementById("activity-log-ordering").value});
                const search = document.getElementById("activity-log-search").value.trim();
                if (search) query.set("search", search);
                return `/api/v1/activity-logs/?${query}`;
            },
            renderRow: activityLogRow,
        });
        controller.load();
    }

    async function setupActivityLogDetail() {
        const id = document.body.dataset.activityLogId;
        const loading = document.getElementById("activity-log-detail-loading");
        const content = document.getElementById("activity-log-detail-content");
        try {
            const item = await apiRequest(`/api/v1/activity-logs/${id}/`);
            document.getElementById("activity-operation").value = item.operation_display || item.operation;
            document.getElementById("activity-object-type").value = item.object_type;
            document.getElementById("activity-object-id").value = item.object_id || "";
            document.getElementById("activity-actor").value = item.actor || "";
            document.getElementById("activity-actor-role").value = ROLE_LABELS[item.actor_role_snapshot] || item.actor_role_snapshot;
            document.getElementById("activity-object-role").value = ROLE_LABELS[item.object_role_snapshot] || item.object_role_snapshot;
            document.getElementById("activity-request-id").value = item.request_id || "";
            document.getElementById("activity-ip").value = item.ip_address || "";
            document.getElementById("activity-created-at").value = displayDate(item.created_at);
            document.getElementById("activity-changes").textContent = JSON.stringify(item.safe_changes, null, 2);
            loading.hidden = true;
            content.hidden = false;
        } catch (error) {
            loading.hidden = true;
            showError(error);
        }
    }


    // --- Inventory, billing, and financial-report pages ----------------------

    const DOCUMENT_STATUS_TEXT = Object.freeze({
        draft: "پیش‌نویس",
        sent: "ارسال‌شده",
        accepted: "پذیرفته‌شده",
        rejected: "ردشده",
        expired: "منقضی‌شده",
        cancelled: "لغوشده",
        confirmed: "تأییدشده",
        fulfilled: "تحویل‌شده",
        issued: "صادرشده",
    });
    const SETTLEMENT_TEXT = Object.freeze({
        unpaid: "تسویه‌نشده",
        partially_paid: "تسویه جزئی",
        paid: "تسویه کامل",
    });
    const MOVEMENT_TEXT = Object.freeze({
        opening: "موجودی اول دوره",
        purchase: "رسید خرید",
        sale: "خروج فروش",
        return_in: "برگشت از مشتری",
        return_out: "برگشت به تأمین‌کننده",
        adjustment_in: "اصلاح افزایشی",
        adjustment_out: "اصلاح کاهشی",
        transfer_in: "انتقال ورودی",
        transfer_out: "انتقال خروجی",
    });
    const PAYMENT_METHOD_TEXT = Object.freeze({
        cash: "نقدی",
        card: "کارت‌خوان",
        bank_transfer: "حواله بانکی",
        cheque: "چک",
    });
    const PAYMENT_DIRECTION_TEXT = Object.freeze({
        receipt: "دریافتی",
        disbursement: "پرداختی",
    });
    const PAYMENT_STATUS_TEXT = Object.freeze({
        pending: "در انتظار وصول",
        confirmed: "تأییدشده",
        cancelled: "ابطال‌شده",
    });
    // وضعیت — one of the two axes a cheque has since 1.3.0. The other, حالت,
    // is a yes/no and is rendered by CHEQUE_REGISTRATION_TEXT below.
    //: The server sends `invoice_type_display` already translated; this is the
    //: fallback for a row that predates it, and the source for the filter's own
    //: two options.
    const INVOICE_TYPE_TEXT = Object.freeze({
        official: "رسمی",
        unofficial: "غیررسمی",
    });

    const CHEQUE_STATUS_TEXT = Object.freeze({
        pending: "در انتظار",
        cleared: "وصول شده",
        bounced: "برگشت",
        spent: "خرج شده",
    });
    const CHEQUE_REGISTRATION_TEXT = Object.freeze({
        true: "ثبت شده",
        false: "ثبت نشده",
    });
    // Mirrors billing.models.Cheque.TRANSITIONS. Display only — the server
    // refuses a jump that is not in its own table regardless of what is offered
    // here, so a drift in this copy narrows the menu, it never widens access.
    //: Mirrors `Cheque.TRANSITIONS` on the server, which refuses anything this
    //: lets through anyway — this only spares the trip. Every state can return
    //: to «در انتظار» so a wrong button on a row can be corrected.
    const CHEQUE_TRANSITIONS = Object.freeze({
        pending: ["cleared", "bounced", "spent"],
        cleared: ["pending"],
        bounced: ["pending"],
        spent: ["pending"],
    });
    // Mirrors billing.models.Order.TRANSITIONS. Display only — the server
    // refuses a jump that is not in its own table regardless of what is offered
    // here, so a drift in this copy narrows the menu, it never widens access.
    // The order board's own dragTo restriction (setupOrderBoard) reads this
    // same table, so a drop this omits is one jKanban itself already refuses
    // before the request is ever sent.
    const ORDER_TRANSITIONS = Object.freeze({
        draft: ["confirmed", "cancelled"],
        confirmed: ["fulfilled", "cancelled"],
        fulfilled: [],
        cancelled: [],
    });
    const INSTALLMENT_STATUS_TEXT = Object.freeze({
        pending: "پرداخت‌نشده",
        partially_paid: "پرداخت جزئی",
        paid: "پرداخت‌شده",
        cancelled: "لغوشده",
    });
    const LEDGER_ENTRY_TEXT = Object.freeze({
        opening_balance: "مانده اول دوره",
        invoice_issued: "صدور فاکتور",
        invoice_cancelled: "ابطال فاکتور",
        payment_received: "دریافت وجه",
        payment_made: "پرداخت به مشتری",
        payment_cancelled: "ابطال دریافت",
        adjustment_debit: "اصلاح بدهکار",
        adjustment_credit: "اصلاح بستانکار",
    });

    /**
     * What a pager says: which records are on screen, out of how many.
     *
     * "صفحه ۲" alone never told an operator whether they were looking at 12
     * customers or 12 of 3,400. The API already returns `count`, so the range
     * is derived rather than guessed, and a page whose size is unknown falls
     * back to the page number alone instead of inventing a range.
     */
    function pageRangeLabel(data, page, pageSize = 25) {
        const total = Number(data.count);
        if (!Number.isFinite(total)) return `صفحه ${toPersianDigits(String(page))}`;
        if (total === 0) return "بدون رکورد";
        const first = (page - 1) * pageSize + 1;
        const last = Math.min(page * pageSize, total);
        return `${toPersianDigits(String(first))} تا ${toPersianDigits(String(last))} از ${toPersianDigits(String(total))}`;
    }

    function labelled(map, value) {
        return map[value] || value || "—";
    }

    /**
     * Which theme accent a status wears.
     *
     * A document list is scanned, not read: an operator looking for the one
     * cancelled invoice among fifty should find it by colour, not by reading
     * every row. The meaning stays the backend's — this only decides how the
     * value already sent is painted, and an unknown value falls back to a
     * neutral badge rather than disappearing.
     */
    const STATUS_ACCENTS = Object.freeze({
        // Commercial documents.
        draft: "secondary",
        sent: "info",
        accepted: "success",
        confirmed: "success",
        issued: "success",
        fulfilled: "primary",
        rejected: "danger",
        cancelled: "danger",
        expired: "warning",
        // Settlement.
        unpaid: "danger",
        partially_paid: "warning",
        paid: "success",
        // Payments and cheques.
        pending: "warning",
        registered: "info",
        cleared: "success",
        bounced: "danger",
        returned: "warning",
        // Campaign and target audience.
        completed: "success",
        lead: "primary",
        engaged: "warning",
        customer: "success",
        failed: "danger",
        // Inventory movement direction.
        opening: "info",
        purchase: "success",
        sale: "primary",
        return_in: "success",
        return_out: "warning",
        adjustment_in: "success",
        adjustment_out: "warning",
        transfer_in: "info",
        transfer_out: "info",
    });

    /** A status rendered as the theme's badge, ready to append to a row. */
    function statusBadge(map, value) {
        const badge = document.createElement("span");
        badge.className = `badge badge-light-${STATUS_ACCENTS[value] || "secondary"}`;
        badge.textContent = labelled(map, value);
        return badge;
    }

    /** Append a status cell carrying that badge. */
    function appendStatusBadgeCell(row, map, value) {
        const cell = document.createElement("td");
        cell.append(statusBadge(map, value));
        row.append(cell);
        return cell;
    }

    // Group thousands by walking the string rather than going through Number:
    // an amount is authoritative as sent, and a float round-trip could move the
    // last digit of a large total.
    /**
     * A stored amount as the panel shows it: grouped, in rial, no decimals.
     *
     * Rial has no sub-unit in daily use, so a trailing `.00` on every figure is
     * noise that makes an eight-digit total harder to scan, not more precise.
     * The fraction is dropped by rounding half-up on the digit string rather
     * than through `Number`, because the amount is authoritative as stored and
     * a float round-trip could move its last digit.
     *
     * The stored value keeps its two decimals — this is display only.
     */
    function money(value, {withCurrency = true} = {}) {
        if (value === null || value === undefined || value === "") return "—";
        const text = String(value).trim();
        const negative = text.startsWith("-");
        const [rawWhole, fraction = ""] = (negative ? text.slice(1) : text).split(".");
        if (!/^\d+$/.test(rawWhole)) return String(value);

        // Ceiling, not half-up: any fraction at all rounds the whole number up.
        //
        // The product owner's rule is that the rial figure must never be
        // reported lower than the amount actually owed, and that no decimal is
        // ever shown. Half-up would round 1.4 down to 1 and quietly understate
        // it; rounding up can overstate by at most one rial, which is the
        // direction chosen deliberately.
        //
        // Carried through the digit string with BigInt rather than through a
        // float, because a rial total can exceed what a double represents
        // exactly.
        let whole = rawWhole;
        if (fraction && /[1-9]/.test(fraction)) {
            whole = (BigInt(whole) + 1n).toString();
        }
        const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, "،");
        const body = negative && grouped !== "0" ? `‏-${grouped}` : grouped;
        // Persian digits, same as every date and count elsewhere in the
        // panel — found missing in the 1.7.13 debug sweep, where a rial
        // figure was the one place still reading in Latin numerals next to
        // Jalali dates and Persian-digit counts on the same page. `dir:
        // ltr` on the cell (appendMoneyCell) keeps the digit order left to
        // right regardless of script, so this is display-only: the grouping
        // and rounding above are untouched, and moneyValue() below still
        // reads Persian digits back into what the API expects.
        const shown = withCurrency ? `${body} ریال` : body;
        return toPersianDigits(shown);
    }

    /** The same grouping for a text input, without the currency word. */
    function moneyDigits(value) {
        const shown = money(value, {withCurrency: false});
        return shown === "—" ? "" : shown;
    }

    /** Strip grouping and Persian digits back to what the API expects. */
    function moneyValue(text) {
        const latin = toLatinDigits(String(text || ""));
        return latin.replace(/[،,\s]/g, "").trim();
    }

    /**
     * Group a price field as it is typed, so nobody types separators by hand.
     *
     * Applied to `[data-money-input]`. The field is `type="text"` rather than
     * `type="number"`, because a number input refuses a grouped value outright.
     * `moneyValue` turns it back into digits on submit.
     */
    function setupMoneyInputs(root = document) {
        root.querySelectorAll("[data-money-input]").forEach((field) => {
            if (field.dataset.moneyBound === "1") return;
            field.dataset.moneyBound = "1";
            field.setAttribute("inputmode", "numeric");
            field.addEventListener("input", () => {
                const raw = moneyValue(field.value);
                const [whole, ...rest] = raw.split(".");
                const digits = whole.replace(/\D/g, "");
                const grouped = digits ? moneyDigits(digits) : "";
                // A decimal point that has been typed is kept, and only the
                // whole part is grouped. Dropping the point as it is typed
                // would leave the digits behind it: `15.00` became `1500`,
                // a hundredfold error on a field an operator types by hand.
                // The fraction is dropped on display and at submit instead,
                // where nothing can be mistaken for a further digit.
                field.value = rest.length
                    ? `${grouped}.${rest.join("").replace(/\D/g, "")}`
                    : grouped;
            });
        });
    }

    function appendMoneyCell(row, value) {
        const cell = appendCell(row, money(value));
        cell.dir = "ltr";
        return cell;
    }

    function appendActionLinks(row, links) {
        const cell = document.createElement("td");
        cell.className = "row-actions";
        links.forEach(([href, label]) => {
            const link = document.createElement("a");
            link.className = "btn btn-sm btn-light";
            link.href = href;
            link.textContent = label;
            cell.appendChild(link);
        });
        row.appendChild(cell);
        return cell;
    }

    function setSelectValue(select, value) {
        select.value = value === null || value === undefined ? "" : String(value);
    }

    /**
     * A money field's value as digits, or null when it was left empty.
     *
     * Money fields are grouped text, so `Number()` on them would read `1،200`
     * as NaN. The digit string goes to the API as text and is parsed there as
     * a Decimal — turning it into a JS number first would lose precision on
     * large rial amounts.
     */
    function moneyOrNull(value) {
        const digits = moneyValue(value);
        return digits === "" ? null : digits;
    }

    function numberOrNull(value) {
        const text = String(value ?? "").trim();
        return text === "" ? null : Number(text);
    }

    function textOrNull(value) {
        const text = String(value ?? "").trim();
        return text === "" ? null : text;
    }

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
            select.dispatchEvent(new Event("change", {bubbles: true}));
            close();
        }

        function render(term) {
            const needle = term.trim().toLowerCase();
            const matches = options().filter((option) =>
                option.textContent.toLowerCase().includes(needle),
            );
            list.replaceChildren();
            if (!matches.length) {
                const empty = document.createElement("li");
                empty.className = "searchable-select-empty";
                empty.textContent = select.options.length > 1 ? "چیزی پیدا نشد." : "در حال دریافت…";
                list.append(empty);
            } else {
                matches.slice(0, 50).forEach((option, index) => {
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
                    const matches = options().filter((option) =>
                        option.textContent.toLowerCase().includes(input.value.trim().toLowerCase()),
                    );
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

    function setupSearchableSelects(root = document) {
        root.querySelectorAll("[data-searchable-select]").forEach((block) => {
            if (block.dataset.searchableBound === "1") return;
            block.dataset.searchableBound = "1";
            setupSearchableSelect(block);
        });
    }

    async function loadCustomerOptions(select, emptyLabel) {
        if (!select) return [];
        const rows = await loadAllPages("/api/v1/customers/?ordering=full_name");
        fillSelect(select, rows, (row) => row.full_name, emptyLabel);
        return rows;
    }

    async function loadProductOptions(select, emptyLabel) {
        if (!select) return [];
        const rows = await loadAllPages("/api/v1/products/?is_active=true&ordering=name");
        fillSelect(select, rows, (row) => `${row.name} (${row.sku})`, emptyLabel);
        return rows;
    }

    async function loadWarehouseOptions(select, emptyLabel) {
        if (!select) return [];
        const rows = await loadAllPages("/api/v1/warehouses/?is_active=true&ordering=name");
        fillSelect(select, rows, (row) => row.name, emptyLabel);
        return rows;
    }

    // --- Warehouses ---------------------------------------------------------

    function warehouseRow(warehouse) {
        const row = document.createElement("tr");
        appendCell(row, warehouse.code);
        appendCell(row, warehouse.name);
        appendCell(row, warehouse.address);
        appendCell(row, warehouse.is_default ? "بله" : "خیر");
        appendStatusCell(row, (warehouse.is_active));
        appendDetailLink(row, `/warehouses/${warehouse.id}/`);
        return row;
    }

    function setupWarehouses() {
        const form = document.getElementById("warehouse-search-form");
        setupListFilter("warehouse");
        const dialog = document.getElementById("create-warehouse-dialog");
        if (dialog) {
            const createForm = document.getElementById("create-warehouse-form");
            function renderReview() {
                renderWizardReview(document.getElementById("create-warehouse-review"), [
                    ["کد انبار", document.getElementById("create-warehouse-code").value],
                    ["نام", document.getElementById("create-warehouse-name").value],
                    ["انبار پیش‌فرض", selectedOptionText(document.getElementById("create-warehouse-default"))],
                    ["نشانی", document.getElementById("create-warehouse-address").value || "—"],
                ]);
            }
            const wizard = setupWizard(dialog, {onReachLastStep: renderReview});
            document.getElementById("open-create-warehouse").addEventListener("click", () => {
                createForm.reset();
                clearMessages(createForm);
                wizard?.goFirst();
                dialog.showModal();
            });
            dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
            createForm.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(createForm, async () => {
                    const payload = formPayload(createForm, ["code", "name", "address"]);
                    payload.is_default = new FormData(createForm).get("is_default") === "true";
                    const warehouse = await apiRequest(createForm.action, {method: "POST", body: payload});
                    window.location.assign(`/warehouses/${warehouse.id}/`);
                });
            });
        }
        const controller = setupPagedList({
            key: "warehouses",
            form,
            search: document.getElementById("warehouse-search"),
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page)});
                const search = document.getElementById("warehouse-search").value.trim();
                if (search) query.set("search", search);
                const isActive = document.getElementById("warehouse-status-filter").value;
                if (isActive) query.set("is_active", isActive);
                query.set("ordering", document.getElementById("warehouse-ordering").value);
                return `/api/v1/warehouses/?${query}`;
            },
            renderRow: warehouseRow,
        });
        controller.load();
    }

    function fillWarehouse(warehouse) {
        document.getElementById("edit-warehouse-code").value = warehouse.code;
        document.getElementById("edit-warehouse-name").value = warehouse.name;
        setSelectValue(document.getElementById("edit-warehouse-default"), String(warehouse.is_default));
        document.getElementById("edit-warehouse-address").value = warehouse.address || "";
        document.getElementById("warehouse-status").value = statusText(warehouse.is_active);
        document.getElementById("warehouse-created-by").value = warehouse.created_by_display || warehouse.created_by;
        document.getElementById("warehouse-updated-by").value = warehouse.updated_by_display || warehouse.updated_by;
        const toggle = document.getElementById("toggle-warehouse");
        if (toggle) {
            toggle.textContent = warehouse.is_active ? "غیرفعال کردن انبار" : "فعال کردن دوباره انبار";
            toggle.classList.toggle("btn-danger", warehouse.is_active);
        }
    }

    async function setupWarehouseDetail() {
        const warehouseId = document.body.dataset.warehouseId;
        const endpoint = `/api/v1/warehouses/${warehouseId}/`;
        const loading = document.getElementById("warehouse-detail-loading");
        const content = document.getElementById("warehouse-detail-content");
        const dangerZone = document.getElementById("warehouse-danger-zone");
        let warehouse;
        try {
            warehouse = await apiRequest(endpoint);
            fillWarehouse(warehouse);
            loading.hidden = true;
            content.hidden = false;
            if (dangerZone) dangerZone.hidden = false;
        } catch (error) {
            loading.hidden = true;
            showError(error);
            return;
        }
        const form = document.getElementById("edit-warehouse-form");
        if (form.querySelector("button[type='submit']")) {
            form.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(form, async () => {
                    const payload = formPayload(form, ["name", "address"]);
                    payload.is_default = new FormData(form).get("is_default") === "true";
                    warehouse = await apiRequest(endpoint, {method: "PATCH", body: payload});
                    fillWarehouse(warehouse);
                    globalMessage("انبار ذخیره شد.", true);
                });
            });
        }
        const toggle = document.getElementById("toggle-warehouse");
        toggle?.addEventListener("click", async () => {
            const action = warehouse.is_active ? "deactivate" : "reactivate";
            const prompt = warehouse.is_active ? "این انبار غیرفعال شود؟" : "این انبار دوباره فعال شود؟";
            if (!window.confirm(prompt)) return;
            toggle.disabled = true;
            try {
                warehouse = await apiRequest(`${endpoint}${action}/`, {method: "POST"});
                fillWarehouse(warehouse);
                globalMessage(warehouse.is_active ? "انبار فعال شد." : "انبار غیرفعال شد.", true);
            } catch (error) {
                showError(error);
            } finally {
                toggle.disabled = false;
            }
        });
    }

    // --- Stock levels and movements -----------------------------------------

    function stockItemRow(item) {
        const row = document.createElement("tr");
        appendCell(row, item.warehouse_name);
        appendCell(row, item.product_sku).dir = "ltr";
        appendCell(row, item.product_name);
        appendCell(row, item.quantity);
        appendMoneyCell(row, item.average_cost);
        appendMoneyCell(row, item.stock_value);
        appendCell(row, displayDate(item.last_movement_at));
        return row;
    }

    async function setupStockLevels() {
        const form = document.getElementById("stock-search-form");
        setupListFilter("stock");
        const movementDialog = document.getElementById("create-movement-dialog");
        const transferDialog = document.getElementById("transfer-stock-dialog");
        let controller = null;

        // Handlers are attached before any awaited load so a click landing in
        // the first moments of the page is not silently discarded.
        if (movementDialog) {
            const createForm = document.getElementById("create-movement-form");
            function renderMovementReview() {
                renderWizardReview(document.getElementById("create-movement-review"), [
                    ["انبار", selectedOptionText(document.getElementById("create-movement-warehouse"))],
                    ["کالا", selectedOptionText(document.getElementById("create-movement-product"))],
                    ["نوع حرکت", selectedOptionText(document.getElementById("create-movement-type"))],
                    ["تعداد", createForm.quantity.value || "—"],
                    ["بهای واحد", createForm.unit_cost.value || "—"],
                    ["یادداشت", createForm.notes.value || "—"],
                ]);
            }
            const movementWizard = setupWizard(movementDialog, {onReachLastStep: renderMovementReview});
            document.getElementById("open-create-movement").addEventListener("click", () => {
                createForm.reset();
                clearMessages(createForm);
                movementWizard?.goFirst();
                movementDialog.showModal();
            });
            movementDialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => movementDialog.close()));
            createForm.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(createForm, async () => {
                    const data = new FormData(createForm);
                    const payload = {
                        warehouse: Number(data.get("warehouse")),
                        product: Number(data.get("product")),
                        movement_type: String(data.get("movement_type")),
                        quantity: Number(data.get("quantity")),
                        notes: String(data.get("notes") || ""),
                    };
                    const cost = moneyOrNull(data.get("unit_cost"));
                    if (cost !== null) payload.unit_cost = cost;
                    await apiRequest(createForm.action, {method: "POST", body: payload});
                    movementDialog.close();
                    globalMessage("حرکت انبار ثبت شد.", true);
                    controller?.load();
                });
            });
        }
        if (transferDialog) {
            const transferForm = document.getElementById("transfer-stock-form");
            function renderTransferReview() {
                renderWizardReview(document.getElementById("transfer-stock-review"), [
                    ["از انبار", selectedOptionText(document.getElementById("transfer-from-warehouse"))],
                    ["به انبار", selectedOptionText(document.getElementById("transfer-to-warehouse"))],
                    ["کالا", selectedOptionText(document.getElementById("transfer-product"))],
                    ["تعداد", transferForm.quantity.value || "—"],
                    ["یادداشت", transferForm.notes.value || "—"],
                ]);
            }
            const transferWizard = setupWizard(transferDialog, {onReachLastStep: renderTransferReview});
            document.getElementById("open-transfer-stock").addEventListener("click", () => {
                transferForm.reset();
                clearMessages(transferForm);
                transferWizard?.goFirst();
                transferDialog.showModal();
            });
            transferDialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => transferDialog.close()));
            transferForm.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(transferForm, async () => {
                    const data = new FormData(transferForm);
                    await apiRequest(transferForm.action, {method: "POST", body: {
                        from_warehouse: Number(data.get("from_warehouse")),
                        to_warehouse: Number(data.get("to_warehouse")),
                        product: Number(data.get("product")),
                        quantity: Number(data.get("quantity")),
                        notes: String(data.get("notes") || ""),
                    }});
                    transferDialog.close();
                    globalMessage("انتقال بین انبار ثبت شد.", true);
                    controller?.load();
                });
            });
        }

        try {
            const [warehouses] = await Promise.all([
                loadWarehouseOptions(document.getElementById("stock-warehouse-filter"), "همه انبارها"),
                loadProductOptions(document.getElementById("create-movement-product"), "یک کالا انتخاب کنید"),
                loadProductOptions(document.getElementById("transfer-product"), "یک کالا انتخاب کنید"),
            ]);
            [
                ["create-movement-warehouse", "یک انبار انتخاب کنید"],
                ["transfer-from-warehouse", "انبار مبدأ"],
                ["transfer-to-warehouse", "انبار مقصد"],
            ].forEach(([id, emptyLabel]) => {
                const select = document.getElementById(id);
                if (select) fillSelect(select, warehouses, (row) => row.name, emptyLabel);
            });
        } catch (error) {
            showError(error);
        }

        controller = setupPagedList({
            key: "stock-items",
            form,
            search: document.getElementById("stock-search"),
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page)});
                const search = document.getElementById("stock-search").value.trim();
                if (search) query.set("search", search);
                const warehouse = document.getElementById("stock-warehouse-filter").value;
                if (warehouse) query.set("warehouse", warehouse);
                const threshold = document.getElementById("stock-threshold").value.trim();
                if (threshold) query.set("below_or_equal", threshold);
                query.set("ordering", document.getElementById("stock-ordering").value);
                return `/api/v1/stock-items/?${query}`;
            },
            renderRow: stockItemRow,
        });
        controller.load();
    }

    function stockMovementRow(movement) {
        const row = document.createElement("tr");
        appendCell(row, displayDate(movement.occurred_at));
        appendCell(row, movement.warehouse_name);
        appendCell(row, movement.product_name);
        appendStatusBadgeCell(row, MOVEMENT_TEXT, movement.movement_type);
        appendCell(row, movement.quantity);
        appendMoneyCell(row, movement.unit_cost);
        appendCell(row, movement.resulting_quantity);
        appendCell(row, movement.reference_number || "—").dir = "ltr";
        appendCell(row, movement.created_by_display || movement.created_by);
        return row;
    }

    async function setupStockMovements() {
        const form = document.getElementById("stock-movement-search-form");
        setupListFilter("stock-movement");
        try {
            await loadWarehouseOptions(document.getElementById("stock-movement-warehouse"), "همه انبارها");
        } catch (error) {
            showError(error);
        }
        const controller = setupPagedList({
            key: "stock-movements",
            form,
            search: document.getElementById("stock-movement-search"),
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page)});
                const search = document.getElementById("stock-movement-search").value.trim();
                if (search) query.set("search", search);
                const warehouse = document.getElementById("stock-movement-warehouse").value;
                if (warehouse) query.set("warehouse", warehouse);
                const movementType = document.getElementById("stock-movement-type").value;
                if (movementType) query.set("movement_type", movementType);
                query.set("ordering", document.getElementById("stock-movement-ordering").value);
                return `/api/v1/stock-movements/?${query}`;
            },
            renderRow: stockMovementRow,
        });
        controller.load();
    }

    // --- Commercial documents -----------------------------------------------

    function documentListRow(document_, columns, href) {
        const row = document.createElement("tr");
        columns.forEach((render) => render(row, document_));
        appendDetailLink(row, href(document_));
        return row;
    }

    function setupDocumentList({key, prefix, endpoint, columns, detailPath, createFields, onOpen}) {
        const form = document.getElementById(`${prefix}-search-form`);
        setupListFilter(prefix);
        const dialog = document.getElementById(`create-${prefix}-dialog`);
        let controller = null;
        if (dialog) {
            const createForm = document.getElementById(`create-${prefix}-form`);
            document.getElementById(`open-create-${prefix}`).addEventListener("click", () => {
                onOpen?.();
                dialog.showModal();
            });
            dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
            createForm.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(createForm, async () => {
                    const created = await apiRequest(createForm.action, {
                        method: "POST",
                        body: createFields(new FormData(createForm)),
                    });
                    window.location.assign(`${detailPath}${created.id}/`);
                });
            });
        }
        controller = setupPagedList({
            key,
            form,
            search: document.getElementById(`${prefix}-search`),
            endpoint,
            renderRow: (row) => documentListRow(row, columns, (item) => `${detailPath}${item.id}/`),
        });
        controller.load();
        return controller;
    }

    /**
     * Wire the theme's own real `KTStepper` inside a create dialog's `.stepper`.
     *
     * The vendor component only tracks the current step and toggles its own
     * `current`/`completed`/`pending`/`first`/`between`/`last` classes — the
     * already-loaded theme stylesheet is what shows and hides the previous/
     * next/submit buttons from those. Advancing past "next" is left to the
     * page on purpose (this is how the vendor's own reference wizard is
     * wired too): it is the one place worth gating on the step's own
     * required fields, the same native check the browser would already run
     * on submit if these forms were not marked `novalidate`. No form-
     * validation library or SweetAlert is pulled in for it — neither is used
     * anywhere else in this codebase, and `showError`/`data-error-for`
     * already cover the server's own validation once the form is sent.
     *
     * The submit button stays a plain `type="submit"` inside the form, so
     * the existing `setupDocumentList` submit handler needs no change at
     * all: the wizard only decides which step is visible.
     */
    function setupWizard(dialog, {onReachLastStep} = {}) {
        const root = dialog?.querySelector(".stepper");
        if (!root) return null;
        const stepper = new KTStepper(root);
        const totalSteps = root.querySelectorAll('[data-kt-stepper-element="nav"]').length;
        const contentOf = (index) => root.querySelectorAll('[data-kt-stepper-element="content"]')[index - 1];
        stepper.on("kt.stepper.next", () => {
            const invalid = contentOf(stepper.getCurrentStepIndex())?.querySelector(":invalid");
            if (invalid) {
                invalid.reportValidity();
                return;
            }
            stepper.goNext();
            dialog.scrollTop = 0;
            if (stepper.getCurrentStepIndex() === totalSteps) onReachLastStep?.();
        });
        stepper.on("kt.stepper.previous", () => {
            stepper.goPrevious();
            dialog.scrollTop = 0;
        });
        return stepper;
    }

    /**
     * One dynamic "product + quantity" row, shared by the invoice and order
     * creation wizards. `host` is the container the rows live in; `products`
     * is the shared catalogue list the caller has already fetched once.
     */
    function createLineItemRows(host, products) {
        function addLine() {
            if (!host) return;
            const row = document.createElement("div");
            // `gap-5` and the row's own separator are the purchased theme's own
            // repeater spacing (its ecommerce catalog add-product page,
            // `data-repeater-item`), not a number picked here — product-owner
            // decision 2026-09-09 asked this step to breathe more.
            row.className = "d-flex flex-wrap align-items-center gap-5 wizard-line-row";
            row.dataset.lineRow = "";

            const picker = document.createElement("div");
            picker.className = "searchable-select flex-grow-1";
            picker.setAttribute("data-searchable-select", "");
            const search = document.createElement("input");
            search.className = "form-control form-control-solid";
            search.type = "search";
            search.autocomplete = "off";
            search.placeholder = "نام یا کد کالا…";
            search.setAttribute("data-searchable-input", "");
            search.setAttribute("role", "combobox");
            search.setAttribute("aria-label", "جستجوی کالا");
            search.hidden = true;
            const select = document.createElement("select");
            select.className = "form-select form-select-solid";
            select.dataset.lineProduct = "";
            select.setAttribute("data-searchable-source", "");
            select.setAttribute("aria-label", "کالا");
            fillSelect(select, products, (item) => `${item.name} (${item.sku})`, "یک کالا انتخاب کنید");
            const options = document.createElement("ul");
            options.className = "searchable-select-options";
            options.setAttribute("role", "listbox");
            options.hidden = true;
            picker.append(search, select, options);

            const quantity = document.createElement("input");
            // A fixed narrow column rather than `w-auto`: every row's quantity
            // then lines up under the next, which `w-auto` (sized to the
            // number typed) never does.
            quantity.className = "form-control form-control-solid w-100px";
            quantity.type = "number";
            quantity.min = "1";
            quantity.step = "1";
            quantity.value = "1";
            quantity.dataset.lineQuantity = "";
            quantity.setAttribute("aria-label", "تعداد");

            const remove = document.createElement("button");
            // The theme's own repeater delete control, icon and all — a real
            // `ki-cross` rather than a literal "×" character, which rendered
            // at text weight beside two solid inputs.
            remove.className = "btn btn-sm btn-icon btn-light-danger";
            remove.type = "button";
            const removeIcon = document.createElement("i");
            removeIcon.className = "ki-duotone ki-cross fs-2";
            ["path1", "path2"].forEach((name) => {
                const path = document.createElement("span");
                path.className = name;
                removeIcon.append(path);
            });
            remove.append(removeIcon);
            remove.setAttribute("aria-label", "حذف ردیف");
            remove.addEventListener("click", () => {
                row.remove();
                // Never none: a document without a line cannot be submitted,
                // so the form always offers one to fill.
                if (!host.children.length) addLine();
            });

            row.append(picker, quantity, remove);
            host.append(row);
            setupSearchableSelects(row);
        }

        function reset() {
            if (!host) return;
            host.innerHTML = "";
            addLine();
        }

        function collect() {
            if (!host) return [];
            return [...host.querySelectorAll("[data-line-row]")]
                .map((row) => ({
                    product: Number(row.querySelector("[data-line-product]").value),
                    quantity: Number(row.querySelector("[data-line-quantity]").value),
                }))
                .filter((line) => line.product && line.quantity > 0);
        }

        return {addLine, reset, collect};
    }

    /** A field's chosen option text for a review step, or an em dash for one
     * nothing has been picked for yet. */
    function selectedOptionText(select) {
        return select?.selectedOptions[0]?.textContent || "—";
    }

    /** Fill a wizard's review step from `[label, value]` pairs. Read at the
     * moment the step is shown, never kept live — the review step's only job
     * is to reflect what is about to be sent, not to recompute it. */
    function renderWizardReview(container, rows) {
        if (!container) return;
        container.innerHTML = "";
        rows.forEach(([label, value]) => {
            const col = document.createElement("div");
            col.className = "col-md-6";
            const labelEl = document.createElement("span");
            labelEl.className = "text-muted d-block fs-7";
            labelEl.textContent = label;
            const valueEl = document.createElement("span");
            valueEl.className = "fw-bold fs-6";
            valueEl.textContent = value;
            col.append(labelEl, valueEl);
            container.append(col);
        });
    }

    async function setupOrders() {
        const lineHost = document.getElementById("create-order-lines");
        // Replaced once the catalogue arrives below; a no-op stub means an
        // impatient click on "افزودن کالا" before then does nothing instead
        // of throwing.
        let lines = {addLine() {}, reset() {}, collect: () => []};
        const dialog = document.getElementById("create-order-dialog");
        const wizard = setupWizard(dialog, {onReachLastStep: () => renderReview()});

        function renderReview() {
            renderWizardReview(document.getElementById("create-order-review"), [
                ["مشتری", selectedOptionText(document.getElementById("create-order-customer"))],
                ["انبار", selectedOptionText(document.getElementById("create-order-warehouse"))],
                ["روش ارسال", selectedOptionText(document.getElementById("create-order-shipping"))],
                ["تاریخ ارسال", document.getElementById("create-order-delivery")?.value || "تعیین نشده"],
                ["تعداد اقلام", toPersianDigits(String(lines.collect().length))],
            ]);
        }

        try {
            const [, , products] = await Promise.all([
                loadCustomerOptions(document.getElementById("create-order-customer"), "یک مشتری انتخاب کنید"),
                // The order names the warehouse its goods leave from on approval.
                loadWarehouseOptions(document.getElementById("create-order-warehouse"), "بدون اثر انبار"),
                loadAllPages("/api/v1/products/?is_active=true&ordering=name"),
            ]);
            lines = createLineItemRows(lineHost, products);
            setupSearchableSelects(dialog);
            lines.addLine();
        } catch (error) {
            showError(error);
        }
        document.getElementById("create-order-add-line")?.addEventListener("click", () => lines.addLine());
        setupDocumentList({
            key: "orders",
            prefix: "order",
            detailPath: "/orders/",
            onOpen: () => {
                document.getElementById("create-order-form")?.reset();
                lines.reset();
                wizard?.goFirst();
            },
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page)});
                const search = document.getElementById("order-search").value.trim();
                if (search) query.set("search", search);
                const status = document.getElementById("order-status-filter").value;
                if (status) query.set("status", status);
                query.set("ordering", document.getElementById("order-ordering").value);
                return `/api/v1/orders/?${query}`;
            },
            columns: [
                (row, item) => {
                    // The order number, centred like the amount beside it.
                    const cell = appendCell(row, item.number);
                    cell.dir = "ltr";
                    cell.classList.add("text-center");
                },
                (row, item) => appendCell(row, item.customer_name),
                (row, item) => appendStatusBadgeCell(row, DOCUMENT_STATUS_TEXT, item.status),
                (row, item) => appendMoneyCell(row, item.total_amount).classList.add("text-center"),
                // Registration is server-generated and immutable; delivery is
                // the date the operator sets on the order.
                (row, item) => appendCell(row, displayDay(item.created_at)),
                (row, item) => appendCell(row, displayDay(item.expected_delivery_at)),
                (row, item) => appendCell(row, item.created_by_display || item.created_by),
            ],
            createFields: (data) => {
                const payload = {
                    customer: Number(data.get("customer")),
                    items: lines.collect(),
                    notes: String(data.get("notes") || ""),
                    shipping_method: String(data.get("shipping_method") || ""),
                };
                const warehouse = numberOrNull(data.get("warehouse"));
                if (warehouse !== null) payload.warehouse = warehouse;
                payload.expected_delivery_at = apiDateTime(textOrNull(data.get("expected_delivery_at")));
                return payload;
            },
        });
    }

    async function setupInvoices() {
        const lineHost = document.getElementById("create-invoice-lines");
        let lines = {addLine() {}, reset() {}, collect: () => []};
        const dialog = document.getElementById("create-invoice-dialog");
        const wizard = setupWizard(dialog, {onReachLastStep: () => renderReview()});

        function renderReview() {
            const taxRate = document.getElementById("create-invoice-tax")?.value || "0";
            const discount = document.getElementById("create-invoice-discount")?.value || "0";
            renderWizardReview(document.getElementById("create-invoice-review"), [
                ["مشتری", selectedOptionText(document.getElementById("create-invoice-customer"))],
                ["نوع فاکتور", selectedOptionText(document.getElementById("create-invoice-type"))],
                ["تاریخ صدور", document.getElementById("create-invoice-document-date")?.value || "روز صدور"],
                ["نرخ مالیات", `${toPersianDigits(taxRate)}٪`],
                ["تخفیف", `${toPersianDigits(discount)}٪`],
                ["تعداد اقلام", toPersianDigits(String(lines.collect().length))],
            ]);
        }

        try {
            const [, products] = await Promise.all([
                loadCustomerOptions(document.getElementById("create-invoice-customer"), "یک مشتری انتخاب کنید"),
                loadAllPages("/api/v1/products/?is_active=true&ordering=name"),
            ]);
            lines = createLineItemRows(lineHost, products);
            setupSearchableSelects(dialog);
            lines.addLine();
        } catch (error) {
            showError(error);
        }
        document.getElementById("create-invoice-add-line")?.addEventListener("click", () => lines.addLine());
        setupDocumentList({
            key: "invoices",
            prefix: "invoice",
            detailPath: "/invoices/",
            onOpen: () => {
                document.getElementById("create-invoice-form")?.reset();
                lines.reset();
                wizard?.goFirst();
            },
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page)});
                const search = document.getElementById("invoice-search").value.trim();
                if (search) query.set("search", search);
                const status = document.getElementById("invoice-status-filter").value;
                if (status) query.set("status", status);
                const settlement = document.getElementById("invoice-settlement-filter").value;
                if (settlement) query.set("settlement", settlement);
                const invoiceType = document.getElementById("invoice-type-filter").value;
                if (invoiceType) query.set("invoice_type", invoiceType);
                query.set("ordering", document.getElementById("invoice-ordering").value);
                return `/api/v1/invoices/?${query}`;
            },
            columns: [
                // Every value column is centred; the action column is not.
                (row, item) => {
                    const cell = appendCell(row, item.number);
                    cell.dir = "ltr";
                    cell.classList.add("text-center");
                },
                (row, item) => appendCell(row, item.customer_name).classList.add("text-center"),
                (row, item) => appendStatusBadgeCell(row, DOCUMENT_STATUS_TEXT, item.status).classList.add("text-center"),
                (row, item) => appendMoneyCell(row, item.total_amount).classList.add("text-center"),
                (row, item) => appendMoneyCell(row, item.paid_amount).classList.add("text-center"),
                (row, item) => appendMoneyCell(row, item.balance_due).classList.add("text-center"),
                // The date written on the document. Rows from before this field
                // existed have none, so the issue timestamp stands in rather
                // than leaving the column blank.
                (row, item) =>
                    appendCell(
                        row,
                        displayDay(item.document_date || item.issued_at),
                    ).classList.add("text-center"),
                // Was the due date, which this product never sets — a column of
                // dashes. Whether an invoice is official is what a reader
                // actually needs beside it, and it is also what the new filter
                // narrows by.
                (row, item) =>
                    appendCell(
                        row,
                        item.invoice_type_display || labelled(INVOICE_TYPE_TEXT, item.invoice_type),
                    ).classList.add("text-center"),
            ],
            createFields: (data) => {
                // No warehouse: an invoice moves no stock, so naming one would
                // suggest an effect it does not have.
                const discountPercent = Number(data.get("discount_percent")) || 0;
                const body = {
                    customer: Number(data.get("customer")),
                    invoice_type: String(data.get("invoice_type") || "unofficial"),
                    tax_rate: Number(data.get("tax_rate")) || 0,
                    // The discount is a percentage and rides on each line, which
                    // already has `discount_percent`. Nothing new is invented
                    // server-side and the order of calculation is the one the
                    // line rules are already tested against.
                    items: lines.collect().map((line) => ({...line, discount_percent: discountPercent})),
                };
                // The date on the document, if the operator wrote one. Left out
                // rather than sent empty when they did not, because issuing
                // fills it from the day it was issued.
                const documentDate = apiDate(data.get("document_date"));
                if (documentDate) body.document_date = documentDate;
                return body;
            },
        });
    }

    /** Shared line editor and totals for one commercial document.
     *
     * Lines are edited as one local list and written back with a single call to
     * the document's `items` endpoint, which replaces the whole set. That keeps
     * the stored header totals and the stored lines from ever disagreeing —
     * the service recomputes the totals from the lines it just wrote.
     */
    function documentLineEditor({doc, endpoint, onSaved}) {
        const body = document.getElementById(`${doc}-lines-body`);
        const empty = document.getElementById(`${doc}-lines-empty`);
        const editor = document.getElementById(`${doc}-lines-editor`);
        const countLabel = document.getElementById(`${doc}-lines-count`);
        const addForm = document.getElementById(`${doc}-add-line-form`);
        const saveButton = document.getElementById(`${doc}-save-lines`);
        const resetButton = document.getElementById(`${doc}-reset-lines`);
        const productSelect = document.getElementById(`${doc}-line-product`);
        let stored = [];
        let draft = [];
        let editable = false;
        let products = [];

        function productLabel(id) {
            const match = products.find((item) => item.id === Number(id));
            return match ? `${match.name} (${match.sku})` : String(id);
        }

        function render() {
            const rows = draft.map((line, index) => {
                const row = document.createElement("tr");
                appendCell(row, index + 1);
                appendCell(row, line.product_sku_snapshot || "—").dir = "ltr";
                appendCell(row, line.product_name_snapshot || productLabel(line.product));
                appendCell(row, line.quantity);
                appendMoneyCell(row, line.unit_price);
                appendMoneyCell(row, line.discount_amount);
                appendMoneyCell(row, line.line_total);
                const actions = document.createElement("td");
                actions.className = "row-actions";
                if (editable) {
                    const remove = document.createElement("button");
                    remove.type = "button";
                    remove.className = "btn btn-sm btn-light";
                    remove.textContent = "حذف سطر";
                    remove.addEventListener("click", () => {
                        draft.splice(index, 1);
                        render();
                    });
                    actions.appendChild(remove);
                }
                row.appendChild(actions);
                return row;
            });
            body.replaceChildren(...rows);
            empty.hidden = draft.length > 0;
            countLabel.textContent = draft.length ? `${draft.length} سطر` : "";
        }

        addForm?.addEventListener("submit", (event) => {
            event.preventDefault();
            const data = new FormData(addForm);
            const product = numberOrNull(data.get("product"));
            const quantity = numberOrNull(data.get("quantity"));
            if (product === null || quantity === null || quantity < 1) {
                globalMessage("کالا و تعداد سطر را کامل وارد کنید.");
                return;
            }
            const unitPrice = moneyOrNull(data.get("unit_price"));
            const discountPercent = numberOrNull(data.get("discount_percent"));
            const match = products.find((item) => item.id === product);
            const price = unitPrice === null ? Number(match ? match.current_price : 0) : Number(unitPrice);
            const gross = price * quantity;
            const discount = discountPercent ? (gross * discountPercent) / 100 : 0;
            draft.push({
                product,
                quantity,
                unit_price: unitPrice,
                discount_percent: discountPercent,
                // Preview only. The server recomputes every amount from the
                // product price it reads at write time, and its numbers win.
                product_name_snapshot: match ? match.name : "",
                product_sku_snapshot: match ? match.sku : "",
                line_total: (gross - discount).toFixed(2),
                discount_amount: discount.toFixed(2),
            });
            addForm.reset();
            document.getElementById(`${doc}-line-quantity`).value = "1";
            render();
        });

        resetButton?.addEventListener("click", () => {
            draft = stored.map((line) => ({...line}));
            render();
            globalMessage("اقلام ذخیره‌شده بازگردانده شد.", true);
        });

        saveButton?.addEventListener("click", async () => {
            if (!draft.length) {
                globalMessage("سند باید دست‌کم یک سطر داشته باشد.");
                return;
            }
            saveButton.disabled = true;
            clearMessages();
            try {
                const payload = draft.map((line) => {
                    const item = {product: Number(line.product), quantity: Number(line.quantity)};
                    if (line.unit_price !== null && line.unit_price !== undefined) {
                        item.unit_price = String(line.unit_price);
                    }
                    if (line.discount_percent) item.discount_percent = String(line.discount_percent);
                    return item;
                });
                const updated = await apiRequest(`${endpoint}items/`, {method: "POST", body: {items: payload}});
                globalMessage("اقلام سند ذخیره شد.", true);
                onSaved(updated);
            } catch (error) {
                showError(error);
            } finally {
                saveButton.disabled = false;
            }
        });

        return {
            async loadProducts() {
                products = await loadAllPages("/api/v1/products/?is_active=true&ordering=name");
                if (productSelect) {
                    fillSelect(productSelect, products, (item) => `${item.name} (${item.sku})`, "یک کالا انتخاب کنید");
                }
            },
            apply(document_) {
                stored = (document_.line_items || []).map((line) => ({
                    product: line.product,
                    quantity: line.quantity,
                    unit_price: line.unit_price,
                    discount_percent: Number(line.discount_percent) || null,
                    discount_amount: line.discount_amount,
                    line_total: line.line_total,
                    product_name_snapshot: line.product_name_snapshot,
                    product_sku_snapshot: line.product_sku_snapshot,
                }));
                draft = stored.map((line) => ({...line}));
                editable = document_.status === "draft";
                if (editor) editor.hidden = !editable;
                render();
                document.getElementById(`${doc}-subtotal`).value = money(document_.subtotal_amount);
                document.getElementById(`${doc}-discount-total`).value = money(document_.discount_amount);
                document.getElementById(`${doc}-tax-rate-view`).value = document_.tax_rate;
                document.getElementById(`${doc}-tax-amount`).value = money(document_.tax_amount);
                document.getElementById(`${doc}-total`).value = money(document_.total_amount);
            },
        };
    }

    function bindTransitions(attribute, endpoint, apply) {
        document.querySelectorAll(`[data-${attribute}-transition]`).forEach((button) => {
            button.addEventListener("click", async () => {
                const target = button.dataset[`${attribute}Transition`];
                if (!window.confirm(`وضعیت سند به «${labelled(DOCUMENT_STATUS_TEXT, target)}» تغییر کند؟`)) return;
                button.disabled = true;
                clearMessages();
                try {
                    const updated = await apiRequest(`${endpoint}transition/`, {
                        method: "POST",
                        body: {to_status: target},
                    });
                    globalMessage("وضعیت سند ثبت شد.", true);
                    apply(updated);
                } catch (error) {
                    showError(error);
                } finally {
                    button.disabled = false;
                }
            });
        });
    }

    async function setupOrderDetail() {
        const orderId = document.body.dataset.orderId;
        const endpoint = `/api/v1/orders/${orderId}/`;
        const loading = document.getElementById("order-detail-loading");
        const content = document.getElementById("order-detail-content");
        const statusSelect = document.getElementById("order-status-select");
        const form = document.getElementById("edit-order-form");
        const editActions = document.getElementById("order-edit-actions");
        const lockedNote = document.getElementById("order-locked-note");
        const lines = documentLineEditor({doc: "order", endpoint, onSaved: (updated) => apply(updated)});

        let current = null;

        function apply(order) {
            current = order;
            document.getElementById("order-number").value = order.number;
            document.getElementById("order-customer").value = order.customer_name;
            // Registration is server-generated and immutable, shown as a day.
            document.getElementById("order-registered-at").value = displayDay(order.created_at);
            document.getElementById("order-created-by").value = order.created_by_display || order.created_by;
            if (statusSelect) {
                statusSelect.value = order.status;
            } else {
                document.getElementById("order-status").value = labelled(DOCUMENT_STATUS_TEXT, order.status);
            }
            document.getElementById("edit-order-delivery").value = localDateValue(order.expected_delivery_at);
            document.getElementById("edit-order-notes").value = order.notes || "";
            // A draft and an approved order are both editable: the service moves
            // only the stock difference when an approved one changes.
            const editable = ["draft", "confirmed"].includes(order.status);
            if (editActions) editActions.hidden = !editable;
            if (lockedNote) lockedNote.hidden = editable;
            form.querySelectorAll("input[name], textarea[name]").forEach((field) => { field.disabled = !editable; });
            lines.apply(order);
        }

        /**
         * Invoices linked to this order.
         *
         * Read through the real relation — `?order=<id>` — rather than by
         * comparing document numbers as text.
         */
        async function loadLinkedInvoices() {
            const wrap = document.getElementById("order-invoices-table-wrap");
            const body = document.getElementById("order-invoices-table-body");
            const invoiceLoading = document.getElementById("order-invoices-loading");
            const empty = document.getElementById("order-invoices-empty");
            if (!wrap || !body) return;
            invoiceLoading.hidden = false; wrap.hidden = true; empty.hidden = true;
            try {
                const data = await apiRequest(`/api/v1/invoices/?order=${orderId}`);
                body.replaceChildren(...data.results.map((invoice) => {
                    const row = document.createElement("tr");
                    appendCell(row, invoice.number).dir = "ltr";
                    appendMoneyCell(row, invoice.total_amount);
                    const cell = document.createElement("td");
                    const link = document.createElement("a");
                    link.className = "btn btn-sm btn-light";
                    link.href = `/invoices/${invoice.id}/`;
                    link.textContent = "مشاهده";
                    cell.append(link);
                    row.append(cell);
                    return row;
                }));
                invoiceLoading.hidden = true;
                empty.hidden = data.results.length > 0;
                wrap.hidden = data.results.length === 0;
            } catch (error) {
                invoiceLoading.hidden = true;
                showError(error);
            }
        }

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const data = new FormData(form);
                // Document discount and tax rate are not offered on this form.
                const payload = {notes: String(data.get("notes") || "")};
                payload.expected_delivery_at = apiDateTime(textOrNull(data.get("expected_delivery_at")));
                const updated = await apiRequest(endpoint, {method: "PATCH", body: payload});
                apply(updated);
                globalMessage("سربرگ سفارش ذخیره شد.", true);
            });
        });
        // Changing the status is what moves stock, so it asks first and reports
        // what the server decided — an approval the warehouse cannot cover comes
        // back cancelled, with the reason on the order.
        statusSelect?.addEventListener("change", async () => {
            const next = statusSelect.value;
            if (!current || next === current.status) return;
            const label = labelled(DOCUMENT_STATUS_TEXT, next);
            if (!window.confirm(`وضعیت سفارش به «${label}» تغییر کند؟`)) {
                statusSelect.value = current.status;
                return;
            }
            statusSelect.disabled = true;
            clearMessages();
            try {
                const updated = await apiRequest(`${endpoint}transition/`, {
                    method: "POST", body: {to_status: next},
                });
                apply(updated);
                if (updated.status === "cancelled" && next !== "cancelled") {
                    globalMessage("موجودی کافی نبود؛ سفارش لغو شد.");
                } else {
                    globalMessage("وضعیت سفارش ثبت شد.", true);
                }
            } catch (error) {
                statusSelect.value = current.status;
                showError(error);
            } finally {
                statusSelect.disabled = false;
            }
        });

        try {
            const [order] = await Promise.all([apiRequest(endpoint), lines.loadProducts()]);
            apply(order);
            await loadLinkedInvoices();
            loading.hidden = true;
            content.hidden = false;
        } catch (error) {
            loading.hidden = true;
            showError(error);
        }
    }

    /**
     * What this invoice still lacks before it can be issued as official.
     *
     * The server decides this - `official_invoice_identity_errors` in
     * billing/services.py refuses the issue - and this only mirrors the same
     * conditions so the operator learns before pressing the button rather than
     * after. It is a convenience, never the check: an invoice that got past
     * this list is still refused by the service if it is genuinely incomplete.
     */
    function officialInvoiceChecklist(invoice) {
        const missing = [];
        if (!invoice.customer_national_id) {
            missing.push("کد/شناسه ملی خریدار در پروندهٔ مشتری");
        }
        if (invoice.customer_kind === "legal" && !invoice.customer_economic_code) {
            missing.push("شماره اقتصادی خریدار (مشتری حقوقی)");
        }
        return missing;
    }

    function syncOfficialInvoiceNotice(invoice) {
        const notice = document.getElementById("invoice-official-requirements");
        const list = document.getElementById("invoice-official-checklist");
        const select = document.getElementById("edit-invoice-type");
        if (!notice || !list || !select) return;
        if (select.value !== "official") {
            notice.hidden = true;
            return;
        }
        const missing = officialInvoiceChecklist(invoice || {});
        list.textContent = missing.length
            ? `این موارد هنوز ثبت نشده‌اند: ${missing.join("، ")}`
            : "هویت‌های لازم کامل است. هویت فروشنده از تنظیمات استقرار خوانده می‌شود و هنگام صدور بررسی می‌شود.";
        notice.hidden = false;
    }

    async function setupInvoiceDetail() {
        const invoiceId = document.body.dataset.invoiceId;
        const endpoint = `/api/v1/invoices/${invoiceId}/`;
        const loading = document.getElementById("invoice-detail-loading");
        const content = document.getElementById("invoice-detail-content");
        const statusSelect = document.getElementById("invoice-status-select");
        const paidInput = document.getElementById("invoice-paid");
        const allocationsSection = document.getElementById("invoice-allocations");
        const form = document.getElementById("edit-invoice-form");
        const editActions = document.getElementById("invoice-edit-actions");
        const lockedNote = document.getElementById("invoice-locked-note");
        const issuedNote = document.getElementById("invoice-issued-note");
        const planForm = document.getElementById("invoice-plan-form");
        const lines = documentLineEditor({doc: "invoice", endpoint, onSaved: (updated) => apply(updated)});
        let allocationsController = null;

        let current = null;

        function apply(invoice) {
            current = invoice;
            document.getElementById("invoice-number").value = invoice.number;
            document.getElementById("invoice-customer").value = invoice.customer_name;
            if (statusSelect) {
                statusSelect.value = invoice.status;
            } else {
                document.getElementById("invoice-status").value = labelled(DOCUMENT_STATUS_TEXT, invoice.status);
            }
            // Settlement is derived and read-only for everyone.
            document.getElementById("invoice-settlement").value = labelled(SETTLEMENT_TEXT, invoice.settlement_status);
            // Editable only while the invoice is a draft: after issue the type is
            // part of what was issued, and the service refuses to change it.
            const typeSelect = document.getElementById("edit-invoice-type");
            if (typeSelect) {
                typeSelect.value = invoice.invoice_type || "unofficial";
                typeSelect.disabled = invoice.status !== "draft";
            }
            syncOfficialInvoiceNotice(invoice);
            document.getElementById("edit-invoice-document-date").value =
                localDayValue(invoice.document_date);
            document.getElementById("invoice-issued-at").value = displayDay(invoice.issued_at);
            // Derived, and shown as such. It is the sum of the allocations made
            // against this invoice from the receipts desk; «مانده» follows it.
            if (paidInput) paidInput.value = money(invoice.paid_amount);
            document.getElementById("invoice-balance").value = money(invoice.balance_due);
            document.getElementById("edit-invoice-notes").value = invoice.notes || "";
            const editable = invoice.status === "draft";
            // Issued and correctable are not the same thing: an issued invoice
            // can still have its note corrected, so the save action stays
            // available and only the note field itself is enabled — everything
            // that could move money or the document's legal shape stays locked.
            const noteOnly = invoice.status === "issued";
            if (editActions) editActions.hidden = !(editable || noteOnly);
            if (issuedNote) issuedNote.hidden = !noteOnly;
            if (lockedNote) lockedNote.hidden = editable || noteOnly;
            form.querySelectorAll("input[name], textarea[name]").forEach((field) => {
                field.disabled = noteOnly ? field.name !== "notes" : !editable;
            });
            if (allocationsSection) allocationsSection.hidden = invoice.status !== "issued";
            if (invoice.status === "issued") {
                allocationsController?.load();
                loadPlan();
            }
            lines.apply(invoice);
        }

        async function loadPlan() {
            const wrap = document.getElementById("invoice-plan-summary");
            const body = document.getElementById("invoice-plan-body");
            if (!wrap) return;
            try {
                const data = await apiRequest(`/api/v1/installment-plans/?invoice=${invoiceId}`);
                const plan = data.results[0];
                if (!plan) { wrap.hidden = true; return; }
                body.replaceChildren(...plan.installments.map((item) => {
                    const row = document.createElement("tr");
                    appendCell(row, item.sequence);
                    appendCell(row, displayDay(item.due_date));
                    appendMoneyCell(row, item.amount);
                    appendMoneyCell(row, item.paid_amount);
                    appendStatusBadgeCell(row, INSTALLMENT_STATUS_TEXT, item.status);
                    return row;
                }));
                wrap.hidden = false;
            } catch (error) {
                showError(error);
            }
        }

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const data = new FormData(form);
                // An issued invoice may correct only its note — the server
                // enforces this too, but sending anything else here would fail
                // on a field the reader never touched, since every disabled
                // input still has whatever value it was showing. `due_at` has
                // no field on this form since 1.4.0 and is never sent; sending
                // it as `null` on every save was silently clearing a value nothing
                // on screen offered to change.
                const payload = {notes: String(data.get("notes") || "")};
                if (current?.status !== "issued") {
                    // Null when cleared rather than omitted, so an operator can
                    // take a wrong date off a draft as well as correct one.
                    payload.document_date = apiDate(data.get("document_date"));
                    const typeField = document.getElementById("edit-invoice-type");
                    if (typeField && !typeField.disabled) payload.invoice_type = typeField.value;
                }
                const updated = await apiRequest(endpoint, {method: "PATCH", body: payload});
                apply(updated);
                globalMessage("سربرگ فاکتور ذخیره شد.", true);
            });
        });

        // The invoice lifecycle runs from the status select. Issuing posts the
        // customer debit and freezes the lines; it moves no stock, because the
        // order already did.
        statusSelect?.addEventListener("change", async () => {
            const next = statusSelect.value;
            if (!current || next === current.status) return;
            const questions = {
                issued: "فاکتور صادر شود؟ پس از صدور، اقلام و مبالغ تغییرناپذیر می‌شوند و بدهکاری مشتری ثبت می‌شود.",
                cancelled: "فاکتور ابطال شود؟ اثر دفتر حساب برگردانده می‌شود.",
            };
            if (!window.confirm(questions[next] || "وضعیت فاکتور تغییر کند؟")) {
                statusSelect.value = current.status;
                return;
            }
            statusSelect.disabled = true;
            clearMessages();
            try {
                if (next === "issued") {
                    apply(await apiRequest(`${endpoint}issue/`, {method: "POST"}));
                    globalMessage("فاکتور صادر شد.", true);
                } else if (next === "cancelled") {
                    apply(await apiRequest(`${endpoint}cancel/`, {method: "POST", body: {reason: ""}}));
                    globalMessage("فاکتور ابطال شد.", true);
                } else {
                    statusSelect.value = current.status;
                    globalMessage("بازگشت به پیش‌نویس ممکن نیست.");
                }
            } catch (error) {
                statusSelect.value = current.status;
                showError(error);
            } finally {
                statusSelect.disabled = false;
            }
        });

        document.getElementById("edit-invoice-type")?.addEventListener("change", () => {
            syncOfficialInvoiceNotice(current);
        });

        // No handler for «پرداخت شده» any more, and none for «سفارش».
        //
        // The paid figure used to be typed here and posted to `manual-paid/`,
        // which settled the invoice without writing a Payment, an allocation or
        // a ledger entry — a second source of truth for how much had been paid,
        // and the one with no trail behind it. It is now only ever the sum of
        // the allocations recorded on the receipts desk.

        planForm?.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(planForm, async () => {
                const data = new FormData(planForm);
                const payload = {
                    invoice: Number(invoiceId),
                    installment_count: Number(data.get("installment_count")),
                    start_date: apiDate(data.get("start_date")),
                };
                const interval = numberOrNull(data.get("interval_days"));
                if (interval !== null) payload.interval_days = interval;
                await apiRequest("/api/v1/installment-plans/", {method: "POST", body: payload});
                globalMessage("قسط‌بندی ساخته شد.", true);
                loadPlan();
            });
        });

        if (allocationsSection) {
            allocationsController = setupPagedList({
                key: "invoice-allocations",
                form: null,
                endpoint: (page) => `${endpoint}allocations/?page=${page}`,
                renderRow: (allocation) => {
                    const row = document.createElement("tr");
                    appendCell(row, allocation.payment_number).dir = "ltr";
                    appendMoneyCell(row, allocation.amount);
                    appendCell(row, allocation.is_reversed ? "آزادشده" : "فعال");
                    appendCell(row, allocation.created_by_display || allocation.created_by);
                    appendCell(row, displayDate(allocation.created_at));
                    return row;
                },
            });
        }

        try {
            const [invoice] = await Promise.all([apiRequest(endpoint), lines.loadProducts()]);
            apply(invoice);
            loading.hidden = true;
            content.hidden = false;
        } catch (error) {
            loading.hidden = true;
            showError(error);
        }
    }

    // --- Payments, cheques, installments -------------------------------------

    function paymentRow(payment) {
        const row = document.createElement("tr");
        appendCell(row, payment.number).dir = "ltr";
        // The party. A disbursement often names no customer and records who was
        // paid instead, so the payee is the fallback rather than a dash.
        //
        // An endorsed cheque shows the customer it came from on both desks,
        // which is right: it is the same document, and that is whose cheque it
        // was. Where it went is on the cheque itself.
        appendCell(row, payment.customer_name || payment.payee || "—");
        appendCell(row, labelled(PAYMENT_METHOD_TEXT, payment.method));
        appendMoneyCell(row, payment.amount);
        // On a cheque the document's own status is the wrong answer. Spending a
        // cheque onward closes the receipt it came in on, so the payment reads
        // «ابطال‌شده» while the instrument is alive and «خرج شده» — the reader
        // sees a cancelled receipt for a cheque that was never cancelled. The
        // cheque's status is the one that describes where the money is, so on
        // this method it is the one shown, and it is the same value the cheques
        // page displays for the same row.
        if (payment.method === "cheque" && payment.cheque_detail) {
            appendStatusBadgeCell(row, CHEQUE_STATUS_TEXT, payment.cheque_detail.status);
        } else {
            appendStatusBadgeCell(row, PAYMENT_STATUS_TEXT, payment.status);
        }
        // The date it was recorded, without the hour: a clock reading is not
        // what this column is ever scanned for.
        appendCell(row, displayDay(payment.received_at));
        appendDetailLink(row, `/payments/${payment.id}/`);
        return row;
    }

    async function setupPayments() {
        const form = document.getElementById("payment-search-form");
        setupListFilter("payment");
        const dialog = document.getElementById("create-payment-dialog");
        let controller = null;
        if (dialog) {
            const createForm = document.getElementById("create-payment-form");
            const methodField = document.getElementById("create-payment-method");
            const bankFields = document.getElementById("create-payment-bank-fields");
            const chequeFields = document.getElementById("create-payment-cheque-fields");
            const chequeNote = document.getElementById("create-payment-cheque-note");
            const modeButtons = Array.from(createForm.querySelectorAll("[data-payment-mode]"));

            // Which direction this desk records. It is fixed by the page, not
            // chosen on the form: a receipt desk files receipts. Asking again
            // only ever let someone file a document in the wrong ledger from
            // the right screen.
            const direction = document.body.dataset.paymentDirection === "disbursement"
                ? "disbursement"
                : "receipt";
            const referenceField = createForm.querySelector('[data-payment-field="reference"]');
            const chequeSourceRow = createForm.querySelector('[data-payment-field="cheque-source"]');
            const chequeSource = document.getElementById("create-cheque-source");
            const existingChequeRow = document.getElementById("create-cheque-existing");
            const newChequeFields = document.getElementById("create-cheque-new-fields");

            function selectMode(method) {
                methodField.value = method;
                modeButtons.forEach((button) => {
                    const active = button.dataset.paymentMode === method;
                    button.classList.toggle("btn-primary", active);
                    button.classList.toggle("btn-light", !active);
                    button.setAttribute("aria-pressed", String(active));
                });
                bankFields.hidden = method !== "bank_transfer";
                chequeFields.hidden = method !== "cheque";
                if (chequeNote) chequeNote.hidden = method !== "cheque";
                // A reference number exists on a transfer and nowhere else. Cash
                // handed over has none, and a cheque is identified by its own
                // serial rather than by a tracking code.
                if (referenceField) referenceField.hidden = method !== "bank_transfer";
                // Only a disbursement can hand on a cheque already taken in.
                if (chequeSourceRow) {
                    chequeSourceRow.hidden = !(method === "cheque" && direction === "disbursement");
                }
                applyChequeSource();
                clearMessages(createForm);
            }

            // Where the party, amount and date live on a non-cheque method, so
            // they can be put back when the reader switches away from cheque.
            const partyField = createForm.querySelector('[data-payment-field="customer"]');
            const amountField = createForm.querySelector('[data-payment-field="amount"]');
            const dateField = createForm.querySelector('[data-payment-field="received-at"]');
            const headerRow = partyField?.parentElement || null;
            const payeeBlock = document.getElementById("create-cheque-payee-block");
            const payeeFields = document.getElementById("create-cheque-payee-fields");

            /**
             * The cheque form, in the order the questions are actually asked.
             *
             * نوع چک decides the shape, so it comes first, with شماره چک beside
             * it. Then «اطلاعات گیرنده» — who this cheque goes to, and the one
             * or two facts that belong to that side of it.
             *
             * Which of those facts appear differs by kind, and neither omission
             * is cosmetic:
             *
             * «چک مشتری» hands on an instrument already recorded, so its amount
             * is the cheque's own and asking for it again would invite a figure
             * that disagrees with the document being spent. It takes a payment
             * date instead.
             *
             * «چک تازه» writes a new instrument, so it needs an amount — and it
             * has no payment date, because nothing has been paid yet: the cheque
             * carries a due date of its own, which is already in its details.
             */
            function applyChequeSource() {
                const onCheque = methodField.value === "cheque";
                const spending =
                    direction === "disbursement" &&
                    onCheque &&
                    chequeSource &&
                    chequeSource.value === "customer_endorsed";
                if (existingChequeRow) existingChequeRow.hidden = !spending;
                if (newChequeFields) newChequeFields.hidden = !onCheque || spending;
                if (chequeNote) chequeNote.hidden = !onCheque || spending;

                // Only the disbursement desk is rearranged. A cheque taken in
                // is still a receipt with a party, an amount and the date it
                // arrived — moving those under «اطلاعات گیرنده» would name the
                // customer who paid us as the recipient, and hiding the date
                // would take away the one this desk exists to record.
                const grouped = onCheque && direction === "disbursement";
                if (payeeBlock && payeeFields && headerRow) {
                    payeeBlock.hidden = !grouped;
                    const host = grouped ? payeeFields : headerRow;
                    [partyField, amountField, dateField].forEach((field) => {
                        if (field && field.parentElement !== host) host.append(field);
                    });
                    if (amountField) amountField.hidden = grouped && spending;
                    if (dateField) dateField.hidden = grouped && !spending;
                }
                // A hidden required field blocks submission with a message the
                // reader cannot see the field for, so `required` follows what is
                // on screen rather than staying pinned to the markup.
                const amountInput = document.getElementById("create-payment-amount");
                if (amountInput) amountInput.required = !(grouped && spending);
            }

            if (chequeSource) chequeSource.addEventListener("change", applyChequeSource);

            modeButtons.forEach((button) => {
                button.addEventListener("click", () => {
                    selectMode(button.dataset.paymentMode);
                    // The method is now its own first step with nothing else
                    // to answer on it (product-owner request 2026-09-12), so
                    // choosing one advances the wizard the same way clicking
                    // «بعدی» would — a real click on that same button rather
                    // than calling the stepper API directly, so the existing
                    // validation/scroll-reset/`onReachLastStep` wiring
                    // (`setupWizard` above) runs exactly as it does for an
                    // explicit click.
                    createForm.querySelector('[data-kt-stepper-action="next"]')?.click();
                });
            });

            selectMode("cash");
            setupSearchableSelects(createForm);

            function renderPaymentReview() {
                const method = methodField.value;
                const methodLabel = {cash: "نقدی", bank_transfer: "حواله بانکی", cheque: "چک"}[method] || method;
                const spending =
                    direction === "disbursement" &&
                    method === "cheque" &&
                    chequeSource &&
                    chequeSource.value === "customer_endorsed";
                const rows = [["روش", methodLabel]];
                if (spending) {
                    const chequeSelect = document.getElementById("create-cheque-existing-id");
                    rows.push(["شماره چک", selectedOptionText(chequeSelect)]);
                    rows.push(["گیرنده", document.getElementById("create-payment-customer-search").value || "—"]);
                } else {
                    rows.push([
                        direction === "disbursement" ? "گیرنده" : "مشتری",
                        document.getElementById("create-payment-customer-search").value ||
                            selectedOptionText(document.getElementById("create-payment-customer")),
                    ]);
                    if (!amountField.hidden) rows.push(["مبلغ", createForm.amount.value || "—"]);
                    if (!dateField.hidden) rows.push([direction === "disbursement" ? "تاریخ پرداخت" : "تاریخ دریافت", createForm.received_at.value || "امروز"]);
                }
                if (method === "bank_transfer") {
                    rows.push(["شماره پیگیری", createForm.reference.value || "—"]);
                    rows.push([direction === "disbursement" ? "بانک مبدأ" : "بانک مقصد", createForm.bank_name.value || "—"]);
                }
                if (method === "cheque" && !spending) {
                    rows.push([direction === "disbursement" ? "بانک مقصد" : "بانک مبدأ", createForm.cheque_bank_name.value || "—"]);
                    rows.push(["شماره چک", createForm.cheque_serial_number.value || "—"]);
                    rows.push(["تاریخ سررسید چک", createForm.cheque_due_date.value || "—"]);
                }
                rows.push(["یادداشت", createForm.notes.value || "—"]);
                renderWizardReview(document.getElementById("create-payment-review"), rows);
            }
            const paymentWizard = setupWizard(dialog, {onReachLastStep: renderPaymentReview});

            document.getElementById("open-create-payment").addEventListener("click", () => {
                createForm.reset();
                clearMessages(createForm);
                selectMode("cash");
                paymentWizard?.goFirst();
                dialog.showModal();
            });
            dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
            createForm.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(createForm, async () => {
                    const data = new FormData(createForm);
                    const method = String(data.get("method"));
                    const chosenCustomer = String(data.get("customer") || "");
                    const spendingExisting =
                        direction === "disbursement" &&
                        method === "cheque" &&
                        chequeSource &&
                        chequeSource.value === "customer_endorsed";

                    // Handing on a cheque already recorded is not a new payment.
                    // It is the same instrument moving, so it goes to the spend
                    // endpoint — creating a second document here would count the
                    // same money twice everywhere it is summed.
                    if (spendingExisting) {
                        const chequeId = String(data.get("cheque_existing") || "");
                        if (!chequeId) {
                            const slot = createForm.querySelector('[data-error-for="cheque_existing"]');
                            if (slot) slot.textContent = "یک چک را انتخاب کنید.";
                            return;
                        }
                        const payee = chosenCustomer
                            ? (document.getElementById("create-payment-customer-search").value || "")
                            : "";
                        if (!payee) {
                            const slot = createForm.querySelector('[data-error-for="customer"]');
                            if (slot) slot.textContent = "گیرنده را انتخاب کنید.";
                            return;
                        }
                        // No amount and no document: the instrument already
                        // carries its figure, and spending it is a state change
                        // on that row. It reaches this desk because the payments
                        // list includes receipts whose cheque has been spent —
                        // where it reads «خرج شده», the cheque's own status.
                        await apiRequest(`/api/v1/cheques/${chequeId}/spend/`, {
                            method: "POST",
                            body: {payee, reason: String(data.get("notes") || "")},
                        });
                        window.location.assign("/disbursements/");
                        return;
                    }

                    const payload = {
                        method,
                        direction,
                        amount: moneyValue(data.get("amount")),
                        notes: String(data.get("notes") || ""),
                    };
                    // A reference exists on a transfer and nowhere else, so it
                    // is only sent from there — a value left over from another
                    // method would otherwise be filed against cash.
                    if (method === "bank_transfer") {
                        payload.reference = String(data.get("reference") || "");
                    }
                    // Omitted rather than null when a disbursement names nobody:
                    // the field is optional there, and sending an empty value is
                    // a different claim from not sending one.
                    if (chosenCustomer) payload.customer = Number(chosenCustomer);
                    if (direction === "disbursement") {
                        // The party is one field on this form. On a disbursement
                        // the name typed into it is who was paid.
                        payload.payee =
                            document.getElementById("create-payment-customer-search").value.trim() ||
                            "گیرنده";
                    }
                    // Blank means "today" on the server, which is what an
                    // operator recording a receipt as it happens expects.
                    const receivedAt = apiDateTime(textOrNull(data.get("received_at")));
                    if (receivedAt) payload.received_at = receivedAt;

                    // Only ever sent for a transfer. The service refuses these
                    // on any other method, and a hidden field left populated
                    // from a previous mode would otherwise be submitted.
                    if (method === "bank_transfer") {
                        payload.bank_name = String(data.get("bank_name") || "");
                    }
                    if (method === "cheque") {
                        payload.cheque = {
                            bank_name: String(data.get("cheque_bank_name") || ""),
                            bank_account: String(data.get("cheque_bank_account") || ""),
                            branch_name: String(data.get("cheque_branch_name") || ""),
                            serial_number: String(data.get("cheque_serial_number") || ""),
                            due_date: apiDate(data.get("cheque_due_date")) || "",
                            registered_on: apiDate(data.get("cheque_registered_on")) || null,
                            // Always unregistered on arrival, whichever desk
                            // wrote it. Both axes are moved by hand from the
                            // cheque page and nowhere else, so this form cannot
                            // put an instrument into a state nobody chose.
                            is_registered: false,
                        };
                        if (direction === "disbursement") {
                            payload.cheque.source = "own";
                        }
                    }
                    const payment = await apiRequest(createForm.action, {method: "POST", body: payload});
                    window.location.assign(`/payments/${payment.id}/`);
                });
            });
        }
        try {
            await loadCustomerOptions(
                document.getElementById("create-payment-customer"),
                document.body.dataset.paymentDirection === "disbursement"
                    ? "یک گیرنده انتخاب کنید"
                    : "یک مشتری انتخاب کنید",
            );
            // The cheques this desk may hand on: taken in from a customer and
            // still waiting. A cleared one is spent money and a spent one is
            // already gone, so neither is offered — the same rule the service
            // enforces, asked of the API rather than restated here.
            const existing = document.getElementById("create-cheque-existing-id");
            if (existing) {
                const rows = await loadAllPages(
                    "/api/v1/cheques/?status=pending&ordering=due_date",
                );
                fillSelect(
                    existing,
                    rows.filter((row) => row.source !== "own"),
                    (row) =>
                        `${row.serial_number} — ${row.bank_name} — ${money(row.amount)}` +
                        (row.customer_name ? ` — ${row.customer_name}` : ""),
                    "یک چک انتخاب کنید",
                );
            }
            setupSearchableSelects(document.getElementById("create-payment-form") || document);
        } catch (error) {
            showError(error);
        }
        controller = setupPagedList({
            key: "payments",
            form,
            search: document.getElementById("payment-search"),
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page)});
                const search = document.getElementById("payment-search").value.trim();
                if (search) query.set("search", search);
                // `desk`, not `direction`. A cheque taken in and later handed
                // on is one document that belongs on both screens — still the
                // receipt it was, and also money that has left — so the paying
                // desk asks for a desk rather than for a direction. The server
                // decides what that means; nothing here duplicates the rule.
                query.set(
                    "desk",
                    document.body.dataset.paymentDirection === "disbursement"
                        ? "disbursement"
                        : "receipt",
                );
                const method = document.getElementById("payment-method-filter").value;
                if (method) query.set("method", method);
                query.set("ordering", document.getElementById("payment-ordering").value);
                return `/api/v1/payments/?${query}`;
            },
            renderRow: paymentRow,
        });
        controller.load();
    }

    async function setupPaymentDetail() {
        const paymentId = document.body.dataset.paymentId;
        const endpoint = `/api/v1/payments/${paymentId}/`;
        const loading = document.getElementById("payment-detail-loading");
        const content = document.getElementById("payment-detail-content");
        const allocateSection = document.getElementById("payment-allocate-section");
        const allocateForm = document.getElementById("payment-allocate-form");
        let payment;
        let allocationsController = null;
        //: The invoices this payment may settle, held here rather than read back
        //: out of a select on the page. Every allocation row is built from this
        //: one list, so no two rows can offer different invoices.
        let allocatableInvoices = [];

        function apply(value) {
            payment = value;
            document.getElementById("payment-number").value = payment.number;
            document.getElementById("payment-method").value = labelled(PAYMENT_METHOD_TEXT, payment.method);
            document.getElementById("payment-received-by").value = payment.received_by_display || payment.received_by;

            // The party. On a disbursement with no customer the select holds
            // nothing and the payee is what names it, so the label follows.
            const customerSelect = document.getElementById("payment-customer");
            const customerSearch = document.getElementById("payment-customer-search");
            const isDisbursement = payment.direction === "disbursement";
            const partyLabel = document.querySelector('label[for="payment-customer-search"]');
            if (partyLabel) partyLabel.textContent = isDisbursement ? "گیرنده" : "مشتری";
            if (customerSelect) {
                customerSelect.value = payment.customer ? String(payment.customer) : "";
                if (customerSearch) {
                    customerSearch.value = payment.customer_name || payment.payee || "";
                }
            }

            // Two values, and the one it currently holds. A payment still
            // pending on a cheque shows as confirmed here only once it is; until
            // then the select simply carries no match, which is honest — the
            // status is not the operator's to set while the cheque decides it.
            const statusSelect = document.getElementById("payment-status");
            if (statusSelect) {
                statusSelect.value = payment.status;
                // Cancelling is one-way. Once a document is cancelled it is
                // recorded anew rather than revived, so «تأییدشده» is disabled
                // instead of being offered and then refused by the server.
                const confirmOption = statusSelect.querySelector('option[value="confirmed"]');
                if (confirmOption) {
                    confirmOption.disabled = payment.status === "cancelled";
                }
            }

            document.getElementById("payment-amount").value = money(payment.amount);
            document.getElementById("payment-received-at").value = displayDate(payment.received_at);
            document.getElementById("payment-reference").value = payment.reference || "";
            const bankName = document.getElementById("payment-bank-name");
            if (bankName) bankName.value = payment.bank_name || "";
            document.getElementById("payment-notes").value = payment.notes || "";

            // A reference belongs to a transfer, and so does the bank. On cash
            // and on a cheque the rows are absent rather than empty.
            const referenceRow = document.querySelector('[data-payment-detail="reference"]');
            if (referenceRow) referenceRow.hidden = payment.method !== "bank_transfer";
            const bankRow = document.querySelector('[data-payment-detail="bank"]');
            if (bankRow) bankRow.hidden = payment.method !== "bank_transfer";
            const chequeBlock = document.getElementById("payment-cheque-block");
            if (chequeBlock) {
                const cheque = payment.cheque_detail;
                chequeBlock.hidden = !cheque;
                if (cheque) {
                    document.getElementById("payment-cheque-bank").value = cheque.bank_name;
                    document.getElementById("payment-cheque-serial").value = cheque.serial_number;
                    document.getElementById("payment-cheque-due").value = displayDay(cheque.due_date);
                    document.getElementById("payment-cheque-status").value = labelled(CHEQUE_STATUS_TEXT, cheque.status);
                    // Both axes are shown, and neither is editable from here.
                    const registration = document.getElementById("payment-cheque-registration");
                    if (registration) {
                        registration.value = labelled(
                            CHEQUE_REGISTRATION_TEXT,
                            String(Boolean(cheque.is_registered)),
                        );
                    }
                }
            }
            // The document's own status is hidden on a cheque. There the
            // cheque's status is the one that describes where the money is, and
            // two controls answering the same question differently is worse than
            // one — spending a cheque closes the receipt it arrived on, so this
            // one would read «ابطال‌شده» for a cheque that is alive.
            const statusRow = document.querySelector('[data-payment-detail="status"]');
            if (statusRow) statusRow.hidden = payment.method === "cheque";
            if (allocateSection) allocateSection.hidden = payment.status !== "confirmed";
            if (payment.status === "confirmed") allocationsController?.load();
        }

        // --- تخصیص به فاکتور -----------------------------------------------
        //
        // One form, whatever the arity. There used to be two — "allocate to an
        // invoice" and "split between several" — under separate headings, which
        // asked the reader to work out that they were the same operation. A
        // single invoice is the one-row case of a split, and it posts through
        // the same endpoint and the same server rules either way.
        const splitRows = document.getElementById("payment-split-rows");
        const splitTotal = document.getElementById("payment-split-total");

        function refreshSplitTotal() {
            if (!splitRows || !splitTotal) return;
            let sum = 0;
            let anyBlank = false;
            splitRows.querySelectorAll("[data-split-amount]").forEach((input) => {
                const value = moneyOrNull(input.value);
                if (value === null) anyBlank = true;
                else sum += Number(value);
            });
            // A blank row takes "whatever the invoice still owes", which is not
            // known here, so the total is reported as at-least rather than as a
            // figure that would be wrong.
            splitTotal.textContent = sum === 0 && anyBlank ? "—" : (anyBlank ? "حداقل " : "") + money(sum);
        }

        function addSplitRow() {
            if (!splitRows) return;
            const row = document.createElement("div");
            row.className = "d-flex flex-wrap align-items-center gap-3";
            row.dataset.splitRow = "";
            // A searchable invoice, because the one thing a reader knows is
            // its number. The plain select showed nothing usable once a customer
            // had more than a handful of open invoices and could not be typed
            // into at all. The real `<select>` stays underneath and is still what
            // is read on submit, so nothing below this cares.
            const picker = document.createElement("div");
            picker.className = "searchable-select w-auto flex-grow-1";
            picker.setAttribute("data-searchable-select", "");
            const search = document.createElement("input");
            search.className = "form-control form-control-solid";
            search.type = "search";
            search.autocomplete = "off";
            search.placeholder = "شماره فاکتور را بنویسید…";
            search.setAttribute("data-searchable-input", "");
            search.setAttribute("role", "combobox");
            search.setAttribute("aria-label", "جستجوی فاکتور");
            search.hidden = true;
            const select = document.createElement("select");
            select.className = "form-select form-select-solid";
            select.dataset.splitInvoice = "";
            select.setAttribute("data-searchable-source", "");
            select.setAttribute("aria-label", "فاکتور");
            fillSelect(
                select,
                allocatableInvoices,
                (invoice) => `${invoice.number} — مانده ${money(invoice.balance_due)}`,
                "یک فاکتور انتخاب کنید",
            );
            const options = document.createElement("ul");
            options.className = "searchable-select-options";
            options.setAttribute("role", "listbox");
            options.hidden = true;
            picker.append(search, select, options);
            const amount = document.createElement("input");
            amount.className = "form-control form-control-solid w-auto flex-grow-1";
            amount.type = "text";
            amount.inputMode = "numeric";
            amount.dir = "ltr";
            amount.placeholder = "مبلغ به ریال (خالی = مانده فاکتور)";
            amount.setAttribute("data-money-input", "");
            amount.dataset.splitAmount = "";
            amount.setAttribute("aria-label", "مبلغ");
            amount.addEventListener("input", refreshSplitTotal);
            const remove = document.createElement("button");
            remove.className = "btn btn-icon btn-light-danger";
            remove.type = "button";
            remove.textContent = "×";
            remove.setAttribute("aria-label", "حذف سطر");
            remove.addEventListener("click", () => {
                row.remove();
                refreshSplitTotal();
            });
            row.append(picker, amount, remove);
            splitRows.append(row);
            // Money grouping is wired once per input by the shared helper, which
            // guards against binding the same field twice.
            setupMoneyInputs(row);
            setupSearchableSelects(row);
            refreshSplitTotal();
        }

        document.getElementById("payment-split-add")?.addEventListener("click", addSplitRow);

        allocateForm?.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(allocateForm, async () => {
                const splits = [];
                splitRows.querySelectorAll("[data-split-row]").forEach((row) => {
                    const invoice = Number(row.querySelector("[data-split-invoice]").value);
                    if (!invoice) return;
                    const entry = {invoice};
                    const amount = moneyOrNull(row.querySelector("[data-split-amount]").value);
                    if (amount !== null) entry.amount = amount;
                    splits.push(entry);
                });
                if (!splits.length) {
                    const slot = allocateForm.querySelector('[data-error-for="splits"]');
                    if (slot) slot.textContent = "حداقل یک فاکتور را انتخاب کنید.";
                    return;
                }
                await apiRequest(`${endpoint}allocate-across/`, {method: "POST", body: {splits}});
                globalMessage("دریافت به فاکتور تخصیص یافت.", true);
                splitRows.replaceChildren();
                addSplitRow();
                apply(await apiRequest(endpoint));
            });
        });

        // --- correcting a recorded document (بند: مدیر پلتفرم) --------------
        //
        // The controls are only enabled for the platform admin, and that is a
        // convenience: the endpoint and the service both check the role again,
        // because a field being editable on screen has never been the
        // authorisation for changing it.
        const editForm = document.getElementById("payment-edit-form");
        const saveButton = document.getElementById("save-payment-edit");
        if (editForm && saveButton) {
            loadCustomerOptions(
                document.getElementById("payment-customer"),
                "بدون طرف حساب",
            )
                .then(() => {
                    const select = document.getElementById("payment-customer");
                    if (payment && select) {
                        select.value = payment.customer ? String(payment.customer) : "";
                    }
                    setupSearchableSelects(editForm);
                })
                .catch(showError);

            editForm.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(editForm, async () => {
                    const data = new FormData(editForm);
                    const body = {
                        amount: moneyValue(data.get("amount")),
                        notes: String(data.get("notes") || ""),
                        status: String(data.get("status") || payment.status),
                    };
                    const chosen = String(data.get("customer") || "");
                    // Null, not omitted: on a disbursement clearing the party is
                    // a real edit, and the two are different claims.
                    body.customer = chosen ? Number(chosen) : null;
                    const receivedAt = apiDateTime(textOrNull(data.get("received_at")));
                    if (receivedAt) body.received_at = receivedAt;
                    if (payment.method === "bank_transfer") {
                        body.reference = String(data.get("reference") || "");
                        body.bank_name = String(data.get("bank_name") || "");
                    }
                    if (payment.method === "cheque") {
                        body.cheque = {
                            bank_name: String(data.get("cheque_bank_name") || ""),
                            serial_number: String(data.get("cheque_serial_number") || ""),
                        };
                        const due = apiDate(data.get("cheque_due_date"));
                        if (due) body.cheque.due_date = due;
                    }
                    apply(await apiRequest(`${endpoint}correct/`, {method: "POST", body}));
                    globalMessage("تغییرات ذخیره شد.", true);
                });
            });
        } else if (editForm) {
            // No save button means this reader may not correct anything, so the
            // controls are made read-only rather than left looking usable.
            editForm.querySelectorAll("input, select, textarea").forEach((field) => {
                field.disabled = true;
            });
        }

        allocationsController = setupPagedList({
            key: "payment-allocations",
            form: null,
            endpoint: (page) => `${endpoint}allocations/?page=${page}`,
            renderRow: (allocation) => {
                const row = document.createElement("tr");
                appendCell(row, allocation.invoice_number).dir = "ltr";
                appendMoneyCell(row, allocation.amount);
                appendCell(row, allocation.is_reversed ? "آزادشده" : "فعال");
                appendCell(row, displayDay(allocation.created_at));
                const actions = document.createElement("td");
                actions.className = "row-actions";
                if (!allocation.is_reversed) {
                    const release = document.createElement("button");
                    release.type = "button";
                    release.className = "btn btn-sm btn-light";
                    release.textContent = "آزادکردن";
                    release.addEventListener("click", async () => {
                        if (!window.confirm("این تخصیص آزاد شود؟")) return;
                        release.disabled = true;
                        try {
                            await apiRequest(`/api/v1/payment-allocations/${allocation.id}/release/`, {method: "POST"});
                            globalMessage("تخصیص آزاد شد.", true);
                            apply(await apiRequest(endpoint));
                        } catch (error) {
                            release.disabled = false;
                            showError(error);
                        }
                    });
                    actions.appendChild(release);
                }
                row.appendChild(actions);
                return row;
            },
        });

        try {
            const value = await apiRequest(endpoint);
            if (value.customer) {
                const invoices = await loadAllPages(
                    `/api/v1/invoices/?status=issued&customer=${value.customer}&ordering=due_at`
                );
                allocatableInvoices = invoices.filter(
                    (invoice) => Number(invoice.balance_due) > 0,
                );
            }
            apply(value);
            // One row to start with, so the common case — settle this against
            // that invoice — is a form that is already there rather than one the
            // reader has to summon with «افزودن فاکتور» first.
            if (splitRows && !splitRows.children.length) addSplitRow();
            loading.hidden = true;
            content.hidden = false;
        } catch (error) {
            loading.hidden = true;
            showError(error);
        }
    }

    function setupCheques() {
        // Endorsing a cheque onward. Kept beside the transition dialog rather
        // than folded into it: this action needs a recipient, and a dropdown
        // that sometimes demands a second field is worse than two buttons.
        const spendDialog = document.getElementById("spend-cheque-dialog");
        const spendForm = document.getElementById("spend-cheque-form");
        let spendingCheque = null;

        const form = document.getElementById("cheque-search-form");
        setupListFilter("cheque");
        const dialog = document.getElementById("cheque-transition-dialog");
        const transitionForm = document.getElementById("cheque-transition-form");
        const targetSelect = document.getElementById("cheque-transition-target");
        let controller = null;
        let currentCheque = null;

        dialog?.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        transitionForm?.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(transitionForm, async () => {
                await apiRequest(`/api/v1/cheques/${currentCheque.id}/transition/`, {
                    method: "POST",
                    body: {
                        to_status: targetSelect.value,
                        reason: document.getElementById("cheque-transition-reason").value,
                    },
                });
                dialog.close();
                globalMessage("وضعیت چک ثبت شد.", true);
                controller?.load();
            });
        });

        controller = setupPagedList({
            key: "cheques",
            form,
            search: document.getElementById("cheque-search"),
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page)});
                const search = document.getElementById("cheque-search").value.trim();
                if (search) query.set("search", search);
                const status = document.getElementById("cheque-status-filter").value;
                if (status) query.set("status", status);
                query.set("ordering", document.getElementById("cheque-ordering").value);
                return `/api/v1/cheques/?${query}`;
            },
            renderRow: (cheque) => {
                const row = document.createElement("tr");
                appendCell(row, cheque.bank_name);
                appendCell(row, cheque.bank_account || "—").dir = "ltr";
                appendCell(row, cheque.serial_number).dir = "ltr";
                appendCell(row, cheque.customer_name);
                appendMoneyCell(row, cheque.amount);
                appendCell(row, displayDay(cheque.due_date));
                appendStatusBadgeCell(row, CHEQUE_STATUS_TEXT, cheque.status);
                // حالت is the other axis and gets its own column, because a
                // reader scanning for unregistered cheques should not have to
                // open each one to find out.
                appendStatusBadgeCell(
                    row,
                    CHEQUE_REGISTRATION_TEXT,
                    String(Boolean(cheque.is_registered)),
                );

                // --- وضعیت: one button per destination ----------------------
                //
                // Four buttons rather than a dropdown behind a «تغییر وضعیت»
                // button. The four are the whole vocabulary of this axis, so
                // naming them costs one row of the table and saves two clicks
                // and a guess every time.
                //
                // A destination the status graph refuses is shown disabled
                // rather than hidden: a button that appears and disappears as
                // rows change state reads as a rendering fault, and the reader
                // learns nothing about why it cannot be pressed. The server
                // refuses the same jumps regardless — this only spares the trip.
                const actions = document.createElement("td");
                actions.className = "row-actions";
                const allowed = CHEQUE_TRANSITIONS[cheque.status] || [];

                [
                    ["bounced", "برگشت"],
                    ["spent", "خرج کردن"],
                    ["cleared", "وصول"],
                    ["pending", "در انتظار"],
                ].forEach(([target, label]) => {
                    const button = document.createElement("button");
                    button.type = "button";
                    button.className = "btn btn-sm btn-light";
                    button.textContent = label;
                    const reachable = allowed.includes(target);
                    button.disabled = !reachable;
                    if (!reachable) {
                        button.title = `از «${labelled(CHEQUE_STATUS_TEXT, cheque.status)}» نمی‌توان به «${label}» رفت.`;
                    }
                    button.addEventListener("click", async () => {
                        // Spending needs a second answer the others do not —
                        // who it went to — so it asks before it acts.
                        if (target === "spent") {
                            if (!spendDialog) return;
                            spendingCheque = cheque;
                            document.getElementById("spend-cheque-payee").value = "";
                            document.getElementById("spend-cheque-reason").value = "";
                            clearMessages(spendForm);
                            spendDialog.showModal();
                            return;
                        }
                        button.disabled = true;
                        try {
                            await apiRequest(`/api/v1/cheques/${cheque.id}/transition/`, {
                                method: "POST",
                                body: {to_status: target},
                            });
                            globalMessage(`وضعیت چک به «${label}» تغییر کرد.`, true);
                            controller.load();
                        } catch (error) {
                            button.disabled = false;
                            showError(error);
                        }
                    });
                    actions.appendChild(button);
                });
                row.appendChild(actions);

                // --- عملیات ثبت: registered, or not, as a two-way toggle ----
                //
                // Two icon buttons rather than two text buttons (product-
                // owner request 2026-09-12: "ثبت شده"/"ثبت نشده" side by side
                // read as two separate actions, not one on/off switch). A
                // check and a cross are the whole vocabulary of this axis —
                // the same reasoning the four وضعیت buttons above already
                // follow — kept in their own cell so the column width stays
                // put as state changes.
                const registration = document.createElement("td");
                registration.className = "row-actions";
                [
                    [true, "check", 1, "ثبت‌شده علامت بزن", "success"],
                    [false, "cross", 2, "ثبت‌نشده علامت بزن", "danger"],
                ].forEach(([target, icon, iconPaths, label, accent]) => {
                    const button = document.createElement("button");
                    button.type = "button";
                    const current = Boolean(cheque.is_registered) === target;
                    button.className = `btn btn-icon btn-sm ${current ? `btn-${accent}` : "btn-light"}`;
                    button.setAttribute("aria-label", label);
                    button.title = label;
                    const glyph = document.createElement("i");
                    glyph.className = `ki-duotone ki-${icon} fs-3`;
                    for (let index = 1; index <= iconPaths; index += 1) {
                        const path = document.createElement("span");
                        path.className = `path${index}`;
                        glyph.appendChild(path);
                    }
                    button.appendChild(glyph);
                    // The state it already holds is shown as the pressed one
                    // rather than removed, so both remain readable as a pair.
                    button.disabled = current;
                    button.setAttribute("aria-pressed", String(current));
                    button.addEventListener("click", async () => {
                        button.disabled = true;
                        try {
                            await apiRequest(`/api/v1/cheques/${cheque.id}/registration/`, {
                                method: "POST",
                                body: {is_registered: target},
                            });
                            globalMessage(`حالت چک به «${target ? "ثبت شده" : "ثبت نشده"}» تغییر کرد.`, true);
                            controller.load();
                        } catch (error) {
                            button.disabled = false;
                            showError(error);
                        }
                    });
                    registration.appendChild(button);
                });
                row.appendChild(registration);
                return row;
            },
        });
        spendDialog?.querySelectorAll("[data-close-dialog]").forEach((button) =>
            button.addEventListener("click", () => spendDialog.close()),
        );
        document.getElementById("confirm-spend-cheque")?.addEventListener("click", async () => {
            if (!spendingCheque) return;
            const payee = document.getElementById("spend-cheque-payee").value.trim();
            if (!payee) {
                const slot = spendForm.querySelector('[data-error-for="payee"]');
                if (slot) slot.textContent = "گیرنده را وارد کنید.";
                return;
            }
            clearMessages(spendForm);
            try {
                await apiRequest(`/api/v1/cheques/${spendingCheque.id}/spend/`, {
                    method: "POST",
                    body: {payee, reason: document.getElementById("spend-cheque-reason").value},
                });
                spendDialog.close();
                globalMessage("چک خرج شد.", true);
                controller.load();
            } catch (error) {
                showError(error, spendForm);
            }
        });

        controller.load();
    }

    function setupInstallments() {
        const form = document.getElementById("installment-search-form");
        setupListFilter("installment");
        const controller = setupPagedList({
            key: "installments",
            form,
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page)});
                const status = document.getElementById("installment-status-filter").value;
                if (status) query.set("status", status);
                const dueBefore = document.getElementById("installment-due-before").value;
                if (dueBefore) query.set("due_before", apiDate(dueBefore));
                query.set("ordering", document.getElementById("installment-ordering").value);
                return `/api/v1/installments/?${query}`;
            },
            renderRow: (installment) => {
                const row = document.createElement("tr");
                appendCell(row, installment.plan);
                appendCell(row, installment.sequence);
                appendCell(row, displayDay(installment.due_date));
                appendMoneyCell(row, installment.amount);
                appendMoneyCell(row, installment.paid_amount);
                appendMoneyCell(row, installment.balance_due);
                appendStatusBadgeCell(row, INSTALLMENT_STATUS_TEXT, installment.status);
                appendActionLinks(row, []);
                return row;
            },
        });
        controller.load();
    }

    // --- Customer ledger -----------------------------------------------------

    async function setupCustomerLedger() {
        const filterForm = document.getElementById("ledger-filter-form");
        const openingForm = document.getElementById("opening-balance-form");
        const customerSelect = document.getElementById("ledger-customer");
        const balanceNode = document.getElementById("ledger-balance");
        const nameNode = document.getElementById("ledger-customer-name");
        const loading = document.getElementById("ledger-entries-loading");
        let controller = null;
        let customers = [];

        openingForm?.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(openingForm, async () => {
                const data = new FormData(openingForm);
                await apiRequest(openingForm.action, {method: "POST", body: {
                    customer: Number(data.get("customer")),
                    amount: moneyValue(data.get("amount")),
                    notes: String(data.get("notes") || ""),
                }});
                globalMessage("مانده اول دوره ثبت شد.", true);
                openingForm.reset();
                if (customerSelect.value) refresh();
            });
        });

        async function refresh() {
            if (!customerSelect.value) return;
            loading.hidden = true;
            try {
                const balance = await apiRequest(`/api/v1/customer-ledger/balance/?customer=${customerSelect.value}`);
                balanceNode.textContent = money(balance.balance);
                const match = customers.find((row) => row.id === Number(customerSelect.value));
                nameNode.textContent = match ? match.full_name : "—";
                controller?.load();
            } catch (error) {
                showError(error);
            }
        }

        filterForm.addEventListener("submit", (event) => {
            event.preventDefault();
            refresh();
        });

        controller = setupPagedList({
            key: "ledger-entries",
            form: null,
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page), customer: customerSelect.value});
                const entryType = document.getElementById("ledger-entry-type").value;
                if (entryType) query.set("entry_type", entryType);
                return `/api/v1/customer-ledger/?${query}`;
            },
            renderRow: (entry) => {
                const row = document.createElement("tr");
                appendCell(row, displayDate(entry.occurred_at));
                appendCell(row, labelled(LEDGER_ENTRY_TEXT, entry.entry_type));
                appendCell(row, entry.reference_number || "—").dir = "ltr";
                appendMoneyCell(row, Number(entry.debit) > 0 ? entry.debit : "");
                appendMoneyCell(row, Number(entry.credit) > 0 ? entry.credit : "");
                appendMoneyCell(row, entry.balance_after);
                appendCell(row, entry.created_by_display || entry.created_by);
                return row;
            },
        });

        try {
            customers = await loadCustomerOptions(customerSelect, "یک مشتری انتخاب کنید");
            fillSelect(
                document.getElementById("opening-balance-customer"),
                customers,
                (row) => row.full_name,
                "یک مشتری انتخاب کنید",
            );
        } catch (error) {
            showError(error);
        }
    }

    // --- Financial reports ---------------------------------------------------

    function reportSection(prefix) {
        return {
            loading: document.getElementById(`${prefix}-loading`),
            empty: document.getElementById(`${prefix}-empty`),
            wrap: document.getElementById(`${prefix}-table-wrap`),
            body: document.getElementById(`${prefix}-table-body`),
        };
    }

    function renderReportRows(prefix, rows, renderRow) {
        const nodes = reportSection(prefix);
        nodes.body.replaceChildren(...rows.map(renderRow));
        nodes.loading.hidden = true;
        nodes.empty.hidden = rows.length > 0;
        nodes.wrap.hidden = rows.length === 0;
    }

    /**
     * Where the outstanding money is sitting, by age.
     *
     * The five buckets are a fixed sequence running from not-yet-due to more
     * than ninety days late, so this neither sorts nor drops empties: an
     * ageing chart reordered by size would say nothing, and a missing bucket
     * is the reader's good news.
     */
    function renderReceivablesAgingChart(buckets) {
        const order = [
            ["سررسید نشده", buckets.not_due],
            ["۱ تا ۳۰ روز", buckets.days_1_30],
            ["۳۱ تا ۶۰ روز", buckets.days_31_60],
            ["۶۱ تا ۹۰ روز", buckets.days_61_90],
            ["بیش از ۹۰ روز", buckets.days_over_90],
        ];
        renderBarChart(
            document.getElementById("receivables-aging-chart"),
            document.getElementById("receivables-aging-chart-empty"),
            order.map(([label, amount]) => ({
                label,
                value: Number(amount),
                display: money(amount),
            })),
            {
                sort: false,
                keepZero: true,
                ariaLabel: "نمودار سنی مطالبات در پنج بازه سررسید",
                // Not decoration: the buckets run from "not yet due" to "over
                // ninety days", so the colour carries the same order the reader
                // is already looking for.
                colorBy: (item, index) => severityRamp()[index] || severityRamp()[0],
            },
        );
    }

    /**
     * Revenue against cost against gross profit, for the period.
     *
     * Three bars rather than a ratio, because the question a reader brings to
     * this page is how much of the revenue the cost ate. Not sorted: revenue is
     * always the largest and the sequence is the comparison.
     *
     * Profit can be negative, and the renderer draws no bar below zero. The
     * figure is still printed beside the empty track, and the summary card
     * above carries it too, so a loss is never hidden — it simply has no bar.
     */
    function renderProfitCompositionChart(report) {
        const order = [
            ["درآمد", report.revenue],
            ["بهای تمام‌شده", report.cost],
            ["سود ناخالص", report.profit],
        ];
        renderBarChart(
            document.getElementById("profit-composition-chart"),
            document.getElementById("profit-composition-chart-empty"),
            order.map(([label, amount]) => ({
                label,
                value: Math.max(0, Number(amount)),
                display: money(amount),
            })),
            {
                sort: false,
                keepZero: true,
                // Revenue is the whole, cost is what it ate, profit is what
                // survived — so cost is warned and profit is green.
                colorBy: (item, index) => {
                    const palette = chartPalette();
                    return [palette[0], palette[3], palette[1]][index] || palette[0];
                },
                ariaLabel: "نمودار مقایسه درآمد، بهای تمام‌شده و سود ناخالص",
            },
        );
    }

    /**
     * The ten products holding the most stock value.
     *
     * Sorted and capped, because a valuation report can run to hundreds of rows
     * and a bar per row is unreadable. The rest stay in the table below, which
     * is also the accessible alternative to this chart.
     */
    function renderValuationChart(rows) {
        const items = rows.map((row) => ({
            label: `${row.product_name} (${row.warehouse_name})`,
            value: Number(row.stock_value),
            display: money(row.stock_value),
        }));
        const drawn = Math.min(10, items.filter((item) => Number.isFinite(item.value) && item.value > 0).length);
        renderBarChart(
            document.getElementById("valuation-chart"),
            document.getElementById("valuation-chart-empty"),
            items,
            {
                limit: 10,
                ariaLabel: `نمودار ${toPersianDigits(String(drawn))} کالای با بیشترین ارزش موجودی`,
            },
        );
    }

    async function setupReceivablesReport() {
        const form = document.getElementById("receivables-filter-form");
        const exportLink = document.getElementById("receivables-export");
        bindReportTableSearch(
            document.getElementById("receivables-search"),
            [document.getElementById("receivables-table-body")],
        );

        function query() {
            const params = new URLSearchParams();
            const customer = document.getElementById("receivables-customer").value;
            if (customer) params.set("customer_id", customer);
            return params;
        }

        async function load() {
            const nodes = reportSection("receivables");
            nodes.loading.hidden = false;
            nodes.wrap.hidden = true;
            nodes.empty.hidden = true;
            clearMessages();
            const params = query();
            exportLink.href = `/api/v1/exports/receivables.xlsx${params.toString() ? `?${params}` : ""}`;
            try {
                const report = await apiRequest(`/api/v1/reports/receivables/?${params}`);
                document.getElementById("receivables-total").textContent = money(report.total_outstanding);
                document.getElementById("receivables-not-due").textContent = money(report.buckets.not_due);
                document.getElementById("receivables-1-30").textContent = money(report.buckets.days_1_30);
                document.getElementById("receivables-31-60").textContent = money(report.buckets.days_31_60);
                document.getElementById("receivables-61-90").textContent = money(report.buckets.days_61_90);
                document.getElementById("receivables-over-90").textContent = money(report.buckets.days_over_90);
                renderReceivablesAgingChart(report.buckets);
                renderReportRows("receivables", report.results, (item) => {
                    const row = document.createElement("tr");
                    appendCell(row, item.customer_name);
                    appendCell(row, item.invoice_count);
                    appendMoneyCell(row, item.total_outstanding);
                    appendMoneyCell(row, item.not_due);
                    appendMoneyCell(row, item.days_1_30);
                    appendMoneyCell(row, item.days_31_60);
                    appendMoneyCell(row, item.days_61_90);
                    appendMoneyCell(row, item.days_over_90);
                    appendActionLinks(row, [[`/invoices/?customer=${item.customer_id}`, "فاکتورها"]]);
                    return row;
                });
            } catch (error) {
                reportSection("receivables").loading.hidden = true;
                showError(error);
            }
        }

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            load();
        });
        try {
            await loadCustomerOptions(document.getElementById("receivables-customer"), "همه مشتریان");
        } catch (error) {
            showError(error);
        }
        load();
    }

    async function setupProfitReport() {
        const form = document.getElementById("profit-filter-form");
        const exportLink = document.getElementById("profit-export");
        bindReportTableSearch(
            document.getElementById("profit-search"),
            [document.getElementById("profit-table-body")],
        );
        const startField = document.getElementById("profit-period-start");
        const endField = document.getElementById("profit-period-end");

        // A month back to now, so the page shows real numbers on arrival rather
        // than an empty frame waiting for the operator to guess a range.
        const now = new Date();
        const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
        startField.value = localDateTimeValue(monthAgo.toISOString());
        endField.value = localDateTimeValue(now.toISOString());

        function query() {
            const params = new URLSearchParams();
            params.set("period_start", apiDateTime(startField.value));
            params.set("period_end", apiDateTime(endField.value));
            const customer = document.getElementById("profit-customer").value;
            if (customer) params.set("customer_id", customer);
            return params;
        }

        async function load() {
            const nodes = reportSection("profit");
            nodes.loading.hidden = false;
            nodes.wrap.hidden = true;
            nodes.empty.hidden = true;
            clearMessages();
            const params = query();
            exportLink.href = `/api/v1/exports/profit.xlsx?${params}`;
            try {
                const report = await apiRequest(`/api/v1/reports/profit/?${params}`);
                document.getElementById("profit-revenue").textContent = money(report.revenue);
                document.getElementById("profit-cost").textContent = money(report.cost);
                document.getElementById("profit-profit").textContent = money(report.profit);
                document.getElementById("profit-margin").textContent = `${report.margin_percent}٪`;
                document.getElementById("profit-measured").textContent = report.measured_invoice_count;
                document.getElementById("profit-unmeasured").textContent = report.unmeasured_invoice_count;
                renderProfitCompositionChart(report);
                renderReportRows("profit", report.results, (item) => {
                    const row = document.createElement("tr");
                    appendCell(row, item.number).dir = "ltr";
                    appendCell(row, item.customer_name);
                    appendCell(row, displayDate(item.issued_at));
                    appendMoneyCell(row, item.revenue);
                    appendMoneyCell(row, item.cost);
                    appendMoneyCell(row, item.profit);
                    appendCell(row, `${item.margin_percent}٪`);
                    appendActionLinks(row, [[`/invoices/${item.invoice_id}/`, "فاکتور"]]);
                    return row;
                });
            } catch (error) {
                reportSection("profit").loading.hidden = true;
                showError(error);
            }
        }

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            load();
        });
        try {
            await loadCustomerOptions(document.getElementById("profit-customer"), "همه مشتریان");
        } catch (error) {
            showError(error);
        }
        load();
    }

    async function setupStockValuationReport() {
        const form = document.getElementById("valuation-filter-form");
        const exportLink = document.getElementById("valuation-export");
        bindReportTableSearch(
            document.getElementById("valuation-search"),
            [document.getElementById("valuation-table-body")],
        );

        async function load() {
            const nodes = reportSection("valuation");
            nodes.loading.hidden = false;
            nodes.wrap.hidden = true;
            nodes.empty.hidden = true;
            clearMessages();
            const params = new URLSearchParams();
            const warehouse = document.getElementById("valuation-warehouse").value;
            if (warehouse) params.set("warehouse_id", warehouse);
            exportLink.href = `/api/v1/exports/stock-valuation.xlsx${params.toString() ? `?${params}` : ""}`;
            try {
                const report = await apiRequest(`/api/v1/reports/stock-valuation/?${params}`);
                document.getElementById("valuation-quantity").textContent = report.total_quantity;
                document.getElementById("valuation-value").textContent = money(report.total_value);
                renderValuationChart(report.results);
                renderReportRows("valuation", report.results, (item) => {
                    const row = document.createElement("tr");
                    appendCell(row, item.warehouse_name);
                    appendCell(row, item.product_sku).dir = "ltr";
                    appendCell(row, item.product_name);
                    appendCell(row, item.quantity);
                    appendMoneyCell(row, item.average_cost);
                    appendMoneyCell(row, item.stock_value);
                    return row;
                });
            } catch (error) {
                reportSection("valuation").loading.hidden = true;
                showError(error);
            }
        }

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            load();
        });
        try {
            await loadWarehouseOptions(document.getElementById("valuation-warehouse"), "همه انبارها");
        } catch (error) {
            showError(error);
        }
        load();
    }

    function setupDocumentPrint() {
        document.getElementById("print-document")?.addEventListener("click", () => window.print());
    }

    /**
     * Every `<dialog>` in the app (every "ثبت" wizard, every confirm/detail
     * modal) closes when the reader clicks outside it — product-owner
     * decision 2026-09-09. One listener for the whole app rather than one
     * per dialog: a click that lands on the dialog element itself, rather
     * than on anything inside it, is by construction a click on `::backdrop`
     * — `<dialog>` has no visible box beyond its own content, so a listener
     * on `document` whose `event.target` is exactly the open `<dialog>` (not
     * a descendant) is a backdrop click and nothing else. `showModal()`'s
     * own focus trap and Escape-to-close are untouched; this only adds the
     * third way a modal is expected to close.
     */
    function setupDialogBackdropClose() {
        document.addEventListener("click", (event) => {
            if (event.target instanceof HTMLDialogElement && event.target.open) {
                event.target.close();
            }
        });
    }

    setupJalaliInputs();
    setupNav();
    setupNavActiveState();
    setupSidebarAccordionScroll();
    setupLogout();
    setupUserMenu();
    setupSessionsDialog();
    setupDialogBackdropClose();

    // A denied page is served with the error card in place of its content, so
    // its module has no markup to bind to and every call it makes would be
    // refused anyway. Navigation and sign-out above still work; the module does
    // not run, which is what stopped an uncaught TypeError from being thrown
    // behind the Persian "دسترسی مجاز نیست" card.
    if (document.getElementById("app-error")) return;

    // Every price field on the page groups itself as it is typed. Bound once
    // here rather than per module, because a price is a price on whichever
    // screen it appears; dialogs are in the DOM at load, so they are covered.
    setupMoneyInputs();
    // Any searchable select present in the served markup. A page that fills its
    // options later calls this again for its own block; binding twice is a
    // no-op, so neither has to know about the other.

    /**
     * The theme row in the user menu, and the small popup beside it.
     *
     * `KTThemeMode` already binds the three buttons and does the switching; it
     * finds them by `data-kt-element` wherever they sit, so all that is left is
     * showing and hiding the popup and keeping the row's own label current.
     *
     * Opened on hover and on click. Hover alone would strand a touch screen,
     * where there is no hover at all, and a keyboard user who tabs to the row.
     */
    /**
     * The collapsed mark expands the sidebar.
     *
     * It defers to the real toggle rather than flipping the attribute itself,
     * so `KTToggle` stays the only thing that owns the state and writes the
     * cookie the server reads back. Two controls, one source of truth.
     */
    /**
     * The profile dialog, opened from the account menu on any page.
     *
     * Loaded on first open rather than on page load: it lives in the shell now,
     * so eagerly fetching it would add a request to every single screen for a
     * form most visits never touch. Loaded once and kept, because reopening it
     * to re-read what the reader just saved would be worse than stale.
     */
    function setupProfileDialog() {
        const dialog = document.getElementById("profile-dialog");
        const open = document.getElementById("open-profile");
        if (!dialog || !open) return;
        let loaded = false;

        open.addEventListener("click", async () => {
            dialog.showModal();
            if (loaded) return;
            loaded = true;
            try {
                await setupProfile();
            } catch (error) {
                // `setupProfile` reports its own failure into the dialog; this
                // only stops one bad load from wedging the button shut.
                loaded = false;
                showError(error);
            }
        });
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) =>
            button.addEventListener("click", () => dialog.close()),
        );
    }

    /**
     * Stops a collapse from immediately undoing itself.
     *
     * The toggle sits on the sidebar's outer edge but is a child of it, so the
     * pointer that just clicked "collapse" is still inside the sidebar when the
     * collapse finishes — and hover-to-peek reopens it at once. The sidebar
     * never narrows, so the toggle never moves out from under the pointer
     * either. Confirmed in a real browser: the click flipped the attribute and
     * the width stayed at its full 265px until the pointer moved.
     *
     * The theme knows about this and holds the peek off for 300ms with an
     * `.animating` class, which is long enough for the animation and not for a
     * pointer that simply stays where it is.
     *
     * Suspending it by taking `data-kt-app-sidebar-hoverable` off the body,
     * rather than by adding a class of our own, is what keeps this to one line
     * of effect: every peek rule in the theme is keyed on that attribute, so
     * dropping it turns off the widened width and the expanded contents
     * together. A class fighting `:hover` would have suppressed the width and
     * left the wide brand and labels rendering inside a 75px box.
     *
     * Only when the pointer is genuinely over the sidebar: reaching the toggle
     * by keyboard leaves no pointer to wait for, and a suspension nothing would
     * ever clear would disable the peek for the rest of the page's life.
     */
    function setupSidebarPeekGuard() {
        const sidebar = document.getElementById("app-sidebar");
        const toggle = document.getElementById("kt_app_sidebar_toggle");
        if (!sidebar || !toggle) return;

        const HOVERABLE = "data-kt-app-sidebar-hoverable";
        toggle.addEventListener("click", () => {
            if (!sidebar.matches(":hover")) return;
            document.body.removeAttribute(HOVERABLE);
        });
        sidebar.addEventListener("mouseleave", () => {
            document.body.setAttribute(HOVERABLE, "true");
        });
    }

    /**
     * Redraw every chart when the panel changes theme.
     *
     * `KTThemeMode` writes `data-bs-theme` on `<html>`, and does it both when a
     * mode is picked and when a reader on "system" changes their OS setting, so
     * watching the attribute covers both without knowing which happened.
     */
    function setupChartThemeRedraw() {
        const root = document.documentElement;
        let previous = root.getAttribute("data-bs-theme");
        const observer = new MutationObserver(() => {
            const current = root.getAttribute("data-bs-theme");
            // The theme's own code touches this attribute on its way to the
            // same value; a redraw per touch would be a visible flicker.
            if (current === previous) return;
            previous = current;
            chartRedraws.forEach((redraw, chart) => {
                // A chart whose page has been replaced under it is gone; its
                // entry would otherwise keep the detached node alive.
                if (!chart.isConnected) {
                    chartRedraws.delete(chart);
                    return;
                }
                redraw();
            });
        });
        observer.observe(root, {attributes: true, attributeFilter: ["data-bs-theme"]});
    }

    function setupThemeModePopup() {
        const item = document.querySelector("[data-theme-mode-item]");
        const trigger = document.getElementById("theme-mode-trigger");
        const popup = document.getElementById("theme-mode-popup");
        if (!item || !trigger || !popup) return;

        let hideTimer = null;

        function open() {
            window.clearTimeout(hideTimer);
            popup.hidden = false;
            trigger.setAttribute("aria-expanded", "true");
            // Which side has room is not knowable in advance: it depends on the
            // window width and where the user menu ended up. Measure once, and
            // flip only if the preferred side would put the popup off-screen.
            popup.classList.remove("is-flipped");
            const box = popup.getBoundingClientRect();
            if (box.left < 0 || box.right > window.innerWidth) {
                popup.classList.add("is-flipped");
            }
        }

        function close(delay = 0) {
            window.clearTimeout(hideTimer);
            hideTimer = window.setTimeout(() => {
                popup.hidden = true;
                trigger.setAttribute("aria-expanded", "false");
            }, delay);
        }

        item.addEventListener("mouseenter", open);
        item.addEventListener("mouseleave", () => close(180));
        trigger.addEventListener("click", (event) => {
            event.preventDefault();
            if (popup.hidden) open();
            else close();
        });

        // Choosing a mode closes the popup and updates the row. The switching
        // itself is KTThemeMode's; this only reacts to it.
        popup.querySelectorAll("[data-kt-element='mode']").forEach((button) => {
            // The row's own icon follows `data-bs-theme` through the theme's
            // CSS, so nothing here has to update it.
            button.addEventListener("click", () => close(120));
        });

        // A click anywhere else, and Escape, both dismiss it.
        document.addEventListener("click", (event) => {
            if (!item.contains(event.target)) close();
        });
        item.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                close();
                trigger.focus();
            }
        });

    }

    /**
     * `/branding/` — this deployment's own name/logo, Platform Admin only.
     *
     * Same shape as the attachments panel above: GET to fill the form, a
     * plain multipart POST (never JSON — `raw: true`) so the optional file
     * input rides along unencoded, and a re-fetch of the logo preview after
     * a successful save so the page reflects exactly what the server now
     * holds rather than assuming the upload matched what was picked.
     */
    function setupBrandingSettings() {
        const form = document.getElementById("branding-form");
        if (!form) return;
        const loading = document.getElementById("branding-loading");
        const nameField = document.getElementById("branding-display-name");
        const preview = document.getElementById("branding-logo-preview");
        const emptyNote = document.getElementById("branding-logo-empty");
        const removeRow = document.getElementById("branding-remove-logo-row");
        const removeBox = document.getElementById("branding-remove-logo");
        const DEFAULT_ACCENT_COLOR = "#1b84ff";
        const colorField = document.getElementById("branding-accent-color");
        const colorHexField = document.getElementById("branding-accent-color-hex");
        const colorResetButton = document.getElementById("branding-accent-color-reset");

        // The two accent-colour inputs — a native colour picker (always a
        // valid hex, no validation needed) and a plain text field for typing
        // one directly — stay mirrors of each other; each edit updates the
        // other rather than the two silently disagreeing about what will be
        // submitted.
        colorField.addEventListener("input", () => {
            colorHexField.value = colorField.value;
        });
        colorHexField.addEventListener("input", () => {
            if (/^#[0-9a-fA-F]{6}$/.test(colorHexField.value)) colorField.value = colorHexField.value;
        });
        colorResetButton.addEventListener("click", () => {
            colorField.value = DEFAULT_ACCENT_COLOR;
            colorHexField.value = "";
        });

        function showLogo(hasLogo) {
            if (hasLogo) {
                preview.src = `/api/v1/branding/logo/?v=${Date.now()}`;
                preview.classList.remove("d-none");
                emptyNote.classList.add("d-none");
            } else {
                preview.classList.add("d-none");
                preview.removeAttribute("src");
                emptyNote.classList.remove("d-none");
            }
            removeRow.hidden = !hasLogo;
            removeBox.checked = false;
        }

        async function load() {
            try {
                const data = await apiRequest("/api/v1/branding/");
                nameField.value = data.display_name || "";
                colorField.value = data.accent_color || DEFAULT_ACCENT_COLOR;
                colorHexField.value = data.accent_color || "";
                showLogo(Boolean(data.has_logo));
                loading.classList.add("d-none");
                form.classList.remove("d-none");
            } catch (error) {
                showError(error);
                loading.classList.add("d-none");
            }
        }

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const payload = new FormData();
                payload.set("display_name", nameField.value);
                payload.set("accent_color", colorHexField.value.trim());
                const file = document.getElementById("branding-logo-file").files[0];
                if (file) payload.set("logo", file);
                if (removeBox.checked) payload.set("remove_logo", "true");
                const data = await apiRequest("/api/v1/branding/", {method: "POST", body: payload, raw: true});
                document.getElementById("branding-logo-file").value = "";
                colorField.value = data.accent_color || DEFAULT_ACCENT_COLOR;
                colorHexField.value = data.accent_color || "";
                showLogo(Boolean(data.has_logo));
                globalMessage("تنظیمات برند ذخیره شد. برای دیدن رنگ تازه در همهٔ عناصر، صفحه را تازه کنید.", true);
            });
        });

        load();
    }

    /**
     * `/settings/dashboard/` — which home-page widgets show, and in what
     * order (`common.dashboard_layout`). Rendered from the catalog the API
     * itself returns rather than a second hardcoded list of widget
     * labels, so a widget added or renamed on the Python side never needs a
     * matching edit here.
     *
     * Reordering is two small buttons per row, not drag-and-drop: this
     * settings page is opened rarely, by one role, and a working keyboard-
     * reachable control beats a heavier library for a list of eight rows.
     */
    function setupDashboardLayoutSettings() {
        const form = document.getElementById("dashboard-layout-form");
        if (!form) return;
        const loading = document.getElementById("dashboard-layout-loading");
        const list = document.getElementById("dashboard-layout-list");
        const resetButton = document.getElementById("dashboard-layout-reset");
        let rows = [];
        // The catalog's own order, nothing hidden — `/api/v1/dashboard-
        // layout/`'s `catalog` array is already `WIDGET_CATALOG`'s order
        // (`common/dashboard_layout.py`), so "بازگشت به پیش‌فرض" needs no
        // second endpoint, only forgetting the reader's own saved order and
        // hidden set. Captured once in `load()`, before either is applied.
        let defaultRows = [];

        function render() {
            list.innerHTML = "";
            rows.forEach((row, index) => {
                const item = document.createElement("li");
                item.className = "list-group-item d-flex align-items-center gap-3";
                item.draggable = true;
                item.dataset.dashboardLayoutRow = row.key;
                // A drag handle rather than the whole row: the checkbox and
                // both buttons already have their own click behaviour, and a
                // `draggable` ancestor intercepting `mousedown` on them would
                // cost a native click, checkbox toggle, or button press to
                // start a drag by accident (Apple HIG: `drag-threshold` and
                // `gesture-alternative` — the up/down buttons below stay the
                // full keyboard/no-drag path to the same reorder).
                const handle = document.createElement("i");
                handle.className = "ki-duotone ki-dots-vertical fs-3 text-gray-500 cursor-grab";
                handle.setAttribute("aria-hidden", "true");
                ["path1", "path2", "path3"].forEach((name) => {
                    handle.appendChild(document.createElement("span")).className = name;
                });
                const checkWrap = document.createElement("div");
                checkWrap.className = "form-check form-check-custom form-check-solid";
                const check = document.createElement("input");
                check.className = "form-check-input";
                check.type = "checkbox";
                check.id = `dashboard-layout-widget-${row.key}`;
                check.checked = !row.hidden;
                check.addEventListener("change", () => { row.hidden = !check.checked; });
                const label = document.createElement("label");
                label.className = "form-check-label";
                label.setAttribute("for", check.id);
                label.textContent = row.label;
                checkWrap.append(check, label);
                const featureNote = document.createElement("span");
                featureNote.className = "text-muted fs-8 flex-grow-1";
                featureNote.textContent = `ماژول: ${row.feature}`;
                const upButton = document.createElement("button");
                upButton.type = "button";
                upButton.className = "btn btn-icon btn-sm btn-light";
                upButton.setAttribute("aria-label", "بالاتر");
                upButton.disabled = index === 0;
                upButton.innerHTML = '<i class="ki-duotone ki-arrow-up fs-3"><span class="path1"></span><span class="path2"></span></i>';
                upButton.addEventListener("click", () => {
                    [rows[index - 1], rows[index]] = [rows[index], rows[index - 1]];
                    render();
                });
                const downButton = document.createElement("button");
                downButton.type = "button";
                downButton.className = "btn btn-icon btn-sm btn-light";
                downButton.setAttribute("aria-label", "پایین‌تر");
                downButton.disabled = index === rows.length - 1;
                downButton.innerHTML = '<i class="ki-duotone ki-arrow-down fs-3"><span class="path1"></span><span class="path2"></span></i>';
                downButton.addEventListener("click", () => {
                    [rows[index + 1], rows[index]] = [rows[index], rows[index + 1]];
                    render();
                });
                item.append(handle, checkWrap, featureNote, upButton, downButton);

                // Native HTML5 drag and drop — no library, the same choice
                // this codebase already made for the lead/order kanban
                // boards' own card drag (`jkanban`'s dragula, a purchased-
                // theme dependency; a settings list of a dozen rows does not
                // need a second one). `dragover`'s own default is to refuse
                // a drop, so it is always prevented here.
                item.addEventListener("dragstart", (event) => {
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", row.key);
                    item.classList.add("opacity-50");
                });
                item.addEventListener("dragend", () => item.classList.remove("opacity-50"));
                item.addEventListener("dragover", (event) => event.preventDefault());
                item.addEventListener("drop", (event) => {
                    event.preventDefault();
                    const draggedKey = event.dataTransfer.getData("text/plain");
                    const from = rows.findIndex((candidate) => candidate.key === draggedKey);
                    const to = rows.findIndex((candidate) => candidate.key === row.key);
                    if (from === -1 || to === -1 || from === to) return;
                    const [moved] = rows.splice(from, 1);
                    rows.splice(to, 0, moved);
                    render();
                });

                list.append(item);
            });
        }

        async function load() {
            try {
                const data = await apiRequest("/api/v1/dashboard-layout/");
                const hidden = new Set(data.hidden_widgets || []);
                const position = new Map((data.widget_order || []).map((key, index) => [key, index]));
                rows = [...data.catalog].sort((a, b) => {
                    const aPos = position.has(a.key) ? position.get(a.key) : Infinity;
                    const bPos = position.has(b.key) ? position.get(b.key) : Infinity;
                    return aPos - bPos;
                }).map((widget) => ({...widget, hidden: hidden.has(widget.key)}));
                defaultRows = data.catalog.map((widget) => ({...widget, hidden: false}));
                render();
                loading.classList.add("d-none");
                form.classList.remove("d-none");
            } catch (error) {
                showError(error);
                loading.classList.add("d-none");
            }
        }

        // Forgets the reader's own saved order/hidden set, back to the
        // catalog's own order with everything shown — still only in memory
        // until «ذخیره» is pressed, the same as every other change on this
        // form (product-owner request 2026-09-12).
        resetButton?.addEventListener("click", () => {
            rows = defaultRows.map((widget) => ({...widget}));
            render();
        });

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const payload = {
                    hidden_widgets: rows.filter((row) => row.hidden).map((row) => row.key),
                    widget_order: rows.map((row) => row.key),
                };
                await apiRequest("/api/v1/dashboard-layout/", {method: "POST", body: payload});
                globalMessage("چیدمان داشبورد ذخیره شد.", true);
            });
        });

        load();
    }

    /**
     * `/settings/sms-provider/` — this deployment's own outbound SMS gateway
     * (`communications.models.SmsProviderSettings`). Same load/submit shape
     * as `setupBrandingSettings` above, with two things that function does
     * not need: an auth-mode-dependent section (the OAuth2 fields are
     * useless, and hidden, in `api_key` mode) and a "تست اتصال" button that
     * calls a second endpoint against whatever is already saved.
     */
    function setupSmsProviderSettings() {
        const form = document.getElementById("sms-provider-form");
        if (!form) return;
        const loading = document.getElementById("sms-provider-loading");
        const authModeField = document.getElementById("sms-provider-auth-mode");
        const oauthSection = document.getElementById("sms-provider-oauth-section");
        const oauthHeading = document.getElementById("sms-provider-oauth-heading");
        const passwordField = document.getElementById("sms-provider-token-password");
        const passwordNote = document.getElementById("sms-provider-token-password-note");
        const updatedNote = document.getElementById("sms-provider-updated-note");
        const testButton = document.getElementById("sms-provider-test-button");
        const testResult = document.getElementById("sms-provider-test-result");

        function syncOAuthVisibility() {
            const isOAuth = authModeField.value === "oauth2_password";
            oauthSection.hidden = !isOAuth;
            oauthHeading.hidden = !isOAuth;
        }
        authModeField.addEventListener("change", syncOAuthVisibility);

        function fillUpdatedNote(data) {
            if (!data.updated_by_name) { updatedNote.textContent = ""; return; }
            updatedNote.textContent = `آخرین به‌روزرسانی: ${data.updated_by_name} — ${displayDate(data.updated_at)}`;
        }

        function fill(data) {
            document.getElementById("sms-provider-enabled").checked = Boolean(data.is_enabled);
            document.getElementById("sms-provider-label").value = data.label || "";
            authModeField.value = data.auth_mode;
            document.getElementById("sms-provider-number-style").value = data.recipient_number_style;
            document.getElementById("sms-provider-send-url").value = data.send_url || "";
            document.getElementById("sms-provider-sender-id").value = data.sender_id || "";
            document.getElementById("sms-provider-timeout").value = data.timeout_seconds;
            document.getElementById("sms-provider-body-template").value = data.body_template || "";
            document.getElementById("sms-provider-headers").value = data.headers || "";
            document.getElementById("sms-provider-token-url").value = data.token_url || "";
            document.getElementById("sms-provider-token-username").value = data.token_username || "";
            document.getElementById("sms-provider-token-extra").value = data.token_extra_params || "";
            document.getElementById("sms-provider-test-url").value = data.test_url || "";
            passwordField.value = "";
            passwordNote.textContent = data.has_token_password
                ? "رمزی از قبل ذخیره شده — برای تغییر، مقدار تازه وارد کنید؛ برای نگه‌داشتن مقدار فعلی، خالی بگذارید."
                : "هنوز رمزی ذخیره نشده.";
            fillUpdatedNote(data);
            syncOAuthVisibility();
        }

        async function load() {
            try {
                const data = await apiRequest("/api/v1/sms-provider-settings/");
                fill(data);
                loading.classList.add("d-none");
                form.classList.remove("d-none");
            } catch (error) {
                showError(error);
                loading.classList.add("d-none");
            }
        }

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const payload = {
                    is_enabled: document.getElementById("sms-provider-enabled").checked,
                    label: document.getElementById("sms-provider-label").value,
                    auth_mode: authModeField.value,
                    recipient_number_style: document.getElementById("sms-provider-number-style").value,
                    send_url: document.getElementById("sms-provider-send-url").value,
                    sender_id: document.getElementById("sms-provider-sender-id").value,
                    timeout_seconds: Number(document.getElementById("sms-provider-timeout").value || 10),
                    body_template: document.getElementById("sms-provider-body-template").value,
                    headers: document.getElementById("sms-provider-headers").value,
                    token_url: document.getElementById("sms-provider-token-url").value,
                    token_username: document.getElementById("sms-provider-token-username").value,
                    token_extra_params: document.getElementById("sms-provider-token-extra").value,
                    test_url: document.getElementById("sms-provider-test-url").value,
                };
                // Omitted, not sent blank: leaving the password field empty
                // means "keep the value already stored" — sending an empty
                // string would instead clear it (see the update service's
                // own "independent and optional" contract).
                if (passwordField.value) payload.token_password = passwordField.value;
                const data = await apiRequest("/api/v1/sms-provider-settings/", {method: "POST", body: payload});
                fill(data);
                globalMessage("تنظیمات سامانهٔ پیامک ذخیره شد.", true);
            });
        });

        testButton?.addEventListener("click", async () => {
            testButton.disabled = true;
            testResult.hidden = true;
            try {
                const data = await apiRequest("/api/v1/sms-provider-settings/test/", {method: "POST", body: {}});
                testResult.hidden = false;
                testResult.className = `alert d-flex align-items-center p-4 mt-3 ${data.success ? "alert-success" : "alert-danger"}`;
                testResult.textContent = data.status_detail;
            } catch (error) {
                showError(error);
            } finally {
                testButton.disabled = false;
            }
        });

        load();
    }

    /**
     * The topbar search box, on every page.
     *
     * One request per settled keystroke, not per keystroke: a debounce
     * (`SEARCH_DEBOUNCE_MS`) and a two-character floor together mean typing
     * a customer's name sends one query, not eleven. A sequence number
     * guards against the older of two overlapping answers painting last,
     * which is the classic search-box bug — type fast, and a slow reply for
     * "رض" arrives after the quick one for "رضا" and replaces it.
     *
     * Rows are shared with the reminder bell (`topbar-list-*`): the two
     * panels are the same list in the same dropdown, and only their content
     * differs.
     */
    function setupGlobalSearch() {
        const toggle = document.getElementById("global-search-toggle");
        const menu = document.getElementById("global-search-menu");
        if (!toggle || !menu) return;

        const input = document.getElementById("global-search-input");
        const body = document.getElementById("global-search-body");
        const empty = document.getElementById("global-search-empty");
        const errorNote = document.getElementById("global-search-error");
        const SEARCH_DEBOUNCE_MS = 250;
        const MIN_QUERY_LENGTH = 2;
        let timer = null;
        let sequence = 0;

        const setOpen = (open) => {
            menu.classList.toggle("show", open);
            toggle.setAttribute("aria-expanded", String(open));
            // Opening a search box that is not focused is opening nothing.
            if (open) input.focus();
        };

        // `node` is `null` before typing starts — an empty box, not an
        // instructional message, product-owner decision 2026-09-08.
        function show(node) {
            [empty, errorNote].forEach((each) => { each.hidden = each !== node; });
        }

        function renderGroup(group) {
            const section = document.createElement("div");
            section.className = "topbar-list-group";

            const heading = document.createElement("div");
            heading.className = "d-flex align-items-center justify-content-between gap-2 px-2 mb-1";
            const left = document.createElement("span");
            left.className = "d-flex align-items-center gap-2";
            const icon = document.createElement("i");
            icon.className = `ki-duotone ${group.icon} fs-5 text-${group.accent}`;
            for (let index = 1; index <= (group.icon_paths || 2); index += 1) {
                icon.append(searchPathSpan(index));
            }
            const label = document.createElement("span");
            label.className = "text-gray-700 fw-bold fs-8";
            label.textContent = `${group.label} (${toPersianDigits(String(group.count))})`;
            left.append(icon, label);
            heading.appendChild(left);

            // More matches than the group lists: the module's own page has
            // the real filters, so send the reader there rather than paging
            // a dropdown.
            if (group.count > group.items.length) {
                const more = document.createElement("a");
                more.className = "text-primary fw-semibold fs-8 text-decoration-none";
                more.href = group.list_url;
                more.textContent = "همه";
                heading.appendChild(more);
            }
            section.appendChild(heading);

            group.items.forEach((item) => {
                const link = document.createElement("a");
                link.className = "topbar-list-item";
                link.href = item.url;
                const text = document.createElement("span");
                text.className = "flex-grow-1 min-w-0";
                const title = document.createElement("span");
                title.className = "d-block text-gray-900 fw-semibold fs-7 text-truncate";
                title.textContent = item.title;
                const subtitle = document.createElement("span");
                subtitle.className = "d-block text-muted fs-8 text-truncate";
                subtitle.textContent = item.subtitle;
                text.append(title, subtitle);
                link.appendChild(text);
                section.appendChild(link);
            });
            return section;
        }

        function searchPathSpan(index) {
            const span = document.createElement("span");
            span.className = `path${index}`;
            return span;
        }

        async function run(query) {
            const mine = ++sequence;
            try {
                const data = await apiRequest(`/api/v1/search/?q=${encodeURIComponent(query)}`);
                // A stale answer must never paint over a newer one.
                if (mine !== sequence) return;
                body.replaceChildren();
                data.groups.forEach((group) => body.appendChild(renderGroup(group)));
                show(data.count ? null : empty);
            } catch (error) {
                if (mine !== sequence) return;
                body.replaceChildren();
                show(errorNote);
            }
        }

        input.addEventListener("input", () => {
            const query = input.value.trim();
            if (timer) clearTimeout(timer);
            if (query.length < MIN_QUERY_LENGTH) {
                // Abandon any answer still in flight, so it cannot arrive and
                // fill a box the user has just cleared.
                sequence += 1;
                body.replaceChildren();
                show(null);
                return;
            }
            timer = setTimeout(() => run(query), SEARCH_DEBOUNCE_MS);
        });

        // Enter opens the first result, which is what a search box is for
        // when the answer is already on screen.
        input.addEventListener("keydown", (event) => {
            if (event.key !== "Enter") return;
            const first = body.querySelector(".topbar-list-item");
            if (first) {
                event.preventDefault();
                window.location.href = first.getAttribute("href");
            }
        });

        toggle.addEventListener("click", (event) => {
            event.stopPropagation();
            setOpen(!menu.classList.contains("show"));
        });
        document.addEventListener("click", (event) => {
            if (!menu.contains(event.target) && event.target !== toggle) setOpen(false);
        });
        document.addEventListener("keydown", (event) => {
            // Ctrl/⌘+K from anywhere, the shortcut a keyboard already
            // expects for a search box.
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
                event.preventDefault();
                setOpen(true);
                input.select();
                return;
            }
            if (event.key === "Escape" && menu.classList.contains("show")) {
                setOpen(false);
                toggle.focus();
            }
        });
    }

    /**
     * The topbar reminder bell, on every page.
     *
     * Two requests, deliberately: the badge count is polled on a timer for
     * every open tab, and the grouped list is fetched only when someone
     * opens the panel. Building and sending every row on a poll nobody is
     * looking at would be avoidable load on every page of every session —
     * the same split `chat` makes between its thread list and
     * `unread-count`.
     *
     * There is no read/dismiss state anywhere in this feature. The badge is
     * a count of work that is actually due, so it clears when the work is
     * done — the follow-up is rescheduled, the cheque clears — not when
     * somebody glances at the panel. See `common/reminders.py` for why.
     */
    function setupReminderBell() {
        const toggle = document.getElementById("reminder-bell-toggle");
        const menu = document.getElementById("reminder-bell-menu");
        if (!toggle || !menu) return;

        const body = document.getElementById("reminder-bell-body");
        const empty = document.getElementById("reminder-bell-empty");
        const errorNote = document.getElementById("reminder-bell-error");
        const badge = document.querySelector("[data-reminder-badge]");
        const count = document.querySelector("[data-reminder-count]");
        const summary = document.querySelector("[data-reminder-summary]");
        let loading = false;

        const setOpen = (open) => {
            menu.classList.toggle("show", open);
            toggle.setAttribute("aria-expanded", String(open));
            if (open) load();
        };

        function setBadge(total) {
            if (!badge || !count) return;
            badge.hidden = total <= 0;
            // Three digits is already an unusual amount of overdue work; past
            // that the exact figure stops being the useful part and the
            // button would start growing to fit it.
            count.textContent = total > 999 ? "+۹۹۹" : toPersianDigits(String(total));
        }

        function renderItem(item) {
            const link = document.createElement("a");
            link.className = "topbar-list-item";
            link.href = item.url;

            const text = document.createElement("span");
            text.className = "flex-grow-1 min-w-0";
            const title = document.createElement("span");
            title.className = "d-block text-gray-900 fw-semibold fs-7 text-truncate";
            title.textContent = item.title;
            const subtitle = document.createElement("span");
            subtitle.className = "d-block text-muted fs-8 text-truncate";
            subtitle.textContent = item.subtitle;
            text.append(title, subtitle);

            const due = document.createElement("span");
            due.className = "topbar-list-meta fs-8 fw-semibold " + (item.overdue ? "text-danger" : "text-muted");
            // A cheque's due date is a calendar day with no clock of its own
            // (`DateField`); a follow-up is an instant. Rendering the first
            // through the instant path would push it through a time zone and
            // could land it on the day before.
            due.textContent = item.due_kind === "date" ? displayDay(item.due_at) : displayDate(item.due_at);

            link.append(text, due);
            return link;
        }

        function renderGroup(group) {
            const section = document.createElement("div");
            section.className = "topbar-list-group";

            const heading = document.createElement("div");
            heading.className = "d-flex align-items-center gap-2 px-2 mb-1";
            const icon = document.createElement("i");
            icon.className = `ki-duotone ${group.icon} fs-5 text-${group.accent}`;
            // A duotone keenicon is drawn from nested `.path*` spans, and the
            // count differs per glyph — `ki-call` has eight. The server sends
            // it with the group, the same way the dashboard tiles carry
            // `icon_paths`; drawing two for an eight-path icon draws a
            // quarter of it.
            for (let index = 1; index <= (group.icon_paths || 2); index += 1) icon.append(pathSpan(index));
            const label = document.createElement("span");
            label.className = "text-gray-700 fw-bold fs-8";
            label.textContent = `${group.label} (${toPersianDigits(String(group.count))})`;
            heading.append(icon, label);
            section.appendChild(heading);

            group.items.forEach((item) => section.appendChild(renderItem(item)));

            // The group holds more than the page it returned: say so rather
            // than letting the list look complete when it is not.
            if (group.count > group.items.length) {
                const more = document.createElement("div");
                more.className = "text-muted fs-8 px-2 pt-1";
                more.textContent = `و ${toPersianDigits(String(group.count - group.items.length))} مورد دیگر`;
                section.appendChild(more);
            }
            return section;
        }

        function pathSpan(index) {
            const span = document.createElement("span");
            span.className = `path${index}`;
            return span;
        }

        async function load() {
            if (loading) return;
            loading = true;
            try {
                const data = await apiRequest("/api/v1/reminders/");
                body.replaceChildren();
                data.groups.forEach((group) => body.appendChild(renderGroup(group)));
                empty.hidden = data.count > 0;
                errorNote.hidden = true;
                setBadge(data.count);
                if (summary) {
                    summary.textContent = data.overdue_count > 0
                        ? `${toPersianDigits(String(data.overdue_count))} مورد گذشته از موعد`
                        : `${toPersianDigits(String(data.count))} مورد`;
                }
            } catch (error) {
                body.replaceChildren();
                empty.hidden = true;
                errorNote.hidden = false;
                if (summary) summary.textContent = "";
            } finally {
                loading = false;
            }
        }

        async function pollCount() {
            try {
                const data = await apiRequest("/api/v1/reminders/count/");
                setBadge(data.count);
            } catch (error) {
                // A missed poll tick is not worth bothering anyone about.
            }
        }

        toggle.addEventListener("click", (event) => {
            event.stopPropagation();
            setOpen(!menu.classList.contains("show"));
        });
        document.addEventListener("click", (event) => {
            if (!menu.contains(event.target) && event.target !== toggle) setOpen(false);
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && menu.classList.contains("show")) {
                setOpen(false);
                toggle.focus();
            }
        });

        pollCount();
        // Slower than chat's twenty seconds: a due date does not move while
        // someone is looking at it, and this query touches four tables.
        setInterval(pollCount, 60000);
    }

    /**
     * The sidebar's chat badge, on every page — not only `/chat/` itself.
     *
     * `setupChat()` below updates it immediately from the thread list it
     * already has whenever *that* page changes it; this is the only thing
     * that keeps it truthful everywhere else, since the badge markup itself
     * lives in the shared sidebar template that every page renders.
     */
    function updateChatUnreadBadge(totalUnread) {
        const badge = document.querySelector("[data-chat-unread-badge]");
        const count = document.querySelector("[data-chat-unread-count]");
        if (!badge || !count) return;
        badge.hidden = totalUnread <= 0;
        count.textContent = toPersianDigits(String(totalUnread));
    }

    function setupChatUnreadPoll() {
        if (!document.querySelector("[data-chat-unread-badge]")) return;
        async function poll() {
            try {
                const data = await apiRequest("/api/v1/chat/unread-count/");
                updateChatUnreadBadge(data.count);
            } catch (error) {
                // A missed poll tick is not worth bothering anyone about.
            }
        }
        poll();
        setInterval(poll, 20000);
    }

    /**
     * Internal chat: a slide-in drawer, matching the purchased theme's own
     * `kt_drawer_chat` pattern (header icon, `data-kt-drawer`, the same
     * message-bubble classes) with two states inside it — a thread list, or
     * one open conversation — since the theme's own demo shows a single
     * fixed conversation and this panel has many.
     *
     * No websocket in this codebase (no channel-layer infrastructure exists
     * anywhere else here), so "live" means polling — the same choice the
     * agent work queue and every report already make. What makes this feel
     * live rather than merely refreshed: both intervals run only while the
     * drawer is actually open (checked against the theme's own `drawer-on`
     * class on every tick, the same class the drawer gets however it was
     * opened — the header icon, or the theme's own overlay/Escape handling),
     * and opening the drawer polls immediately rather than waiting for the
     * next tick. A closed drawer costs nothing; an open one updates every
     * few seconds without anyone touching it.
     */
    function setupChat() {
        const drawer = document.getElementById("kt_drawer_chat");
        const toggle = document.getElementById("kt_drawer_chat_toggle");
        const threadListEl = document.getElementById("chat-drawer-thread-list");
        if (!drawer || !toggle || !threadListEl) return;

        const threadsLoading = document.getElementById("chat-drawer-threads-loading");
        const threadsEmpty = document.getElementById("chat-drawer-threads-empty");
        const listTitle = document.getElementById("chat-drawer-list-title");
        const peerTitle = document.getElementById("chat-drawer-peer-title");
        const listPanel = document.getElementById("chat-drawer-list-panel");
        const conversationPanel = document.getElementById("chat-drawer-conversation-panel");
        const footer = document.getElementById("chat-drawer-footer");
        const messagesEl = document.getElementById("chat-drawer-messages");
        const messagesEmpty = document.getElementById("chat-drawer-messages-empty");
        const peerNameEl = document.getElementById("chat-drawer-peer-name");
        const peerRoleEl = document.getElementById("chat-drawer-peer-role");
        const backButton = document.getElementById("chat-drawer-back");
        const sendForm = document.getElementById("chat-drawer-send-form");
        const messageInput = document.getElementById("chat-drawer-message-input");
        const newDialog = document.getElementById("chat-drawer-new-dialog");
        const colleaguesLoading = document.getElementById("chat-drawer-colleagues-loading");
        const colleaguesEmpty = document.getElementById("chat-drawer-colleagues-empty");
        const colleaguesList = document.getElementById("chat-drawer-colleagues-list");

        const AVATAR_COLORS = ["primary", "success", "info", "warning", "danger"];
        function avatarColor(userId) {
            return AVATAR_COLORS[Math.abs(Number(userId)) % AVATAR_COLORS.length];
        }
        // 35px, matching the purchased theme's own drawer-chat avatar size
        // exactly (its message rows and its contact rows both use it).
        function avatarSymbol(name, userId) {
            const symbol = document.createElement("div");
            symbol.className = "symbol symbol-35px symbol-circle";
            const label = document.createElement("span");
            label.className = `symbol-label bg-light-${avatarColor(userId)} text-${avatarColor(userId)} fw-bold`;
            label.textContent = (name || "?").trim().charAt(0);
            symbol.appendChild(label);
            return symbol;
        }

        let activeThreadId = null;
        let lastMessageId = 0;
        let threads = [];

        function isOpen() {
            return drawer.classList.contains("drawer-on");
        }

        function showList() {
            activeThreadId = null;
            listTitle.classList.remove("d-none");
            peerTitle.classList.add("d-none");
            listPanel.classList.remove("d-none");
            listPanel.hidden = false;
            conversationPanel.classList.add("d-none");
            footer.classList.add("d-none");
            renderThreadList();
        }

        function showConversation() {
            listTitle.classList.add("d-none");
            peerTitle.classList.remove("d-none");
            listPanel.classList.add("d-none");
            conversationPanel.classList.remove("d-none");
            footer.classList.remove("d-none");
        }

        function renderThreadList() {
            threadListEl.replaceChildren();
            updateChatUnreadBadge(threads.reduce((sum, thread) => sum + thread.unread_count, 0));
            threadsEmpty.hidden = threads.length > 0;
            threadListEl.hidden = threads.length === 0;
            threads.forEach((thread) => {
                const row = document.createElement("button");
                row.type = "button";
                row.className = "btn btn-flush d-flex align-items-center justify-content-between w-100 py-3 px-2 text-start rounded";
                row.dataset.chatThreadRow = String(thread.id);

                const left = document.createElement("div");
                left.className = "d-flex align-items-center overflow-hidden";
                left.appendChild(avatarSymbol(thread.peer.display_name, thread.peer.id));
                const details = document.createElement("div");
                details.className = "ms-3 text-start overflow-hidden";
                const nameLine = document.createElement("div");
                nameLine.className = "fs-6 fw-bold text-gray-900 text-truncate";
                nameLine.textContent = thread.peer.display_name;
                const previewLine = document.createElement("div");
                previewLine.className = "fs-7 text-muted text-truncate";
                previewLine.textContent = thread.last_message_body || "—";
                details.append(nameLine, previewLine);
                left.appendChild(details);
                row.appendChild(left);

                if (thread.unread_count > 0) {
                    const badge = document.createElement("span");
                    badge.className = "badge badge-circle badge-danger ms-2";
                    badge.textContent = toPersianDigits(String(thread.unread_count));
                    row.appendChild(badge);
                }
                row.addEventListener("click", () => openThread(thread.id));
                threadListEl.appendChild(row);
            });
        }

        async function loadThreads() {
            try {
                threads = await apiRequest("/api/v1/chat/threads/");
                threadsLoading.hidden = true;
                renderThreadList();
            } catch (error) {
                threadsLoading.hidden = true;
                showError(error);
            }
        }

        function appendMessageBubble(message) {
            const row = document.createElement("div");
            row.className = `d-flex mb-6 ${message.mine ? "justify-content-end" : "justify-content-start"}`;
            const wrap = document.createElement("div");
            wrap.className = `d-flex flex-column ${message.mine ? "align-items-end" : "align-items-start"}`;

            const meta = document.createElement("div");
            meta.className = "d-flex align-items-center mb-2";
            const senderId = message.mine
                ? Number(document.body.dataset.chatUserId)
                : (threads.find((t) => t.id === activeThreadId)?.peer.id ?? 0);
            const senderName = message.mine ? "شما" : message.sender_display_name;
            if (message.mine) {
                const metaTime = document.createElement("span");
                metaTime.className = "fs-8 text-muted me-1";
                metaTime.textContent = displayDate(message.created_at);
                const metaName = document.createElement("span");
                metaName.className = "fs-7 fw-bold text-gray-900 ms-1";
                metaName.textContent = senderName;
                meta.append(metaTime, metaName, avatarSymbol(senderName, senderId));
            } else {
                const metaName = document.createElement("span");
                metaName.className = "fs-7 fw-bold text-gray-900 me-1";
                metaName.textContent = senderName;
                const metaTime = document.createElement("span");
                metaTime.className = "fs-8 text-muted ms-1";
                metaTime.textContent = displayDate(message.created_at);
                meta.append(avatarSymbol(senderName, senderId), metaName, metaTime);
            }

            const bubble = document.createElement("div");
            bubble.className = `p-4 rounded fw-semibold mw-lg-300px ${message.mine ? "bg-light-primary text-end" : "bg-light-info text-start"}`;
            bubble.style.whiteSpace = "pre-wrap";
            bubble.style.wordBreak = "break-word";
            bubble.textContent = message.body;

            wrap.append(meta, bubble);
            row.appendChild(wrap);
            messagesEl.appendChild(row);
        }

        function scrollMessagesToBottom() {
            messagesEl.scrollTop = messagesEl.scrollHeight;
        }

        async function openThread(threadId) {
            activeThreadId = threadId;
            lastMessageId = 0;
            showConversation();
            const thread = threads.find((item) => item.id === threadId);
            if (thread) {
                peerNameEl.textContent = thread.peer.display_name;
                peerRoleEl.textContent = thread.peer.role_label;
            }
            messagesEl.replaceChildren();
            messagesEmpty.hidden = true;
            try {
                const messages = await apiRequest(`/api/v1/chat/threads/${threadId}/messages/`);
                messagesEmpty.hidden = messages.length > 0;
                messages.forEach(appendMessageBubble);
                if (messages.length) lastMessageId = messages[messages.length - 1].id;
                scrollMessagesToBottom();
                // Opening it just marked it read server-side; reflect that locally
                // without waiting for the next thread-list poll.
                const row = threads.find((item) => item.id === threadId);
                if (row) row.unread_count = 0;
                updateChatUnreadBadge(threads.reduce((sum, item) => sum + item.unread_count, 0));
            } catch (error) {
                showError(error);
            }
            messageInput.focus();
        }

        async function pollActiveThread() {
            if (!activeThreadId || !isOpen()) return;
            try {
                const messages = await apiRequest(
                    `/api/v1/chat/threads/${activeThreadId}/messages/?after_id=${lastMessageId}`,
                );
                if (!messages.length) return;
                messagesEmpty.hidden = true;
                messages.forEach(appendMessageBubble);
                lastMessageId = messages[messages.length - 1].id;
                scrollMessagesToBottom();
                // A message that arrived while the thread was open is read the
                // moment it is drawn — mark it so the badge never lags what the
                // reader can already see on screen.
                await apiRequest(`/api/v1/chat/threads/${activeThreadId}/read/`, {method: "POST"});
            } catch (error) {
                // A transient poll failure is not worth interrupting anyone
                // over; the next tick tries again.
            }
        }

        async function pollThreads() {
            if (!isOpen()) return;
            await loadThreads();
        }

        sendForm.addEventListener("submit", (event) => {
            event.preventDefault();
            if (!activeThreadId) return;
            withSubmit(sendForm, async () => {
                const body = messageInput.value;
                const message = await apiRequest(`/api/v1/chat/threads/${activeThreadId}/messages/`, {
                    method: "POST", body: {body},
                });
                messageInput.value = "";
                messagesEmpty.hidden = true;
                appendMessageBubble(message);
                lastMessageId = message.id;
                scrollMessagesToBottom();
                loadThreads();
            });
        });

        messageInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                sendForm.requestSubmit();
            }
        });

        backButton.addEventListener("click", () => {
            showList();
            loadThreads();
        });

        async function loadColleagues() {
            try {
                const colleagues = await apiRequest("/api/v1/chat/colleagues/");
                colleaguesLoading.hidden = true;
                colleaguesEmpty.hidden = colleagues.length > 0;
                colleaguesList.hidden = colleagues.length === 0;
                colleaguesList.replaceChildren();
                colleagues.forEach((colleague) => {
                    const row = document.createElement("button");
                    row.type = "button";
                    row.className = "btn btn-flush d-flex align-items-center w-100 py-3 px-2 text-start rounded";
                    row.appendChild(avatarSymbol(colleague.display_name, colleague.id));
                    const details = document.createElement("div");
                    details.className = "ms-3 text-start";
                    const nameLine = document.createElement("div");
                    nameLine.className = "fs-6 fw-bold text-gray-900";
                    nameLine.textContent = colleague.display_name;
                    const roleLine = document.createElement("div");
                    roleLine.className = "fs-7 text-muted";
                    roleLine.textContent = colleague.role_label;
                    details.append(nameLine, roleLine);
                    row.appendChild(details);
                    row.addEventListener("click", async () => {
                        try {
                            const thread = await apiRequest("/api/v1/chat/threads/", {
                                method: "POST", body: {other_user_id: colleague.id},
                            });
                            newDialog.close();
                            const exists = threads.some((item) => item.id === thread.id);
                            if (!exists) threads.unshift(thread);
                            openThread(thread.id);
                        } catch (error) {
                            showError(error);
                        }
                    });
                    colleaguesList.appendChild(row);
                });
            } catch (error) {
                colleaguesLoading.hidden = true;
                showError(error);
            }
        }

        document.getElementById("chat-drawer-open-new").addEventListener("click", () => {
            newDialog.showModal();
            loadColleagues();
        });
        newDialog.querySelectorAll("[data-close-dialog]").forEach((button) =>
            button.addEventListener("click", () => newDialog.close()));

        // The theme's own KTDrawer binds its open/close click on this same
        // button; this listener runs alongside it, not instead of it, and
        // only reacts to the drawer actually being open — a click that
        // closes it triggers no wasted request.
        toggle.addEventListener("click", () => {
            // KTDrawer flips its own `drawer-on` class synchronously inside
            // the same click handler, but listener order between it and this
            // one is not something to depend on — a microtask delay reads the
            // class after every same-tick handler has run either way.
            Promise.resolve().then(() => { if (isOpen()) loadThreads(); });
        });

        showList();
        setInterval(pollThreads, 8000);
        setInterval(pollActiveThread, 3000);
    }

    /**
     * Every list page's filter row, collapsed behind a header button that
     * opens a dropdown panel — the purchased theme's own filter pattern
     * (the vendor demo's own customers list page — its "فیلتر" button + its
     * `.menu.menu-sub.menu-sub-dropdown` panel), applied generically rather
     * than rebuilt per page.
     *
     * Twenty-five templates carry `<form class="list-filters">`, each with
     * its own fields and its own `setupPagedList({form, ...})` submit
     * listener already attached directly to that form element. This moves
     * the existing form node — never clones it — into a new panel, so every
     * one of those listeners, and every input's id the page's own script
     * reads by `getElementById`, survives untouched; `getElementById` finds
     * an element wherever it sits in the document, so nothing about *where*
     * the form now lives affects any lookup already written against it.
     *
     * Opened and closed the same hand-rolled way as the reminder bell, the
     * search box and the user menu — `.show`, not `data-kt-menu-trigger` —
     * for the same reason all three of those are: `KTMenu` positions its
     * panel with Popper, and Popper lives in the plugins bundle this
     * deployment does not load.
     */
    function setupListFilterPopovers() {
        document.querySelectorAll("form.list-filters").forEach((form) => {
            const anchor = document.createElement("div");
            anchor.className = "list-filters-popover position-relative d-inline-block";

            const toggle = document.createElement("button");
            toggle.type = "button";
            toggle.className = "btn btn-light-primary";
            toggle.setAttribute("aria-haspopup", "true");
            toggle.setAttribute("aria-expanded", "false");
            // Named after the form it opens, since the form's own id is the
            // one stable thing about it that already varies meaningfully
            // page to page — a test or a future script can find "the filter
            // button for the product list" without this module inventing a
            // second id for the same relationship.
            if (form.id) toggle.dataset.filterToggleFor = form.id;
            const icon = document.createElement("i");
            icon.className = "ki-duotone ki-filter fs-2 me-1";
            icon.append(document.createElement("span"), document.createElement("span"));
            icon.children[0].className = "path1";
            icon.children[1].className = "path2";
            toggle.append(icon, document.createTextNode("فیلتر"));

            const panel = document.createElement("div");
            panel.className = "menu menu-sub menu-sub-dropdown menu-column w-300px w-md-350px list-filters-panel";
            const header = document.createElement("div");
            header.className = "px-6 py-4 fs-5 fw-bold text-gray-900";
            header.textContent = "فیلتر";
            const separator = document.createElement("div");
            separator.className = "separator border-gray-200";
            const body = document.createElement("div");
            body.className = "px-6 py-5";
            panel.append(header, separator, body);

            form.parentElement.insertBefore(anchor, form);
            anchor.append(toggle, panel);
            body.appendChild(form);
            form.classList.add("mb-0");

            // The theme's own filter panel pairs "ریست" beside "تایید" in one
            // row; these forms only ever shipped the one submit button, so
            // the reset button is built here rather than in twenty-five
            // templates. A native `type="reset"` needs no per-page knowledge
            // of which fields exist — the browser already knows how to put a
            // form back to its own defaults.
            const submit = form.querySelector(".list-filters-submit, button[type='submit']");
            if (submit) {
                const actions = document.createElement("div");
                actions.className = "d-flex justify-content-end gap-2";
                const reset = document.createElement("button");
                reset.type = "reset";
                reset.className = "btn btn-light";
                reset.textContent = "بازنشانی";
                submit.replaceWith(actions);
                actions.append(reset, submit);
            }

            function setOpen(open) {
                panel.classList.toggle("show", open);
                toggle.setAttribute("aria-expanded", String(open));
            }
            toggle.addEventListener("click", (event) => {
                event.stopPropagation();
                setOpen(!panel.classList.contains("show"));
            });
            document.addEventListener("click", (event) => {
                if (!panel.contains(event.target) && event.target !== toggle && !toggle.contains(event.target)) {
                    setOpen(false);
                }
            });
            document.addEventListener("keydown", (event) => {
                if (event.key === "Escape" && panel.classList.contains("show")) {
                    setOpen(false);
                    toggle.focus();
                }
            });
            // Closes the popover on a successful apply, matching the theme's
            // own `data-kt-menu-dismiss` on its filter panel's submit button.
            form.addEventListener("submit", () => setOpen(false));
            // A native reset only restores the fields; nothing here re-asks
            // for the now-default list on its own. Resubmitting after the
            // browser's own reset has already run — not before it — is what
            // makes "بازنشانی" behave like "clear the filters and reload"
            // rather than "clear the filters, and reload whenever something
            // else happens to next."
            form.addEventListener("reset", () => setTimeout(() => form.requestSubmit()));
        });
    }

    setupSearchableSelects();
    setupChartThemeRedraw();
    setupSidebarPeekGuard();
    setupThemeModePopup();
    setupProfileDialog();
    setupListFilterPopovers();

    // Any page that declares an attachments panel gets one wired up,
    // whichever page it is — same reasoning as the chart cards below.
    setupAttachmentsPanel();

    // Any page that declares a chart card gets one, whichever page it is.
    setupListCharts();

    // The chat drawer, the reminder bell and search all live in the header
    // shell, so every page that has one wires it up — same reasoning as the
    // two lines above, not only a page named after the feature.
    setupGlobalSearch();
    setupReminderBell();
    setupChatUnreadPoll();
    setupChat();

    const page = document.body.dataset.page;
    if (page === "login") setupLogin();
    if (page === "dashboard") setupDashboard();
    if (page === "users") setupUsers();
    if (page === "user-detail") setupUserDetail();
    if (page === "customers") setupCustomers();
    if (page === "customer-detail") setupCustomerDetail();
    if (page === "leads") setupLeads();
    if (page === "lead-calendar") setupLeadCalendar();
    if (page === "lead-board") setupLeadBoard();
    if (page === "after-sales-calendar") setupAfterSalesCalendar();
    if (page === "lead-detail") setupLeadDetail();
    if (page === "interactions") setupInteractions();
    if (page === "interaction-detail") setupInteractionDetail();
    if (page === "products") setupProducts();
    if (page === "product-detail") setupProductDetail();
    if (page === "product-categories") setupProductCategories();
    if (page === "product-category-detail") setupProductCategoryDetail();
    if (page === "sales") setupSales();
    if (page === "sale-detail") setupSaleDetail();
    if (page === "sales-documents") setupSalesDocuments();
    if (page === "sales-document-detail") setupSalesDocumentDetail();
    if (page === "user-performance") setupUserPerformance();
    if (page === "user-profile") setupSellerProfile();
    if (page === "sales-document-report") setupSalesDocumentReport();
    if (page === "inbound-sms-report") setupInboundSMSReport();
    if (page === "outbound-sms") setupOutboundSms();
    if (page === "after-sales") setupAfterSales();
    if (page === "after-sales-detail") setupAfterSalesDetail();
    if (page === "activity-logs") setupActivityLogs();
    if (page === "activity-log-detail") setupActivityLogDetail();
    if (page === "warehouses") setupWarehouses();
    if (page === "warehouse-detail") setupWarehouseDetail();
    if (page === "stock-levels") setupStockLevels();
    if (page === "stock-movements") setupStockMovements();
    if (page === "orders") setupOrders();
    if (page === "order-board") setupOrderBoard();
    if (page === "order-detail") setupOrderDetail();
    if (page === "invoices") setupInvoices();
    if (page === "invoice-detail") setupInvoiceDetail();
    if (page === "payments") setupPayments();
    if (page === "payment-detail") setupPaymentDetail();
    if (page === "cheques") setupCheques();
    if (page === "installments") setupInstallments();
    if (page === "customer-ledger") setupCustomerLedger();
    if (page === "receivables-report") setupReceivablesReport();
    if (page === "profit-report") setupProfitReport();
    if (page === "stock-valuation-report") setupStockValuationReport();
    if (page === "branding-settings") setupBrandingSettings();
    if (page === "dashboard-layout-settings") setupDashboardLayoutSettings();
    if (page === "sms-provider-settings") setupSmsProviderSettings();
    // `document-print` is the print base's own id, used when a printable page
    // does not override it; every printable page needs the print button wired.
    if (page === "invoice-print" || page === "document-print") setupDocumentPrint();
})();
