/**
 * «حقیقی» / «حقوقی» with their icon (2.40.8) — the JavaScript twin of the
 * `{% customer_kind %}` template tag (`common/templatetags/customer_kind_tags.py`),
 * and the one label table on this side. The icon is `1em` in `currentColor`
 * (`.customer-kind` in dolphin.css) and decorative: the word is beside it.
 */

const KINDS = {
    individual: {label: "حقیقی", icon: "di-profile-circle", paths: 3},
    legal: {label: "حقوقی", icon: "di-bank", paths: 2},
};

/** The plain word, for a place an icon cannot go. */
export function customerKindLabel(kind) {
    return KINDS[kind]?.label || "";
}

/** The icon and the word, as one inline element; `null` for an unknown kind. */
export function customerKindBadge(kind) {
    const entry = KINDS[kind];
    if (!entry) return null;
    const badge = document.createElement("span");
    badge.className = "customer-kind";
    badge.dataset.customerKindBadge = kind;
    const icon = document.createElement("i");
    icon.className = `di-duotone ${entry.icon} customer-kind-icon`;
    icon.setAttribute("aria-hidden", "true");
    for (let path = 1; path <= entry.paths; path += 1) {
        const span = document.createElement("span");
        span.className = `path${path}`;
        icon.append(span);
    }
    const text = document.createElement("span");
    text.textContent = entry.label;
    badge.append(icon, text);
    return badge;
}
