import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {loadAllPages} from "dolphin/ui/lists.js";

/** One supply document for several issued invoices (2.39.6): pick invoices, pick a warehouse. */
export function setupSupplyBatch() {
    const open = document.getElementById("open-supply-batch");
    const dialog = document.getElementById("supply-batch-dialog");
    if (!open || !dialog) return;
    const form = document.getElementById("supply-batch-form");
    const list = document.getElementById("supply-batch-list");
    const search = document.getElementById("supply-batch-search");
    const count = document.getElementById("supply-batch-count");
    const warehouse = document.getElementById("supply-batch-warehouse");
    let rows = [];

    const checked = () => Array.from(list.querySelectorAll("input:checked")).map((box) => Number(box.value));
    const updateCount = () => { count.textContent = toPersianDigits(String(checked().length)); };

    function draw() {
        const term = search.value.trim();
        const keep = new Set(checked());
        list.replaceChildren(...rows
            .filter((row) => !term || `${row.number} ${row.customer_name}`.includes(term) || keep.has(row.id))
            .map((row) => {
                const label = document.createElement("label");
                label.className = "form-check form-check-custom form-check-solid d-flex align-items-center gap-3 py-2";
                const box = document.createElement("input");
                box.type = "checkbox";
                box.className = "form-check-input";
                box.value = String(row.id);
                box.checked = keep.has(row.id);
                box.addEventListener("change", updateCount);
                const text = document.createElement("span");
                text.className = "form-check-label";
                text.textContent = `${row.number} — ${row.customer_name} — ${money(row.total_amount)}`;
                label.append(box, text);
                return label;
            }));
        if (!list.children.length) list.textContent = "فاکتوری یافت نشد.";
        updateCount();
    }

    open.addEventListener("click", async () => {
        form.reset();
        clearMessages(form);
        dialog.showModal();
        try {
            const [invoices, requests, stores] = await Promise.all([
                loadAllPages("/api/v1/invoices/?status=issued&ordering=-created_at"),
                loadAllPages("/api/v1/orders/?ordering=-created_at"),
                loadAllPages("/api/v1/warehouses/?is_active=true&ordering=name"),
            ]);
            const taken = new Set(requests.filter((row) => row.invoice && row.status !== "cancelled").map((row) => row.invoice));
            rows = invoices.filter((row) => !taken.has(row.id) && !row.stock_applied);
            warehouse.replaceChildren(new Option("انتخاب انبار", ""), ...stores.map((row) => new Option(row.name, String(row.id))));
            draw();
        } catch (error) {
            showError(error);
        }
    });
    search.addEventListener("input", draw);
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const invoices = checked();
            if (!invoices.length) {
                const slot = form.querySelector('[data-error-for="invoices"]');
                if (slot) slot.textContent = "حداقل یک فاکتور را تیک بزنید.";
                return;
            }
            const result = await apiRequest("/api/v1/orders/from-invoices/", {
                method: "POST",
                body: {invoices, warehouse: Number(warehouse.value), notes: form.elements.notes.value},
            });
            dialog.close();
            globalMessage(`سند تأمین ${result.batch_number} با ${toPersianDigits(String(result.orders.length))} درخواست ثبت شد.`, true);
            window.location.reload();
        });
    });
}
