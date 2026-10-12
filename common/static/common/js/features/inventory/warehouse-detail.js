import {apiRequest} from "dolphin/core/api.js";
import {formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {liveRecord} from "dolphin/ui/live-record.js";
import {statusText} from "dolphin/ui/table.js";

function setSelectValue(select, value) {
    select.value = value === null || value === undefined ? "" : String(value);
}

function fillWarehouse(warehouse) {
    document.getElementById("edit-warehouse-code").value = warehouse.code;
    document.getElementById("edit-warehouse-name").value = warehouse.name;
    setSelectValue(document.getElementById("edit-warehouse-default"), String(warehouse.is_default));
    document.getElementById("edit-warehouse-address").value = warehouse.address || "";
    document.getElementById("warehouse-status").value = statusText(warehouse.is_active);
    document.getElementById("warehouse-created-by").value = warehouse.created_by_display || warehouse.created_by;
    document.getElementById("warehouse-updated-by").value = warehouse.updated_by_display || warehouse.updated_by;
    const toggle = document.getElementById("toggle-warehouse");
    if (toggle) {
        toggle.textContent = warehouse.is_active ? "غیرفعال کردن انبار" : "فعال کردن دوباره انبار";
        toggle.classList.toggle("btn-danger", warehouse.is_active);
    }
}

export async function setupWarehouseDetail() {
    const warehouseId = document.body.dataset.warehouseId;
    const endpoint = `/api/v1/warehouses/${warehouseId}/`;
    const loading = document.getElementById("warehouse-detail-loading");
    const content = document.getElementById("warehouse-detail-content");
    const dangerZone = document.getElementById("warehouse-danger-zone");
    let warehouse;
    // Live (2.40.41): the record redraws in place when it changes elsewhere.
    const show = (value) => { warehouse = value; fillWarehouse(value); settle(value); };
    const settle = liveRecord({read: () => apiRequest(endpoint), draw: show});
    try {
        show(await apiRequest(endpoint));
        loading.hidden = true;
        content.hidden = false;
        if (dangerZone) dangerZone.hidden = false;
    } catch (error) {
        loading.hidden = true;
        showError(error);
        return;
    }
    const form = document.getElementById("edit-warehouse-form");
    if (form.querySelector("button[type='submit']")) {
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const payload = formPayload(form, ["name", "address"]);
                payload.is_default = new FormData(form).get("is_default") === "true";
                show(await apiRequest(endpoint, {method: "PATCH", body: payload}));
                globalMessage("انبار ذخیره شد.", true);
            });
        });
    }
    const toggle = document.getElementById("toggle-warehouse");
    toggle?.addEventListener("click", async () => {
        const action = warehouse.is_active ? "deactivate" : "reactivate";
        const prompt = warehouse.is_active ? "این انبار غیرفعال شود؟" : "این انبار دوباره فعال شود؟";
        if (!await confirmDialog(prompt)) return;
        toggle.disabled = true;
        try {
            show(await apiRequest(`${endpoint}${action}/`, {method: "POST"}));
            globalMessage(warehouse.is_active ? "انبار فعال شد." : "انبار غیرفعال شد.", true);
        } catch (error) {
            showError(error);
        } finally {
            toggle.disabled = false;
        }
    });
}
