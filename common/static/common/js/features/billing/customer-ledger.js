import {apiRequest} from "dolphin/core/api.js";
import {displayDate} from "dolphin/core/jalali.js";
import {globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {money, moneyToStorage} from "dolphin/core/money.js";
import {loadCustomerOptions} from "dolphin/features/billing/shared.js";
import {fillSelect, setupPagedList} from "dolphin/ui/lists.js";
import {appendCell, appendMoneyCell, labelled} from "dolphin/ui/table.js";

const LEDGER_ENTRY_TEXT = Object.freeze({
    opening_balance: "مانده اول دوره",
    invoice_issued: "صدور فاکتور",
    invoice_cancelled: "ابطال فاکتور",
    payment_received: "دریافت وجه",
    payment_made: "پرداخت به مشتری",
    payment_cancelled: "ابطال دریافت",
    adjustment_debit: "اصلاح بدهکار",
    adjustment_credit: "اصلاح بستانکار",
});

// --- Customer ledger -----------------------------------------------------

export async function setupCustomerLedger() {
    const filterForm = document.getElementById("ledger-filter-form");
    const openingForm = document.getElementById("opening-balance-form");
    const customerSelect = document.getElementById("ledger-customer");
    const balanceNode = document.getElementById("ledger-balance");
    const nameNode = document.getElementById("ledger-customer-name");
    const loading = document.getElementById("ledger-entries-loading");
    let controller = null;
    let customers = [];

    openingForm?.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(openingForm, async () => {
            const data = new FormData(openingForm);
            await apiRequest(openingForm.action, {method: "POST", body: {
                customer: Number(data.get("customer")),
                amount: moneyToStorage(data.get("amount")),
                notes: String(data.get("notes") || ""),
            }});
            globalMessage("مانده اول دوره ثبت شد.", true);
            openingForm.reset();
            if (customerSelect.value) refresh();
        });
    });

    async function refresh() {
        if (!customerSelect.value) return;
        loading.hidden = true;
        try {
            const balance = await apiRequest(`/api/v1/customer-ledger/balance/?customer=${customerSelect.value}`);
            balanceNode.textContent = money(balance.balance);
            const match = customers.find((row) => row.id === Number(customerSelect.value));
            nameNode.textContent = match ? match.full_name : "—";
            controller?.load();
        } catch (error) {
            showError(error);
        }
    }

    filterForm.addEventListener("submit", (event) => {
        event.preventDefault();
        refresh();
    });

    controller = setupPagedList({
        key: "ledger-entries",
        form: null,
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page), customer: customerSelect.value});
            const entryType = document.getElementById("ledger-entry-type").value;
            if (entryType) query.set("entry_type", entryType);
            return `/api/v1/customer-ledger/?${query}`;
        },
        renderRow: (entry) => {
            const row = document.createElement("tr");
            appendCell(row, displayDate(entry.occurred_at));
            appendCell(row, labelled(LEDGER_ENTRY_TEXT, entry.entry_type));
            appendCell(row, entry.reference_number || "—").dir = "ltr";
            appendMoneyCell(row, Number(entry.debit) > 0 ? entry.debit : "");
            appendMoneyCell(row, Number(entry.credit) > 0 ? entry.credit : "");
            appendMoneyCell(row, entry.balance_after);
            appendCell(row, entry.created_by_display || entry.created_by);
            return row;
        },
    });

    try {
        customers = await loadCustomerOptions(customerSelect, "یک مشتری انتخاب کنید");
        fillSelect(
            document.getElementById("opening-balance-customer"),
            customers,
            (row) => row.full_name,
            "یک مشتری انتخاب کنید",
        );
        // A customer profile links here with `?customer=<id>` (2.19.0);
        // open straight onto that customer's ledger when it is one this
        // reader may see — the balance endpoint re-checks regardless.
        const requested = new URLSearchParams(window.location.search).get("customer");
        if (requested && customers.some((row) => String(row.id) === requested)) {
            customerSelect.value = requested;
            customerSelect.dispatchEvent(new Event("change"));
            await refresh();
        }
    } catch (error) {
        showError(error);
    }
}
