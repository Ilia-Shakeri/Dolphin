import {apiRequest} from "dolphin/core/api.js";
import {displayDate} from "dolphin/core/jalali.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {loadAllPages} from "dolphin/ui/lists.js";

/**
 * The «کمپین فاکتور» card on an invoice (2.36.0): which campaign a valid
 * invoice counts for, how that was decided, and — for someone holding
 * `campaigns.attribute` — a way to correct it with a reason. Only the link to a
 * campaign changes; the invoice is never touched. The server re-checks the
 * capability, the invoice's status and the reason.
 */
export async function setupInvoiceCampaign(invoiceId, status) {
    const card = document.getElementById("invoice-campaign");
    if (!card) return;
    const current = card.querySelector("[data-campaign-current]");
    const history = card.querySelector("[data-campaign-history]");
    const form = card.querySelector("[data-campaign-form]");
    const select = form?.elements.campaign;

    async function refresh() {
        const log = await apiRequest(`/api/v1/campaigns/attribution-log/?invoice=${invoiceId}`);
        const latest = log.results[0];
        current.textContent = latest?.to
            ? `${latest.to} (${latest.source === "manual" ? "دستی" : "خودکار"})`
            : "به هیچ کمپینی نسبت داده نشده است.";
        history.replaceChildren(...log.results.map((entry) => {
            const item = document.createElement("li");
            item.textContent = `${displayDate(entry.at)} — ${entry.from || "—"} ← ${entry.to || "—"}${entry.actor ? ` (${entry.actor})` : ""}${entry.reason ? `: ${entry.reason}` : ""}`;
            return item;
        }));
    }

    try {
        await refresh();
        card.hidden = false;
        if (form) {
            const campaigns = await loadAllPages("/api/v1/campaigns/");
            select.replaceChildren(new Option("انتخاب کمپین", ""), ...campaigns.map((campaign) => new Option(campaign.name, String(campaign.id))));
            // Only a valid (issued) invoice counts for a campaign.
            form.hidden = status !== "issued";
            form.addEventListener("submit", (event) => {
                event.preventDefault();
                withSubmit(form, async () => {
                    clearMessages(form);
                    await apiRequest("/api/v1/campaigns/attribute-invoice/", {
                        method: "POST",
                        body: {invoice: Number(invoiceId), campaign: Number(select.value), reason: form.elements.reason.value},
                    });
                    form.reset();
                    globalMessage("کمپین فاکتور تغییر کرد.", true);
                    await refresh();
                });
            });
        }
    } catch (error) {
        // A deployment or role without campaigns simply has no card.
        if (error?.status && error.status !== 403 && error.status !== 404) showError(error);
    }
}
