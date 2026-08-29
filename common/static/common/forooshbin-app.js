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
        node.classList.toggle("success", success);
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
        const path = window.location.pathname;

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
     * Open and close the header user menu.
     *
     * The theme owns how the panel looks and its `.show` rule; KTMenu would
     * normally toggle that class and position the panel with Popper, which
     * lives in the plugins bundle this deployment does not load. Toggling the
     * class here is the whole of what was missing — placement is two CSS lines
     * in forooshbin.css.
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
        await Promise.all([setupWorkQueue(), setupPerformancePanel("dashboard")]);
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
        const link = document.createElement("a");
        link.className = "btn btn-sm btn-light";
        link.href = `/users/${user.id}/`;
        link.textContent = "جزئیات";
        actionCell.appendChild(link);
        row.appendChild(actionCell);
        return row;
    }

    function setupUsers() {
        const searchForm = document.getElementById("user-search-form");
        const tableWrap = document.getElementById("users-table-wrap");
        const tableBody = document.getElementById("users-table-body");
        const loading = document.getElementById("users-loading");
        const empty = document.getElementById("users-empty");
        const pagination = document.getElementById("users-pagination");
        const prev = document.getElementById("users-prev");
        const next = document.getElementById("users-next");
        let currentPage = 1;
        let search = "";

        async function loadUsers(page = 1) {
            loading.hidden = false;
            empty.hidden = true;
            tableWrap.hidden = true;
            pagination.hidden = true;
            clearMessages();
            try {
                const query = new URLSearchParams({page: String(page)});
                if (search) query.set("search", search);
                const data = await apiRequest(`/api/v1/users/?${query}`);
                tableBody.replaceChildren(...data.results.map(userRow));
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

        searchForm.addEventListener("submit", (event) => {
            event.preventDefault();
            search = document.getElementById("user-search").value.trim();
            loadUsers(1);
        });
        prev.addEventListener("click", () => loadUsers(currentPage - 1));
        next.addEventListener("click", () => loadUsers(currentPage + 1));

        const dialog = document.getElementById("create-user-dialog");
        const createForm = document.getElementById("create-user-form");
        document.getElementById("open-create-user").addEventListener("click", () => dialog.showModal());
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const user = await apiRequest(createForm.action, {
                    method: "POST",
                    body: formPayload(createForm, ["username", "password", "first_name", "last_name", "email", "phone", "workstream"]),
                });
                window.location.assign(`/users/${user.id}/`);
            });
        });
        loadUsers();
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
            roleForm.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(roleForm, async () => {
                    user = await apiRequest(roleForm.action, {method: "POST", body: formPayload(roleForm, ["role"])});
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

    /**
     * Give every Jalali input the same behaviour once, at start-up.
     *
     * Persian digits are accepted as typed and the field reports its own error
     * on blur, so a bad date is caught where it was entered rather than as a
     * 400 from the server after submit.
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
        if (next) throw new Error("Result set is too large for this form.");
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

    function setupPagedList({key, form, endpoint, renderRow}) {
        const loading = document.getElementById(`${key}-loading`);
        if (!loading) return null;
        const empty = document.getElementById(`${key}-empty`);
        const wrap = document.getElementById(`${key}-table-wrap`);
        const body = document.getElementById(`${key}-table-body`);
        const pagination = document.getElementById(`${key}-pagination`);
        const previous = document.getElementById(`${key}-prev`);
        const next = document.getElementById(`${key}-next`);
        let currentPage = 1;

        async function load(page = 1) {
            loading.hidden = false;
            empty.hidden = true;
            wrap.hidden = true;
            pagination.hidden = true;
            clearMessages();
            try {
                const data = await apiRequest(endpoint(page));
                body.replaceChildren(...data.results.map(renderRow));
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
        // Which of the two books is on screen. A marketer never sees the
        // switch, and `customers_for` confines them to this book in the
        // database regardless of what the page asks for.
        let kind = "individual";
        const controller = setupPagedList({
            key: "customers",
            form,
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
            // Give the range the room: the search keeps growing, the sort does not.
            orderingSelect.classList.toggle("flex-grow-1", !active);
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
        document.getElementById("open-create-customer").addEventListener("click", () => dialog.showModal());
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
        const controller = setupPagedList({
            key: "leads", form,
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
        document.getElementById("open-create-lead").addEventListener("click", () => dialog.showModal());
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
        const controller = setupPagedList({
            key: "interactions", form,
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
        document.getElementById("create-interaction-occurred").value = localDateTimeValue(new Date().toISOString());
        document.getElementById("open-create-interaction").addEventListener("click", () => dialog.showModal());
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
        const controller = setupPagedList({
            key: "product-categories",
            form,
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
            document.getElementById("open-create-product-category").addEventListener("click", () => dialog.showModal());
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
        setupProductImport();
        // Wire the dialog before any awaited load: a click that lands while a
        // network load is still pending would otherwise be silently discarded,
        // leaving the create button inert for the first moments of the page.
        const dialog = document.getElementById("create-product-dialog");
        if (dialog) {
            const createForm = document.getElementById("create-product-form");
            document.getElementById("open-create-product").addEventListener("click", () => dialog.showModal());
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
        const controller = setupPagedList({
            key: "sales",
            form,
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
        document.getElementById("open-create-sale").addEventListener("click", () => dialog.showModal());
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
        const controller = setupPagedList({
            key: "sales-documents",
            form,
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
        document.getElementById("open-create-sales-document").addEventListener("click", () => dialog.showModal());
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

    async function setupSalesDocumentReport() {
        const form = document.getElementById("sales-document-report-form");
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

    function afterSalesRow(item) {
        const row = document.createElement("tr");
        [item.subject, item.customer_name || item.customer, item.status, item.assigned_to_display || "تخصیص‌نیافته", item.closed_at ? "بسته" : "باز", displayDate(item.created_at)].forEach((value) => appendCell(row, value));
        appendDetailLink(row, `/after-sales/${item.id}/`);
        return row;
    }

    async function setupAfterSales() {
        const form = document.getElementById("after-sales-search-form");
        const controller = setupPagedList({key: "after-sales", form, endpoint: (page) => {
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
        // Wire the dialog before the awaited loads below, so a click during
        // them opens the dialog instead of being silently discarded.
        customerSelect.addEventListener("change", refreshRelations);
        document.getElementById("open-create-after-sales").addEventListener("click", () => dialog.showModal());
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
        document.getElementById("after-sales-description-detail").value = item.description;
        document.getElementById("after-sales-actions").hidden = Boolean(item.closed_at);
    }

    async function loadAfterSalesHistory(id) {
        const rows = await loadAllPages(`/api/v1/after-sales/${id}/history/`);
        const eventLabels = {created: "ایجاد", assigned: "تخصیص", status_changed: "تغییر وضعیت", closed: "بستن"};
        const nodes = rows.map((item) => { const row = document.createElement("tr"); [eventLabels[item.event] || item.event, `${item.from_status || "—"} / ${item.to_status || "—"}`, `${item.from_user_display || "—"} / ${item.to_user_display || "—"}`, item.actor_display, item.reason || "—", displayDate(item.created_at)].forEach((value) => appendCell(row, value)); return row; });
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
            read("--bs-dark", "#1E2129"),
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
            },
            tooltip: {
                style: {fontFamily: "IRANSansWeb, Helvetica, sans-serif", fontSize: "13px"},
            },
            legend: {
                fontFamily: "IRANSansWeb, Helvetica, sans-serif",
                labels: {colors: ink.muted},
                markers: {radius: 3},
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
            stroke: {width: 2, colors: ["transparent"]},
            dataLabels: {
                enabled: true,
                formatter: (percent) => `${toPersianDigits(String(Math.round(percent)))}٪`,
                style: {fontFamily: "IRANSansWeb, Helvetica, sans-serif", fontSize: "12px"},
                dropShadow: {enabled: false},
            },
            legend: {...apexBase(320).legend, position: "bottom"},
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
            fill: {
                type: "gradient",
                gradient: {shadeIntensity: 1, opacityFrom: 0.4, opacityTo: 0.05, stops: [0, 90, 100]},
            },
            markers: {size: 4, strokeWidth: 2, hover: {size: 6}},
            xaxis: {
                categories: usable.map((point) => point.label),
                // Apex would print every category and let them collide; this is
                // the same thinning the hand-drawn chart did, expressed as the
                // most labels the axis may show.
                tickAmount: Math.min(maxLabels, usable.length),
                labels: {
                    style: {fontFamily: "IRANSansWeb, Helvetica, sans-serif", fontSize: "12px"},
                    hideOverlappingLabels: true,
                    trim: true,
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
            plotOptions: {
                bar: {
                    horizontal: true,
                    borderRadius: 4,
                    barHeight: "62%",
                    // Without this every bar takes the first colour, because a
                    // single series is one colour to Apex unless told otherwise.
                    distributed: true,
                },
            },
            // `distributed` gives each bar its own legend entry, which for a
            // top-ten list is ten redundant swatches beside ten labelled bars.
            legend: {show: false},
            dataLabels: {
                enabled: true,
                formatter: (_value, {dataPointIndex}) => displays[dataPointIndex],
                offsetX: 0,
                style: {
                    fontFamily: "IRANSansWeb, Helvetica, sans-serif",
                    fontSize: "12px",
                    fontWeight: 600,
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
            },
            yaxis: {
                labels: {
                    style: {fontFamily: "IRANSansWeb, Helvetica, sans-serif", fontSize: "12px"},
                    // A long customer name would otherwise push the plot into a
                    // sliver; past this it ellipsises and the tooltip has it.
                    maxWidth: 180,
                },
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
            actions.className = "row-actions";
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
        renderPerformanceChart(prefix, report.results);
        const hasActivity = Number(report.summary.customers_created_count) > 0 || Number(report.summary.sales_count) > 0;
        document.getElementById(`${prefix}-performance-empty`).hidden = hasActivity;
        document.getElementById(`${prefix}-performance-content`).hidden = false;
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
            const button = form.querySelector("button[type='submit']");
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
        const controller = setupPagedList({
            key: "activity-logs",
            form,
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
    const CHEQUE_TRANSITIONS = Object.freeze({
        pending: ["cleared", "bounced", "spent"],
        cleared: [],
        bounced: ["pending"],
        spent: [],
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
        return withCurrency ? `${body} ریال` : body;
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
        const dialog = document.getElementById("create-warehouse-dialog");
        if (dialog) {
            const createForm = document.getElementById("create-warehouse-form");
            document.getElementById("open-create-warehouse").addEventListener("click", () => dialog.showModal());
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
        const movementDialog = document.getElementById("create-movement-dialog");
        const transferDialog = document.getElementById("transfer-stock-dialog");
        let controller = null;

        // Handlers are attached before any awaited load so a click landing in
        // the first moments of the page is not silently discarded.
        if (movementDialog) {
            const createForm = document.getElementById("create-movement-form");
            document.getElementById("open-create-movement").addEventListener("click", () => movementDialog.showModal());
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
            document.getElementById("open-transfer-stock").addEventListener("click", () => transferDialog.showModal());
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
        try {
            await loadWarehouseOptions(document.getElementById("stock-movement-warehouse"), "همه انبارها");
        } catch (error) {
            showError(error);
        }
        const controller = setupPagedList({
            key: "stock-movements",
            form,
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

    function setupDocumentList({key, prefix, endpoint, columns, detailPath, createFields}) {
        const form = document.getElementById(`${prefix}-search-form`);
        const dialog = document.getElementById(`create-${prefix}-dialog`);
        let controller = null;
        if (dialog) {
            const createForm = document.getElementById(`create-${prefix}-form`);
            document.getElementById(`open-create-${prefix}`).addEventListener("click", () => dialog.showModal());
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
            endpoint,
            renderRow: (row) => documentListRow(row, columns, (item) => `${detailPath}${item.id}/`),
        });
        controller.load();
        return controller;
    }

    function documentFirstLine(data) {
        const line = {product: Number(data.get("product")), quantity: Number(data.get("quantity"))};
        return [line];
    }

    async function setupOrders() {
        try {
            await Promise.all([
                loadCustomerOptions(document.getElementById("create-order-customer"), "یک مشتری انتخاب کنید"),
                loadProductOptions(document.getElementById("create-order-product"), "یک کالا انتخاب کنید"),
                // The order names the warehouse its goods leave from on approval.
                loadWarehouseOptions(document.getElementById("create-order-warehouse"), "بدون اثر انبار"),
            ]);
        } catch (error) {
            showError(error);
        }
        setupDocumentList({
            key: "orders",
            prefix: "order",
            detailPath: "/orders/",
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
                    items: documentFirstLine(data),
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
        try {
            await Promise.all([
                loadCustomerOptions(document.getElementById("create-invoice-customer"), "یک مشتری انتخاب کنید"),
                loadProductOptions(document.getElementById("create-invoice-product"), "یک کالا انتخاب کنید"),
            ]);
        } catch (error) {
            showError(error);
        }
        setupDocumentList({
            key: "invoices",
            prefix: "invoice",
            detailPath: "/invoices/",
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page)});
                const search = document.getElementById("invoice-search").value.trim();
                if (search) query.set("search", search);
                const status = document.getElementById("invoice-status-filter").value;
                if (status) query.set("status", status);
                const settlement = document.getElementById("invoice-settlement-filter").value;
                if (settlement) query.set("settlement", settlement);
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
                (row, item) => appendCell(row, displayDay(item.issued_at)).classList.add("text-center"),
                (row, item) => appendCell(row, displayDay(item.due_at)).classList.add("text-center"),
            ],
            createFields: (data) => {
                // No warehouse: an invoice moves no stock, so naming one would
                // suggest an effect it does not have.
                return {
                    customer: Number(data.get("customer")),
                    invoice_type: String(data.get("invoice_type") || "unofficial"),
                    items: documentFirstLine(data),
                };
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
        const orderSelect = document.getElementById("invoice-order");
        const paidInput = document.getElementById("invoice-paid");
        const allocationsSection = document.getElementById("invoice-allocations");
        const form = document.getElementById("edit-invoice-form");
        const editActions = document.getElementById("invoice-edit-actions");
        const lockedNote = document.getElementById("invoice-locked-note");
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
            if (orderSelect) orderSelect.value = invoice.order ? String(invoice.order) : "";
            // Editable only while the invoice is a draft: after issue the type is
            // part of what was issued, and the service refuses to change it.
            const typeSelect = document.getElementById("edit-invoice-type");
            if (typeSelect) {
                typeSelect.value = invoice.invoice_type || "unofficial";
                typeSelect.disabled = invoice.status !== "draft";
            }
            syncOfficialInvoiceNotice(invoice);
            document.getElementById("invoice-issued-at").value = displayDate(invoice.issued_at);
            document.getElementById("edit-invoice-due").value = localDateValue(invoice.due_at);
            // The typed figure is what the operator last entered; when nothing
            // has been typed the canonical paid amount is shown instead.
            paidInput.value = moneyDigits(invoice.manual_paid_entry ?? invoice.paid_amount);
            paidInput.disabled = Boolean(invoice.is_manually_settled);
            document.getElementById("invoice-balance").value = money(invoice.balance_due);
            document.getElementById("edit-invoice-notes").value = invoice.notes || "";
            const editable = invoice.status === "draft";
            if (editActions) editActions.hidden = !editable;
            if (lockedNote) lockedNote.hidden = editable;
            form.querySelectorAll("input[name], textarea[name]").forEach((field) => { field.disabled = !editable; });
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
                // Document discount and tax rate are not offered on this form.
                const payload = {notes: String(data.get("notes") || "")};
                payload.due_at = apiDateTime(textOrNull(data.get("due_at")));
                const typeField = document.getElementById("edit-invoice-type");
                if (typeField && !typeField.disabled) payload.invoice_type = typeField.value;
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

        // Attaching the invoice to an order, after both already exist. Client-1
        // raises the invoice first, so this is the normal order of events.
        orderSelect?.addEventListener("change", async () => {
            const chosen = numberOrNull(orderSelect.value);
            if (!current || chosen === (current.order ?? null)) return;
            orderSelect.disabled = true;
            clearMessages();
            try {
                apply(await apiRequest(`${endpoint}link-order/`, {
                    method: "POST", body: {order: chosen},
                }));
                globalMessage(chosen === null ? "پیوند سفارش برداشته شد." : "فاکتور به سفارش پیوند خورد.", true);
            } catch (error) {
                orderSelect.value = current.order ? String(current.order) : "";
                showError(error);
            } finally {
                orderSelect.disabled = false;
            }
        });

        // The typed "پرداخت شده" figure. Matching the outstanding amount settles
        // the invoice for good; it writes no Payment, allocation or ledger entry.
        document.getElementById("edit-invoice-type")?.addEventListener("change", () => {
            syncOfficialInvoiceNotice(current);
        });

        paidInput?.addEventListener("change", async () => {
            if (!current || current.is_manually_settled) return;
            const typed = moneyValue(paidInput.value);
            if (!typed) return;
            paidInput.disabled = true;
            clearMessages();
            try {
                const updated = await apiRequest(`${endpoint}manual-paid/`, {
                    method: "POST", body: {amount: typed},
                });
                apply(updated);
                globalMessage(
                    updated.is_manually_settled
                        ? "فاکتور تسویه‌شده ثبت شد."
                        : "مبلغ پرداخت‌شده ثبت شد.",
                    true,
                );
            } catch (error) {
                paidInput.value = moneyDigits(current.manual_paid_entry ?? current.paid_amount);
                showError(error);
            } finally {
                paidInput.disabled = Boolean(current?.is_manually_settled);
            }
        });

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
            if (orderSelect) {
                // Only the caller's own orders for this customer are offered;
                // the API refuses anything else regardless.
                const orders = await loadAllPages(
                    `/api/v1/orders/?customer=${invoice.customer}&ordering=-created_at`
                );
                fillSelect(orderSelect, orders, (item) => item.number, "بدون سفارش");
            }
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
        appendStatusBadgeCell(row, PAYMENT_STATUS_TEXT, payment.status);
        appendCell(row, displayDate(payment.received_at));
        appendDetailLink(row, `/payments/${payment.id}/`);
        return row;
    }

    async function setupPayments() {
        const form = document.getElementById("payment-search-form");
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

            // «چک مشتری» spends an instrument already recorded, so the only
            // thing to ask for is which one. «چک تازه» writes a new one and
            // needs its details.
            function applyChequeSource() {
                const spending =
                    direction === "disbursement" &&
                    methodField.value === "cheque" &&
                    chequeSource &&
                    chequeSource.value === "customer_endorsed";
                if (existingChequeRow) existingChequeRow.hidden = !spending;
                if (newChequeFields) {
                    newChequeFields.hidden = methodField.value !== "cheque" || spending;
                }
                if (chequeNote) {
                    chequeNote.hidden = methodField.value !== "cheque" || spending;
                }
            }

            if (chequeSource) chequeSource.addEventListener("change", applyChequeSource);

            modeButtons.forEach((button) => {
                button.addEventListener("click", () => selectMode(button.dataset.paymentMode));
            });

            selectMode("cash");
            setupSearchableSelects(createForm);

            document.getElementById("open-create-payment").addEventListener("click", () => dialog.showModal());
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
        const cancelSection = document.getElementById("payment-cancel-section");
        const allocateForm = document.getElementById("payment-allocate-form");
        let payment;
        let allocationsController = null;

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
            if (allocateSection) allocateSection.hidden = payment.status !== "confirmed";
            if (cancelSection) cancelSection.hidden = payment.status === "cancelled";
            if (payment.status === "confirmed") allocationsController?.load();
        }

        // --- تقسیم یک دریافت بین چند فاکتور (بند ۳.۲) ----------------------
        //
        // A second form rather than more controls on the first one. Allocating
        // to a single invoice is the common action and stays a single line;
        // dividing a receipt is a deliberate, multi-row decision and is worth
        // its own submit. Both post to the same rules on the server.
        const splitForm = document.getElementById("payment-split-form");
        const splitRows = document.getElementById("payment-split-rows");
        const splitTotal = document.getElementById("payment-split-total");

        function splitInvoiceOptions() {
            // Cloned from the single-allocation select, which is already
            // filtered to this customer's issued invoices that still owe
            // something, so the two lists can never disagree.
            const source = document.getElementById("payment-allocate-invoice");
            return source ? source.innerHTML : "";
        }

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
            const select = document.createElement("select");
            select.className = "form-select form-select-solid w-auto flex-grow-1";
            select.dataset.splitInvoice = "";
            select.setAttribute("aria-label", "فاکتور");
            select.innerHTML = splitInvoiceOptions();
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
            row.append(select, amount, remove);
            splitRows.append(row);
            // Money grouping is wired once per input by the shared helper, which
            // guards against binding the same field twice.
            setupMoneyInputs(row);
            refreshSplitTotal();
        }

        document.getElementById("payment-split-add")?.addEventListener("click", addSplitRow);

        splitForm?.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(splitForm, async () => {
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
                    const slot = splitForm.querySelector('[data-error-for="splits"]');
                    if (slot) slot.textContent = "حداقل یک فاکتور را انتخاب کنید.";
                    return;
                }
                await apiRequest(`${endpoint}allocate-across/`, {method: "POST", body: {splits}});
                globalMessage("دریافت بین فاکتورها تقسیم شد.", true);
                splitRows.replaceChildren();
                refreshSplitTotal();
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

        allocateForm?.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(allocateForm, async () => {
                const data = new FormData(allocateForm);
                const body = {invoice: Number(data.get("invoice"))};
                const amount = moneyOrNull(data.get("amount"));
                if (amount !== null) body.amount = amount;
                await apiRequest(`${endpoint}allocate/`, {method: "POST", body});
                globalMessage("دریافت به فاکتور تخصیص یافت.", true);
                apply(await apiRequest(endpoint));
            });
        });

        document.getElementById("cancel-payment")?.addEventListener("click", async () => {
            if (!window.confirm("این دریافت ابطال شود؟ همه تخصیص‌های فعال آزاد می‌شوند.")) return;
            const button = document.getElementById("cancel-payment");
            button.disabled = true;
            clearMessages();
            try {
                const reason = document.getElementById("payment-cancel-reason").value;
                apply(await apiRequest(`${endpoint}cancel/`, {method: "POST", body: {reason}}));
                globalMessage("دریافت ابطال شد.", true);
            } catch (error) {
                showError(error);
            } finally {
                button.disabled = false;
            }
        });

        allocationsController = setupPagedList({
            key: "payment-allocations",
            form: null,
            endpoint: (page) => `${endpoint}allocations/?page=${page}`,
            renderRow: (allocation) => {
                const row = document.createElement("tr");
                appendCell(row, allocation.invoice_number).dir = "ltr";
                appendMoneyCell(row, allocation.amount);
                appendCell(row, allocation.is_reversed ? "آزادشده" : "فعال");
                appendCell(row, displayDate(allocation.created_at));
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
            const invoices = await loadAllPages(
                `/api/v1/invoices/?status=issued&customer=${value.customer}&ordering=due_at`
            );
            fillSelect(
                document.getElementById("payment-allocate-invoice"),
                invoices.filter((invoice) => Number(invoice.balance_due) > 0),
                (invoice) => `${invoice.number} — مانده ${money(invoice.balance_due)}`,
                "یک فاکتور انتخاب کنید",
            );
            apply(value);
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

                // --- حالت: registered, or not -------------------------------
                //
                // Its own cell so the column widths stay put: the two buttons
                // are always both present and always the same size, so a row
                // does not resize as its state changes.
                const registration = document.createElement("td");
                registration.className = "row-actions";
                [
                    [true, "ثبت شده"],
                    [false, "ثبت نشده"],
                ].forEach(([target, label]) => {
                    const button = document.createElement("button");
                    button.type = "button";
                    const current = Boolean(cheque.is_registered) === target;
                    button.className = `btn btn-sm ${current ? "btn-primary" : "btn-light"}`;
                    button.textContent = label;
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
                            globalMessage(`حالت چک به «${label}» تغییر کرد.`, true);
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

    setupJalaliInputs();
    setupNav();
    setupNavActiveState();
    setupLogout();
    setupUserMenu();
    setupSessionsDialog();

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

    function setupSidebarExpander() {
        const expand = document.getElementById("app-sidebar-expand");
        const toggle = document.getElementById("kt_app_sidebar_toggle");
        if (!expand || !toggle) return;
        expand.addEventListener("click", () => toggle.click());
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

    setupSearchableSelects();
    setupChartThemeRedraw();
    setupThemeModePopup();
    setupSidebarExpander();
    setupProfileDialog();

    // Any page that declares a chart card gets one, whichever page it is.
    setupListCharts();

    const page = document.body.dataset.page;
    if (page === "login") setupLogin();
    if (page === "dashboard") setupDashboard();
    if (page === "users") setupUsers();
    if (page === "user-detail") setupUserDetail();
    if (page === "customers") setupCustomers();
    if (page === "customer-detail") setupCustomerDetail();
    if (page === "leads") setupLeads();
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
    if (page === "sales-document-report") setupSalesDocumentReport();
    if (page === "inbound-sms-report") setupInboundSMSReport();
    if (page === "after-sales") setupAfterSales();
    if (page === "after-sales-detail") setupAfterSalesDetail();
    if (page === "activity-logs") setupActivityLogs();
    if (page === "activity-log-detail") setupActivityLogDetail();
    if (page === "warehouses") setupWarehouses();
    if (page === "warehouse-detail") setupWarehouseDetail();
    if (page === "stock-levels") setupStockLevels();
    if (page === "stock-movements") setupStockMovements();
    if (page === "orders") setupOrders();
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
    // `document-print` is the print base's own id, used when a printable page
    // does not override it; every printable page needs the print button wired.
    if (page === "invoice-print" || page === "document-print") setupDocumentPrint();
})();
