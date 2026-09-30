import {apiRequest} from "dolphin/core/api.js";
import {displayDay} from "dolphin/core/jalali.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {CHEQUE_REGISTRATION_TEXT, CHEQUE_STATUS_TEXT} from "dolphin/features/billing/shared.js";
import {setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {appendCell, appendMoneyCell, appendStatusBadgeCell, labelled} from "dolphin/ui/table.js";

// Mirrors billing.models.Cheque.TRANSITIONS. Display only — the server
// refuses a jump that is not in its own table regardless of what is offered
// here, so a drift in this copy narrows the menu, it never widens access.
//: Mirrors `Cheque.TRANSITIONS` on the server, which refuses anything this
//: lets through anyway — this only spares the trip. Every state can return
//: to «در انتظار» so a wrong button on a row can be corrected.
const CHEQUE_TRANSITIONS = Object.freeze({
    pending: ["cleared", "bounced", "spent"],
    cleared: ["pending"],
    bounced: ["pending"],
    spent: ["pending"],
});

export function setupCheques() {
    // Endorsing a cheque onward. Kept beside the transition dialog rather
    // than folded into it: this action needs a recipient, and a dropdown
    // that sometimes demands a second field is worse than two buttons.
    const spendDialog = document.getElementById("spend-cheque-dialog");
    const spendForm = document.getElementById("spend-cheque-form");
    let spendingCheque = null;

    const form = document.getElementById("cheque-search-form");
    setupListFilter("cheque");
    const dialog = document.getElementById("cheque-transition-dialog");
    const transitionForm = document.getElementById("cheque-transition-form");
    const targetSelect = document.getElementById("cheque-transition-target");
    let controller = null;
    let currentCheque = null;

    dialog?.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    transitionForm?.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(transitionForm, async () => {
            await apiRequest(`/api/v1/cheques/${currentCheque.id}/transition/`, {
                method: "POST",
                body: {
                    to_status: targetSelect.value,
                    reason: document.getElementById("cheque-transition-reason").value,
                },
            });
            dialog.close();
            globalMessage("وضعیت چک ثبت شد.", true);
            controller?.load();
        });
    });

    controller = setupPagedList({
        key: "cheques",
        form,
        search: document.getElementById("cheque-search"),
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page)});
            const search = document.getElementById("cheque-search").value.trim();
            if (search) query.set("search", search);
            const status = document.getElementById("cheque-status-filter").value;
            if (status) query.set("status", status);
            query.set("ordering", document.getElementById("cheque-ordering").value);
            return `/api/v1/cheques/?${query}`;
        },
        renderRow: (cheque) => {
            const row = document.createElement("tr");
            appendCell(row, cheque.bank_name);
            appendCell(row, cheque.bank_account || "—").dir = "ltr";
            appendCell(row, cheque.serial_number).dir = "ltr";
            appendCell(row, cheque.customer_name);
            appendMoneyCell(row, cheque.amount);
            appendCell(row, displayDay(cheque.due_date));
            appendStatusBadgeCell(row, CHEQUE_STATUS_TEXT, cheque.status);
            // حالت is the other axis and gets its own column, because a
            // reader scanning for unregistered cheques should not have to
            // open each one to find out.
            appendStatusBadgeCell(
                row,
                CHEQUE_REGISTRATION_TEXT,
                String(Boolean(cheque.is_registered)),
            );

            // --- وضعیت: one button per destination ----------------------
            //
            // Four buttons rather than a dropdown behind a «تغییر وضعیت»
            // button. The four are the whole vocabulary of this axis, so
            // naming them costs one row of the table and saves two clicks
            // and a guess every time.
            //
            // A destination the status graph refuses is shown disabled
            // rather than hidden: a button that appears and disappears as
            // rows change state reads as a rendering fault, and the reader
            // learns nothing about why it cannot be pressed. The server
            // refuses the same jumps regardless — this only spares the trip.
            //
            // Laid out two-by-two rather than left to wrap (product-owner
            // request 2026-09-20). `.row-actions` is `flex-wrap`, so where
            // the four broke depended on how wide the column happened to
            // be for that page of data — four across on one render, three
            // and one on the next, and the «عملیات ثبت» column beside it
            // shifting every time. A two-column grid is the same four
            // buttons in the same order, in a cell whose width no longer
            // depends on its content.
            // The grid goes on a wrapper inside the cell, never on the
            // cell: a `<td>` carrying a grid or flex display stops being a
            // table cell and drops out of the table's column model, which
            // is exactly what pulled «عملیات ثبت» out from under its own
            // header (see `.row-actions` in dolphin.css).
            const actions = document.createElement("td");
            actions.className = "row-actions";
            const actionGrid = document.createElement("div");
            actionGrid.className = "row-actions-2x2";
            actions.appendChild(actionGrid);
            const allowed = CHEQUE_TRANSITIONS[cheque.status] || [];

            [
                ["bounced", "برگشت"],
                ["spent", "خرج کردن"],
                ["cleared", "وصول"],
                ["pending", "در انتظار"],
            ].forEach(([target, label]) => {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "btn btn-sm btn-light";
                button.textContent = label;
                const reachable = allowed.includes(target);
                button.disabled = !reachable;
                if (!reachable) {
                    button.title = `از «${labelled(CHEQUE_STATUS_TEXT, cheque.status)}» نمی‌توان به «${label}» رفت.`;
                }
                button.addEventListener("click", async () => {
                    // Spending needs a second answer the others do not —
                    // who it went to — so it asks before it acts.
                    if (target === "spent") {
                        if (!spendDialog) return;
                        spendingCheque = cheque;
                        document.getElementById("spend-cheque-payee").value = "";
                        document.getElementById("spend-cheque-reason").value = "";
                        clearMessages(spendForm);
                        spendDialog.showModal();
                        return;
                    }
                    button.disabled = true;
                    try {
                        await apiRequest(`/api/v1/cheques/${cheque.id}/transition/`, {
                            method: "POST",
                            body: {to_status: target},
                        });
                        globalMessage(`وضعیت چک به «${label}» تغییر کرد.`, true);
                        controller.load();
                    } catch (error) {
                        button.disabled = false;
                        showError(error);
                    }
                });
                actionGrid.appendChild(button);
            });
            row.appendChild(actions);

            // --- عملیات ثبت: registered, or not, as a two-way toggle ----
            //
            // Two icon buttons rather than two text buttons (product-
            // owner request 2026-09-12: "ثبت شده"/"ثبت نشده" side by side
            // read as two separate actions, not one on/off switch). A
            // check and a cross are the whole vocabulary of this axis —
            // the same reasoning the four وضعیت buttons above already
            // follow — kept in their own cell so the column width stays
            // put as state changes.
            const registration = document.createElement("td");
            registration.className = "row-actions";
            [
                [true, "check", 1, "ثبت‌شده علامت بزن", "success"],
                [false, "cross", 2, "ثبت‌نشده علامت بزن", "danger"],
            ].forEach(([target, icon, iconPaths, label, accent]) => {
                const button = document.createElement("button");
                button.type = "button";
                const current = Boolean(cheque.is_registered) === target;
                button.className = `btn btn-icon btn-sm ${current ? `btn-${accent}` : "btn-light"}`;
                button.setAttribute("aria-label", label);
                button.title = label;
                const glyph = document.createElement("i");
                glyph.className = `di-duotone di-${icon} fs-3`;
                for (let index = 1; index <= iconPaths; index += 1) {
                    const path = document.createElement("span");
                    path.className = `path${index}`;
                    glyph.appendChild(path);
                }
                button.appendChild(glyph);
                // The state it already holds is shown as the pressed one
                // rather than removed, so both remain readable as a pair.
                button.disabled = current;
                button.setAttribute("aria-pressed", String(current));
                button.addEventListener("click", async () => {
                    button.disabled = true;
                    try {
                        await apiRequest(`/api/v1/cheques/${cheque.id}/registration/`, {
                            method: "POST",
                            body: {is_registered: target},
                        });
                        globalMessage(`حالت چک به «${target ? "ثبت شده" : "ثبت نشده"}» تغییر کرد.`, true);
                        controller.load();
                    } catch (error) {
                        button.disabled = false;
                        showError(error);
                    }
                });
                registration.appendChild(button);
            });
            row.appendChild(registration);
            return row;
        },
    });
    spendDialog?.querySelectorAll("[data-close-dialog]").forEach((button) =>
        button.addEventListener("click", () => spendDialog.close()),
    );
    document.getElementById("confirm-spend-cheque")?.addEventListener("click", async () => {
        if (!spendingCheque) return;
        const payee = document.getElementById("spend-cheque-payee").value.trim();
        if (!payee) {
            const slot = spendForm.querySelector('[data-error-for="payee"]');
            if (slot) slot.textContent = "گیرنده را وارد کنید.";
            return;
        }
        clearMessages(spendForm);
        try {
            await apiRequest(`/api/v1/cheques/${spendingCheque.id}/spend/`, {
                method: "POST",
                body: {payee, reason: document.getElementById("spend-cheque-reason").value},
            });
            spendDialog.close();
            globalMessage("چک خرج شد.", true);
            controller.load();
        } catch (error) {
            showError(error, spendForm);
        }
    });

    controller.load();
}
