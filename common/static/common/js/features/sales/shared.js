import {apiRequest} from "dolphin/core/api.js";
import {fillSelect} from "dolphin/ui/lists.js";

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
    // `fillSelect` reads `row.id`; a state's identifier is its `key`.
    fillSelect(
        select,
        states.map((state) => ({id: state.key, ...state})),
        (state) => state.label,
        emptyLabel,
    );
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
