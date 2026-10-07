import {apiRequest} from "dolphin/core/api.js";
import {ROLE_LABELS} from "dolphin/core/config.js";
import {displayDate} from "dolphin/core/jalali.js";
import {showError} from "dolphin/core/messages.js";

export async function setupActivityLogDetail() {
    const id = document.body.dataset.activityLogId;
    const loading = document.getElementById("activity-log-detail-loading");
    const content = document.getElementById("activity-log-detail-content");
    try {
        const item = await apiRequest(`/api/v1/activity-logs/${id}/`);
        document.getElementById("activity-operation").value = item.operation_display || item.operation;
        document.getElementById("activity-object-type").value = item.object_type_display || item.object_type;
        document.getElementById("activity-object-id").value = item.object_id || "";
        document.getElementById("activity-actor").value = item.actor || "";
        document.getElementById("activity-actor-role").value = ROLE_LABELS[item.actor_role_snapshot] || item.actor_role_snapshot;
        document.getElementById("activity-object-role").value = ROLE_LABELS[item.object_role_snapshot] || item.object_role_snapshot;
        document.getElementById("activity-request-id").value = item.request_id || "";
        document.getElementById("activity-ip").value = item.ip_address || "";
        document.getElementById("activity-created-at").value = displayDate(item.created_at);
        document.getElementById("activity-changes").textContent = JSON.stringify(item.safe_changes, null, 2);
        loading.hidden = true;
        content.hidden = false;
    } catch (error) {
        loading.hidden = true;
        showError(error);
    }
}
