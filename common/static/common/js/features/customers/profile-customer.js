import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDay} from "dolphin/core/jalali.js";
import {DOCUMENT_STATUS_TEXT, SETTLEMENT_TEXT} from "dolphin/core/labels.js";
import {clearMessages, formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {customFieldDefinitions, formatCustomValue, readCustomFieldInputs, renderCustomFieldInputs} from "dolphin/ui/custom-fields.js";
import {loadRecentActivity} from "dolphin/features/customers/profile-activity.js";
import {setOverviewFact, setProfileBadge, setProfileBreadcrumb, setProfileHeaderField, setProfileHeaderPhone, setProfileHeaderText} from "dolphin/features/customers/profile-header.js";
import {setupNotesTab, setupTasksTab} from "dolphin/features/customers/profile-work.js";
import {setupAttachmentsPanelFor} from "dolphin/ui/attachments.js";
import {renderAreaChart, showEmptyChart} from "dolphin/ui/charts.js";
import {fillCustomerCategorySelect} from "dolphin/ui/customer-categories.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {fillProvinceSelect} from "dolphin/ui/iran-map.js";
import {loadAllPages} from "dolphin/ui/lists.js";
import {interactionRow, leadRow} from "dolphin/ui/rows.js";
import {appendActionLinks, appendCell, appendMoneyCell, appendStatusBadgeCell, appendStatusCell, labelled, pageRangeLabel, statusText} from "dolphin/ui/table.js";

function phoneRow(phone, edit, deactivate) {
    const row = document.createElement("tr");
    appendCell(row, phone.raw_phone).dir = "ltr";
    appendCell(row, phone.normalized_phone).dir = "ltr";
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
export function customerProfileLoaders(customerId) {
    const endpoint = `/api/v1/customers/${customerId}/`;
    let customer = null;

    function fillCustomer(value) {
        // The company's own fields (2.40.53).
        renderCustomFieldInputs(
            document.getElementById("edit-customer-custom-fields"), customFieldDefinitions(), value.custom_fields || {},
            {prefix: "edit-customer-custom"},
        );
        ["full_name", "job_title", "national_id", "economic_code", "email", "city", "postal_code", "address", "notes"].forEach((name) => {
            const input = document.getElementById(`edit-customer-${name.replaceAll("_", "-").replace("full-name", "name")}`);
            if (input) input.value = value[name] || "";
        });
        fillProvinceSelect(document.getElementById("edit-customer-province"), value.province || "");
        fillCustomerCategorySelect(document.getElementById("edit-customer-category"), value.category || "").catch(showError);
        const ownerField = document.getElementById("edit-customer-owner");
        if (ownerField && value.owner) ownerField.value = String(value.owner);
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
        customFieldDefinitions().forEach((field) => {
            const shown = formatCustomValue(field, value.custom_fields?.[field.key]);
            setOverviewFact(field.key, shown === "—" ? "" : shown);
        });
    }

    // Live (2.40.41): a change made elsewhere reaches the header, the
    // overview and — once it has been opened — the info form.
    let infoShown = false;
    document.addEventListener("dolphin:customer-record", (event) => {
        customer = event.detail;
        reflectCustomer(customer);
        if (infoShown) fillCustomer(customer);
    });

    async function setupInfo() {
        const editForm = document.getElementById("edit-customer-form");
        const loadingNode = editForm.querySelector("[data-info-loading]");
        const fields = editForm.querySelector("[data-info-fields]");
        customer = await apiRequest(endpoint);
        fillCustomer(customer);
        infoShown = true;
        loadingNode.hidden = true;
        fields.hidden = false;
        editForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(editForm, async () => {
                const body = formPayload(editForm, ["full_name", "job_title", "national_id", "economic_code", "email", "province", "city", "postal_code", "category", "address", "notes"]);
                const ownerField = document.getElementById("edit-customer-owner");
                if (ownerField?.value) body.owner = Number(ownerField.value);
                const customContainer = document.getElementById("edit-customer-custom-fields");
                if (customContainer) body.custom_fields = readCustomFieldInputs(customContainer);
                customer = await apiRequest(endpoint, {method: "PATCH", body});
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

// The customer «تحلیل» tab (2.33.0): one request fills five figures; the
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
