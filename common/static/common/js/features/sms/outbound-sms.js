import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDateTime, displayDate} from "dolphin/core/jalali.js";
import {formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {bindLiveSearch, fillSelect, loadAllPages} from "dolphin/ui/lists.js";
import {setupSearchableSelects} from "dolphin/ui/searchable-select.js";
import {appendCell} from "dolphin/ui/table.js";
import {selectedOptionText} from "dolphin/ui/wizard.js";

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
export async function setupOutboundSms() {
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
            const customers = await loadAllPages("/api/v1/customers/");
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
            const leads = await loadAllPages("/api/v1/leads/");
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
    // A profile's «پیامک» quick action (2.19.0) opens this page with the
    // recipient already chosen — `?customer=<id>` or `?phone=<number>`.
    // Only the field is filled; nothing is sent until the reader writes
    // the text and presses send.
    const requested = new URLSearchParams(window.location.search);
    const requestedCustomer = requested.get("customer");
    const requestedPhone = requested.get("phone");
    if (requestedCustomer && /^\d+$/.test(requestedCustomer)) {
        document.getElementById("outbound-sms-customer").value = requestedCustomer;
    } else if (requestedPhone) {
        document.getElementById("outbound-sms-phone").value = requestedPhone;
    }
    if (requestedCustomer || requestedPhone) bodyInput.focus();
    await Promise.all([
        loadOutboundSmsLog("/api/v1/outbound-sms/"),
        loadCampaigns("/api/v1/outbound-sms/campaigns/"),
        loadTemplates(),
    ]);
}
