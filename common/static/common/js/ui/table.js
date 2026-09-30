import {toPersianDigits} from "dolphin/core/digits.js";
import {STATUS_ACCENTS} from "dolphin/core/labels.js";
import {money} from "dolphin/core/money.js";

export function appendCell(row, value) {
    const cell = document.createElement("td");
    cell.textContent = value === null || value === undefined || value === "" ? "—" : String(value);
    row.appendChild(cell);
    return cell;
}

export function appendDetailLink(row, href) {
    const cell = document.createElement("td");
    const link = document.createElement("a");
    link.className = "btn btn-sm btn-light";
    link.href = href;
    link.textContent = "جزئیات";
    cell.appendChild(link);
    row.appendChild(cell);
}

export function statusText(active) {
    return active ? "فعال" : "غیرفعال";
}

/** An active/inactive cell as the theme's badge rather than bare text. */
export function appendStatusCell(row, active) {
    const cell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = active ? "badge badge-light-success" : "badge badge-light-danger";
    badge.textContent = statusText(active);
    cell.appendChild(badge);
    row.appendChild(cell);
    return cell;
}

export function directionText(direction) {
    return direction === "inbound" ? "ورودی" : direction === "outbound" ? "خروجی" : direction;
}

/**
 * What a pager says: which records are on screen, out of how many.
 *
 * "صفحه ۲" alone never told an operator whether they were looking at 12
 * customers or 12 of 3,400. The API already returns `count`, so the range
 * is derived rather than guessed, and a page whose size is unknown falls
 * back to the page number alone instead of inventing a range.
 */
export function pageRangeLabel(data, page, pageSize = 25) {
    const total = Number(data.count);
    if (!Number.isFinite(total)) return `صفحه ${toPersianDigits(String(page))}`;
    if (total === 0) return "بدون رکورد";
    const first = (page - 1) * pageSize + 1;
    const last = Math.min(page * pageSize, total);
    return `${toPersianDigits(String(first))} تا ${toPersianDigits(String(last))} از ${toPersianDigits(String(total))}`;
}

export function labelled(map, value) {
    return map[value] || value || "—";
}

/** A status rendered as the theme's badge, ready to append to a row. */
function statusBadge(map, value) {
    const badge = document.createElement("span");
    badge.className = `badge badge-light-${STATUS_ACCENTS[value] || "secondary"}`;
    badge.textContent = labelled(map, value);
    return badge;
}

/** Append a status cell carrying that badge. */
export function appendStatusBadgeCell(row, map, value) {
    const cell = document.createElement("td");
    cell.append(statusBadge(map, value));
    row.append(cell);
    return cell;
}

export function appendMoneyCell(row, value) {
    const cell = appendCell(row, money(value));
    cell.dir = "ltr";
    return cell;
}

export function appendActionLinks(row, links) {
    const cell = document.createElement("td");
    cell.className = "row-actions";
    links.forEach(([href, label]) => {
        const link = document.createElement("a");
        link.className = "btn btn-sm btn-light";
        link.href = href;
        link.textContent = label;
        cell.appendChild(link);
    });
    row.appendChild(cell);
    return cell;
}
