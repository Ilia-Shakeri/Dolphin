export const ROLE_LABELS = Object.freeze({
    sales_agent: "بازاریاب (کال سنتر)",
    sales_manager: "مدیر فروشگاه",
    company_it: "مدیر فنی مشتری",
    platform_admin: "مدیر پلتفرم",
});
/**
 * Rial or toman — this reader's own choice, stamped on `<body>` by
 * `base.html` from `common.preferences`.
 *
 * Read once, not per call: it cannot change without a page load, and a
 * `dataset` lookup inside `money()` would run on every cell of every
 * table. The fallback is `rial`, which is both the stored unit and what
 * every page showed before the preference existed — so a page rendered
 * by anything that does not set the attribute behaves exactly as it did.
 */
export const CURRENCY_UNIT = document.body?.dataset.currencyUnit === "toman" ? "toman" : "rial";
export const CURRENCY_LABEL = CURRENCY_UNIT === "toman" ? "تومان" : "ریال";
