import {apiRequest} from "dolphin/core/api.js";

//: The two real `sales.Sale.Status` values, as the map `statusBadge`
//: reads. Both keys are already in `STATUS_ACCENTS` (confirmed → success,
//: cancelled → danger), so the colour agrees with the same two words
//: everywhere else in the panel rather than being chosen again here.
export const SALE_STATUS_TEXT = Object.freeze({
    confirmed: "تأییدشده",
    cancelled: "لغوشده",
});

/**
 * Fill a `<select>` with the postal vocabulary.
 *
 * Two forms offer it — registering a document and moving one along — and
 * both read it from the server rather than from a list here, so
 * `sales/postal.py` stays the one declaration. A failed fetch leaves the
 * selector empty, which `required` then refuses to submit: better than
 * sending a state nobody defined.
 */
export async function fillPostalStates(select, {emptyLabel = null} = {}) {
    if (!select || select.tagName !== "SELECT") return;
    const states = await loadPostalStates();
    // Two groups (2.40.26): the four stages a parcel moves through, then every
    // status Iran Post itself reports. A checklist (`multiple`) shows them as
    // one list; `<optgroup>` keeps them apart in a dropdown.
    const options = [];
    if (emptyLabel !== null) options.push(new Option(emptyLabel, ""));
    [["stage", "مراحل ارسال"], ["carrier", "وضعیت‌های پست"]].forEach(([group, label]) => {
        const rows = states.filter((state) => (state.group || "stage") === group);
        if (!rows.length) return;
        const items = rows.map((state) => new Option(state.label, state.key));
        if (select.multiple) {
            options.push(...items);
        } else {
            const optgroup = document.createElement("optgroup");
            optgroup.label = label;
            optgroup.append(...items);
            options.push(optgroup);
        }
    });
    select.replaceChildren(...options);
}

/**
 * A postal status as a small badge with its own icon (2.40.26) — the
 * `postal_badge` the server sends: `{label, icon, icon_paths, tone}`.
 */
export function postalBadge(badge) {
    if (!badge) return null;
    const node = document.createElement("span");
    node.className = `badge badge-light-${badge.tone || "primary"} postal-badge`;
    const icon = document.createElement("i");
    icon.className = `di-duotone ${badge.icon} fs-6`;
    icon.setAttribute("aria-hidden", "true");
    for (let path = 1; path <= (badge.icon_paths || 2); path += 1) {
        icon.appendChild(document.createElement("span")).className = `path${path}`;
    }
    const text = document.createElement("span");
    text.textContent = badge.label;
    node.append(icon, text);
    return node;
}

//: The vocabulary, fetched at most once per page. Three surfaces want it
//: — two selectors and the parcels report's own status column — and
//: three requests for a four-row constant is three too many.
let postalStatesPromise = null;
export const postalStateLabels = new Map();

function loadPostalStates() {
    postalStatesPromise ??= apiRequest("/api/v1/sales-documents/postal-states/")
        .then((data) => {
            data.results.forEach((state) => postalStateLabels.set(state.key, state.label));
            return data.results;
        })
        .catch((error) => {
            // Not cached as a rejection: a failed fetch should not make
            // every later caller on the page fail too.
            postalStatesPromise = null;
            throw error;
        });
    return postalStatesPromise;
}
