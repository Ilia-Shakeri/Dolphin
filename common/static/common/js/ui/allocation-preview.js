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
    // Whole hundredths of a rial as BigInt (2.40.0): floating point drifted on
    // large amounts, and the starting figure is the server's own
    // `unallocated_amount` — nothing is recomputed here but the rows on screen.
    let left = toCents(available);
    const used = new Map();
    let over = false;
    rows.forEach((row) => {
        const id = Number(row.querySelector(invoiceSelector)?.value);
        const invoice = invoices.find((candidate) => Number(candidate.id) === id);
        if (!invoice) return;
        const balance = toCents(invoice.balance_due) - (used.get(id) || 0n);
        const entered = moneyOrNull(row.querySelector(amountSelector)?.value);
        let amount;
        if (entered === null) {
            amount = left < balance ? left : balance;
            if (amount < 0n) amount = 0n;
        } else {
            amount = toCents(entered);
        }
        if (amount > balance || amount > left) over = true;
        used.set(id, (used.get(id) || 0n) + amount);
        left -= amount;
    });
    return {after: fromCents(left), over};
}

/** "1234.5" -> 123450n; anything unreadable -> 0n. */
export function toCents(value) {
    const text = String(value ?? "").trim();
    const match = /^(-?)(\d*)(?:\.(\d{0,2})\d*)?$/.exec(text);
    if (!match || (match[2] === "" && !match[3])) return 0n;
    const cents = BigInt(match[2] || "0") * 100n + BigInt((match[3] || "").padEnd(2, "0") || "0");
    return match[1] ? -cents : cents;
}

/** 123450n -> "1234.50" (the API's own decimal text). */
export function fromCents(cents) {
    const negative = cents < 0n;
    const absolute = negative ? -cents : cents;
    const whole = absolute / 100n;
    const fraction = String(absolute % 100n).padStart(2, "0");
    return `${negative ? "-" : ""}${whole}.${fraction}`;
}

export function renderAllocationPreview(node, preview) {
    if (!node) return;
    node.textContent = money(preview.after);
    node.classList.toggle("text-danger", preview.over || preview.after.startsWith("-"));
}
