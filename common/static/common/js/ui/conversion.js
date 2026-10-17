import {toPersianDigits} from "dolphin/core/digits.js";

/**
 * One conversion figure as the reports show it (2.40.59, BIZ-004): the rate,
 * its numerator and denominator, and what it means — product owner: «تعریف
 * هر شاخص و صورت و مخرج آن مشخص باشد». The figure comes whole from the
 * server (`sales.conversion.figure`); nothing is computed here.
 */

const count = (value) => toPersianDigits(String(value ?? 0));

export function rateText(figure) {
    return figure?.rate === null || figure?.rate === undefined ? "—" : `${toPersianDigits(String(figure.rate))}٪`;
}

/** «۲ از ۵» — the numerator over the denominator, named. */
export function fractionText(figure) {
    if (!figure) return "";
    return `${count(figure.numerator)} ${figure.numerator_label} از ${count(figure.denominator)} ${figure.denominator_label}`;
}

/** A card for one figure: name, rate, fraction and definition. */
export function figureCard(figure, {extra = ""} = {}) {
    const column = document.createElement("div");
    column.className = "col-md-6 col-xl-4";
    const card = document.createElement("div");
    card.className = "card card-flush h-100 border border-gray-300";
    const body = document.createElement("div");
    body.className = "card-body py-5 d-flex flex-column gap-2";
    const title = document.createElement("span");
    title.className = "text-gray-700 fw-semibold fs-7";
    title.textContent = figure.label;
    const value = document.createElement("span");
    value.className = "text-gray-900 fw-bolder fs-2";
    value.textContent = rateText(figure);
    const fraction = document.createElement("span");
    fraction.className = "text-gray-800 fs-7";
    fraction.textContent = fractionText(figure) + (extra ? ` — ${extra}` : "");
    const definition = document.createElement("p");
    definition.className = "text-muted fs-8 mb-0";
    definition.textContent = figure.definition;
    body.append(title, value, fraction, definition);
    card.append(body);
    column.append(card);
    return column;
}

/** A plain count beside the rates (repeat purchases), with what it means. */
export function countCard(label, value, definition) {
    const column = figureCard({label, rate: null, definition});
    column.querySelector(".fw-bolder").textContent = count(value);
    column.querySelector(".text-gray-800").remove();
    return column;
}
