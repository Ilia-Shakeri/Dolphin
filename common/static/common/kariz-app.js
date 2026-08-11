(() => {
    "use strict";

    const ROLE_LABELS = Object.freeze({
        sales_agent: "کارشناس فروش",
        sales_manager: "مدیر فروش",
        company_it: "فناوری اطلاعات شرکت",
        platform_admin: "مدیر سامانه",
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

    function userRow(user) {
        const row = document.createElement("tr");
        const displayName = [user.first_name, user.last_name].filter(Boolean).join(" ") || "—";
        const cells = [user.username, displayName, ROLE_LABELS[user.role] || "—"];
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
                    body: formPayload(createForm, ["username", "password", "first_name", "last_name", "email", "phone"]),
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
        document.getElementById("edit-role").value = user.role;
        const deactivate = document.getElementById("deactivate-user");
        deactivate.disabled = !user.is_active;
        deactivate.textContent = user.is_active ? "غیرفعال کردن کاربر" : "کاربر غیرفعال است";
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
                const payload = formPayload(editForm, ["username", "first_name", "last_name", "email", "phone", "password"]);
                if (!payload.password) delete payload.password;
                user = await apiRequest(endpoint, {method: "PATCH", body: payload});
                fillUser(user);
                globalMessage("مشخصات کاربر ذخیره شد.", true);
            });
        });

        const roleForm = document.getElementById("change-role-form");
        roleForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(roleForm, async () => {
                user = await apiRequest(roleForm.action, {method: "POST", body: formPayload(roleForm, ["role"])});
                fillUser(user);
                globalMessage("نقش کاربر تغییر کرد.", true);
            });
        });

        const deactivate = document.getElementById("deactivate-user");
        deactivate.addEventListener("click", async () => {
            if (!window.confirm("این کاربر غیرفعال شود؟")) return;
            clearMessages();
            deactivate.disabled = true;
            try {
                user = await apiRequest(endpoint, {method: "PATCH", body: {is_active: false}});
                fillUser(user);
                globalMessage("کاربر غیرفعال شد.", true);
            } catch (error) {
                deactivate.disabled = false;
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
                fillSelect(document.getElementById("reassign-to-user"), assignees, (item) => [item.first_name, item.last_name].filter(Boolean).join(" ") || item.username, "انتخاب کارشناس");
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
            fillSelect(document.getElementById("create-interaction-lead"), allowed, (item) => `${item.customer_name || item.customer} — ${item.source || `#${item.id}`}`, "انتخاب سرنخ");
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

    function productRow(product) {
        const row = document.createElement("tr");
        appendCell(row, product.sku);
        appendCell(row, product.name);
        appendCell(row, product.current_price);
        appendCell(row, statusText(product.is_active));
        appendDetailLink(row, `/products/${product.id}/`);
        return row;
    }

    function setupProducts() {
        const form = document.getElementById("product-search-form");
        const controller = setupPagedList({
            key: "products",
            form,
            endpoint: (page) => {
                const query = new URLSearchParams({page: String(page)});
                const search = document.getElementById("product-search").value.trim();
                if (search) query.set("search", search);
                query.set("ordering", document.getElementById("product-ordering").value);
                return `/api/v1/products/?${query}`;
            },
            renderRow: productRow,
        });
        const dialog = document.getElementById("create-product-dialog");
        if (dialog) {
            const createForm = document.getElementById("create-product-form");
            document.getElementById("open-create-product").addEventListener("click", () => dialog.showModal());
            dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
            createForm.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(createForm, async () => {
                    const product = await apiRequest(createForm.action, {method: "POST", body: formPayload(createForm, ["sku", "name", "current_price", "description"])});
                    window.location.assign(`/products/${product.id}/`);
                });
            });
        }
        controller.load();
    }

    function fillProduct(product) {
        document.getElementById("edit-product-sku").value = product.sku;
        document.getElementById("edit-product-name").value = product.name;
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
            product = await apiRequest(endpoint);
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
                    product = await apiRequest(endpoint, {method: "PATCH", body: formPayload(form, ["sku", "name", "current_price", "description"])});
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
            fillSelect(document.getElementById("create-sale-lead"), leads, (lead) => `${lead.customer_name} — ${lead.source}`, "یک سرنخ انتخاب کنید");
            fillSelect(document.getElementById("create-sale-product"), products.filter((product) => product.is_active), (product) => `${product.name} — ${product.current_price}`, "یک محصول انتخاب کنید");
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

    async function setupUserPerformance() {
        const form = document.getElementById("performance-filter-form");
        const now = new Date();
        const start = new Date(now.getFullYear(), now.getMonth(), 1);
        document.getElementById("report-period-start").value = localDateTimeValue(start);
        document.getElementById("report-period-end").value = localDateTimeValue(new Date(now.getTime() + 60000));
        try {
            const products = await loadAllPages("/api/v1/products/?ordering=name");
            fillSelect(document.getElementById("report-product"), products, (product) => product.name, "همه محصولات");
        } catch (error) {
            showError(error);
        }
        const exportLink = document.getElementById("performance-xlsx");
        const updateExport = () => { exportLink.href = `/api/v1/exports/user-performance.xlsx?${reportQuery(form)}`; };
        form.addEventListener("input", updateExport);
        form.addEventListener("change", updateExport);
        updateExport();
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const loading = document.getElementById("performance-loading");
                const empty = document.getElementById("performance-empty");
                const content = document.getElementById("performance-content");
                loading.hidden = false;
                empty.hidden = true;
                content.hidden = true;
                const query = reportQuery(form);
                exportLink.href = `/api/v1/exports/user-performance.xlsx?${query}`;
                let report;
                try {
                    report = await apiRequest(`/api/v1/reports/user-performance/?${query}`);
                } finally {
                    loading.hidden = true;
                }
                const rows = report.results.map((item) => {
                    const row = document.createElement("tr");
                    [item.username, item.customers_created_count, item.sales_count, item.sales_amount, item.average_sale_amount].forEach((value) => appendCell(row, value));
                    return row;
                });
                document.getElementById("performance-table-body").replaceChildren(...rows);
                if (!rows.length) empty.hidden = false;
                else content.hidden = false;
            });
        });
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
    if (page === "profile") setupProfile();
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
    if (page === "sales") setupSales();
    if (page === "sale-detail") setupSaleDetail();
    if (page === "user-performance") setupUserPerformance();
    if (page === "activity-logs") setupActivityLogs();
    if (page === "activity-log-detail") setupActivityLogDetail();
})();
