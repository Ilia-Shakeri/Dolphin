import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate} from "dolphin/core/jalali.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {localPhone} from "dolphin/ui/rows.js";
import {appendCell} from "dolphin/ui/table.js";

/**
 * Settings → «نتیجهٔ تماس» (2.40.58, BIZ-003): the outcome list, the
 * company's own outcomes, matching older calls, and the do-not-contact list.
 * Every rule is `sales.call_outcomes`'s; this shows what the server answers.
 */
export function setupCallOutcomesSection() {
    const body = document.getElementById("call-outcomes-body");
    if (!body) return;
    const dialog = document.getElementById("call-outcome-dialog");
    const form = document.getElementById("call-outcome-form");
    const standardSelect = document.getElementById("call-outcome-standard");
    const liftDialog = document.getElementById("do-not-contact-dialog");
    const liftForm = document.getElementById("do-not-contact-form");
    let data = null;
    let editing = null;
    let lifting = null;

    function badge(text, tone) {
        const node = document.createElement("span");
        node.className = `badge badge-light-${tone}`;
        node.textContent = text;
        return node;
    }

    function cellWith(row, node) {
        const cell = document.createElement("td");
        cell.append(node);
        row.append(cell);
        return cell;
    }

    function button(label, onClick, className = "btn btn-sm btn-light") {
        const node = document.createElement("button");
        node.type = "button";
        node.className = className;
        node.textContent = label;
        node.addEventListener("click", onClick);
        return node;
    }

    function renderOutcomes(value) {
        data = value;
        if (!standardSelect.options.length) {
            value.standards.forEach((item) => standardSelect.append(new Option(item.label, item.key)));
        }
        document.getElementById("call-outcome-add").hidden = !value.can_add;
        document.getElementById("call-outcomes-feature-note").hidden = value.can_add;
        body.replaceChildren(...value.outcomes.map((outcome) => {
            const row = document.createElement("tr");
            appendCell(row, outcome.label);
            appendCell(row, outcome.is_system ? "استاندارد" : outcome.standard_label);
            appendCell(row, outcome.successful ? "بله" : "خیر");
            appendCell(row, outcome.may_qualify ? "مجاز" : "—");
            cellWith(row, badge(outcome.is_active ? "روشن" : "خاموش", outcome.is_active ? "success" : "secondary"));
            const actions = document.createElement("td");
            actions.className = "text-end";
            if (value.can_add) actions.append(button("ویرایش", () => open(outcome)));
            row.append(actions);
            return row;
        }));
        document.getElementById("call-outcomes-loading").hidden = true;
        document.getElementById("call-outcomes-table-wrap").hidden = false;
    }

    function renderLegacy(texts) {
        const legacyBody = document.getElementById("legacy-outcomes-body");
        document.getElementById("legacy-outcomes-loading").hidden = true;
        document.getElementById("legacy-outcomes-empty").hidden = texts.length > 0;
        document.getElementById("legacy-outcomes-table-wrap").hidden = !texts.length;
        legacyBody.replaceChildren(...texts.map((item, index) => {
            const row = document.createElement("tr");
            appendCell(row, item.text);
            appendCell(row, toPersianDigits(String(item.count)));
            const select = document.createElement("select");
            select.className = "form-select form-select-sm form-select-solid w-200px";
            select.id = `legacy-outcome-${index}`;
            select.setAttribute("aria-label", `نتیجهٔ فهرست برای «${item.text}»`);
            select.append(new Option("یک نتیجه انتخاب کنید", ""));
            (data?.outcomes || []).filter((outcome) => outcome.is_active)
                .forEach((outcome) => select.append(new Option(outcome.label, outcome.key)));
            cellWith(row, select);
            const actions = document.createElement("td");
            actions.className = "text-end";
            actions.append(button("نگاشت", async () => {
                if (!select.value) { select.focus(); return; }
                try {
                    const answer = await apiRequest("/api/v1/call-outcomes/legacy/", {method: "POST", body: {text: item.text, result: select.value}});
                    globalMessage(`${toPersianDigits(String(answer.mapped))} تماس نگاشت شد.`, true);
                    renderLegacy(answer.texts);
                    loadBlocks();
                } catch (error) { showError(error); }
            }, "btn btn-sm btn-light-primary"));
            row.append(actions);
            return row;
        }));
    }

    function renderBlocks(rows) {
        const blocksBody = document.getElementById("do-not-contact-body");
        document.getElementById("do-not-contact-loading").hidden = true;
        document.getElementById("do-not-contact-empty").hidden = rows.length > 0;
        document.getElementById("do-not-contact-table-wrap").hidden = !rows.length;
        blocksBody.replaceChildren(...rows.map((item) => {
            const row = document.createElement("tr");
            appendCell(row, localPhone(item.phone)).dir = "ltr";
            appendCell(row, item.note);
            appendCell(row, item.created_by_display);
            appendCell(row, displayDate(item.created_at));
            const actions = document.createElement("td");
            actions.className = "text-end";
            actions.append(button("برداشتن", () => {
                lifting = item;
                liftForm.reset();
                clearMessages(liftForm);
                document.getElementById("do-not-contact-subject").textContent = `شمارهٔ ${localPhone(item.phone)} دوباره در تماس‌های بازاریابی و کمپین‌ها می‌آید.`;
                liftDialog.showModal();
            }));
            row.append(actions);
            return row;
        }));
    }

    async function loadBlocks() {
        try { renderBlocks((await apiRequest("/api/v1/do-not-contact/")).results); } catch (error) { showError(error); }
    }

    function open(outcome = null) {
        editing = outcome;
        form.reset();
        clearMessages(form);
        document.getElementById("call-outcome-label").value = outcome?.label || "";
        standardSelect.value = outcome?.standard_key || "connected";
        document.getElementById("call-outcome-standard-field").hidden = Boolean(outcome);
        document.getElementById("call-outcome-active-wrap").hidden = !outcome || outcome.is_system;
        document.getElementById("call-outcome-active").checked = outcome ? outcome.is_active : true;
        dialog.showModal();
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const payload = {label: document.getElementById("call-outcome-label").value};
            let value;
            if (editing) {
                if (!document.getElementById("call-outcome-active-wrap").hidden) {
                    payload.is_active = document.getElementById("call-outcome-active").checked;
                }
                value = await apiRequest(`/api/v1/call-outcomes/${editing.id}/`, {method: "PATCH", body: payload});
            } else {
                value = await apiRequest("/api/v1/call-outcomes/", {method: "POST", body: {...payload, standard_key: standardSelect.value}});
            }
            dialog.close();
            renderOutcomes(value);
            globalMessage("نتیجه ذخیره شد. فرم ثبت تماس با بارگذاری دوباره آن را نشان می‌دهد.", true);
        });
    });

    liftForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(liftForm, async () => {
            await apiRequest(`/api/v1/do-not-contact/${lifting.id}/lift/`, {method: "POST", body: {reason: document.getElementById("do-not-contact-reason").value}});
            liftDialog.close();
            globalMessage("شماره از فهرست برداشته شد.", true);
            await loadBlocks();
        });
    });

    // The attribution window and the figures' meanings (2.40.59).
    const salesForm = document.getElementById("sales-settings-form");
    function renderSalesSettings(value) {
        document.getElementById("sales-settings-window").value = String(value.attribution_window_days);
        document.getElementById("sales-settings-default").hidden = !value.is_default;
        document.getElementById("sales-settings-definitions").replaceChildren(...value.definitions.flatMap((item) => {
            const term = document.createElement("dt");
            term.className = "fw-bold text-gray-900 fs-7";
            term.textContent = item.label;
            const detail = document.createElement("dd");
            detail.className = "text-gray-700 fs-7 mb-4";
            detail.textContent = item.denominator_label
                ? `${item.definition} صورت: ${item.numerator_label}؛ مخرج: ${item.denominator_label}.`
                : item.definition;
            return [term, detail];
        }));
    }
    salesForm?.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(salesForm, async () => {
            const days = document.getElementById("sales-settings-window").value.trim();
            renderSalesSettings(await apiRequest("/api/v1/sales-settings/", {method: "PATCH", body: {attribution_window_days: Number(days)}}));
            globalMessage("پنجرهٔ انتساب ذخیره شد. از این پس برای خریدهای تازه به کار می‌رود.", true);
        });
    });

    document.getElementById("call-outcome-add").addEventListener("click", () => open());
    [dialog, liftDialog].forEach((node) => node.querySelectorAll("[data-close-dialog]")
        .forEach((close) => close.addEventListener("click", () => node.close())));

    (async () => {
        try {
            renderOutcomes(await apiRequest("/api/v1/call-outcomes/"));
            renderLegacy((await apiRequest("/api/v1/call-outcomes/legacy/")).texts);
        } catch (error) {
            document.getElementById("call-outcomes-loading").textContent = "نتیجه‌ها دریافت نشد.";
            showError(error);
        }
        await loadBlocks();
        try { renderSalesSettings(await apiRequest("/api/v1/sales-settings/")); } catch (error) { showError(error); }
    })();
}
