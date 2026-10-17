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
 *
 * 2.40.56 redrew it to the product owner's redesign: the shipment's own
 * heading, then one boxed section per question — where it is, where it goes
 * next, what is known about it, what has happened to it — instead of four
 * plain blocks running together. The data, the endpoints and the permission
 * boundary are untouched.
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

/** A section's own heading: its icon, its name, and whatever belongs opposite. */
function sectionHead(glyph, paths, title, trailing = null) {
    const head = el("div", "postal-section-head");
    const named = el("div", "postal-section-title");
    const badge = el("span", "postal-section-icon");
    badge.append(icon(glyph, paths, "fs-4"));
    named.append(badge, el("h3", "fs-6 fw-bold text-gray-900 mb-0", title));
    head.append(named);
    if (trailing) head.append(trailing);
    return head;
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

function fact(glyph, paths, label, value, {wide = false} = {}) {
    const row = el("div", `postal-fact${wide ? " postal-fact-wide" : ""}`);
    const head = el("span", "postal-fact-label");
    head.append(icon(glyph, paths, "fs-6"), el("span", "", label));
    row.append(head, el("span", "postal-fact-value", value || "—"));
    return row;
}

function historyList(rows, currentStatus, currentTone) {
    if (!rows.length) return el("p", "text-muted mb-0", "هنوز تغییری ثبت نشده است.");
    const list = el("ol", "postal-timeline");
    rows.forEach((row, index) => {
        const item = el("li", "postal-timeline-item");
        // Only the newest row is coloured, and only when it really is the
        // status the document is in now — the history endpoint sends each
        // row's icon but no tone of its own, and colouring the rest would be
        // this file deciding what a past status meant.
        const tone = index === 0 && row.to_status && row.to_status === currentStatus ? currentTone : null;
        const dot = el("span", `postal-timeline-dot${tone ? ` postal-timeline-dot-${tone}` : ""}`);
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
        const back = el("button", "btn btn-sm btn-icon btn-light d-lg-none postal-pane-back");
        back.type = "button";
        back.setAttribute("aria-label", "بازگشت به فهرست مرسوله‌ها");
        // Right, not left: in RTL «back» points the way the list is, which
        // is what the chat page's own back button already does.
        back.append(icon("di-arrow-right", 2, "fs-3"));
        back.addEventListener("click", () => workspace.classList.remove("is-viewing"));
        const mark = el("span", "postal-pane-icon");
        mark.setAttribute("aria-hidden", "true");
        mark.append(icon("di-package", 3, "fs-2hx"));
        const titles = el("div", "postal-pane-titles");
        titles.append(el("span", "postal-pane-label", "شماره سند"));
        const number = el("h2", "fs-2 fw-bolder text-gray-900 mb-0 postal-pane-number", item.document_number);
        number.dir = "ltr";
        titles.append(number);
        const who = el("a", "postal-pane-customer text-hover-primary fw-semibold", item.customer_name || "—");
        who.href = `/customers/${item.customer}/`;
        titles.append(who);
        const tools = el("div", "postal-pane-tools");
        const copy = el("button", "btn btn-sm btn-light postal-pane-action");
        copy.type = "button";
        copy.append(el("i", "di-outline di-copy fs-5"), el("span", "", "کپی شماره"));
        copy.addEventListener("click", async () => {
            try {
                await navigator.clipboard.writeText(item.document_number);
                globalMessage("شمارهٔ سند کپی شد.", true);
            } catch (error) { showError(error); }
        });
        const full = el("a", "btn btn-sm btn-light-primary postal-pane-action");
        full.href = `/sales-documents/${item.id}/`;
        full.append(icon("di-exit-up", 2, "fs-5"), el("span", "", "صفحهٔ کامل"));
        tools.append(copy, full);
        head.append(back, mark, titles, tools);
        nodes.push(head);

        // Where it is: the post office's own status first, then the stages.
        const badge = postalBadge(item.postal_badge);
        const tone = item.postal_badge?.tone || "";
        const status = el("section", "postal-pane-section postal-pane-status");
        if (tone === "danger" || tone === "warning") status.classList.add(`postal-pane-status-${tone}`);
        status.append(sectionHead("di-parcel-tracking", 3, "وضعیت ارسال",
            badge || el("span", "text-muted fs-7", item.postal_status_display || item.postal_status || "—")));
        if (item.postal_stepper && item.postal_stepper.length) {
            status.append(stepper(item.postal_stepper));
        } else {
            // No stepper on purpose: the server sends none for a status
            // outside the four stages (a return, a seizure) or for free text
            // from before the vocabulary, and four marks with none of them
            // current would claim to know where the parcel is when nobody does.
            const note = el("div", "postal-pane-note");
            note.append(icon("di-information-5", 3, "fs-5"),
                el("span", "", "این وضعیت بیرون از چهار مرحلهٔ ارسال است، پس مرحله‌ای برای آن نمایش داده نمی‌شود."));
            status.append(note);
        }
        if (!item.is_active) {
            const inactive = el("div", "postal-pane-note postal-pane-note-warning");
            inactive.append(icon("di-information-5", 3, "fs-5"),
                el("span", "", "این سند غیرفعال است؛ تاریخچه‌اش حفظ شده است."));
            status.append(inactive);
        }
        nodes.push(status);

        // Moving it on, for whoever may.
        if (canManage && item.is_active) {
            const form = el("form", "postal-pane-section postal-pane-move");
            form.noValidate = true;
            const select = el("select", "form-select form-select-solid");
            select.id = "postal-pane-to-status";
            select.name = "to_status";
            select.setAttribute("aria-label", "وضعیت تازه");
            // The section heading names it on screen, so the control carries its
            // own name and its requiredness for anyone who cannot see that heading.
            select.required = true;
            const reason = el("input", "form-control form-control-solid");
            reason.name = "reason";
            reason.maxLength = 500;
            reason.placeholder = "توضیح (اختیاری)";
            reason.setAttribute("aria-label", "توضیح تغییر وضعیت");
            const submit = el("button", "btn btn-primary", "ثبت وضعیت");
            submit.type = "submit";
            form.append(sectionHead("di-arrows-loop", 2, "تغییر وضعیت",
                el("span", "text-muted fs-8 postal-section-hint", "وضعیت تازه را انتخاب و ثبت کنید")));
            const row = el("div", "postal-pane-move-row");
            row.append(select, reason, submit);
            form.append(row);
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
        const facts = el("section", "postal-facts");
        facts.append(
            fact("di-geolocation", 2, "استان / شهر", [item.province_snapshot, item.city_snapshot].filter(Boolean).join(" / ")),
            fact("di-barcode", 8, "کد پستی", item.postal_code_snapshot ? toPersianDigits(item.postal_code_snapshot) : ""),
            fact("di-home-2", 2, "نشانی", item.address_snapshot, {wide: true}),
            fact("di-calendar", 2, "ثبت", `${item.registered_by_display || ""} · ${displayDate(item.registered_at)}`),
            fact("di-dollar", 3, "فروش مرتبط", item.sale ? `فروش ${toPersianDigits(String(item.sale))}` : ""),
            fact("di-notepad", 5, "یادداشت", item.notes, {wide: true}),
        );
        nodes.push(facts);

        // What happened, newest first.
        const whole = el("a", "btn btn-sm btn-link postal-section-link", "مشاهدهٔ همه");
        whole.href = `/sales-documents/${item.id}/`;
        const timeline = el("section", "postal-pane-section postal-pane-history");
        timeline.append(sectionHead("di-time", 2, "تاریخچهٔ وضعیت", whole));
        timeline.append(historyList(history, item.postal_status, tone));
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
