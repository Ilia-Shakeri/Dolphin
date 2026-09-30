const CALL_DIRECTION_ICON = {inbound: "di-entrance-left", outbound: "di-exit-right", internal: "di-arrow-right-left"};

/** The three states a campaign is tracked in, as the theme's badges. */
export const LEAD_STATUS_LABELS = {
    pending: ["در انتظار تکمیل", "badge-light-warning"],
    completed: ["تکمیل", "badge-light-success"],
    cancelled: ["کنسل شده", "badge-light-danger"],
};


// --- Inventory, billing, and financial-report pages ----------------------

export const DOCUMENT_STATUS_TEXT = Object.freeze({
    draft: "پیش‌نویس",
    sent: "ارسال‌شده",
    accepted: "پذیرفته‌شده",
    rejected: "ردشده",
    expired: "منقضی‌شده",
    cancelled: "لغوشده",
    confirmed: "تأییدشده",
    fulfilled: "تحویل‌شده",
    issued: "صادرشده",
});
export const SETTLEMENT_TEXT = Object.freeze({
    unpaid: "تسویه‌نشده",
    partially_paid: "تسویه جزئی",
    paid: "تسویه کامل",
});
const PAYMENT_DIRECTION_TEXT = Object.freeze({
    receipt: "دریافتی",
    disbursement: "پرداختی",
});
const INSTALLMENT_STATUS_TEXT = Object.freeze({
    pending: "پرداخت‌نشده",
    partially_paid: "پرداخت جزئی",
    paid: "پرداخت‌شده",
    cancelled: "لغوشده",
});

/**
 * Which theme accent a status wears.
 *
 * A document list is scanned, not read: an operator looking for the one
 * cancelled invoice among fifty should find it by colour, not by reading
 * every row. The meaning stays the backend's — this only decides how the
 * value already sent is painted, and an unknown value falls back to a
 * neutral badge rather than disappearing.
 */
export const STATUS_ACCENTS = Object.freeze({
    // Commercial documents.
    draft: "secondary",
    sent: "info",
    accepted: "success",
    confirmed: "success",
    issued: "success",
    fulfilled: "primary",
    rejected: "danger",
    cancelled: "danger",
    expired: "warning",
    // Settlement.
    unpaid: "danger",
    partially_paid: "warning",
    paid: "success",
    // Payments and cheques.
    pending: "warning",
    registered: "info",
    cleared: "success",
    bounced: "danger",
    returned: "warning",
    // Campaign and target audience.
    completed: "success",
    lead: "primary",
    engaged: "warning",
    customer: "success",
    failed: "danger",
    // Inventory movement direction.
    opening: "info",
    purchase: "success",
    sale: "primary",
    return_in: "success",
    return_out: "warning",
    adjustment_in: "success",
    adjustment_out: "warning",
    transfer_in: "info",
    transfer_out: "info",
});
