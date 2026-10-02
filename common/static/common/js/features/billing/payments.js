import {apiRequest} from "dolphin/core/api.js";
import {CURRENCY_LABEL} from "dolphin/core/config.js";
import {apiDate, apiDateTime, displayDay} from "dolphin/core/jalali.js";
import {clearMessages, showError, withSubmit} from "dolphin/core/messages.js";
import {money, moneyOrNull, moneyToStorage, setupMoneyInputs, textOrNull} from "dolphin/core/money.js";
import {CHEQUE_STATUS_TEXT, PAYMENT_METHOD_TEXT, loadCustomerOptions} from "dolphin/features/billing/shared.js";
import {previewAllocation, renderAllocationPreview} from "dolphin/ui/allocation-preview.js";
import {fillSelect, loadAllPages, setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {setupSearchableSelects} from "dolphin/ui/searchable-select.js";
import {appendCell, appendDetailLink, appendMoneyCell, appendStatusBadgeCell, labelled} from "dolphin/ui/table.js";
import {renderWizardReview, selectedOptionText, setupWizard} from "dolphin/ui/wizard.js";

const PAYMENT_STATUS_TEXT = Object.freeze({
    pending: "در انتظار وصول",
    confirmed: "تأییدشده",
    cancelled: "ابطال‌شده",
});

// --- Payments, cheques, installments -------------------------------------

function paymentRow(payment) {
    const row = document.createElement("tr");
    appendCell(row, payment.number).dir = "ltr";
    // The party. A disbursement often names no customer and records who was
    // paid instead, so the payee is the fallback rather than a dash.
    //
    // An endorsed cheque shows the customer it came from on both desks,
    // which is right: it is the same document, and that is whose cheque it
    // was. Where it went is on the cheque itself.
    appendCell(row, payment.customer_name || payment.payee || "—");
    appendCell(row, labelled(PAYMENT_METHOD_TEXT, payment.method));
    appendMoneyCell(row, payment.amount);
    // On a cheque the document's own status is the wrong answer. Spending a
    // cheque onward closes the receipt it came in on, so the payment reads
    // «ابطال‌شده» while the instrument is alive and «خرج شده» — the reader
    // sees a cancelled receipt for a cheque that was never cancelled. The
    // cheque's status is the one that describes where the money is, so on
    // this method it is the one shown, and it is the same value the cheques
    // page displays for the same row.
    if (payment.method === "cheque" && payment.cheque_detail) {
        appendStatusBadgeCell(row, CHEQUE_STATUS_TEXT, payment.cheque_detail.status);
    } else {
        appendStatusBadgeCell(row, PAYMENT_STATUS_TEXT, payment.status);
    }
    // The date it was recorded, without the hour: a clock reading is not
    // what this column is ever scanned for.
    appendCell(row, displayDay(payment.received_at));
    appendDetailLink(row, `/payments/${payment.id}/`);
    return row;
}

export async function setupPayments() {
    const form = document.getElementById("payment-search-form");
    setupListFilter("payment");
    const dialog = document.getElementById("create-payment-dialog");
    let controller = null;
    if (dialog) {
        const createForm = document.getElementById("create-payment-form");
        const methodField = document.getElementById("create-payment-method");
        const bankFields = document.getElementById("create-payment-bank-fields");
        const chequeFields = document.getElementById("create-payment-cheque-fields");
        const chequeNote = document.getElementById("create-payment-cheque-note");
        const modeButtons = Array.from(createForm.querySelectorAll("[data-payment-mode]"));

        // Which direction this desk records. It is fixed by the page, not
        // chosen on the form: a receipt desk files receipts. Asking again
        // only ever let someone file a document in the wrong ledger from
        // the right screen.
        const direction = document.body.dataset.paymentDirection === "disbursement"
            ? "disbursement"
            : "receipt";
        const referenceField = createForm.querySelector('[data-payment-field="reference"]');
        const chequeSourceRow = createForm.querySelector('[data-payment-field="cheque-source"]');
        const chequeSource = document.getElementById("create-cheque-source");
        const existingChequeRow = document.getElementById("create-cheque-existing");
        const newChequeFields = document.getElementById("create-cheque-new-fields");

        function selectMode(method) {
            methodField.value = method;
            modeButtons.forEach((button) => {
                const active = button.dataset.paymentMode === method;
                button.classList.toggle("btn-primary", active);
                button.classList.toggle("btn-light", !active);
                button.setAttribute("aria-pressed", String(active));
            });
            bankFields.hidden = method !== "bank_transfer";
            chequeFields.hidden = method !== "cheque";
            if (chequeNote) chequeNote.hidden = method !== "cheque";
            // A reference number exists on a transfer and nowhere else. Cash
            // handed over has none, and a cheque is identified by its own
            // serial rather than by a tracking code.
            if (referenceField) referenceField.hidden = method !== "bank_transfer";
            // Only a disbursement can hand on a cheque already taken in.
            if (chequeSourceRow) {
                chequeSourceRow.hidden = !(method === "cheque" && direction === "disbursement");
            }
            applyChequeSource();
            clearMessages(createForm);
        }

        // Where the party, amount and date live on a non-cheque method, so
        // they can be put back when the reader switches away from cheque.
        const partyField = createForm.querySelector('[data-payment-field="customer"]');
        const amountField = createForm.querySelector('[data-payment-field="amount"]');
        const dateField = createForm.querySelector('[data-payment-field="received-at"]');
        const headerRow = partyField?.parentElement || null;
        const payeeBlock = document.getElementById("create-cheque-payee-block");
        const payeeFields = document.getElementById("create-cheque-payee-fields");

        /**
         * The cheque form, in the order the questions are actually asked.
         *
         * نوع چک decides the shape, so it comes first, with شماره چک beside
         * it. Then «اطلاعات گیرنده» — who this cheque goes to, and the one
         * or two facts that belong to that side of it.
         *
         * Which of those facts appear differs by kind, and neither omission
         * is cosmetic:
         *
         * «چک مشتری» hands on an instrument already recorded, so its amount
         * is the cheque's own and asking for it again would invite a figure
         * that disagrees with the document being spent. It takes a payment
         * date instead.
         *
         * «چک تازه» writes a new instrument, so it needs an amount — and it
         * has no payment date, because nothing has been paid yet: the cheque
         * carries a due date of its own, which is already in its details.
         */
        function applyChequeSource() {
            const onCheque = methodField.value === "cheque";
            const spending =
                direction === "disbursement" &&
                onCheque &&
                chequeSource &&
                chequeSource.value === "customer_endorsed";
            if (existingChequeRow) existingChequeRow.hidden = !spending;
            if (newChequeFields) newChequeFields.hidden = !onCheque || spending;
            if (chequeNote) chequeNote.hidden = !onCheque || spending;

            // Only the disbursement desk is rearranged. A cheque taken in
            // is still a receipt with a party, an amount and the date it
            // arrived — moving those under «اطلاعات گیرنده» would name the
            // customer who paid us as the recipient, and hiding the date
            // would take away the one this desk exists to record.
            const grouped = onCheque && direction === "disbursement";
            if (payeeBlock && payeeFields && headerRow) {
                payeeBlock.hidden = !grouped;
                const host = grouped ? payeeFields : headerRow;
                [partyField, amountField, dateField].forEach((field) => {
                    if (field && field.parentElement !== host) host.append(field);
                });
                if (amountField) amountField.hidden = grouped && spending;
                if (dateField) dateField.hidden = grouped && !spending;
            }
            // A hidden required field blocks submission with a message the
            // reader cannot see the field for, so `required` follows what is
            // on screen rather than staying pinned to the markup.
            const amountInput = document.getElementById("create-payment-amount");
            if (amountInput) amountInput.required = !(grouped && spending);
        }

        if (chequeSource) chequeSource.addEventListener("change", applyChequeSource);

        modeButtons.forEach((button) => {
            button.addEventListener("click", () => {
                selectMode(button.dataset.paymentMode);
                // The method is now its own first step with nothing else
                // to answer on it (product-owner request 2026-09-12), so
                // choosing one advances the wizard the same way clicking
                // «بعدی» would — a real click on that same button rather
                // than calling the stepper API directly, so the existing
                // validation/scroll-reset/`onReachLastStep` wiring
                // (`setupWizard` above) runs exactly as it does for an
                // explicit click.
                createForm.querySelector('[data-dolphin-stepper-action="next"]')?.click();
            });
        });

        selectMode("cash");
        setupSearchableSelects(createForm);

        // --- «تخصیص به فاکتور» inside the wizard (2.28.0) --------------------
        //
        // The rows the payment page's own section takes, sent with the receipt
        // as `allocations` and recorded in the same transaction. They follow
        // the chosen customer — the server only ever allocates to that
        // customer's own issued invoices — and a cheque gets none, since it
        // stays pending until it clears.
        const allocationBlock = document.getElementById("create-payment-allocations");
        const allocationChequeNote = document.getElementById("create-payment-allocations-cheque");
        const wizardSplitRows = document.getElementById("create-payment-split-rows");
        const paymentCustomer = document.getElementById("create-payment-customer");
        let wizardInvoices = [];
        let wizardInvoicesFor = null;

        // What the receipt will have left after the rows below, from the amount
        // typed above — the same arithmetic the server applies.
        function refreshWizardPreview() {
            const node = document.getElementById("create-payment-alloc-after");
            if (!node || !wizardSplitRows) return;
            const typed = moneyOrNull(document.getElementById("create-payment-amount")?.value);
            if (typed === null) {
                node.textContent = "—";
                node.classList.remove("text-danger");
                return;
            }
            renderAllocationPreview(node, previewAllocation({
                rows: [...wizardSplitRows.querySelectorAll("[data-wizard-split-row]")],
                invoiceSelector: "[data-wizard-split-invoice]",
                amountSelector: "[data-wizard-split-amount]",
                invoices: wizardInvoices,
                available: typed,
            }));
        }

        function addWizardSplitRow() {
            if (!wizardSplitRows) return;
            const row = document.createElement("div");
            row.className = "d-flex flex-wrap align-items-center gap-3";
            row.dataset.wizardSplitRow = "";
            const picker = document.createElement("div");
            picker.className = "searchable-select w-auto flex-grow-1";
            picker.setAttribute("data-searchable-select", "");
            const search = document.createElement("input");
            search.className = "form-control form-control-solid";
            search.type = "search";
            search.autocomplete = "off";
            search.placeholder = "شماره یا مبلغ فاکتور را بنویسید…";
            search.setAttribute("data-searchable-input", "");
            search.setAttribute("role", "combobox");
            search.setAttribute("aria-label", "جستجوی فاکتور");
            search.hidden = true;
            const select = document.createElement("select");
            select.className = "form-select form-select-solid";
            select.dataset.wizardSplitInvoice = "";
            select.setAttribute("data-searchable-source", "");
            select.setAttribute("aria-label", "فاکتور");
            select.dataset.searchableLimit = "0";
            select.dataset.searchableEmpty = "این مشتری فاکتور صادرشدهٔ تسویه‌نشده‌ای ندارد.";
            fillSelect(
                select,
                wizardInvoices,
                (invoice) => `${invoice.number} — مانده ${money(invoice.balance_due)}`,
                "یک فاکتور انتخاب کنید",
            );
            const options = document.createElement("ul");
            options.className = "searchable-select-options";
            options.setAttribute("role", "listbox");
            options.hidden = true;
            picker.append(search, select, options);
            const amount = document.createElement("input");
            amount.className = "form-control form-control-solid w-auto flex-grow-1";
            amount.type = "text";
            amount.inputMode = "numeric";
            amount.dir = "ltr";
            amount.placeholder = `مبلغ به ${CURRENCY_LABEL} (خالی = مانده فاکتور)`;
            amount.setAttribute("data-money-input", "");
            amount.dataset.wizardSplitAmount = "";
            amount.setAttribute("aria-label", "مبلغ تخصیص");
            const remove = document.createElement("button");
            remove.className = "btn btn-icon btn-light-danger";
            remove.type = "button";
            remove.textContent = "×";
            remove.setAttribute("aria-label", "حذف سطر");
            remove.addEventListener("click", () => {
                row.remove();
                refreshWizardPreview();
            });
            amount.addEventListener("input", refreshWizardPreview);
            select.addEventListener("change", refreshWizardPreview);
            row.append(picker, amount, remove);
            wizardSplitRows.append(row);
            setupMoneyInputs(row);
            setupSearchableSelects(row);
        }

        async function refreshWizardAllocations() {
            if (!allocationBlock) return;
            const onCheque = methodField.value === "cheque";
            const customer = paymentCustomer?.value || "";
            if (allocationChequeNote) allocationChequeNote.hidden = !onCheque;
            allocationBlock.hidden = onCheque || !customer;
            if (onCheque || !customer || wizardInvoicesFor === customer) return;
            wizardInvoicesFor = customer;
            wizardSplitRows.replaceChildren();
            try {
                const rows = await loadAllPages(
                    `/api/v1/invoices/?status=issued&customer=${customer}&ordering=due_at`,
                );
                // The customer changed while this was on its way: its rows
                // belong to nobody on screen any more.
                if (wizardInvoicesFor !== customer) return;
                wizardInvoices = rows.filter((invoice) => Number(invoice.balance_due) > 0);
                addWizardSplitRow();
            } catch (error) {
                wizardInvoicesFor = null;
                showError(error);
            }
        }

        function collectWizardAllocations() {
            if (!wizardSplitRows || allocationBlock?.hidden) return [];
            const rows = [];
            wizardSplitRows.querySelectorAll("[data-wizard-split-row]").forEach((row) => {
                const invoice = Number(row.querySelector("[data-wizard-split-invoice]").value);
                if (!invoice) return;
                const entry = {invoice};
                const amount = moneyOrNull(row.querySelector("[data-wizard-split-amount]").value);
                if (amount !== null) entry.amount = amount;
                rows.push(entry);
            });
            return rows;
        }

        document.getElementById("create-payment-split-add")?.addEventListener("click", addWizardSplitRow);
        paymentCustomer?.addEventListener("change", refreshWizardAllocations);
        document.getElementById("create-payment-amount")?.addEventListener("input", refreshWizardPreview);
        modeButtons.forEach((button) => button.addEventListener("click", refreshWizardAllocations));

        function renderPaymentReview() {
            const method = methodField.value;
            const methodLabel = {cash: "نقدی", bank_transfer: "حواله بانکی", cheque: "چک"}[method] || method;
            const spending =
                direction === "disbursement" &&
                method === "cheque" &&
                chequeSource &&
                chequeSource.value === "customer_endorsed";
            const rows = [["روش", methodLabel]];
            if (spending) {
                const chequeSelect = document.getElementById("create-cheque-existing-id");
                rows.push(["شماره چک", selectedOptionText(chequeSelect)]);
                rows.push(["گیرنده", document.getElementById("create-payment-customer-search").value || "—"]);
            } else {
                rows.push([
                    direction === "disbursement" ? "گیرنده" : "مشتری",
                    document.getElementById("create-payment-customer-search").value ||
                        selectedOptionText(document.getElementById("create-payment-customer")),
                ]);
                if (!amountField.hidden) rows.push(["مبلغ", createForm.amount.value || "—"]);
                if (!dateField.hidden) rows.push([direction === "disbursement" ? "تاریخ پرداخت" : "تاریخ دریافت", createForm.received_at.value || "امروز"]);
            }
            if (method === "bank_transfer") {
                rows.push(["شماره پیگیری", createForm.reference.value || "—"]);
                rows.push([direction === "disbursement" ? "بانک مبدأ" : "بانک مقصد", createForm.bank_name.value || "—"]);
            }
            if (method === "cheque" && !spending) {
                rows.push([direction === "disbursement" ? "بانک مقصد" : "بانک مبدأ", createForm.cheque_bank_name.value || "—"]);
                rows.push(["شماره چک", createForm.cheque_serial_number.value || "—"]);
                rows.push(["تاریخ سررسید چک", createForm.cheque_due_date.value || "—"]);
            }
            const allocated = collectWizardAllocations();
            if (allocated.length) {
                rows.push([
                    "تخصیص به فاکتور",
                    allocated.map((entry) => {
                        const invoice = wizardInvoices.find((item) => item.id === entry.invoice);
                        const number = invoice ? invoice.number : String(entry.invoice);
                        return `${number}: ${entry.amount !== undefined ? money(entry.amount) : "تا سقف مانده"}`;
                    }).join("، "),
                ]);
            }
            rows.push(["یادداشت", createForm.notes.value || "—"]);
            renderWizardReview(document.getElementById("create-payment-review"), rows);
        }
        const paymentWizard = setupWizard(dialog, {onReachLastStep: renderPaymentReview});

        document.getElementById("open-create-payment").addEventListener("click", () => {
            createForm.reset();
            clearMessages(createForm);
            selectMode("cash");
            // A fresh form starts with no customer, so no invoice rows.
            wizardInvoicesFor = null;
            wizardInvoices = [];
            wizardSplitRows?.replaceChildren();
            refreshWizardAllocations();
            paymentWizard?.goFirst();
            dialog.showModal();
        });
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
        createForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(createForm, async () => {
                const data = new FormData(createForm);
                const method = String(data.get("method"));
                const chosenCustomer = String(data.get("customer") || "");
                const spendingExisting =
                    direction === "disbursement" &&
                    method === "cheque" &&
                    chequeSource &&
                    chequeSource.value === "customer_endorsed";

                // Handing on a cheque already recorded is not a new payment.
                // It is the same instrument moving, so it goes to the spend
                // endpoint — creating a second document here would count the
                // same money twice everywhere it is summed.
                if (spendingExisting) {
                    const chequeId = String(data.get("cheque_existing") || "");
                    if (!chequeId) {
                        const slot = createForm.querySelector('[data-error-for="cheque_existing"]');
                        if (slot) slot.textContent = "یک چک را انتخاب کنید.";
                        return;
                    }
                    const payee = chosenCustomer
                        ? (document.getElementById("create-payment-customer-search").value || "")
                        : "";
                    if (!payee) {
                        const slot = createForm.querySelector('[data-error-for="customer"]');
                        if (slot) slot.textContent = "گیرنده را انتخاب کنید.";
                        return;
                    }
                    // No amount and no document: the instrument already
                    // carries its figure, and spending it is a state change
                    // on that row. It reaches this desk because the payments
                    // list includes receipts whose cheque has been spent —
                    // where it reads «خرج شده», the cheque's own status.
                    await apiRequest(`/api/v1/cheques/${chequeId}/spend/`, {
                        method: "POST",
                        body: {payee, reason: String(data.get("notes") || "")},
                    });
                    window.location.assign("/disbursements/");
                    return;
                }

                const payload = {
                    method,
                    direction,
                    amount: moneyToStorage(data.get("amount")),
                    notes: String(data.get("notes") || ""),
                };
                // A reference exists on a transfer and nowhere else, so it
                // is only sent from there — a value left over from another
                // method would otherwise be filed against cash.
                if (method === "bank_transfer") {
                    payload.reference = String(data.get("reference") || "");
                }
                // Omitted rather than null when a disbursement names nobody:
                // the field is optional there, and sending an empty value is
                // a different claim from not sending one.
                if (chosenCustomer) payload.customer = Number(chosenCustomer);
                if (direction === "disbursement") {
                    // The party is one field on this form. On a disbursement
                    // the name typed into it is who was paid.
                    payload.payee =
                        document.getElementById("create-payment-customer-search").value.trim() ||
                        "گیرنده";
                }
                // Blank means "today" on the server, which is what an
                // operator recording a receipt as it happens expects.
                const receivedAt = apiDateTime(textOrNull(data.get("received_at")));
                if (receivedAt) payload.received_at = receivedAt;

                // Only ever sent for a transfer. The service refuses these
                // on any other method, and a hidden field left populated
                // from a previous mode would otherwise be submitted.
                if (method === "bank_transfer") {
                    payload.bank_name = String(data.get("bank_name") || "");
                }
                if (method === "cheque") {
                    payload.cheque = {
                        bank_name: String(data.get("cheque_bank_name") || ""),
                        bank_account: String(data.get("cheque_bank_account") || ""),
                        branch_name: String(data.get("cheque_branch_name") || ""),
                        serial_number: String(data.get("cheque_serial_number") || ""),
                        due_date: apiDate(data.get("cheque_due_date")) || "",
                        registered_on: apiDate(data.get("cheque_registered_on")) || null,
                        // Always unregistered on arrival, whichever desk
                        // wrote it. Both axes are moved by hand from the
                        // cheque page and nowhere else, so this form cannot
                        // put an instrument into a state nobody chose.
                        is_registered: false,
                    };
                    if (direction === "disbursement") {
                        payload.cheque.source = "own";
                    }
                }
                if (direction === "receipt" && method !== "cheque") {
                    const allocations = collectWizardAllocations();
                    if (allocations.length) payload.allocations = allocations;
                }
                const payment = await apiRequest(createForm.action, {method: "POST", body: payload});
                window.location.assign(`/payments/${payment.id}/`);
            });
        });
    }
    try {
        await loadCustomerOptions(
            document.getElementById("create-payment-customer"),
            document.body.dataset.paymentDirection === "disbursement"
                ? "یک گیرنده انتخاب کنید"
                : "یک مشتری انتخاب کنید",
        );
        // The cheques this desk may hand on: taken in from a customer and
        // still waiting. A cleared one is spent money and a spent one is
        // already gone, so neither is offered — the same rule the service
        // enforces, asked of the API rather than restated here.
        const existing = document.getElementById("create-cheque-existing-id");
        if (existing) {
            const rows = await loadAllPages(
                "/api/v1/cheques/?status=pending&ordering=due_date",
            );
            fillSelect(
                existing,
                rows.filter((row) => row.source !== "own"),
                (row) =>
                    `${row.serial_number} — ${row.bank_name} — ${money(row.amount)}` +
                    (row.customer_name ? ` — ${row.customer_name}` : ""),
                "یک چک انتخاب کنید",
            );
        }
        setupSearchableSelects(document.getElementById("create-payment-form") || document);
    } catch (error) {
        showError(error);
    }
    controller = setupPagedList({
        key: "payments",
        form,
        search: document.getElementById("payment-search"),
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page)});
            const search = document.getElementById("payment-search").value.trim();
            if (search) query.set("search", search);
            // `desk`, not `direction`. A cheque taken in and later handed
            // on is one document that belongs on both screens — still the
            // receipt it was, and also money that has left — so the paying
            // desk asks for a desk rather than for a direction. The server
            // decides what that means; nothing here duplicates the rule.
            query.set(
                "desk",
                document.body.dataset.paymentDirection === "disbursement"
                    ? "disbursement"
                    : "receipt",
            );
            const method = document.getElementById("payment-method-filter").value;
            if (method) query.set("method", method);
            query.set("ordering", document.getElementById("payment-ordering").value);
            return `/api/v1/payments/?${query}`;
        },
        renderRow: paymentRow,
    });
    controller.load();
}
