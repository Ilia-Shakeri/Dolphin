import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDateTime, displayDate, localDateTimeValue} from "dolphin/core/jalali.js";
import {clearMessages, formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {fillSelect, loadAllPages} from "dolphin/ui/lists.js";
import {appendCell, pageRangeLabel} from "dolphin/ui/table.js";

export async function setupLeadDetail() {
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
        document.getElementById("edit-lead-follow-up").value = localDateTimeValue(value.next_follow_up_at);
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
