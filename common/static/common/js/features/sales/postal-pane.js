import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate} from "dolphin/core/jalali.js";
import {errorText, globalMessage, showError} from "dolphin/core/messages.js";
import {fillPostalStates, postalBadge} from "dolphin/features/sales/shared.js";
import {loadAllPages} from "dolphin/ui/lists.js";

/**
 * The right half of «رهگیری پستی» (2.40.34): one shipment, drawn whole beside
 * the list — its four stages, the post office's own status, where it is going,
 * what happened to it and when, and the things one does with a parcel without
 * leaving the page: move it to another status, copy its number, open the
 * customer, open its full page. Everything is read from the same endpoints
 * the full detail page uses; nothing here decides a status or a permission —
 * the server does, and the status form only appears for whoever may manage.
 */
function el(tag, className = "", text = null) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== null) node.textContent = text;
    return node;
}

function icon(name, paths = 2, extra = "") {
    const node = el("i", `di-duotone ${name} ${extra}`.trim());
    node.setAttribute("aria-hidden", "true");
    for (let path = 1; path <= paths; path += 1) node.append(el("span", `path${path}`));
    return node;
}

function stepper(steps) {
    const list = el("ol", "postal-pane-stepper");
    list.setAttribute("aria-label", "مراحل ارسال");
    steps.forEach((step) => {
        const item = el("li", `postal-pane-step postal-pane-step-${step.stage}`);
        if (step.stage === "current") item.setAttribute("aria-current", "step");
        const mark = el("span", "postal-pane-step-mark");
        mark.append(icon(step.icon, step.icon_paths || 2, "fs-3"));
        item.append(mark, el("span", "postal-pane-step-label", step.label));
        list.append(item);
    });
    return list;
}

function fact(label, value) {
    const row = el("div", "postal-fact");
    row.append(el("span", "postal-fact-label", label), el("span", "postal-fact-value", value || "—"));
    return row;
}

function historyList(rows) {
    if (!rows.length) return el("p", "text-muted mb-0", "هنوز تغییری ثبت نشده است.");
    const list = el("ol", "postal-timeline");
    rows.forEach((row) => {
        const item = el("li", "postal-timeline-item");
        const dot = el("span", "postal-timeline-dot");
        const glyph = row.to_status_icon?.icon;
        dot.append(glyph ? icon(glyph, row.to_status_icon.icon_paths || 2, "fs-5") : el("span", "", "•"));
        const body = el("div", "postal-timeline-body");
        body.append(el("span", "fw-bold text-gray-900", row.to_status_display || row.to_status || "—"));
        const meta = [row.changed_by_display || "", displayDate(row.changed_at)].filter(Boolean).join(" · ");
        body.append(el("span", "text-muted fs-8", meta));
        if (row.reason) body.append(el("span", "text-gray-700 fs-7", row.reason));
        item.append(dot, body);
        list.append(item);
    });
    return list;
}

export function setupPostalPane({workspace, onChanged}) {
    const host = document.getElementById("postal-detail-body");
    const placeholder = document.getElementById("postal-detail-placeholder");
    const canManage = workspace.dataset.canManage === "true";
    let shownId = null;
    let token = 0;

    async function show(id, {quiet = false} = {}) {
        shownId = String(id);
        const mine = ++token;
        workspace.classList.add("is-viewing");
        if (!quiet) {
            placeholder.hidden = true;
            host.hidden = false;
            host.replaceChildren(el("div", "text-center text-gray-700 py-15", "در حال دریافت مرسوله…"));
        }
        let item;
        let history;
        try {
            [item, history] = await Promise.all([
                apiRequest(`/api/v1/sales-documents/${id}/`),
                loadAllPages(`/api/v1/sales-documents/${id}/postal-history/`),
            ]);
        } catch (error) {
            if (mine !== token) return;
            host.replaceChildren(el("div", "state state-error", errorText(error)));
            return;
        }
        if (mine !== token) return;
        draw(item, history);
    }

    function draw(item, history) {
        const nodes = [];

        // Head: the number (copyable), the customer, and a way back on a phone.
        const head = el("div", "postal-pane-head");
        const back = el("button", "btn btn-sm btn-icon btn-light d-lg-none");
        back.type = "button";
        back.setAttribute("aria-label", "بازگشت به فهرست مرسوله‌ها");
        back.append(icon("di-arrow-right", 2, "fs-3"));
        back.addEventListener("click", () => workspace.classList.remove("is-viewing"));
        const titles = el("div", "d-flex flex-column gap-1 min-w-0");
        const number = el("h2", "fs-2 fw-bolder text-gray-900 mb-0 postal-pane-number", item.document_number);
        number.dir = "ltr";
        titles.append(number);
        const who = el("a", "text-gray-700 text-hover-primary fw-semibold", item.customer_name || "—");
        who.href = `/customers/${item.customer}/`;
        titles.append(who);
        const tools = el("div", "d-flex flex-wrap gap-2 ms-auto");
        const copy = el("button", "btn btn-sm btn-light d-inline-flex align-items-center gap-2");
        copy.type = "button";
        copy.append(el("i", "di-outline di-copy fs-5"), el("span", "", "کپی شماره"));
        copy.addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(item.document_number);
                globalMessage("شمارهٔ سند کپی شد.", true);
            } catch (error) { showError(error); }
        });
        const full = el("a", "btn btn-sm btn-light-primary d-inline-flex align-items-center gap-2");
        full.href = `/sales-documents/${item.id}/`;
        full.append(icon("di-exit-up", 2, "fs-5"), el("span", "", "صفحهٔ کامل"));
        tools.append(copy, full);
        head.append(back, titles, tools);
        nodes.push(head);

        // Where it is: the post office's own status first, then the stages.
        const status = el("section", "postal-pane-section");
        const badge = postalBadge(item.postal_badge);
        const statusHead = el("div", "d-flex flex-wrap align-items-center justify-content-between gap-3 mb-4");
        statusHead.append(el("h3", "fs-6 fw-bold text-gray-800 mb-0", "وضعیت ارسال"));
        if (badge) statusHead.append(badge);
        else statusHead.append(el("span", "text-muted", item.postal_status_display || item.postal_status || "—"));
        status.append(statusHead);
        if (item.postal_stepper && item.postal_stepper.length) status.append(stepper(item.postal_stepper));
        if (!item.is_active) status.append(el("p", "text-warning-emphasis fs-7 mt-3 mb-0", "این سند غیرفعال است؛ تاریخچه‌اش حفظ شده است."));
        nodes.push(status);

        // Moving it on, for whoever may.
        if (canManage && item.is_active) {
            const form = el("form", "postal-pane-section postal-pane-move");
            form.noValidate = true;
            const select = el("select", "form-select form-select-solid");
            select.id = "postal-pane-to-status";
            select.name = "to_status";
            const label = el("label", "form-label fw-semibold required", "تغییر وضعیت");
            label.setAttribute("for", select.id);
            const reason = el("input", "form-control form-control-solid");
            reason.name = "reason";
            reason.maxLength = 500;
            reason.placeholder = "توضیح (اختیاری)";
            reason.setAttribute("aria-label", "توضیح تغییر وضعیت");
            const submit = el("button", "btn btn-primary", "ثبت وضعیت");
            submit.type = "submit";
            const row = el("div", "postal-pane-move-row");
            row.append(select, reason, submit);
            form.append(label, row);
            fillPostalStates(select, {emptyLabel: "یک وضعیت انتخاب کنید"}).catch(showError);
            form.addEventListener("submit", async (event) => {
                event.preventDefault();
                if (!select.value) { select.focus(); return; }
                submit.disabled = true;
                try {
                    await apiRequest(`/api/v1/sales-documents/${item.id}/transition-postal-status/`, {
                        method: "POST", body: {to_status: select.value, reason: reason.value},
                    });
                    globalMessage("وضعیت پستی ثبت شد.", true);
                    await show(item.id, {quiet: true});
                    onChanged?.();
                } catch (error) {
                    showError(error);
                } finally {
                    submit.disabled = false;
                }
            });
            nodes.push(form);
        }

        // Where to, and who.
        const facts = el("section", "postal-pane-section postal-facts");
        facts.append(
            fact("استان / شهر", [item.province_snapshot, item.city_snapshot].filter(Boolean).join(" / ")),
            fact("کد پستی", item.postal_code_snapshot ? toPersianDigits(item.postal_code_snapshot) : ""),
            fact("نشانی", item.address_snapshot),
            fact("ثبت", `${item.registered_by_display || ""} · ${displayDate(item.registered_at)}`),
            fact("فروش مرتبط", item.sale ? `فروش ${toPersianDigits(String(item.sale))}` : ""),
            fact("یادداشت", item.notes),
        );
        nodes.push(facts);

        // What happened, newest first.
        const timeline = el("section", "postal-pane-section");
        timeline.append(el("h3", "fs-6 fw-bold text-gray-800 mb-4", "تاریخچهٔ وضعیت"));
        timeline.append(historyList(history));
        nodes.push(timeline);

        placeholder.hidden = true;
        host.hidden = false;
        host.replaceChildren(...nodes);
    }

    return {
        show,
        /** The one on screen, read again (a live change, a status moved). */
        refresh() { if (shownId) show(shownId, {quiet: true}); },
        get shownId() { return shownId; },
    };
}
