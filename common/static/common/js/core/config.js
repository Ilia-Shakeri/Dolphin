export const ROLE_LABELS = Object.freeze({
    sales_agent: "بازاریاب (کال سنتر)",
    sales_manager: "مدیر فروشگاه",
    company_it: "مدیر فنی مشتری",
    platform_admin: "مدیر پلتفرم",
    system: "سامانه",
});

/**
 * The role an activity row records (2.40.47). A row written before roles were
 * recorded had its role filled in later from the actor's role at that time
 * (`actor_role_inferred`), and says so, so nobody reads today's role as the
 * one held when it happened.
 */
export function activityRoleLabel(code, inferred = false) {
    const label = ROLE_LABELS[code] || code || "—";
    return inferred ? `${label} (نقش فعلی)` : label;
}
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
export const CURRENCY_UNIT = globalThis.document?.body?.dataset.currencyUnit === "toman" ? "toman" : "rial";
/**
 * Whether this reader also sees each date's Gregorian equivalent (2.40.49,
 * «تنظیمات ← نمایش پنل ← تاریخ»). Every date stays Jalali; this only adds.
 */
export const SHOWS_GREGORIAN = globalThis.document?.body?.dataset.calendar === "jalali_gregorian";
export const CURRENCY_LABEL = CURRENCY_UNIT === "toman" ? "تومان" : "ریال";
