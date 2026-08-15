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
            headers["Content-Type"] = "application/json";
            options.body = JSON.stringify(options.body);
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
                    node.textContent = Array.isArray(value) ? value.join(" ") : String(value);
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

    function setupNav() {
        const toggle = document.getElementById("nav-toggle");
        if (!toggle) return;
        toggle.addEventListener("click", () => {
            const open = document.body.classList.toggle("nav-open");
            toggle.setAttribute("aria-expanded", String(open));
        });
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
        appendCell(row, lead.customer_name || lead.customer);
        appendCell(row, lead.source);
        appendCell(row, displayDate(lead.next_follow_up_at));
        const actions = document.createElement("td");
        actions.className = "row-actions";
        [
            [`/customers/${lead.customer}/`, "مشتری"],
            [`/leads/${lead.id}/`, "سرنخ"],
            [`/interactions/?lead=${lead.id}`, "ثبت تماس"],
            [`/sales/?lead=${lead.id}`, "ثبت فروش"],
        ].forEach(([href, label]) => {
            const link = document.createElement("a");
            link.className = "button button-muted";
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
                document.getElementById("agent-work-queue-page-label").textContent = `صفحه ${page}`;
                pager.hidden = !data.previous && !data.next;
            } catch (error) { loading.hidden = true; showError(error); }
        }
        previous.addEventListener("click", () => load(currentPage - 1));
        next.addEventListener("click", () => load(currentPage + 1));
        await load();
    }

    async function setupDashboard() {
        await Promise.all([setupProfile(), setupWorkQueue(), setupPerformancePanel("dashboard")]);
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
        link.className = "button button-muted";
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
                document.getElementById("users-page-label").textContent = `صفحه ${page}`;
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
        toggle.classList.toggle("button-danger", user.is_active);
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
                const payload = formPayload(editForm, ["username", "first_name", "last_name", "email", "phone", "password", "workstream"]);
                if (!payload.password) delete payload.password;
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
        link.className = "button button-muted";
        link.href = href;
        link.textContent = "جزئیات";
        cell.appendChild(link);
        row.appendChild(cell);
    }

    function statusText(active) {
        return active ? "فعال" : "غیرفعال";
    }

    function directionText(direction) {
        return direction === "inbound" ? "ورودی" : direction === "outbound" ? "خروجی" : direction;
    }

    function displayDate(value) {
        if (!value) return "—";
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? value : date.toLocaleString("fa-IR");
    }

    function localDateTimeValue(value) {
        if (!value) return "";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "";
        const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
        return shifted.toISOString().slice(0, 16);
    }

    function apiDateTime(value) {
        return value ? new Date(value).toISOString() : null;
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
                document.getElementById(`${key}-page-label`).textContent = `صفحه ${page}`;
                pagination.hidden = !data.previous && !data.next;
            } catch (error) {
                loading.hidden = true;
                showError(error);
            }
        }
        form.addEventListener("submit", (event) => { event.preventDefault(); load(1); });
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
        appendCell(row, statusText(customer.is_active));
        appendCell(row, customer.created_by_display || customer.created_by);
        appendDetailLink(row, `/customers/${customer.id}/`);
        return row;
    }

    function setupCustomers() {
        const form = document.getElementById("customer-search-form");
        const controller = setupPagedList({
            key: "customers",
            form,
            endpoint(page) {
                const query = new URLSearchParams({page: String(page), ordering: document.getElementById("customer-ordering").value});
                const search = document.getElementById("customer-search").value.trim();
                if (search) query.set("search", search);
                return `/api/v1/customers/?${query}`;
            },
            renderRow: customerRow,
        });
        controller.load();
        const dialog = document.getElementById("create-customer-dialog");
        const createForm = document.getElementById("create-customer-form");
        document.getElementById("open-create-customer").addEventListener("click", () => dialog.showModal());
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const payload = formPayload(createForm, ["full_name", "national_id", "email", "province", "city", "postal_code", "category", "address", "notes"]);
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

    function phoneRow(phone, edit, deactivate) {
        const row = document.createElement("tr");
        appendCell(row, phone.raw_phone);
        appendCell(row, phone.normalized_phone);
        appendCell(row, phone.label);
        appendCell(row, phone.is_primary ? "بله" : "خیر");
        appendCell(row, statusText(phone.is_active));
        const actions = document.createElement("td");
        const editButton = document.createElement("button");
        editButton.className = "button button-muted";
        editButton.type = "button";
        editButton.textContent = "ویرایش";
        editButton.addEventListener("click", () => edit(phone));
        actions.appendChild(editButton);
        const deactivateButton = document.createElement("button");
        deactivateButton.className = "button button-danger";
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
            ["full_name", "national_id", "email", "province", "city", "postal_code", "category", "address", "notes"].forEach((name) => {
                document.getElementById(`edit-customer-${name.replaceAll("_", "-").replace("full-name", "name")}`).value = value[name] || "";
            });
            document.getElementById("customer-created-by").value = value.created_by_display || value.created_by;
            document.getElementById("customer-active").value = statusText(value.is_active);
            const deactivate = document.getElementById("deactivate-customer");
            if (deactivate) {
                deactivate.disabled = !value.is_active;
                deactivate.textContent = value.is_active ? "غیرفعال کردن مشتری" : "مشتری غیرفعال است";
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

        function setupCustomerRelatedList(key, path, renderRow) {
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
                    const data = await apiRequest(`${endpoint}${path}/?page=${page}`);
                    listBody.replaceChildren(...data.results.map(renderRow));
                    listLoading.hidden = true;
                    if (!data.results.length) { listEmpty.hidden = false; return; }
                    listWrap.hidden = false;
                    currentPage = page;
                    previous.disabled = !data.previous;
                    next.disabled = !data.next;
                    document.getElementById(`customer-${key}-page-label`).textContent = `صفحه ${page}`;
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

        const relatedLists = [
            setupCustomerRelatedList("leads", "leads", leadRow),
            setupCustomerRelatedList("interactions", "interactions", interactionRow),
            setupCustomerRelatedList("sales", "sales", saleRow),
        ];

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
                customer = await apiRequest(endpoint, {method: "PATCH", body: formPayload(editForm, ["full_name", "national_id", "email", "province", "city", "postal_code", "category", "address", "notes"])});
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
        const deactivateCustomer = document.getElementById("deactivate-customer");
        deactivateCustomer?.addEventListener("click", async () => {
            if (!window.confirm("این مشتری غیرفعال شود؟")) return;
            deactivateCustomer.disabled = true;
            clearMessages();
            try {
                customer = await apiRequest(`${endpoint}deactivate/`, {method: "POST"});
                fillCustomer(customer);
                globalMessage("مشتری بدون حذف سابقه غیرفعال شد.", true);
            } catch (error) {
                deactivateCustomer.disabled = false;
                showError(error);
            }
        });
    }

    function leadRow(lead) {
        const row = document.createElement("tr");
        appendCell(row, lead.customer_name || lead.customer);
        appendCell(row, lead.source);
        appendCell(row, lead.campaign_or_batch);
        appendCell(row, lead.status);
        appendCell(row, lead.assigned_to_display || lead.assigned_to);
        appendCell(row, displayDate(lead.next_follow_up_at));
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
            const customers = await loadAllPages("/api/v1/customers/?ordering=full_name");
            const products = await loadAllPages("/api/v1/products/?ordering=name");
            fillSelect(document.getElementById("create-lead-customer"), customers.filter((item) => item.is_active), (item) => item.full_name, "انتخاب مشتری");
            fillSelect(document.getElementById("create-lead-product"), products.filter((item) => item.is_active), (item) => item.name, "بدون محصول");
        } catch (error) { showError(error); }
        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const data = new FormData(createForm);
                const payload = formPayload(createForm, ["source", "campaign_or_batch", "notes"]);
                payload.customer = Number(data.get("customer"));
                if (data.get("interested_product")) payload.interested_product = Number(data.get("interested_product"));
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

        function fillLead(value) {
            document.getElementById("lead-customer").value = value.customer_name || value.customer;
            document.getElementById("lead-customer-profile").href = `/customers/${value.customer}/`;
            document.getElementById("lead-status").value = value.status || "ثبت نشده";
            document.getElementById("lead-assigned-to").value = value.assigned_to_display || value.assigned_to || "تخصیص نیافته";
            document.getElementById("lead-created-by").value = value.created_by;
            document.getElementById("edit-lead-source").value = value.source || "";
            document.getElementById("edit-lead-campaign").value = value.campaign_or_batch || "";
            document.getElementById("edit-lead-product").value = value.interested_product || "";
            document.getElementById("edit-lead-follow-up").value = localDateTimeValue(value.next_follow_up_at);
            document.getElementById("edit-lead-notes").value = value.notes || "";
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
                document.getElementById("history-page-label").textContent = `صفحه ${page}`;
                historyPager.hidden = !data.previous && !data.next;
            } catch (error) { historyLoading.hidden = true; showError(error); }
        }

        try {
            lead = await apiRequest(endpoint);
            const products = await loadAllPages("/api/v1/products/?ordering=name");
            if (lead.interested_product && !products.some((item) => item.id === lead.interested_product)) {
                products.push({id: lead.interested_product, name: `محصول ثبت‌شده #${lead.interested_product}`, is_active: true});
            }
            fillSelect(document.getElementById("edit-lead-product"), products.filter((item) => item.is_active || item.id === lead.interested_product), (item) => item.name, "بدون محصول");
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
                const payload = formPayload(editForm, ["source", "campaign_or_batch", "notes"]);
                payload.interested_product = data.get("interested_product") ? Number(data.get("interested_product")) : null;
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
    }

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
        document.getElementById("create-interaction-occurred").value = localDateTimeValue(new Date().toISOString());
        document.getElementById("open-create-interaction").addEventListener("click", () => dialog.showModal());
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        try {
            await controller.load();
            const me = await apiRequest("/api/v1/auth/me/");
            const leads = await loadAllPages("/api/v1/leads/?ordering=-created_at");
            const allowed = me.role === "sales_agent" ? leads.filter((item) => item.assigned_to === me.id) : leads;
            const leadSelect = document.getElementById("create-interaction-lead");
            fillSelect(leadSelect, allowed, (item) => `${item.customer_name || item.customer} — ${item.source || `#${item.id}`}`, "انتخاب سرنخ");
            const requestedLead = new URLSearchParams(window.location.search).get("lead");
            if (requestedLead && allowed.some((item) => String(item.id) === requestedLead)) {
                leadSelect.value = requestedLead;
                dialog.showModal();
            }
        } catch (error) { showError(error); }
        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const data = new FormData(createForm);
                const payload = formPayload(createForm, ["phone", "direction", "outcome", "notes"]);
                payload.lead = Number(data.get("lead"));
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
        appendCell(row, statusText(category.is_active));
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
            toggle.classList.toggle("button-danger", category.is_active);
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
        appendCell(row, product.current_price);
        appendCell(row, statusText(product.is_active));
        appendDetailLink(row, `/products/${product.id}/`);
        return row;
    }

    async function setupProducts() {
        const form = document.getElementById("product-search-form");
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
                    const payload = formPayload(createForm, ["sku", "name", "brand", "barcode", "current_price", "description"]);
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
                query.set("ordering", document.getElementById("product-ordering").value);
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
        document.getElementById("edit-product-barcode").value = product.barcode || "";
        document.getElementById("edit-product-price").value = product.current_price;
        document.getElementById("edit-product-description").value = product.description || "";
        document.getElementById("product-status").value = statusText(product.is_active);
        document.getElementById("product-created-by").value = product.created_by_display || product.created_by;
        document.getElementById("product-updated-by").value = product.updated_by_display || product.updated_by;
        const deactivate = document.getElementById("deactivate-product");
        if (deactivate) {
            deactivate.disabled = !product.is_active;
            deactivate.textContent = product.is_active ? "غیرفعال کردن محصول" : "محصول غیرفعال است";
        }
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
                    const payload = formPayload(form, ["sku", "name", "brand", "barcode", "current_price", "description"]);
                    payload.category = new FormData(form).get("category") ? Number(new FormData(form).get("category")) : null;
                    product = await apiRequest(endpoint, {method: "PATCH", body: payload});
                    fillProduct(product);
                    globalMessage("محصول ذخیره شد.", true);
                });
            });
        }
        const deactivate = document.getElementById("deactivate-product");
        deactivate?.addEventListener("click", async () => {
            if (!window.confirm("این محصول غیرفعال شود؟")) return;
            deactivate.disabled = true;
            try {
                product = await apiRequest(`${endpoint}deactivate/`, {method: "POST"});
                fillProduct(product);
                globalMessage("محصول غیرفعال شد.", true);
            } catch (error) {
                deactivate.disabled = false;
                showError(error);
            }
        });
    }

    function saleStatusText(value) {
        return value === "confirmed" ? "تأییدشده" : value === "cancelled" ? "لغوشده" : value;
    }

    function saleRow(sale) {
        const row = document.createElement("tr");
        appendCell(row, sale.customer_name || sale.customer);
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
            fillSelect(document.getElementById("create-sale-product"), products.filter((product) => product.is_active), (product) => `${product.name} — ${product.current_price}`, "یک محصول انتخاب کنید");
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
        document.getElementById("sale-unit-price").value = sale.unit_price_snapshot || "—";
        document.getElementById("sale-total").value = sale.total_amount;
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
        const chart = document.getElementById("inbound-sms-chart");
        const empty = document.getElementById("inbound-sms-chart-empty");
        chart.replaceChildren();
        if (!rows.length) {
            chart.hidden = true;
            empty.hidden = false;
            return;
        }
        const maximum = Math.max(...rows.map((item) => Number(item.inbound_sms_count)));
        const nodes = rows.map((item) => {
            const row = document.createElement("div");
            row.className = "performance-chart-row";
            const label = document.createElement("span");
            label.className = "performance-chart-label";
            label.textContent = `${item.local_date} — ساعت ${String(item.local_hour).padStart(2, "0")}`;
            const track = document.createElement("span");
            track.className = "performance-chart-track";
            const bar = document.createElement("span");
            bar.className = "performance-chart-bar";
            bar.style.width = `${Math.max(2, (Number(item.inbound_sms_count) / maximum) * 100)}%`;
            track.appendChild(bar);
            const value = document.createElement("strong");
            value.textContent = String(item.inbound_sms_count);
            row.append(label, track, value);
            return row;
        });
        chart.replaceChildren(...nodes);
        chart.hidden = false;
        empty.hidden = true;
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
                button.className = "button button-muted";
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
                    drill.className = "button button-muted";
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

    function renderPerformanceChart(prefix, rows) {
        const chart = document.getElementById(`${prefix}-performance-chart`);
        const empty = document.getElementById(`${prefix}-performance-chart-empty`);
        const values = rows
            .map((row) => ({username: row.username, display: String(row.sales_amount), value: Number(row.sales_amount)}))
            .filter((row) => Number.isFinite(row.value) && row.value > 0);
        chart.replaceChildren();
        if (!values.length) {
            chart.hidden = true;
            empty.hidden = false;
            return;
        }
        const maximum = Math.max(...values.map((row) => row.value));
        const nodes = values.map((item) => {
            const row = document.createElement("div");
            row.className = "performance-chart-row";
            const label = document.createElement("span");
            label.className = "performance-chart-label";
            label.textContent = item.username;
            const track = document.createElement("span");
            track.className = "performance-chart-track";
            const bar = document.createElement("span");
            bar.className = "performance-chart-bar";
            bar.style.width = `${Math.max(2, (item.value / maximum) * 100)}%`;
            track.appendChild(bar);
            const value = document.createElement("strong");
            value.textContent = item.display;
            row.append(label, track, value);
            return row;
        });
        chart.replaceChildren(...nodes);
        chart.setAttribute("aria-label", `نمودار مبلغ فروش تأییدشده برای ${values.length} کاربر مجاز`);
        chart.hidden = false;
        empty.hidden = true;
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
            document.getElementById(`${prefix}-details-page-label`).textContent = `صفحه ${page}`;
            pager.hidden = !data.previous && !data.next;
        } catch (error) {
            loading.hidden = true;
            errorNode.textContent = errorText(error);
            errorNode.hidden = false;
        }
    }

    function renderPerformanceReport(prefix, report) {
        const panel = document.querySelector(`[data-performance-panel="${prefix}"]`);
        Object.entries(report.summary).forEach(([name, value]) => {
            const node = panel.querySelector(`[data-kpi="${name}"]`);
            if (node) node.textContent = String(value);
        });
        const rows = report.results.map((item) => {
            const row = document.createElement("tr");
            [item.username, item.customers_created_count, item.sales_count, item.sales_amount, item.average_sale_amount]
                .forEach((value) => appendCell(row, value));
            const actions = document.createElement("td");
            actions.className = "row-actions";
            [
                ["customers_created_count", "مشتری‌ها", item.customers_created_count],
                ["sales_count", "فروش‌ها", item.sales_count],
            ].forEach(([metric, label, count]) => {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "button button-muted";
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
        appendCell(row, item.operation);
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
            document.getElementById("activity-operation").value = item.operation;
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

    setupNav();
    setupLogout();
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
})();
