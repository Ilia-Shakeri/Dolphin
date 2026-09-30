import {apiRequest} from "dolphin/core/api.js";
import {DOCUMENT_STATUS_TEXT} from "dolphin/core/labels.js";
import {clearMessages, globalMessage, showError} from "dolphin/core/messages.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {labelled} from "dolphin/ui/table.js";

function bindTransitions(attribute, endpoint, apply) {
    document.querySelectorAll(`[data-${attribute}-transition]`).forEach((button) => {
        button.addEventListener("click", async () => {
            const target = button.dataset[`${attribute}Transition`];
            if (!await confirmDialog(`وضعیت سند به «${labelled(DOCUMENT_STATUS_TEXT, target)}» تغییر کند؟`)) return;
            button.disabled = true;
            clearMessages();
            try {
                const updated = await apiRequest(`${endpoint}transition/`, {
                    method: "POST",
                    body: {to_status: target},
                });
                globalMessage("وضعیت سند ثبت شد.", true);
                apply(updated);
            } catch (error) {
                showError(error);
            } finally {
                button.disabled = false;
            }
        });
    });
}
