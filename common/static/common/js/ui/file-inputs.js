/**
 * File fields in Persian (2.40.36).
 *
 * The browser draws a file field's button and its "no file" text in its own
 * language — «Choose File / No file chosen» on an English system, on a Persian
 * page. Each `input[type=file].form-control` keeps working exactly as before
 * (same element, same form, same name, still focusable and announced), but is
 * drawn as a field of the UI kit: a «انتخاب فایل» button and the chosen file's
 * name. The input moves inside its new label, so a click anywhere on it opens
 * the file picker.
 */

const NOTHING_CHOSEN = "فایلی انتخاب نشده است";

function chosenText(input) {
    const files = input.files ? Array.from(input.files) : [];
    if (!files.length) return NOTHING_CHOSEN;
    return files.length === 1 ? files[0].name : `${files.length.toLocaleString("fa-IR")} فایل`;
}

function enhance(input) {
    input.dataset.fileReady = "";
    const field = document.createElement("label");
    field.className = `${input.className} dolphin-file`;
    // Size limits such as an inline max-width belong to the visible field now.
    if (input.getAttribute("style")) field.setAttribute("style", input.getAttribute("style"));
    const button = document.createElement("span");
    button.className = "btn btn-sm btn-light-primary dolphin-file-button";
    button.textContent = "انتخاب فایل";
    const name = document.createElement("span");
    name.className = "dolphin-file-name";
    name.setAttribute("aria-hidden", "true");
    input.before(field);
    input.className = "dolphin-file-input";
    input.removeAttribute("style");
    field.append(input, button, name);
    const update = () => {
        name.textContent = chosenText(input);
        field.classList.toggle("has-file", Boolean(input.files && input.files.length));
    };
    input.addEventListener("change", update);
    input.form?.addEventListener("reset", () => setTimeout(update));
    update();
}

export function setupFileInputs(root = document) {
    root.querySelectorAll('input[type="file"].form-control:not([data-file-ready])').forEach(enhance);
}
