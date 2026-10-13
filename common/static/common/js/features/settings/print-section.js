import {apiRequest} from "dolphin/core/api.js";
import {globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {syncSegmented} from "dolphin/ui/segmented.js";

/**
 * Settings → «قالب چاپ» (2.40.44): how this company's printed invoice looks.
 *
 * The branding page's shape: GET fills the form, a multipart POST (`raw`)
 * carries the optional images, and after a save the images and the preview
 * are read back from the server rather than assumed. The preview is the real
 * print template drawn from sample data (`/invoices/print/sample/`).
 */
const DEFAULT_ACCENT = "#087f73";
const FLAGS = ["show_warehouse", "show_payment_summary", "show_issuer"];
const IMAGES = ["logo", "stamp"];

export function setupPrintSection() {
    const form = document.getElementById("print-settings-form");
    if (!form) return;
    const loading = document.getElementById("print-settings-loading");
    const colorField = document.getElementById("print-accent-color");
    const hexField = document.getElementById("print-accent-color-hex");
    const paper = document.getElementById("print-paper-size");
    const frame = document.getElementById("print-preview-frame");

    // The picker always holds a valid colour; the text field may be empty,
    // which is what «no colour of its own» is sent as.
    colorField.addEventListener("input", () => { hexField.value = colorField.value; });
    hexField.addEventListener("input", () => {
        if (/^#[0-9a-fA-F]{6}$/.test(hexField.value)) colorField.value = hexField.value;
    });
    document.getElementById("print-accent-color-reset").addEventListener("click", () => {
        colorField.value = DEFAULT_ACCENT;
        hexField.value = "";
    });

    function showImage(name, present) {
        const preview = document.getElementById(`print-${name}-preview`);
        const empty = document.getElementById(`print-${name}-empty`);
        if (present) preview.src = `/api/v1/print-settings/${name}/?v=${Date.now()}`;
        else preview.removeAttribute("src");
        preview.classList.toggle("d-none", !present);
        empty.classList.toggle("d-none", present);
        document.getElementById(`print-remove-${name}-row`).hidden = !present;
        document.getElementById(`print-remove-${name}`).checked = false;
        document.getElementById(`print-${name}-file`).value = "";
    }

    function fill(data) {
        hexField.value = data.accent_color || "";
        colorField.value = data.accent_color || DEFAULT_ACCENT;
        document.getElementById("print-tagline").value = data.tagline || "";
        document.getElementById("print-footer-text").value = data.footer_text || "";
        paper.value = data.paper_size || "a4";
        syncSegmented(document.querySelector('[data-segmented-for="print-paper-size"]'));
        for (const flag of FLAGS) {
            document.getElementById(`print-${flag.replaceAll("_", "-")}`).checked = Boolean(data[flag]);
        }
        showImage("logo", data.has_logo);
        showImage("stamp", data.has_stamp);
    }

    async function load() {
        try {
            fill(await apiRequest("/api/v1/print-settings/"));
            loading.hidden = true;
            form.hidden = false;
        } catch (error) {
            loading.textContent = "قالب چاپ دریافت نشد.";
            showError(error);
        }
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const body = new FormData();
            body.append("accent_color", hexField.value.trim());
            body.append("tagline", document.getElementById("print-tagline").value);
            body.append("footer_text", document.getElementById("print-footer-text").value);
            body.append("paper_size", paper.value);
            for (const flag of FLAGS) {
                body.append(flag, document.getElementById(`print-${flag.replaceAll("_", "-")}`).checked ? "true" : "false");
            }
            for (const name of IMAGES) {
                const file = document.getElementById(`print-${name}-file`).files[0];
                if (file) body.append(name, file);
                if (document.getElementById(`print-remove-${name}`).checked) body.append(`remove_${name}`, "true");
            }
            try {
                fill(await apiRequest("/api/v1/print-settings/", {method: "POST", body, raw: true}));
                globalMessage("قالب چاپ ذخیره شد.", true);
                // A new address rather than reaching into the frame: it reloads
                // whether or not the browser has drawn the frame yet.
                if (frame) frame.src = `${frame.src.split("?")[0]}?v=${Date.now()}`;
            } catch (error) {
                showError(error, form);
            }
        });
    });

    load();
}
