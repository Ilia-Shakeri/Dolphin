import {toPersianDigits} from "dolphin/core/digits.js";

/** The header's #1–#3 line (`data-profile-field`), kept current after an edit. */
export function setProfileHeaderField(name, value, missingTooltip = "") {
    const node = document.querySelector(`[data-profile-field="${name}"]`);
    if (!node) return;
    const icon = node.querySelector("i");
    const label = node.querySelector(".visually-hidden");
    const labelText = label ? label.textContent : "";
    node.replaceChildren();
    if (icon) node.appendChild(icon);
    if (labelText) {
        const hidden = document.createElement("span");
        hidden.className = "visually-hidden";
        hidden.textContent = labelText;
        node.appendChild(hidden);
    }
    if (value) {
        node.append(value);
        node.removeAttribute("title");
    } else {
        node.append("—");
        if (missingTooltip) {
            node.title = missingTooltip;
            const reason = document.createElement("span");
            reason.className = "visually-hidden";
            reason.textContent = missingTooltip;
            node.appendChild(reason);
        }
    }
}

/**
 * The header's phone: a `tel:` link when there is a number, «—» with a
 * reason when there is none. Numbers arrive normalised (`+98…`) and are
 * shown the way people in Iran write them.
 */
export function setProfileHeaderPhone(number, missingTooltip) {
    const node = document.querySelector('[data-profile-field="phone"]');
    if (!node) return;
    const value = String(number || "").trim();
    const local = value.startsWith("+98") ? `0${value.slice(3)}` : value;
    const replacement = document.createElement(value ? "a" : "span");
    replacement.className = node.className.replace(" text-hover-primary", "") + (value ? " text-hover-primary" : "");
    replacement.dataset.profileField = "phone";
    const icon = node.querySelector("i");
    if (icon) replacement.appendChild(icon);
    const label = document.createElement("span");
    label.className = "visually-hidden";
    label.textContent = "تلفن: ";
    replacement.appendChild(label);
    if (value) {
        replacement.href = `tel:${value.replace(/[^\d+]/g, "")}`;
        replacement.dir = "ltr";
        replacement.title = `تماس با ${toPersianDigits(local)}`;
        replacement.append(toPersianDigits(local));
    } else {
        replacement.title = missingTooltip;
        replacement.append("—");
    }
    node.replaceWith(replacement);
    const call = document.querySelector('[data-quick-action="call"]');
    if (call && value) call.href = `tel:${value.replace(/[^\d+]/g, "")}`;
}

export function setProfileHeaderText(name, value) {
    const node = document.querySelector(`[data-profile-${name}]`);
    if (node && value) node.textContent = value;
}

export function setProfileBreadcrumb(value) {
    const node = document.querySelector(".breadcrumb > .breadcrumb-item:last-child");
    if (node && value) node.textContent = value;
    if (value) document.title = document.title.replace(/^[^|]*\|/, `${value} |`);
}

export function setProfileBadge(badge) {
    let node = document.querySelector("[data-profile-badge]");
    if (!badge) { node?.remove(); return; }
    if (!node) {
        node = document.createElement("span");
        node.dataset.profileBadge = "";
        document.querySelector("[data-profile-name]")?.after(node);
    }
    node.className = `badge badge-light-${badge.accent}`;
    node.textContent = badge.label;
}

/** An overview fact (`data-overview-field`), «—» when empty. */
export function setOverviewFact(name, value) {
    document.querySelectorAll(`[data-overview-field="${name}"]`).forEach((node) => {
        node.textContent = value ? String(value) : "—";
    });
}
