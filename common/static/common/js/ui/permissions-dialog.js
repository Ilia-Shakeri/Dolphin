import {apiRequest} from "dolphin/core/api.js";
import {ROLE_LABELS} from "dolphin/core/config.js";
import {errorText, globalMessage} from "dolphin/core/messages.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";

/**
 * The "Permissions" modal: view mode first, an explicit "Edit
 * Permissions" step before anything becomes editable, and the
 * delete-implies-edit-implies-read rule enforced live as the checkboxes
 * on a row are ticked — matching the server-side rule in
 * `accounts.module_permissions.validate_matrix` so nothing the UI
 * allows can ever be rejected by the save call for that reason.
 *
 * The third column, «حذف», arrived in 2.18.8 (product owner: «مدیر اصلی
 * پنل باید بتواند هر چیزی را که می‌خواهد حذف کند، ولی کاربران دیگر باید
 * مجوز بگیرند»). A Platform Admin's own row shows it ticked and locked:
 * that role deletes regardless (`accounts.access.can_delete`).
 */
export function setupPermissionsDialog() {
    const dialog = document.getElementById("permissions-dialog");
    if (!dialog || dialog.dataset.ready) return;
    dialog.dataset.ready = "true";
    // Lifted to <body> (2.40.32). On a profile it is rendered inside the
    // «دسترسی‌ها» tab's pane; a modal <dialog> whose ancestor is `hidden`
    // still makes the whole page inert but draws nothing — the panel looks
    // frozen with no dialog on screen. At the body it shows wherever it is
    // opened from.
    if (dialog.parentElement !== document.body) document.body.append(dialog);
    const loading = document.getElementById("permissions-loading");
    const body = document.getElementById("permissions-body");
    const errorBox = document.getElementById("permissions-error");
    const tableBody = document.getElementById("permissions-table-body");
    const customNote = document.getElementById("permissions-custom-note");
    const nameField = document.getElementById("permissions-user-name");
    const roleField = document.getElementById("permissions-user-role");
    const editButton = document.getElementById("permissions-edit");
    const saveButton = document.getElementById("permissions-save");
    const cancelEditButton = document.getElementById("permissions-cancel-edit");
    const resetButton = document.getElementById("permissions-reset");

    let userId = null;
    let current = null; // last server-confirmed {role, matrix, has_custom_permissions}
    let editing = false;

    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => {
        button.addEventListener("click", () => dialog.close());
    });

    function showError(message) {
        errorBox.textContent = message;
        errorBox.hidden = false;
    }

    function renderRows() {
        const rows = Object.entries(current.matrix).map(([key, entry]) => {
            const row = document.createElement("tr");

            const labelCell = document.createElement("td");
            labelCell.textContent = entry.is_custom ? `${entry.label} *` : entry.label;
            row.appendChild(labelCell);

            const readCell = document.createElement("td");
            readCell.className = "text-center";
            const readInput = document.createElement("input");
            readInput.type = "checkbox";
            readInput.className = "form-check-input";
            readInput.checked = entry.read;
            readInput.disabled = !editing;
            readInput.dataset.module = key;
            readInput.dataset.axis = "read";
            readInput.setAttribute("aria-label", `خواندن — ${entry.label}`);
            readCell.appendChild(readInput);
            row.appendChild(readCell);

            const writeCell = document.createElement("td");
            writeCell.className = "text-center";
            if (entry.supports_write) {
                const writeInput = document.createElement("input");
                writeInput.type = "checkbox";
                writeInput.className = "form-check-input";
                writeInput.checked = entry.write;
                writeInput.disabled = !editing;
                writeInput.dataset.module = key;
                writeInput.dataset.axis = "write";
                writeInput.setAttribute("aria-label", `ویرایش — ${entry.label}`);
                writeCell.appendChild(writeInput);
            } else {
                writeCell.textContent = "—";
            }
            row.appendChild(writeCell);

            const deleteCell = document.createElement("td");
            deleteCell.className = "text-center";
            if (entry.supports_delete) {
                const deleteInput = document.createElement("input");
                deleteInput.type = "checkbox";
                deleteInput.className = "form-check-input";
                deleteInput.checked = entry.delete;
                deleteInput.disabled = !editing || entry.delete_locked;
                deleteInput.dataset.module = key;
                deleteInput.dataset.axis = "delete";
                deleteInput.setAttribute("aria-label", `حذف — ${entry.label}`);
                if (entry.delete_locked) deleteInput.title = "مدیر پلتفرم همیشه می‌تواند حذف کند.";
                deleteCell.appendChild(deleteInput);
            } else {
                deleteCell.textContent = "—";
            }
            row.appendChild(deleteCell);
            return row;
        });
        tableBody.replaceChildren(...rows);
    }

    function render() {
        nameField.textContent = dialog.dataset.userName || "";
        roleField.textContent = ROLE_LABELS[current.role] || current.role;
        customNote.hidden = !current.has_custom_permissions;
        editButton.hidden = editing;
        saveButton.hidden = !editing;
        cancelEditButton.hidden = !editing;
        renderRows();
    }

    // Delete implies Edit implies Read; unchecking a lower right turns
    // the ones above it off too — the same rule the server enforces,
    // applied live so the checkboxes never sit in a state the save call
    // would reject.
    tableBody.addEventListener("change", (event) => {
        const input = event.target.closest('input[type="checkbox"]');
        if (!input) return;
        const moduleKey = input.dataset.module;
        const readInput = tableBody.querySelector(`input[data-module="${moduleKey}"][data-axis="read"]`);
        const writeInput = tableBody.querySelector(`input[data-module="${moduleKey}"][data-axis="write"]`);
        const deleteInput = tableBody.querySelector(`input[data-module="${moduleKey}"][data-axis="delete"]`);
        const axis = input.dataset.axis;
        if (input.checked) {
            if (axis === "delete" && writeInput) writeInput.checked = true;
            if ((axis === "delete" || axis === "write") && readInput) readInput.checked = true;
        } else {
            if (axis === "read" && writeInput) writeInput.checked = false;
            if ((axis === "read" || axis === "write") && deleteInput && !deleteInput.disabled) deleteInput.checked = false;
        }
    });

    function collectMatrix() {
        const matrix = {};
        tableBody.querySelectorAll("tr").forEach((row) => {
            const readInput = row.querySelector('input[data-axis="read"]');
            const writeInput = row.querySelector('input[data-axis="write"]');
            const deleteInput = row.querySelector('input[data-axis="delete"]');
            if (!readInput) return;
            matrix[readInput.dataset.module] = {
                read: readInput.checked,
                write: writeInput ? writeInput.checked : false,
                delete: deleteInput ? deleteInput.checked : false,
            };
        });
        return matrix;
    }

    async function load() {
        loading.hidden = false;
        body.hidden = true;
        errorBox.hidden = true;
        editing = false;
        // A request that never answers left «در حال دریافت…» on screen for
        // good; after 20 seconds it is abandoned with a message instead.
        const timeout = new AbortController();
        const timer = setTimeout(() => timeout.abort(), 20000);
        try {
            current = await apiRequest(`/api/v1/users/${userId}/permissions/`, {signal: timeout.signal});
            loading.hidden = true;
            body.hidden = false;
            render();
        } catch (error) {
            loading.hidden = true;
            showError(error?.name === "AbortError"
                ? "پاسخی از سرور نرسید. پنجره را ببندید و دوباره امتحان کنید."
                : errorText(error));
        } finally {
            clearTimeout(timer);
        }
    }

    editButton.addEventListener("click", () => {
        editing = true;
        render();
    });

    cancelEditButton.addEventListener("click", () => {
        editing = false;
        render();
    });

    saveButton.addEventListener("click", async () => {
        errorBox.hidden = true;
        saveButton.disabled = true;
        try {
            current = await apiRequest(`/api/v1/users/${userId}/permissions/`, {
                method: "PATCH",
                body: {matrix: collectMatrix()},
            });
            editing = false;
            render();
            globalMessage("مجوزهای کاربر ذخیره شد.", true);
        } catch (error) {
            showError(errorText(error));
        } finally {
            saveButton.disabled = false;
        }
    });

    resetButton.addEventListener("click", async () => {
        if (!await confirmDialog("مجوزهای اختصاصی این کاربر حذف و به پیش‌فرض نقشش بازگردانده شود؟")) return;
        resetButton.disabled = true;
        try {
            current = await apiRequest(`/api/v1/users/${userId}/permissions/reset/`, {method: "POST", body: {}});
            editing = false;
            render();
            globalMessage("مجوزهای کاربر به پیش‌فرض نقش بازنشانی شد.", true);
        } catch (error) {
            showError(errorText(error));
        } finally {
            resetButton.disabled = false;
        }
    });

    permissionsDialogOpener = (id, name) => {
        userId = id;
        dialog.dataset.userName = name;
        dialog.showModal();
        load();
    };
}

let permissionsDialogOpener = null;

export function openPermissionsDialog(id, name) {
    if (permissionsDialogOpener) permissionsDialogOpener(id, name);
}
