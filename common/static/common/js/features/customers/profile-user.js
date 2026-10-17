import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate, displayDay, localDateTimeValue} from "dolphin/core/jalali.js";
import {clearMessages, errorText, formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {loadProfileTimeline, loadRecentActivity} from "dolphin/features/customers/profile-activity.js";
import {loadCallStats, loadPbxCalls} from "dolphin/features/customers/profile-calls.js";
import {setOverviewFact, setProfileBadge, setProfileBreadcrumb, setProfileHeaderField, setProfileHeaderPhone, setProfileHeaderText} from "dolphin/features/customers/profile-header.js";
import {setupNotesTab, setupTasksTab} from "dolphin/features/customers/profile-work.js";
import {bucketLabel} from "dolphin/features/customers/shared.js";
import {renderAreaChart, setupChartRange} from "dolphin/ui/charts.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {loadPerformanceDetails} from "dolphin/ui/performance.js";
import {stageBadge} from "dolphin/ui/pipeline.js";
import {reportQuery} from "dolphin/ui/report-wizard.js";
import {appendCell, appendDetailLink, pageRangeLabel} from "dolphin/ui/table.js";

/**
 * The active sessions of one user, with the option to end them.
 *
 * The panel exists only for a user administrator, so it is absent rather
 * than disabled for anyone else. Ending sessions signs the person out; it
 * does not disable the account, which is the separate control above.
 */
/**
 * «نشست‌های فعال» and «تغییر گذرواژه» (2.40.35): two dialogs opened from the
 * profile's «بیشتر» menu, over whichever tab is showing. The sessions are read
 * when the dialog opens, not with the page.
 */
export function setupUserSessions(userId) {
    const sessionsDialog = document.getElementById("user-sessions-dialog");
    const passwordDialog = document.getElementById("set-password-dialog");
    [sessionsDialog, passwordDialog].forEach((dialog) => {
        dialog?.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    });
    const wrap = document.getElementById("user-sessions-table-wrap");
    const body = document.getElementById("user-sessions-table-body");
    const loading = document.getElementById("user-sessions-loading");
    const empty = document.getElementById("user-sessions-empty");
    const revoke = document.getElementById("revoke-user-sessions");

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

    // Setting this account's password (2.40.32): the server ends its
    // sessions.
    const passwordForm = document.getElementById("set-password-form");
    passwordForm?.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(passwordForm, async () => {
            await apiRequest(passwordForm.action, {method: "POST", body: formPayload(passwordForm, ["password", "password_confirm"])});
            passwordForm.reset();
            passwordDialog?.close();
            globalMessage("گذرواژه تغییر کرد و نشست‌های این حساب پایان یافت.", true);
        });
    });

    document.addEventListener("click", (event) => {
        if (event.target.closest('[data-profile-action="set-password"]') && passwordDialog) {
            passwordForm?.reset();
            clearMessages(passwordForm);
            passwordDialog.showModal();
        } else if (event.target.closest('[data-profile-action="sessions"]') && sessionsDialog) {
            sessionsDialog.showModal();
            load();
        }
    });

    if (!wrap || !body || !loading || !empty || !revoke) return;
    revoke.addEventListener("click", async () => {
        if (!await confirmDialog("همه نشست‌های فعال این کاربر پایان یابد؟")) return;
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
}

/** One lead assigned to a user, with the customer it is about. */
function userLeadRow(lead) {
    const row = document.createElement("tr");
    const customerCell = document.createElement("td");
    if (lead.customer) {
        const link = document.createElement("a");
        link.className = "text-gray-900 text-hover-primary fw-semibold";
        link.href = `/customers/${lead.customer}/`;
        link.textContent = lead.customer_name || `مشتری ${toPersianDigits(String(lead.customer))}`;
        customerCell.appendChild(link);
    } else {
        customerCell.textContent = "—";
    }
    row.appendChild(customerCell);
    appendCell(row, lead.source);
    appendCell(row, lead.campaign_or_batch);
    const stageCell = document.createElement("td");
    stageCell.append(stageBadge(lead.stage_display, lead.stage_kind));
    row.append(stageCell);
    appendCell(row, displayDay(lead.next_follow_up_at));
    appendCell(row, displayDay(lead.assigned_at));
    appendDetailLink(row, `/leads/${lead.id}/`);
    return row;
}

function setupUserLeadsTab(userId) {
    const loadingNode = document.getElementById("user-leads-loading");
    const empty = document.getElementById("user-leads-empty");
    const wrap = document.getElementById("user-leads-table-wrap");
    const body = document.getElementById("user-leads-table-body");
    const pagination = document.getElementById("user-leads-pagination");
    const previous = document.getElementById("user-leads-prev");
    const next = document.getElementById("user-leads-next");
    const status = document.getElementById("user-leads-status");
    let currentPage = 1;

    async function load(page = 1) {
        loadingNode.hidden = false;
        empty.hidden = true;
        wrap.hidden = true;
        pagination.hidden = true;
        try {
            const query = new URLSearchParams({page: String(page), assigned_to: String(userId), ordering: "-assigned_at"});
            if (status.value) query.set("status", status.value);
            const data = await apiRequest(`/api/v1/leads/?${query}`);
            body.replaceChildren(...data.results.map(userLeadRow));
            loadingNode.hidden = true;
            if (!data.results.length) { empty.hidden = false; return; }
            wrap.hidden = false;
            currentPage = page;
            previous.disabled = !data.previous;
            next.disabled = !data.next;
            document.getElementById("user-leads-page-label").textContent = pageRangeLabel(data, page);
            pagination.hidden = !data.previous && !data.next;
        } catch (error) {
            loadingNode.hidden = true;
            showError(error);
        }
    }

    previous.addEventListener("click", () => load(currentPage - 1));
    next.addEventListener("click", () => load(currentPage + 1));
    status.addEventListener("change", () => load(1));
    return load();
}

/**
 * «اطلاعات» on a user's profile. `data-edit-mode` says which door the
 * form saves through: `admin` edits the account, `self` only the
 * reader's own profile fields. Neither ever sends a role, an activation
 * flag or a password.
 */
async function setupUserInfoTab() {
    const form = document.getElementById("edit-user-form");
    if (!form) return;
    const mode = form.dataset.editMode;
    const endpoint = form.action;
    const names = mode === "admin"
        ? ["username", "first_name", "last_name", "email", "phone", "workstream", "job_title", "province"]
        : ["first_name", "last_name", "email", "phone", "job_title", "province"];

    function fill(user) {
        names.forEach((name) => {
            const input = form.elements.namedItem(name);
            if (input) input.value = user[name] || "";
        });
        const workstream = form.elements.namedItem("workstream");
        if (workstream) {
            // Only a Sales Agent may run the after-sales workstream — the
            // same rule the service enforces.
            const afterSales = workstream.querySelector('option[value="after_sales"]');
            afterSales.disabled = user.role !== "sales_agent";
            workstream.value = user.role === "sales_agent" ? (user.workstream || "sales") : "sales";
        }
    }

    function reflect(user) {
        const name = [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username;
        setProfileHeaderText("name", name);
        setProfileBreadcrumb(name);
        if (user.job_title) setProfileHeaderField("job_title", user.job_title);
        setProfileHeaderField("province", user.province, "استان این کاربر ثبت نشده است.");
        setProfileHeaderPhone(user.normalized_phone || user.phone, "تلفنی برای این کاربر ثبت نشده است.");
        ["job_title", "province", "email"].forEach((field) => setOverviewFact(field, user[field]));
    }

    const user = await apiRequest(endpoint);
    fill(user);
    form.querySelector("[data-info-loading]").hidden = true;
    form.querySelector("[data-info-fields]").hidden = false;
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const saved = await apiRequest(endpoint, {method: "PATCH", body: formPayload(form, names)});
            fill(saved);
            reflect(saved);
            globalMessage(mode === "admin" ? "مشخصات کاربر ذخیره شد." : "مشخصات شما ذخیره شد.", true);
        });
    });
}

/**
 * «دسترسی‌ها» on a user's profile: the controlled role change, the
 * active sessions and activation, as the old «جزئیات کاربر» page had
 * them. The permission matrix opens the same dialog User Management uses
 * (`setupPermissionsDialog`), wired once for the whole page.
 */
async function setupUserAccessTab(userId) {
    const endpoint = `/api/v1/users/${userId}/`;
    let user = await apiRequest(endpoint);

    function fillAccess(value) {
        const role = document.getElementById("edit-role");
        if (role) role.value = value.role;
        const toggle = document.getElementById("toggle-user-active");
        toggle.disabled = false;
        toggle.dataset.nextActive = String(!value.is_active);
        toggle.classList.toggle("btn-danger", value.is_active);
        toggle.classList.toggle("btn-success", !value.is_active);
        toggle.textContent = value.is_active ? "غیرفعال کردن کاربر" : "فعال کردن دوباره کاربر";
        setProfileBadge(value.is_active ? {label: "فعال", accent: "success"} : {label: "غیرفعال", accent: "danger"});
        const twoFactor = document.getElementById("user-two-factor-card");
        if (twoFactor) twoFactor.hidden = !value.two_factor_enabled;
    }
    fillAccess(user);

    // A lost phone (2.40.42): the Platform Admin takes two-factor sign-in off
    // this account; the server re-checks who may.
    const resetTwoFactor = document.getElementById("reset-user-two-factor");
    resetTwoFactor?.addEventListener("click", async () => {
        if (!await confirmDialog("ورود دومرحله‌ای این کاربر بازنشانی شود؟ از این پس فقط با گذرواژه وارد می‌شود تا دوباره روشنش کند.")) return;
        clearMessages();
        resetTwoFactor.disabled = true;
        try {
            await apiRequest(`${endpoint}reset-two-factor/`, {method: "POST", body: {}});
            user = await apiRequest(endpoint);
            fillAccess(user);
            globalMessage("ورود دومرحله‌ای این کاربر بازنشانی شد.", true);
        } catch (error) {
            showError(error);
        } finally {
            resetTwoFactor.disabled = false;
        }
    });

    const roleForm = document.getElementById("change-role-form");
    if (roleForm) {
        const permissionsDialog = document.getElementById("role-change-access-dialog");
        // Out of the tab pane, for the reason the permissions dialog is (2.40.32).
        if (permissionsDialog.parentElement !== document.body) document.body.append(permissionsDialog);
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
                fillAccess(user);
                globalMessage("نقش کاربر تغییر کرد.", true);
            });
        });
    }

    const toggle = document.getElementById("toggle-user-active");
    toggle.addEventListener("click", async () => {
        const nextActive = toggle.dataset.nextActive === "true";
        if (!await confirmDialog(nextActive ? "این کاربر دوباره فعال شود؟" : "این کاربر غیرفعال شود؟")) return;
        clearMessages();
        toggle.disabled = true;
        try {
            user = await apiRequest(endpoint, {method: "PATCH", body: {is_active: nextActive}});
            fillAccess(user);
            globalMessage(nextActive ? "کاربر دوباره فعال شد." : "کاربر غیرفعال شد.", true);
        } catch (error) {
            toggle.disabled = false;
            showError(error);
        }
    });
}

export function userProfileLoaders(userId) {
    return {
        overview: () => loadRecentActivity("user", userId),
        info: setupUserInfoTab,
        leads: () => setupUserLeadsTab(userId),
        performance: setupSellerProfile,
        calls: () => loadPbxCalls("user-pbx-calls", `/api/v1/calls/?user=${userId}`),
        activity: () => loadProfileTimeline("user", userId),
        tasks: () => setupTasksTab("user", userId),
        notes: () => setupNotesTab("user", userId),
        access: () => setupUserAccessTab(userId),
    };
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
        loadCallStats(targetUserId, query);
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

    // The same shared control the customers page and every list page
    // use. It replaces this page's own «هفتگی/ماهانه» pair, which asked
    // for a bucket width where the reader wanted a window.
    const trendRange = setupChartRange(
        document.getElementById("profile-trend-controls"),
        () => loadTrend(),
        {initial: "1y", label: "بازهٔ زمانی نمودار روند"},
    );

    async function loadTrend() {
        const chart = document.getElementById("profile-trend-chart");
        const empty = document.getElementById("profile-trend-chart-empty");
        try {
            const query = new URLSearchParams({
                user_id: targetUserId,
                ...(trendRange ? trendRange.window() : {}),
            });
            const report = await apiRequest(`/api/v1/reports/user-performance/trend/?${query}`);
            const points = report.results.map((row) => ({
                label: bucketLabel(row.bucket, report.granularity),
                value: Number(row.sales_amount),
                display: money(row.sales_amount),
            }));
            renderAreaChart(chart, empty, points, {
                ariaLabel: "نمودار روند فروش تأییدشده",
                seriesName: "مبلغ فروش تأییدشده",
                resetButton: trendRange && trendRange.resetHost,
            });
        } catch (error) {
            if (chart) chart.hidden = true;
            if (empty) {
                empty.textContent = "نمودار روند در دسترس نیست.";
                empty.hidden = false;
            }
        }
    }

    section.querySelectorAll("[data-performance-detail]").forEach((button) => {
        button.addEventListener("click", () => {
            loadPerformanceDetails("profile", targetUserId, targetUsername, button.dataset.performanceDetail);
        });
    });

    await Promise.all([loadPerformance(), loadTrend()]);
}
