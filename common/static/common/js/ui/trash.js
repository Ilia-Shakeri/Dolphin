/**
 * Delete as a red trash icon, with motion (2.40.33, product owner: «در تمامی
 * صفحه‌هایی که اپشن حذف دارند، باید دکمهٔ قرمز حذف تبدیل به یک آیکن قرمز سطل
 * آشغال شود و برای حذف انیمیشن داشته باشد»).
 *
 * `trashButton(label)` is the one delete control: an icon-only button named
 * by `label` for assistive tech and as its tooltip. `removeWithMotion(node)`
 * plays the leaving of whatever was deleted — the row, the card, the line —
 * before it goes, and resolves when it has (at once under reduced motion).
 * Styles: `.btn-trash` and `.is-leaving` in dolphin.css.
 */
const TRASH_PATHS = 5;

export function trashIcon() {
    const icon = document.createElement("i");
    icon.className = "di-duotone di-trash fs-3";
    icon.setAttribute("aria-hidden", "true");
    for (let index = 1; index <= TRASH_PATHS; index += 1) {
        const path = document.createElement("span");
        path.className = `path${index}`;
        icon.append(path);
    }
    return icon;
}

export function trashButton(label) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-icon btn-trash";
    button.setAttribute("aria-label", label);
    button.title = label;
    button.append(trashIcon());
    return button;
}

export function removeWithMotion(node) {
    if (!node) return Promise.resolve();
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        node.remove();
        return Promise.resolve();
    }
    node.classList.add("is-leaving");
    return new Promise((resolve) => {
        setTimeout(() => {
            node.remove();
            resolve();
        }, 300);
    });
}
