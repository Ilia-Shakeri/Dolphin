import {money, moneyOrNull} from "dolphin/core/money.js";

/**
 * What a receipt will have left after the allocation rows on screen.
 *
 * Mirrors the server's rules row by row, in order — a blank amount takes the
 * smaller of what the invoice still owes and what the receipt still has, and
 * two rows for the same invoice draw on one balance — so the number under the
 * form is the number the server will arrive at. It is a preview only: the
 * server stays authoritative and refuses an overshoot whole.
 *
 * `invoices` are the open invoices offered (`{id, balance_due}`), `available` the
 * receipt's unallocated amount, and each row holds an invoice select and an
 * amount input found by the two selectors.
 */
export function previewAllocation({rows, invoiceSelector, amountSelector, invoices, available}) {
    let left = Number(available) || 0;
    const used = new Map();
    let over = false;
    rows.forEach((row) => {
        const id = Number(row.querySelector(invoiceSelector)?.value);
        const invoice = invoices.find((candidate) => Number(candidate.id) === id);
        if (!invoice) return;
        const balance = Number(invoice.balance_due) - (used.get(id) || 0);
        const entered = moneyOrNull(row.querySelector(amountSelector)?.value);
        const amount = entered === null ? Math.max(0, Math.min(left, balance)) : Number(entered);
        if (amount > balance || amount > left) over = true;
        used.set(id, (used.get(id) || 0) + amount);
        left -= amount;
    });
    return {after: Math.round(left * 100) / 100, over};
}

export function renderAllocationPreview(node, preview) {
    if (!node) return;
    node.textContent = money(String(preview.after));
    node.classList.toggle("text-danger", preview.over || preview.after < 0);
}
