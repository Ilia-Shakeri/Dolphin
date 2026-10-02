import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDateTime, displayDate, displayDay, localDateTimeValue, pad2} from "dolphin/core/jalali.js";
import {DOCUMENT_STATUS_TEXT, LEAD_STATUS_LABELS, SETTLEMENT_TEXT} from "dolphin/core/labels.js";
import {clearMessages, errorText, formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {bucketLabel} from "dolphin/features/customers/shared.js";
import {setupAttachmentsPanelFor} from "dolphin/ui/attachments.js";
import {renderAreaChart, setupChartRange, showEmptyChart} from "dolphin/ui/charts.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {fillProvinceSelect} from "dolphin/ui/iran-map.js";
import {loadAllPages} from "dolphin/ui/lists.js";
import {loadPerformanceDetails} from "dolphin/ui/performance.js";
import {openPermissionsDialog, setupPermissionsDialog} from "dolphin/ui/permissions-dialog.js";
import {registerPopover} from "dolphin/ui/popover.js";
import {setupProfileTabs} from "dolphin/ui/profile-tabs.js";
import {reportQuery} from "dolphin/ui/report-wizard.js";
import {interactionRow, leadRow, localPhone} from "dolphin/ui/rows.js";
import {appendActionLinks, appendCell, appendDetailLink, appendMoneyCell, appendStatusBadgeCell, appendStatusCell, labelled, pageRangeLabel, statusText} from "dolphin/ui/table.js";

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

    await load();
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

/**
 * The customer profile's tabs (2.19.0), each a loader the tab strip runs
 * the first time its tab opens — see `setupPersonProfile`. Everything the
 * old «جزئیات مشتری» page did is here, only no longer all at once: the
 * edit form and phones under «اطلاعات», related leads, calls and invoices
 * under their own tabs, the 360° history under «فعالیت‌ها» and the
 * attachments under «اسناد».
 */
function customerProfileLoaders(customerId) {
    const endpoint = `/api/v1/customers/${customerId}/`;
    let customer = null;

    function fillCustomer(value) {
        ["full_name", "job_title", "national_id", "economic_code", "email", "city", "postal_code", "category", "address", "notes"].forEach((name) => {
            const input = document.getElementById(`edit-customer-${name.replaceAll("_", "-").replace("full-name", "name")}`);
            if (input) input.value = value[name] || "";
        });
        fillProvinceSelect(document.getElementById("edit-customer-province"), value.province || "");
        // Only a legal customer has an economic code.
        const economic = document.getElementById("edit-customer-economic-code");
        if (economic) {
            economic.disabled = value.kind !== "legal";
            economic.closest(".col-md-6").hidden = value.kind !== "legal";
        }
        document.getElementById("customer-created-by").value = value.created_by_display || value.created_by;
        // A status administrator gets a select; everyone else the read-only text.
        const activeSelect = document.getElementById("customer-active-select");
        if (activeSelect) {
            activeSelect.value = String(Boolean(value.is_active));
        } else {
            document.getElementById("customer-active").value = statusText(value.is_active);
        }
    }

    /** Keep the header and the overview in step with a saved record. */
    function reflectCustomer(value) {
        setProfileHeaderText("name", value.full_name);
        setProfileBreadcrumb(value.full_name);
        setProfileHeaderField("job_title", value.job_title || `مشتری ${value.kind_display || ""}`.trim());
        setProfileHeaderField("province", value.province, "استان این مشتری ثبت نشده است.");
        setProfileBadge(value.is_active ? null : {label: "غیرفعال", accent: "danger"});
        const facts = {
            job_title: value.job_title,
            national_id: toPersianDigits(value.national_id || ""),
            economic_code: toPersianDigits(value.economic_code || ""),
            email: value.email,
            place: [value.province, value.city].filter(Boolean).join("، "),
            postal_code: toPersianDigits(value.postal_code || ""),
            category: value.category,
            address: value.address,
            notes: value.notes,
        };
        Object.entries(facts).forEach(([name, text]) => setOverviewFact(name, text));
    }

    async function setupInfo() {
        const editForm = document.getElementById("edit-customer-form");
        const loadingNode = editForm.querySelector("[data-info-loading]");
        const fields = editForm.querySelector("[data-info-fields]");
        customer = await apiRequest(endpoint);
        fillCustomer(customer);
        loadingNode.hidden = true;
        fields.hidden = false;
        editForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(editForm, async () => {
                customer = await apiRequest(endpoint, {method: "PATCH", body: formPayload(editForm, ["full_name", "job_title", "national_id", "economic_code", "email", "province", "city", "postal_code", "category", "address", "notes"])});
                fillCustomer(customer);
                reflectCustomer(customer);
                globalMessage("مشخصات مشتری ذخیره شد.", true);
            });
        });
        // Activation state. Reversible on purpose: it hides the customer
        // from day-to-day work and removes nothing, so switching back
        // restores them.
        const activeSelect = document.getElementById("customer-active-select");
        activeSelect?.addEventListener("change", async () => {
            const nextActive = activeSelect.value === "true";
            if (nextActive === Boolean(customer.is_active)) return;
            const question = nextActive ? "این مشتری دوباره فعال شود؟" : "این مشتری غیرفعال شود؟";
            if (!await confirmDialog(question)) {
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
                reflectCustomer(customer);
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
        await setupPhones();
    }

    async function setupPhones() {
        const phoneLoading = document.getElementById("phones-loading");
        const phoneEmpty = document.getElementById("phones-empty");
        const phoneWrap = document.getElementById("phones-table-wrap");
        const phoneBody = document.getElementById("phones-table-body");
        const phoneDialog = document.getElementById("phone-dialog");
        const phoneForm = document.getElementById("phone-form");
        let editingPhoneId = null;

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
            if (!await confirmDialog("این تلفن غیرفعال شود؟")) return;
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
                // The header shows the primary active number; a change
                // here is reflected there without a reload.
                const active = phones.filter((phone) => phone.is_active);
                const primary = active.find((phone) => phone.is_primary) || active[0] || null;
                setProfileHeaderPhone(primary ? primary.normalized_phone || primary.raw_phone : "", "تلفن فعالی برای این مشتری ثبت نشده است.");
                if (!phones.length) { phoneEmpty.hidden = false; return; }
                phoneWrap.hidden = false;
            } catch (error) {
                phoneLoading.hidden = true;
                showError(error);
            }
        }

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
        await loadPhones();
    }

    function relatedList(key, path, renderRow, {absolute = false} = {}) {
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
                // Most related lists are sub-resources of the customer;
                // invoices read their own endpoint filtered by this
                // customer, because that is where invoices live.
                const url = absolute
                    ? `${path}${path.includes("?") ? "&" : "?"}page=${page}`
                    : `${endpoint}${path}/?page=${page}`;
                const data = await apiRequest(url);
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
        return load();
    }

    /**
     * One row per invoice this customer has. Both settlement columns are
     * shown because they can disagree — a manually settled invoice reads
     * as paid while its canonical balance is untouched, and hiding one of
     * the two would make the page lie.
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

    return {
        overview: () => loadRecentActivity("customer", customerId),
        info: setupInfo,
        leads: () => relatedList("leads", "leads", leadRow),
        // The call-centre records with this customer (2.27.0) — the PBX
        // box left this tab.
        calls: () => relatedList("interactions", "interactions", interactionRow),
        finance: () => relatedList("invoices", `/api/v1/invoices/?customer=${customerId}`, customerInvoiceRow, {absolute: true}),
        tasks: () => setupTasksTab("customer", customerId),
        notes: () => setupNotesTab("customer", customerId),
        documents: () => {
            document.querySelectorAll('[data-profile-pane="documents"] [data-attachments-panel]').forEach(setupAttachmentsPanelFor);
        },
        analysis: () => setupCustomerAnalysis(customerId),
    };
}

// The customer «آنالیز» tab (2.33.0): one request fills five figures; the
// box the reader picks decides which monthly series the smooth line draws.
async function setupCustomerAnalysis(customerId) {
    const root = document.getElementById("customer-analysis");
    if (!root) return;
    const chart = document.getElementById("customer-analysis-chart");
    const empty = document.getElementById("customer-analysis-chart-empty");
    const title = document.getElementById("customer-analysis-chart-title");
    const note = document.getElementById("customer-analysis-chart-note");
    const boxes = Array.from(root.querySelectorAll("[data-analysis-kpi]"));
    let data;
    try {
        data = await apiRequest(`/api/v1/profiles/customer/${customerId}/analysis/`);
    } catch (error) {
        document.getElementById("customer-analysis-error").hidden = false;
        throw error;
    }
    boxes.forEach((box) => {
        const kpi = data.kpis[box.dataset.analysisKpi];
        const value = box.querySelector("[data-analysis-value]");
        value.textContent = kpi?.display ?? "—";
        if (kpi?.tooltip) box.title = kpi.tooltip;
        if (kpi?.overdue) value.classList.add("text-danger");
    });

    function choose(key) {
        boxes.forEach((box) => {
            const on = box.dataset.analysisKpi === key;
            box.setAttribute("aria-pressed", String(on));
            box.classList.toggle("border-primary", on);
        });
        const box = boxes.find((item) => item.dataset.analysisKpi === key);
        const series = data.series[key];
        title.textContent = box.querySelector("[data-analysis-title]").textContent;
        if (!series) {
            note.textContent = data.kpis[key]?.tooltip || "";
            showEmptyChart(chart, empty);
            return;
        }
        note.textContent = series.label;
        renderAreaChart(chart, empty, series.points, {
            ariaLabel: `نمودار ${series.label}`,
            seriesName: series.label,
            maxLabels: 6,
        });
    }

    boxes.forEach((box) => box.addEventListener("click", () => choose(box.dataset.analysisKpi)));
    choose(data.series.total_purchase ? "total_purchase" : (Object.keys(data.series)[0] || boxes[0].dataset.analysisKpi));
}

/** The header's #1–#3 line (`data-profile-field`), kept current after an edit. */
function setProfileHeaderField(name, value, missingTooltip = "") {
    const node = document.querySelector(`[data-profile-field="${name}"]`);
    if (!node) return;
    const icon = node.querySelector("i");
    const label = node.querySelector(".visually-hidden");
    const labelText = label ? label.textContent : "";
    node.replaceChildren();
    if (icon) node.appendChild(icon);
    if (labelText) {
        const hidden = document.createElement("span");
        hidden.className = "visually-hidden";
        hidden.textContent = labelText;
        node.appendChild(hidden);
    }
    if (value) {
        node.append(value);
        node.removeAttribute("title");
    } else {
        node.append("—");
        if (missingTooltip) {
            node.title = missingTooltip;
            const reason = document.createElement("span");
            reason.className = "visually-hidden";
            reason.textContent = missingTooltip;
            node.appendChild(reason);
        }
    }
}

/**
 * The header's phone: a `tel:` link when there is a number, «—» with a
 * reason when there is none. Numbers arrive normalised (`+98…`) and are
 * shown the way people in Iran write them.
 */
function setProfileHeaderPhone(number, missingTooltip) {
    const node = document.querySelector('[data-profile-field="phone"]');
    if (!node) return;
    const value = String(number || "").trim();
    const local = value.startsWith("+98") ? `0${value.slice(3)}` : value;
    const replacement = document.createElement(value ? "a" : "span");
    replacement.className = node.className.replace(" text-hover-primary", "") + (value ? " text-hover-primary" : "");
    replacement.dataset.profileField = "phone";
    const icon = node.querySelector("i");
    if (icon) replacement.appendChild(icon);
    const label = document.createElement("span");
    label.className = "visually-hidden";
    label.textContent = "تلفن: ";
    replacement.appendChild(label);
    if (value) {
        replacement.href = `tel:${value.replace(/[^\d+]/g, "")}`;
        replacement.dir = "ltr";
        replacement.title = `تماس با ${toPersianDigits(local)}`;
        replacement.append(toPersianDigits(local));
    } else {
        replacement.title = missingTooltip;
        replacement.append("—");
    }
    node.replaceWith(replacement);
    const call = document.querySelector('[data-quick-action="call"]');
    if (call && value) call.href = `tel:${value.replace(/[^\d+]/g, "")}`;
}

function setProfileHeaderText(name, value) {
    const node = document.querySelector(`[data-profile-${name}]`);
    if (node && value) node.textContent = value;
}

function setProfileBreadcrumb(value) {
    const node = document.querySelector(".breadcrumb > .breadcrumb-item:last-child");
    if (node && value) node.textContent = value;
    if (value) document.title = document.title.replace(/^[^|]*\|/, `${value} |`);
}

function setProfileBadge(badge) {
    let node = document.querySelector("[data-profile-badge]");
    if (!badge) { node?.remove(); return; }
    if (!node) {
        node = document.createElement("span");
        node.dataset.profileBadge = "";
        document.querySelector("[data-profile-name]")?.after(node);
    }
    node.className = `badge badge-light-${badge.accent}`;
    node.textContent = badge.label;
}

/** An overview fact (`data-overview-field`), «—» when empty. */
function setOverviewFact(name, value) {
    document.querySelectorAll(`[data-overview-field="${name}"]`).forEach((node) => {
        node.textContent = value ? String(value) : "—";
    });
}

/** One timeline event, as the customer timeline has always drawn it. */
function timelineEntry(event) {
    const item = document.createElement("li");
    item.className = "customer-timeline-entry";

    const marker = document.createElement("span");
    marker.className = `customer-timeline-marker bg-light-${event.accent}`;
    const icon = document.createElement("i");
    icon.className = `di-duotone ${event.icon} fs-5 text-${event.accent}`;
    for (let index = 1; index <= (event.icon_paths || 2); index += 1) {
        const path = document.createElement("span");
        path.className = `path${index}`;
        icon.append(path);
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

    const title = document.createElement(event.url ? "a" : "span");
    title.className = "d-block text-gray-900 fw-semibold fs-6 mt-1 text-decoration-none text-break";
    if (event.url) title.href = event.url;
    title.textContent = event.title;

    const subtitle = document.createElement("span");
    subtitle.className = "d-block text-muted fs-7";
    subtitle.textContent = event.subtitle;

    box.append(head, title, subtitle);
    item.append(marker, box);
    return item;
}

/**
 * The «فعالیت‌ها» tab. It reports its own failure in its own card and
 * leaves the rest of the profile standing.
 */
async function loadProfileTimeline(personType, personId) {
    const list = document.getElementById("profile-timeline-list");
    if (!list) return;
    const loadingNode = document.getElementById("profile-timeline-loading");
    const empty = document.getElementById("profile-timeline-empty");
    const failed = document.getElementById("profile-timeline-error");
    const more = document.getElementById("profile-timeline-more");
    try {
        const data = await apiRequest(`/api/v1/profiles/${personType}/${personId}/timeline/`);
        list.replaceChildren(...data.events.map(timelineEntry));
        loadingNode.hidden = true;
        list.hidden = data.events.length === 0;
        empty.hidden = data.events.length > 0;
        // `count` is everything found; `events` is the page shown.
        if (data.count > data.events.length) {
            more.textContent = `${toPersianDigits(String(data.count - data.events.length))} رویداد قدیمی‌تر نشان داده نشده است.`;
            more.hidden = false;
        }
    } catch (error) {
        loadingNode.hidden = true;
        failed.hidden = false;
    }
}

/** The overview's «آخرین رویدادها»: the newest five of the same timeline. */
async function loadRecentActivity(personType, personId) {
    const card = document.querySelector("[data-recent-activity]");
    if (!card) return;
    const list = card.querySelector("[data-recent-activity-list]");
    const loadingNode = card.querySelector("[data-recent-activity-loading]");
    const empty = card.querySelector("[data-recent-activity-empty]");
    const failed = card.querySelector("[data-recent-activity-error]");
    const more = card.querySelector("[data-recent-activity-more]");
    // A customer's box holds the whole timeline and scrolls (2.27.0);
    // a user's still shows the newest few beside «همهٔ رویدادها».
    const all = card.hasAttribute("data-recent-activity-all");
    try {
        // Both addresses written out whole, so each one is a path the
        // route check (`test_ui_connectivity`) can resolve.
        const data = await apiRequest(all
            ? `/api/v1/profiles/${personType}/${personId}/timeline/`
            : `/api/v1/profiles/${personType}/${personId}/timeline/?limit=5`);
        list.replaceChildren(...data.events.map(timelineEntry));
        loadingNode.hidden = true;
        list.hidden = data.events.length === 0;
        empty.hidden = data.events.length > 0;
        // The server shows at most so many events; say when there are more
        // rather than letting the list look complete.
        if (all && more && Number(data.count) > data.events.length) {
            more.hidden = false;
            more.textContent = `${toPersianDigits(String(data.events.length))} رویداد تازه‌تر از ${toPersianDigits(String(data.count))} رویداد نمایش داده شده است.`;
        }
    } catch (error) {
        loadingNode.hidden = true;
        failed.hidden = false;
    }
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
    const [label, badgeClass] = LEAD_STATUS_LABELS[lead.status] || [lead.status || "—", "badge-light"];
    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `badge ${badgeClass}`;
    badge.textContent = label;
    statusCell.append(badge);
    row.append(statusCell);
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
    }
    fillAccess(user);

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

    await setupUserSessions(userId);
}

/**
 * The header's stat cards #4–#7 (2.20.0). The server rendered a shell
 * only for the cards this reader may see; this fills their values for
 * the chosen period and re-fills them when the period changes.
 */
function setupProfileCards(personType, personId) {
    const host = document.querySelector("[data-profile-cards]");
    if (!host) return;
    const select = document.getElementById("profile-card-period");

    function paint(box, card) {
        const value = box.querySelector("[data-card-value]");
        value.textContent = card.value;
        value.classList.toggle("text-danger", card.accent === "danger");
        box.title = card.tooltip || "";
        const icon = box.querySelector("[data-card-icon]");
        icon.classList.remove("text-gray-500", "text-success", "text-primary", "text-warning", "text-danger");
        icon.classList.add(card.accent ? `text-${card.accent}` : "text-gray-500");
        const trend = box.querySelector("[data-card-trend]");
        if (card.trend && card.trend.direction !== "flat") {
            const up = card.trend.direction === "up";
            trend.className = `badge fs-8 ms-2 ${up ? "badge-light-success" : "badge-light-danger"}`;
            trend.textContent = `${up ? "↑" : "↓"} ${card.trend.display}`;
            trend.title = card.trend.tooltip || "";
            trend.hidden = false;
        } else {
            trend.hidden = true;
        }
    }

    async function load() {
        host.setAttribute("aria-busy", "true");
        host.querySelectorAll("[data-card-value]").forEach((node) => { node.textContent = "…"; });
        try {
            const query = new URLSearchParams({period: select ? select.value : ""});
            const data = await apiRequest(`/api/v1/profiles/${personType}/${personId}/cards/?${query}`);
            data.cards.forEach((card) => {
                const box = host.querySelector(`[data-profile-card="${card.key}"]`);
                if (box) paint(box, card);
            });
        } catch (error) {
            host.querySelectorAll("[data-profile-card]").forEach((box) => {
                box.querySelector("[data-card-value]").textContent = "—";
                box.title = "دریافت این رقم ممکن نشد.";
            });
        } finally {
            host.removeAttribute("aria-busy");
        }
    }

    select?.addEventListener("change", load);
    const scoreCard = host.querySelector("[data-score-card]");
    if (scoreCard) {
        const open = () => openScoreDialog(personType, personId);
        scoreCard.addEventListener("click", open);
        scoreCard.addEventListener("keydown", (event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            event.preventDefault();
            open();
        });
    }
    load();
}

/** Why the score is what it is: each factor, its points and its reason. */
async function openScoreDialog(personType, personId) {
    const dialog = document.getElementById("profile-score-dialog");
    if (!dialog) return;
    const part = (name) => dialog.querySelector(`[data-score-${name}]`);
    part("loading").hidden = false;
    part("error").hidden = true;
    part("empty").hidden = true;
    part("body").hidden = true;
    if (!dialog.open) dialog.showModal();
    try {
        const data = await apiRequest(`/api/v1/profiles/${personType}/${personId}/score/`);
        part("loading").hidden = true;
        if (!data.current) { part("empty").hidden = false; return; }
        part("value").textContent = toPersianDigits(String(data.current.score));
        const level = part("level");
        level.className = `badge fs-7 badge-light-${data.current.accent}`;
        level.textContent = data.current.level_label;
        part("when").textContent = `محاسبه‌شده ${displayDate(data.current.computed_at)}`;
        part("breakdown").replaceChildren(...data.current.breakdown.map((factor) => {
            const row = document.createElement("tr");
            appendCell(row, factor.label).className = "fw-semibold";
            appendCell(
                row,
                factor.applicable && factor.weight
                    ? `${toPersianDigits(String(factor.points).replace(".", "٫"))} از ${toPersianDigits(String(factor.weight))}`
                    : "قابل سنجش نیست",
            ).classList.toggle("text-muted", !factor.applicable || !factor.weight);
            appendCell(row, factor.reason).className = "text-gray-700";
            return row;
        }));
        part("history").replaceChildren(...data.history.map((entry) => {
            const item = document.createElement("li");
            item.className = `badge badge-light-${entry.accent} fs-8`;
            item.textContent = `${displayDay(entry.computed_at)} — ${toPersianDigits(String(entry.score))}`;
            return item;
        }));
        part("body").hidden = false;
    } catch (error) {
        part("loading").hidden = true;
        part("error").hidden = false;
    }
}

const TASK_STATUS_BADGE = {open: "badge-light-primary", done: "badge-light-success", cancelled: "badge-light"};

/**
 * «وظایف»: a customer's tasks are the ones about them, a colleague's the
 * ones assigned to them — within the reader's own task scope.
 */
function setupTasksTab(personType, personId) {
    const loadingNode = document.getElementById("profile-tasks-loading");
    const empty = document.getElementById("profile-tasks-empty");
    const wrap = document.getElementById("profile-tasks-table-wrap");
    const body = document.getElementById("profile-tasks-table-body");
    const pagination = document.getElementById("profile-tasks-pagination");
    const previous = document.getElementById("profile-tasks-prev");
    const next = document.getElementById("profile-tasks-next");
    const status = document.getElementById("profile-tasks-status");
    let currentPage = 1;

    async function act(task, verb, button) {
        if (verb === "cancel" && !await confirmDialog("این وظیفه لغو شود؟")) return;
        button.disabled = true;
        clearMessages();
        try {
            const url = {
                complete: `/api/v1/tasks/${task.id}/complete/`,
                cancel: `/api/v1/tasks/${task.id}/cancel/`,
                reopen: `/api/v1/tasks/${task.id}/reopen/`,
            }[verb];
            await apiRequest(url, {method: "POST", body: {}});
            globalMessage({complete: "وظیفه انجام‌شده ثبت شد.", cancel: "وظیفه لغو شد.", reopen: "وظیفه دوباره باز شد."}[verb], true);
            await load(currentPage);
        } catch (error) {
            button.disabled = false;
            showError(error);
        }
    }

    function actionButton(label, className, handler) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `btn btn-sm ${className}`;
        button.textContent = label;
        button.addEventListener("click", () => handler(button));
        return button;
    }

    function taskRow(task) {
        const row = document.createElement("tr");
        const title = document.createElement("td");
        const strong = document.createElement("span");
        strong.className = "d-block fw-semibold text-gray-900";
        strong.textContent = task.title;
        title.appendChild(strong);
        if (task.notes) {
            const notes = document.createElement("span");
            notes.className = "d-block text-muted fs-7 text-break";
            notes.textContent = task.notes;
            title.appendChild(notes);
        }
        row.appendChild(title);
        appendCell(row, task.assignee_display);
        const due = appendCell(row, task.due_at ? displayDate(task.due_at) : "");
        if (task.overdue) {
            const badge = document.createElement("span");
            badge.className = "badge badge-light-danger fs-8 ms-2";
            badge.textContent = "سررسید گذشته";
            due.appendChild(badge);
        }
        const statusCell = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = `badge ${TASK_STATUS_BADGE[task.status] || "badge-light"}`;
        badge.textContent = task.status_display;
        statusCell.appendChild(badge);
        row.appendChild(statusCell);
        const actions = document.createElement("td");
        actions.className = "row-actions";
        if (task.status === "open") {
            actions.append(
                actionButton("انجام شد", "btn-light-success", (button) => act(task, "complete", button)),
                actionButton("لغو", "btn-light", (button) => act(task, "cancel", button)),
            );
        } else {
            actions.append(actionButton("بازکردن دوباره", "btn-light", (button) => act(task, "reopen", button)));
        }
        row.appendChild(actions);
        return row;
    }

    async function load(page = 1) {
        loadingNode.hidden = false;
        empty.hidden = true;
        wrap.hidden = true;
        pagination.hidden = true;
        try {
            const query = new URLSearchParams({page: String(page)});
            if (status.value) query.set("status", status.value);
            if (personType === "user") {
                query.set("assignee", String(personId));
            } else {
                query.set("person_type", personType);
                query.set("person_id", String(personId));
            }
            const data = await apiRequest(`/api/v1/tasks/?${query}`);
            body.replaceChildren(...data.results.map(taskRow));
            loadingNode.hidden = true;
            if (!data.results.length) { empty.hidden = false; return; }
            wrap.hidden = false;
            currentPage = page;
            previous.disabled = !data.previous;
            next.disabled = !data.next;
            document.getElementById("profile-tasks-page-label").textContent = pageRangeLabel(data, page);
            pagination.hidden = !data.previous && !data.next;
        } catch (error) {
            loadingNode.hidden = true;
            showError(error);
        }
    }

    previous.addEventListener("click", () => load(currentPage - 1));
    next.addEventListener("click", () => load(currentPage + 1));
    status.addEventListener("change", () => load(1));
    document.addEventListener("profile:task-created", () => load(1));
    return load();
}

/** «وظیفهٔ تازه» — from the header's quick action or the tasks tab. */
function setupTaskDialog(personType, personId) {
    const dialog = document.getElementById("profile-task-dialog");
    const form = document.getElementById("profile-task-form");
    if (!dialog || !form) return;
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    document.addEventListener("click", (event) => {
        if (!event.target.closest('[data-profile-action="add-task"]')) return;
        form.reset();
        clearMessages(form);
        dialog.showModal();
        document.getElementById("profile-task-title-input").focus();
    });
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const data = new FormData(form);
            const typed = String(data.get("due_at") || "").trim();
            const due = typed ? apiDateTime(typed) : null;
            if (typed && !due) throw new Error("سررسید خوانده نشد؛ قالب باید ۱۴۰۵/۰۵/۲۵ ۱۴:۳۰ باشد.");
            await apiRequest(form.action, {
                method: "POST",
                body: {
                    title: String(data.get("title") || ""),
                    notes: String(data.get("notes") || ""),
                    due_at: due,
                    assignee: Number(data.get("assignee")),
                    person_type: personType,
                    person_id: Number(personId),
                },
            });
            dialog.close();
            globalMessage("وظیفه ثبت شد.", true);
            document.dispatchEvent(new CustomEvent("profile:task-created"));
        });
    });
}

/** «یادداشت‌ها» — newest first, written here, edited by their author. */
function setupNotesTab(personType, personId) {
    const list = document.getElementById("profile-notes-list");
    if (!list) return null;
    const loadingNode = document.getElementById("profile-notes-loading");
    const empty = document.getElementById("profile-notes-empty");
    const failed = document.getElementById("profile-notes-error");
    const more = document.getElementById("profile-notes-more");
    const form = document.getElementById("profile-note-form");
    let nextUrl = null;

    function refreshEmpty() {
        const any = list.children.length > 0;
        list.hidden = !any;
        empty.hidden = any;
    }

    function noteCard(note) {
        const item = document.createElement("article");
        item.className = "border border-gray-300 border-dashed rounded p-5";
        const head = document.createElement("div");
        head.className = "d-flex flex-wrap align-items-center justify-content-between gap-2 mb-2";
        const who = document.createElement("div");
        const author = document.createElement("span");
        author.className = "fw-bold text-gray-900 me-2";
        author.textContent = note.author_display;
        const when = document.createElement("span");
        when.className = "text-muted fs-7";
        // `created_at` and `updated_at` are stamped microseconds apart
        // on creation; only a real later edit is worth saying so.
        const edited = new Date(note.updated_at) - new Date(note.created_at) > 1000;
        when.textContent = displayDate(note.created_at) + (edited ? " (ویرایش‌شده)" : "");
        who.append(author, when);
        const tools = document.createElement("div");
        tools.className = "d-flex gap-2";
        const text = document.createElement("p");
        text.className = "text-gray-800 mb-0 text-break";
        text.style.whiteSpace = "pre-line";
        text.textContent = note.body;

        if (note.can_edit) {
            const edit = document.createElement("button");
            edit.type = "button";
            edit.className = "btn btn-sm btn-light";
            edit.textContent = "ویرایش";
            edit.addEventListener("click", () => {
                const editor = document.createElement("form");
                editor.noValidate = true;
                const area = document.createElement("textarea");
                area.className = "form-control form-control-solid";
                area.name = "body";
                area.rows = 3;
                area.maxLength = 4000;
                area.value = note.body;
                area.setAttribute("aria-label", "متن یادداشت");
                const error = document.createElement("p");
                error.className = "text-danger fs-8 mt-1 mb-0";
                error.dataset.errorFor = "body";
                const buttons = document.createElement("div");
                buttons.className = "d-flex justify-content-end gap-2 mt-3";
                const cancel = document.createElement("button");
                cancel.type = "button";
                cancel.className = "btn btn-sm btn-light";
                cancel.textContent = "انصراف";
                const save = document.createElement("button");
                save.type = "submit";
                save.className = "btn btn-sm btn-primary";
                save.textContent = "ذخیره";
                buttons.append(cancel, save);
                editor.append(area, error, buttons);
                text.replaceWith(editor);
                area.focus();
                cancel.addEventListener("click", () => editor.replaceWith(text));
                editor.addEventListener("submit", (event) => {
                    event.preventDefault();
                    withSubmit(editor, async () => {
                        const saved = await apiRequest(`/api/v1/person-notes/${note.id}/`, {method: "PATCH", body: {body: area.value}});
                        item.replaceWith(noteCard(saved));
                        globalMessage("یادداشت ذخیره شد.", true);
                    });
                });
            });
            tools.appendChild(edit);
        }
        if (note.can_delete) {
            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "btn btn-sm btn-light-danger";
            remove.textContent = "حذف";
            remove.addEventListener("click", async () => {
                if (!await confirmDialog("این یادداشت برای همیشه حذف شود؟")) return;
                remove.disabled = true;
                clearMessages();
                try {
                    await apiRequest(`/api/v1/person-notes/${note.id}/`, {method: "DELETE"});
                    item.remove();
                    refreshEmpty();
                    globalMessage("یادداشت حذف شد.", true);
                } catch (error) {
                    remove.disabled = false;
                    showError(error);
                }
            });
            tools.appendChild(remove);
        }
        head.append(who, tools);
        item.append(head, text);
        return item;
    }

    async function load(url) {
        try {
            const data = await apiRequest(url);
            list.append(...data.results.map(noteCard));
            nextUrl = data.next;
            more.hidden = !nextUrl;
            loadingNode.hidden = true;
            refreshEmpty();
        } catch (error) {
            loadingNode.hidden = true;
            failed.hidden = false;
        }
    }

    more.addEventListener("click", () => { if (nextUrl) load(nextUrl); });
    form?.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const note = await apiRequest(`/api/v1/profiles/${personType}/${personId}/notes/`, {
                method: "POST",
                body: {body: form.elements.namedItem("body").value},
            });
            list.prepend(noteCard(note));
            form.reset();
            refreshEmpty();
            globalMessage("یادداشت ثبت شد.", true);
        });
    });
    return load(`/api/v1/profiles/${personType}/${personId}/notes/`);
}

function userProfileLoaders(userId) {
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

// --- Telephony (2.23.0) ------------------------------------------------
//
// The PBX's own record of calls on a profile, placing a call through the
// PBX from the reader's own extension, and the incoming-call popup. The
// server decides every one of them again: this script only draws what
// the API chose to return.

const CALL_STATUS_ACCENT = {
    completed: "success", missed: "danger", failed: "danger",
    no_answer: "warning", busy: "warning", ringing: "info", answered: "info",
};

/** `155` → `۲:۳۵`, an hour or more → `۱:۰۲:۳۵`; nothing said → «—». */
function talkTime(seconds) {
    const total = Number(seconds) || 0;
    if (!total) return "—";
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const rest = total % 60;
    const text = hours ? `${hours}:${pad2(minutes)}:${pad2(rest)}` : `${minutes}:${pad2(rest)}`;
    return toPersianDigits(text);
}

function callBadge(call) {
    const badge = document.createElement("span");
    badge.className = `badge badge-light-${CALL_STATUS_ACCENT[call.status] || "secondary"}`;
    badge.textContent = call.status_label;
    return badge;
}

function pbxCallRow(call, {showPerson = false} = {}) {
    const row = document.createElement("tr");
    const what = document.createElement("td");
    const direction = document.createElement("span");
    direction.className = "d-block fw-semibold text-gray-900 mb-1";
    direction.textContent = call.direction_label;
    what.append(direction, callBadge(call));
    row.appendChild(what);
    if (showPerson) {
        const person = document.createElement("td");
        if (call.person_url) {
            const link = document.createElement("a");
            link.href = call.person_url;
            link.className = "text-gray-800 text-hover-primary fw-semibold";
            link.textContent = call.person_display;
            person.appendChild(link);
        } else {
            person.textContent = "—";
            person.title = call.person_id
                ? "این شماره به مخاطبی خارج از محدودهٔ دسترسی شما تعلق دارد."
                : "این شماره به مشتری یا همکاری در دلفین تطبیق داده نشد.";
        }
        row.appendChild(person);
    }
    const number = appendCell(row, localPhone(call.external_number || (call.direction === "inbound" ? call.caller : call.callee)));
    number.dir = "ltr";
    appendCell(row, call.extension ? `${toPersianDigits(call.extension)}${call.user_display ? ` — ${call.user_display}` : ""}` : "");
    appendCell(row, displayDate(call.started_at));
    appendCell(row, call.status === "completed" ? talkTime(call.billsec) : "");
    const actions = document.createElement("td");
    actions.className = "row-actions";
    if (call.has_recording) {
        const play = document.createElement("button");
        play.type = "button";
        play.className = "btn btn-sm btn-light-primary";
        play.textContent = "پخش ضبط";
        play.addEventListener("click", () => {
            // Asked for only now, not on page load: every listening is
            // audited, and a table of recordings must not preload audio.
            const audio = document.createElement("audio");
            audio.controls = true;
            audio.preload = "none";
            audio.src = `/api/v1/calls/${call.id}/recording/`;
            audio.className = "mw-100";
            audio.setAttribute("aria-label", `ضبط تماس ${displayDate(call.started_at)}`);
            audio.addEventListener("error", () => {
                const note = document.createElement("span");
                note.className = "text-danger fs-7";
                note.textContent = "ضبط این تماس در دسترس نیست.";
                audio.replaceWith(note);
            });
            play.replaceWith(audio);
            audio.play().catch(() => { /* the reader presses play */ });
        });
        actions.appendChild(play);
    }
    if (call.external_number && document.body.dataset.canOriginate === "1") {
        const again = document.createElement("button");
        again.type = "button";
        again.className = "btn btn-sm btn-light";
        again.textContent = "تماس";
        again.dataset.originateNumber = call.external_number;
        if (call.person_type && call.person_id) {
            again.dataset.originatePersonType = call.person_type;
            again.dataset.originatePersonId = String(call.person_id);
        }
        actions.appendChild(again);
    }
    if (!actions.childElementCount) actions.textContent = "—";
    row.appendChild(actions);
    return row;
}

/** One paginated table of PBX calls (`profiles/tabs/pbx_calls_table.inc`). */
function loadPbxCalls(prefix, baseUrl) {
    const loading = document.getElementById(`${prefix}-loading`);
    if (!loading) return Promise.resolve();
    const empty = document.getElementById(`${prefix}-empty`);
    const wrap = document.getElementById(`${prefix}-table-wrap`);
    const body = document.getElementById(`${prefix}-table-body`);
    const pagination = document.getElementById(`${prefix}-pagination`);
    const previous = document.getElementById(`${prefix}-prev`);
    const next = document.getElementById(`${prefix}-next`);
    const showPerson = body.dataset.showPerson === "1";
    let currentPage = 1;

    async function load(page = 1) {
        loading.hidden = false;
        empty.hidden = true;
        wrap.hidden = true;
        pagination.hidden = true;
        try {
            const data = await apiRequest(`${baseUrl}${baseUrl.includes("?") ? "&" : "?"}page=${page}`);
            body.replaceChildren(...data.results.map((call) => pbxCallRow(call, {showPerson})));
            loading.hidden = true;
            if (!data.results.length) { empty.hidden = false; return; }
            wrap.hidden = false;
            currentPage = page;
            previous.disabled = !data.previous;
            next.disabled = !data.next;
            document.getElementById(`${prefix}-page-label`).textContent = pageRangeLabel(data, page);
            pagination.hidden = !data.previous && !data.next;
        } catch (error) {
            loading.hidden = true;
            showError(error);
        }
    }
    previous.addEventListener("click", () => load(currentPage - 1));
    next.addEventListener("click", () => load(currentPage + 1));
    return load();
}

/** The «عملکرد» tab's call figures for the same period as its report. */
async function loadCallStats(userId, query) {
    const host = document.querySelector("[data-call-stats]");
    if (!host) return;
    const loading = document.getElementById("profile-call-stats-loading");
    const errorNode = document.getElementById("profile-call-stats-error");
    loading.hidden = false;
    errorNode.hidden = true;
    try {
        const params = new URLSearchParams({
            user: userId, period_start: query.get("period_start") || "", period_end: query.get("period_end") || "",
        });
        const stats = await apiRequest(`/api/v1/telephony/stats/?${params}`);
        const values = {
            inbound: toPersianDigits(String(stats.inbound)),
            inbound_answered: toPersianDigits(String(stats.inbound_answered)),
            missed: toPersianDigits(String(stats.missed)),
            outbound: toPersianDigits(String(stats.outbound)),
            talk_seconds: talkTime(stats.talk_seconds),
            average_talk_seconds: talkTime(stats.average_talk_seconds),
            follow_up: stats.missed_decided
                ? toPersianDigits(`${stats.missed_followed_up} از ${stats.missed_decided}`)
                : "—",
        };
        Object.entries(values).forEach(([name, text]) => {
            const node = host.querySelector(`[data-call-stat="${name}"]`);
            if (node) node.textContent = text;
        });
        const followUp = host.querySelector('[data-call-stat="follow_up"]');
        if (followUp) followUp.title = stats.missed_decided ? "" : "در این بازه تماس بی‌پاسخی که مهلت پیگیری‌اش گذشته باشد نبوده است.";
    } catch (error) {
        errorNode.textContent = errorText(error);
        errorNode.hidden = false;
    } finally {
        loading.hidden = true;
    }
}

export function setupPersonProfile() {
    const personType = document.body.dataset.personType;
    const personId = document.body.dataset.personId;
    if (!personType || !personId) return;

    // «بیشتر» — the theme's dropdown, opened the way every other panel
    // in the shell is (`registerPopover`).
    const more = registerPopover({
        toggle: document.getElementById("profile-more-toggle"),
        panel: document.getElementById("profile-more-menu"),
    });
    document.getElementById("profile-more-menu")?.addEventListener("click", (event) => {
        if (event.target.closest("a, button")) more?.close();
    });

    // The permission matrix lives in a dialog shared with User
    // Management; any `data-profile-action="permissions"` opens it.
    if (document.getElementById("permissions-dialog")) setupPermissionsDialog();
    document.addEventListener("click", (event) => {
        const button = event.target.closest('[data-profile-action="permissions"]');
        if (!button) return;
        openPermissionsDialog(button.dataset.userId, button.dataset.userName);
    });

    const loaders = personType === "customer"
        ? customerProfileLoaders(personId)
        : userProfileLoaders(personId);
    setupProfileTabs(loaders);
    setupProfileCards(personType, personId);
    setupTaskDialog(personType, personId);
    const scoreDialog = document.getElementById("profile-score-dialog");
    scoreDialog?.querySelectorAll("[data-close-dialog]").forEach((button) => {
        button.addEventListener("click", () => scoreDialog.close());
    });
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
