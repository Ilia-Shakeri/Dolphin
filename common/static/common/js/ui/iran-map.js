/**
 * The customer province map (product-owner request 2026-09-09): a
 * choropleth of Iran's thirty-one provinces, each shaded by how many of
 * this reader's customers sit in it, naming the province and its count on
 * hover.
 *
 * Drawn as plain inline SVG from a vendored path file rather than with a
 * mapping library. The purchased theme's own map widget
 * (`src/js/widgets/maps/widget-1.js`) uses amCharts 5, which this
 * deployment cannot have: amCharts and its geodata are served from the
 * vendor's own content-delivery host, and nothing in this panel is
 * fetched from an external origin — the base layout links none at all,
 * and
 * the runbook's offline install has no route to one. The geometry instead comes from Natural
 * Earth's public-domain admin-1 layer, projected once at build time into
 * `common/static/common/iran-provinces.json` (see the note in this
 * release's CHANGELOG for how that file is regenerated).
 *
 * The scale is five steps of the theme's own primary colour rather than a
 * continuous ramp: five bands are readable side by side and comparable
 * against the legend, which a continuous ramp is not.
 */
const IRAN_MAP_URL = document.body?.dataset.iranMapUrl || "";
let iranMapPromise = null;

export function loadIranMap() {
    if (!iranMapPromise) {
        iranMapPromise = fetch(IRAN_MAP_URL, {credentials: "same-origin"}).then((response) => {
            if (!response.ok) throw new Error("نقشه بارگذاری نشد.");
            return response.json();
        });
    }
    return iranMapPromise;
}

/**
 * Fills a customer form's province `<select>` with the same 31 province
 * names the choropleth map itself reads from `iran-provinces.json` — the
 * one already-canonical list this codebase has, rather than a second,
 * hand-typed one that could drift from it.
 *
 * A free-text «استان» used to mean a customer whose typed province did
 * not exactly match a map region (a typo, an abbreviation, "تهرون")
 * simply never appeared on the map at all — nothing on screen said why
 * (product-owner request 2026-09-12). A fixed list of the map's own
 * names makes every new customer matchable by construction.
 *
 * `selectedValue` may not be one of the 31 — an existing customer
 * recorded before this dropdown existed. That value is kept as an extra
 * option rather than silently dropped: opening the edit form must never
 * rewrite a stored record just by loading it (`common/dashboard.py` and
 * this file both follow that rule already for other fields).
 */
export async function fillProvinceSelect(select, selectedValue = "", {placeholder: placeholderText = "انتخاب استان"} = {}) {
    if (!select) return;
    let map;
    try {
        map = await loadIranMap();
    } catch {
        // The province list and the map on the customers page read the
        // same vendored file, so if it cannot be fetched neither can be
        // built. Returning silently left an empty dropdown that looked
        // like a province list with no provinces in it — and on the
        // creation form, a required-looking field nobody could fill. Say
        // so instead, and leave the control disabled rather than
        // pretending it is usable.
        select.replaceChildren();
        const failed = document.createElement("option");
        failed.value = "";
        failed.textContent = "فهرست استان‌ها در دسترس نیست";
        select.appendChild(failed);
        select.disabled = true;
        return;
    }
    select.disabled = false;
    const names = Object.values(map.provinces)
        .map((province) => province.name)
        .sort((a, b) => a.localeCompare(b, "fa"));
    select.replaceChildren();
    // A form asks a person to choose one; a filter asks which subset to
    // show, and its empty option means "all of them". Same list, same
    // source, different sentence for the same blank value. A checklist of
    // provinces (`placeholder: null`) has no empty option: ticking none is
    // "all" there.
    if (placeholderText !== null) {
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = placeholderText;
        select.appendChild(placeholder);
    }
    names.forEach((name) => {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        select.appendChild(option);
    });
    if (selectedValue && !names.includes(selectedValue)) {
        const legacy = document.createElement("option");
        legacy.value = selectedValue;
        legacy.textContent = `${selectedValue} (مقدار قبلی)`;
        select.appendChild(legacy);
    }
    select.value = selectedValue || "";
}
