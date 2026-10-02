import {apiRequest} from "dolphin/core/api.js";
import {CURRENCY_LABEL} from "dolphin/core/config.js";
import {apiDate, apiDateTime, displayDate, displayDay} from "dolphin/core/jalali.js";
import {globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {money, moneyOrNull, moneyToStorage, setupMoneyInputs, textOrNull} from "dolphin/core/money.js";
import {CHEQUE_REGISTRATION_TEXT, CHEQUE_STATUS_TEXT, PAYMENT_METHOD_TEXT, loadCustomerOptions} from "dolphin/features/billing/shared.js";
import {previewAllocation, renderAllocationPreview} from "dolphin/ui/allocation-preview.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {fillSelect, loadAllPages, setupPagedList} from "dolphin/ui/lists.js";
import {setupSearchableSelects} from "dolphin/ui/searchable-select.js";
import {appendCell, appendMoneyCell, labelled} from "dolphin/ui/table.js";

export async function setupPaymentDetail() {
    const paymentId = document.body.dataset.paymentId;
    const endpoint = `/api/v1/payments/${paymentId}/`;
    const loading = document.getElementById("payment-detail-loading");
    const content = document.getElementById("payment-detail-content");
    const allocateSection = document.getElementById("payment-allocate-section");
    const allocateForm = document.getElementById("payment-allocate-form");
    let payment;
    let allocationsController = null;
    //: The invoices this payment may settle, held here rather than read back
    //: out of a select on the page. Every allocation row is built from this
    //: one list, so no two rows can offer different invoices.
    let allocatableInvoices = [];
    // What the invoice picker says when there is nothing to pick (2.25.1).
    let allocatableEmptyText = "";

    function apply(value) {
        payment = value;
        document.getElementById("payment-number").value = payment.number;
        document.getElementById("payment-method").value = labelled(PAYMENT_METHOD_TEXT, payment.method);
        document.getElementById("payment-received-by").value = payment.received_by_display || payment.received_by;

        // The party. On a disbursement with no customer the select holds
        // nothing and the payee is what names it, so the label follows.
        const customerSelect = document.getElementById("payment-customer");
        const customerSearch = document.getElementById("payment-customer-search");
        const isDisbursement = payment.direction === "disbursement";
        const partyLabel = document.querySelector('label[for="payment-customer-search"]');
        if (partyLabel) partyLabel.textContent = isDisbursement ? "گیرنده" : "مشتری";
        if (customerSelect) {
            customerSelect.value = payment.customer ? String(payment.customer) : "";
            if (customerSearch) {
                customerSearch.value = payment.customer_name || payment.payee || "";
            }
        }

        // Two values, and the one it currently holds. A payment still
        // pending on a cheque shows as confirmed here only once it is; until
        // then the select simply carries no match, which is honest — the
        // status is not the operator's to set while the cheque decides it.
        const statusSelect = document.getElementById("payment-status");
        if (statusSelect) {
            statusSelect.value = payment.status;
            // Cancelling is one-way. Once a document is cancelled it is
            // recorded anew rather than revived, so «تأییدشده» is disabled
            // instead of being offered and then refused by the server.
            const confirmOption = statusSelect.querySelector('option[value="confirmed"]');
            if (confirmOption) {
                confirmOption.disabled = payment.status === "cancelled";
            }
        }

        document.getElementById("payment-amount").value = money(payment.amount);
        document.getElementById("payment-received-at").value = displayDate(payment.received_at);
        document.getElementById("payment-reference").value = payment.reference || "";
        const bankName = document.getElementById("payment-bank-name");
        if (bankName) bankName.value = payment.bank_name || "";
        document.getElementById("payment-notes").value = payment.notes || "";

        // A reference belongs to a transfer, and so does the bank. On cash
        // and on a cheque the rows are absent rather than empty.
        const referenceRow = document.querySelector('[data-payment-detail="reference"]');
        if (referenceRow) referenceRow.hidden = payment.method !== "bank_transfer";
        const bankRow = document.querySelector('[data-payment-detail="bank"]');
        if (bankRow) bankRow.hidden = payment.method !== "bank_transfer";
        const chequeBlock = document.getElementById("payment-cheque-block");
        if (chequeBlock) {
            const cheque = payment.cheque_detail;
            chequeBlock.hidden = !cheque;
            if (cheque) {
                document.getElementById("payment-cheque-bank").value = cheque.bank_name;
                document.getElementById("payment-cheque-serial").value = cheque.serial_number;
                document.getElementById("payment-cheque-due").value = displayDay(cheque.due_date);
                document.getElementById("payment-cheque-status").value = labelled(CHEQUE_STATUS_TEXT, cheque.status);
                // Both axes are shown, and neither is editable from here.
                const registration = document.getElementById("payment-cheque-registration");
                if (registration) {
                    registration.value = labelled(
                        CHEQUE_REGISTRATION_TEXT,
                        String(Boolean(cheque.is_registered)),
                    );
                }
            }
        }
        // The document's own status is hidden on a cheque. There the
        // cheque's status is the one that describes where the money is, and
        // two controls answering the same question differently is worse than
        // one — spending a cheque closes the receipt it arrived on, so this
        // one would read «ابطال‌شده» for a cheque that is alive.
        const statusRow = document.querySelector('[data-payment-detail="status"]');
        if (statusRow) statusRow.hidden = payment.method === "cheque";
        if (allocateSection) allocateSection.hidden = payment.status !== "confirmed";
        renderAllocationSummary();
        if (payment.status === "confirmed") allocationsController?.load();
    }

    // --- تخصیص به فاکتور -----------------------------------------------
    //
    // One form, whatever the arity. There used to be two — "allocate to an
    // invoice" and "split between several" — under separate headings, which
    // asked the reader to work out that they were the same operation. A
    // single invoice is the one-row case of a split, and it posts through
    // the same endpoint and the same server rules either way.
    const splitRows = document.getElementById("payment-split-rows");
    const splitTotal = document.getElementById("payment-split-total");

    // The receipt's own figures, from the server, and the live remainder under
    // the rows. Nothing is invented here: a remainder of zero closes the form
    // and says so rather than leaving a button that can only be refused.
    function renderAllocationSummary() {
        const set = (id, value) => {
            const node = document.getElementById(id);
            if (node) node.textContent = value === null || value === undefined ? "—" : money(value);
        };
        set("payment-alloc-amount", payment?.amount);
        set("payment-alloc-allocated", payment?.allocated_amount);
        set("payment-alloc-remaining", payment?.unallocated_amount);
        const exhausted = payment && Number(payment.unallocated_amount) <= 0;
        const done = document.getElementById("payment-alloc-done");
        if (done) done.hidden = !exhausted;
        if (allocateForm) allocateForm.hidden = Boolean(exhausted);
        refreshSplitTotal();
    }

    function refreshSplitTotal() {
        if (!splitRows || !splitTotal) return;
        const preview = previewAllocation({
            rows: [...splitRows.querySelectorAll("[data-split-row]")],
            invoiceSelector: "[data-split-invoice]",
            amountSelector: "[data-split-amount]",
            invoices: allocatableInvoices,
            available: payment?.unallocated_amount,
        });
        renderAllocationPreview(document.getElementById("payment-alloc-after"), preview);
        const submit = allocateForm?.querySelector('button[type="submit"]');
        if (submit) submit.disabled = preview.over || preview.after < 0;
        let sum = 0;
        let anyBlank = false;
        splitRows.querySelectorAll("[data-split-amount]").forEach((input) => {
            const value = moneyOrNull(input.value);
            if (value === null) anyBlank = true;
            else sum += Number(value);
        });
        // A blank row takes "whatever the invoice still owes", which is not
        // known here, so the total is reported as at-least rather than as a
        // figure that would be wrong.
        splitTotal.textContent = sum === 0 && anyBlank ? "—" : (anyBlank ? "حداقل " : "") + money(sum);
    }

    function addSplitRow() {
        if (!splitRows) return;
        const row = document.createElement("div");
        row.className = "d-flex flex-wrap align-items-center gap-3";
        row.dataset.splitRow = "";
        // A searchable invoice, because the one thing a reader knows is
        // its number. The plain select showed nothing usable once a customer
        // had more than a handful of open invoices and could not be typed
        // into at all. The real `<select>` stays underneath and is still what
        // is read on submit, so nothing below this cares.
        const picker = document.createElement("div");
        picker.className = "searchable-select w-auto flex-grow-1";
        picker.setAttribute("data-searchable-select", "");
        const search = document.createElement("input");
        search.className = "form-control form-control-solid";
        search.type = "search";
        search.autocomplete = "off";
        search.placeholder = "شماره فاکتور را بنویسید…";
        search.setAttribute("data-searchable-input", "");
        search.setAttribute("role", "combobox");
        search.setAttribute("aria-label", "جستجوی فاکتور");
        search.hidden = true;
        const select = document.createElement("select");
        select.className = "form-select form-select-solid";
        select.dataset.splitInvoice = "";
        select.setAttribute("data-searchable-source", "");
        select.setAttribute("aria-label", "فاکتور");
        select.addEventListener("change", refreshSplitTotal);
        // Every open invoice of this customer, not the first fifty — the
        // one you are looking for is the one that would be cut.
        select.dataset.searchableLimit = "0";
        select.dataset.searchableEmpty = allocatableEmptyText;
        fillSelect(
            select,
            allocatableInvoices,
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
        amount.dataset.splitAmount = "";
        amount.setAttribute("aria-label", "مبلغ");
        amount.addEventListener("input", refreshSplitTotal);
        const remove = document.createElement("button");
        remove.className = "btn btn-icon btn-light-danger";
        remove.type = "button";
        remove.textContent = "×";
        remove.setAttribute("aria-label", "حذف سطر");
        remove.addEventListener("click", () => {
            row.remove();
            refreshSplitTotal();
        });
        row.append(picker, amount, remove);
        splitRows.append(row);
        // Money grouping is wired once per input by the shared helper, which
        // guards against binding the same field twice.
        setupMoneyInputs(row);
        setupSearchableSelects(row);
        refreshSplitTotal();
    }

    document.getElementById("payment-split-add")?.addEventListener("click", addSplitRow);

    allocateForm?.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(allocateForm, async () => {
            const splits = [];
            splitRows.querySelectorAll("[data-split-row]").forEach((row) => {
                const invoice = Number(row.querySelector("[data-split-invoice]").value);
                if (!invoice) return;
                const entry = {invoice};
                const amount = moneyOrNull(row.querySelector("[data-split-amount]").value);
                if (amount !== null) entry.amount = amount;
                splits.push(entry);
            });
            if (!splits.length) {
                const slot = allocateForm.querySelector('[data-error-for="splits"]');
                if (slot) slot.textContent = "حداقل یک فاکتور را انتخاب کنید.";
                return;
            }
            await apiRequest(`${endpoint}allocate-across/`, {method: "POST", body: {splits}});
            globalMessage("دریافت به فاکتور تخصیص یافت.", true);
            splitRows.replaceChildren();
            addSplitRow();
            apply(await apiRequest(endpoint));
        });
    });

    // --- correcting a recorded document (بند: مدیر پلتفرم) --------------
    //
    // The controls are only enabled for the platform admin, and that is a
    // convenience: the endpoint and the service both check the role again,
    // because a field being editable on screen has never been the
    // authorisation for changing it.
    const editForm = document.getElementById("payment-edit-form");
    const saveButton = document.getElementById("save-payment-edit");
    if (editForm && saveButton) {
        loadCustomerOptions(
            document.getElementById("payment-customer"),
            "بدون طرف حساب",
        )
            .then(() => {
                const select = document.getElementById("payment-customer");
                if (payment && select) {
                    select.value = payment.customer ? String(payment.customer) : "";
                }
                setupSearchableSelects(editForm);
            })
            .catch(showError);

        editForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(editForm, async () => {
                const data = new FormData(editForm);
                const body = {
                    amount: moneyToStorage(data.get("amount")),
                    notes: String(data.get("notes") || ""),
                    status: String(data.get("status") || payment.status),
                };
                const chosen = String(data.get("customer") || "");
                // Null, not omitted: on a disbursement clearing the party is
                // a real edit, and the two are different claims.
                body.customer = chosen ? Number(chosen) : null;
                const receivedAt = apiDateTime(textOrNull(data.get("received_at")));
                if (receivedAt) body.received_at = receivedAt;
                if (payment.method === "bank_transfer") {
                    body.reference = String(data.get("reference") || "");
                    body.bank_name = String(data.get("bank_name") || "");
                }
                if (payment.method === "cheque") {
                    body.cheque = {
                        bank_name: String(data.get("cheque_bank_name") || ""),
                        serial_number: String(data.get("cheque_serial_number") || ""),
                    };
                    const due = apiDate(data.get("cheque_due_date"));
                    if (due) body.cheque.due_date = due;
                }
                apply(await apiRequest(`${endpoint}correct/`, {method: "POST", body}));
                globalMessage("تغییرات ذخیره شد.", true);
            });
        });
    } else if (editForm) {
        // No save button means this reader may not correct anything, so the
        // controls are made read-only rather than left looking usable.
        editForm.querySelectorAll("input, select, textarea").forEach((field) => {
            field.disabled = true;
        });
    }

    allocationsController = setupPagedList({
        key: "payment-allocations",
        form: null,
        endpoint: (page) => `${endpoint}allocations/?page=${page}`,
        renderRow: (allocation) => {
            const row = document.createElement("tr");
            appendCell(row, allocation.invoice_number).dir = "ltr";
            appendMoneyCell(row, allocation.amount);
            appendCell(row, allocation.is_reversed ? "آزادشده" : "فعال");
            appendCell(row, displayDay(allocation.created_at));
            const actions = document.createElement("td");
            actions.className = "row-actions";
            if (!allocation.is_reversed) {
                const release = document.createElement("button");
                release.type = "button";
                release.className = "btn btn-sm btn-light";
                release.textContent = "آزادکردن";
                release.addEventListener("click", async () => {
                    if (!await confirmDialog("این تخصیص آزاد شود؟")) return;
                    release.disabled = true;
                    try {
                        await apiRequest(`/api/v1/payment-allocations/${allocation.id}/release/`, {method: "POST"});
                        globalMessage("تخصیص آزاد شد.", true);
                        apply(await apiRequest(endpoint));
                    } catch (error) {
                        release.disabled = false;
                        showError(error);
                    }
                });
                actions.appendChild(release);
            }
            row.appendChild(actions);
            return row;
        },
    });

    try {
        const value = await apiRequest(endpoint);
        if (value.customer) {
            const invoices = await loadAllPages(
                `/api/v1/invoices/?status=issued&customer=${value.customer}&ordering=due_at`
            );
            allocatableInvoices = invoices.filter(
                (invoice) => Number(invoice.balance_due) > 0,
            );
            // Same rule the server applies (`allocate_payment`): only an
            // issued invoice of this payment's own customer, with
            // something still owed.
            allocatableEmptyText = "این مشتری فاکتور صادرشدهٔ تسویه‌نشده‌ای ندارد.";
        } else {
            allocatableEmptyText = "این دریافت طرف حساب ندارد؛ تخصیص فقط به فاکتور همان مشتری ممکن است.";
        }
        apply(value);
        // One row to start with, so the common case — settle this against
        // that invoice — is a form that is already there rather than one the
        // reader has to summon with «افزودن فاکتور» first.
        if (splitRows && !splitRows.children.length) addSplitRow();
        loading.hidden = true;
        content.hidden = false;
    } catch (error) {
        loading.hidden = true;
        showError(error);
    }
}
