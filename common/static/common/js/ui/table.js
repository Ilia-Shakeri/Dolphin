import {toPersianDigits} from "dolphin/core/digits.js";
import {STATUS_ACCENTS} from "dolphin/core/labels.js";
import {money} from "dolphin/core/money.js";

export function appendCell(row, value) {
    const cell = document.createElement("td");
    cell.textContent = value === null || value === undefined || value === "" ? "—" : String(value);
    row.appendChild(cell);
    return cell;
}

/**
 * The row's way into its record (2.40.38): a disclosure chevron at the row's
 * end, and the whole row clicks through to it (`setupRowLinks`). Its name is
 * still «جزئیات» for a screen reader and a keyboard.
 */
export function appendDetailLink(row, href) {
    const cell = document.createElement("td");
    cell.className = "text-end";
    const link = document.createElement("a");
    link.className = "btn btn-icon row-detail-link";
    link.href = href;
    link.setAttribute("aria-label", "جزئیات");
    link.title = "جزئیات";
    // `di-left` draws pointing right in the RTL icon sheet (2.40.39, owner:
    // «تمامی دکمه‌های < را با > عوض کن و برعکس»).
    const icon = document.createElement("i");
    icon.className = "di-outline di-left";
    icon.setAttribute("aria-hidden", "true");
    link.appendChild(icon);
    cell.appendChild(link);
    row.appendChild(cell);
    row.classList.add("is-row-link");
}

const INTERACTIVE = "a, button, input, select, textarea, label, summary, [role=button], .form-check, .dropdown-menu";

/**
 * A click anywhere on a row with a record link opens that record (2.40.38) —
 * not on the row's own controls, not while text is being selected, and in a
 * new tab with Ctrl/⌘ or the middle button, as a link would.
 */
export function setupRowLinks() {
    const open = (event) => {
        const row = event.target.closest?.("tbody > tr.is-row-link");
        if (!row || event.target.closest(INTERACTIVE)) return;
        const link = row.querySelector("a.row-detail-link");
        if (!link || window.getSelection()?.toString()) return;
        if (event.ctrlKey || event.metaKey || event.button === 1) window.open(link.href, "_blank", "noopener");
        else link.click();
    };
    document.addEventListener("click", open);
    document.addEventListener("auxclick", (event) => { if (event.button === 1) open(event); });
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
