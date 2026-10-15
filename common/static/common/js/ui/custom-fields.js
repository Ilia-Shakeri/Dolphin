import {setupDecimalInputs} from "dolphin/core/decimal.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDate, displayDay} from "dolphin/core/jalali.js";
import {setupJalaliInputs} from "dolphin/ui/jalali-picker.js";

/**
 * The company's own fields on a record (2.40.53, feature `customization`).
 *
 * A page that offers them embeds the entity's active definitions with
 * `json_script` as `#custom-field-definitions`; this module draws their
 * inputs into a form, reads them back as `{key: text}` — the form the server
 * stores — and formats a stored value for a list or a profile. Every rule
 * about what a value may be is `customization.services`; this only asks.
 */
export function customFieldDefinitions(id = "custom-field-definitions") {
    const node = document.getElementById(id);
    if (!node) return [];
    try {
        return JSON.parse(node.textContent) || [];
    } catch {
        return [];
    }
}

/** A stored value as the panel shows it; «—» for none. */
export function formatCustomValue(definition, value) {
    if (value === undefined || value === null || value === "") return "—";
    if (definition.field_type === "boolean") return value === "true" ? "بله" : "خیر";
    if (definition.field_type === "date") return displayDay(value);
    if (definition.field_type === "number") return toPersianDigits(String(value));
    return String(value);
}

function inputFor(definition, id, value) {
    let field;
    if (definition.field_type === "long_text") {
        field = document.createElement("textarea");
        field.className = "form-control form-control-solid";
        field.rows = 2;
        field.maxLength = 4000;
        field.value = value || "";
    } else if (definition.field_type === "choice") {
        field = document.createElement("select");
        field.className = "form-select form-select-solid";
        field.append(new Option("انتخاب کنید", ""));
        definition.choices.forEach((choice) => field.append(new Option(choice, choice)));
        field.value = value || "";
    } else if (definition.field_type === "boolean") {
        field = document.createElement("select");
        field.className = "form-select form-select-solid";
        field.append(new Option("—", ""), new Option("بله", "true"), new Option("خیر", "false"));
        field.value = value || "";
    } else {
        field = document.createElement("input");
        field.className = "form-control form-control-solid";
        field.type = "text";
        if (definition.field_type === "number") {
            field.inputMode = "decimal";
            field.dir = "ltr";
            field.dataset.decimalInput = "";
            field.dataset.decimalPlaces = "4";
            field.value = value || "";
        } else if (definition.field_type === "date") {
            field.dataset.jalali = "date";
            field.autocomplete = "off";
            field.value = value ? displayDay(value, {gregorian: false}) : "";
        } else {
            field.maxLength = 500;
            field.value = value || "";
        }
    }
    field.id = id;
    field.dataset.customField = definition.key;
    if (definition.required) field.required = true;
    return field;
}

/**
 * Draw one input per definition into `container` (a `.row`), filled from
 * `values`. `prefix` keeps the ids of two forms on one page apart.
 */
export function renderCustomFieldInputs(container, definitions, values = {}, {prefix = "custom-field"} = {}) {
    if (!container) return;
    container.replaceChildren(...definitions.map((definition) => {
        const column = document.createElement("div");
        column.className = definition.field_type === "long_text" ? "col-12" : "col-md-6";
        const id = `${prefix}-${definition.key}`;
        const label = document.createElement("label");
        label.className = `form-label fw-semibold${definition.required ? " required" : ""}`;
        label.setAttribute("for", id);
        label.textContent = definition.label;
        column.append(label, inputFor(definition, id, values?.[definition.key]));
        return column;
    }));
    container.hidden = !definitions.length;
    setupDecimalInputs(container);
    setupJalaliInputs(container);
}

/** `{key: text}` from the inputs `renderCustomFieldInputs` drew; empty is `""`. */
export function readCustomFieldInputs(container) {
    const values = {};
    container?.querySelectorAll("[data-custom-field]").forEach((field) => {
        const raw = field.value.trim();
        values[field.dataset.customField] = field.dataset.jalali === "date" ? (raw ? apiDate(raw) || raw : "") : raw;
    });
    return values;
}

/** Review rows for a wizard (`renderWizardReview`): `[[label, text]]`. */
export function customFieldReview(definitions, values) {
    return definitions.map((definition) => [definition.label, formatCustomValue(definition, values[definition.key])]);
}
