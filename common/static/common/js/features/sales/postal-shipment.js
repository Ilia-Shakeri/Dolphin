import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {errorReason} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";

/*
 * The Iran Post shipment card on a sales document (2.29.0; a module of the
 * page since 2.40.42 — it was a separate classic script before).
 *
 * Talks only to /api/v1/sales-documents/<id>/shipment-*; the server owns every
 * rule (limits, place matching, status mapping). This shows what the API
 * returns and sends what the operator typed. A refusal keeps the server's own
 * reason (a city the post could not match, a weight over its limit): that is
 * the one thing the operator needs to fix it.
 */

const PLACES = "/api/v1/sales-documents/shipping-places/";

function byId(id) {
    return document.getElementById(id);
}

function addOption(select, value, label) {
    const node = document.createElement("option");
    node.value = value;
    node.textContent = label;
    select.appendChild(node);
}

function say(message, ok = false) {
    const box = byId("shipment-message");
    box.textContent = message || "";
    box.hidden = !message;
    box.className = `alert ${ok ? "alert-success" : "alert-danger"} py-3 mb-5`;
}

function termsPayload() {
    const payload = {
        weight_grams: Number(byId("shipment-weight").value),
        service_type: Number(byId("shipment-service").value),
        pay_type: Number(byId("shipment-pay").value),
    };
    if (byId("shipment-city").value) payload.city_id = Number(byId("shipment-city").value);
    return payload;
}

function fillFacts(shipment) {
    const rows = [
        ["بارکد رهگیری", shipment.parcel_code || "—", true],
        ["شناسهٔ مرسوله", shipment.shenase || "—", true],
        ["نوع سرویس", shipment.service_type_display, false],
        ["نوع پرداخت", shipment.pay_type_display, false],
        ["وزن", `${toPersianDigits(shipment.weight_grams)} گرم`, false],
        ["ارزش کالا", money(shipment.goods_price_rial), false],
        ["هزینهٔ پست", money(shipment.shipping_cost_rial), false],
        ["مالیات پست", money(shipment.shipping_tax_rial), false],
    ];
    byId("shipment-facts").replaceChildren(...rows.map(([label, value, ltr]) => {
        const line = document.createElement("div");
        line.className = "d-flex flex-wrap justify-content-between py-2 border-bottom border-gray-200";
        const name = document.createElement("span");
        name.className = "text-gray-600";
        name.textContent = label;
        const shown = document.createElement("span");
        shown.className = "fw-semibold text-gray-900";
        shown.textContent = value;
        if (ltr) shown.dir = "ltr";
        line.append(name, shown);
        return line;
    }));
    byId("shipment-status").textContent = shipment.status_display;
    byId("shipment-synced").textContent = shipment.last_synced_at
        ? new Date(shipment.last_synced_at).toLocaleString("fa-IR") : "هنوز از پست پرسیده نشده";
}

function render(payload) {
    const active = payload.results.find((row) => !row.is_cancelled);
    const registered = Boolean(active && active.parcel_code);
    byId("shipment-loading").hidden = true;
    byId("shipment-not-connected").hidden = payload.connected;
    byId("shipment-form").hidden = !payload.connected || registered;
    byId("shipment-active").hidden = !registered;
    if (registered) fillFacts(active);
    if (!byId("shipment-service").options.length) {
        payload.service_types.forEach((row) => addOption(byId("shipment-service"), row.value, row.label));
        payload.pay_types.forEach((row) => addOption(byId("shipment-pay"), row.value, row.label));
        byId("shipment-service").value = "1";
        byId("shipment-pay").value = "1";
    }
    const cancelled = payload.results.filter((row) => row.is_cancelled).length;
    const note = byId("shipment-cancelled-note");
    note.hidden = !cancelled;
    if (cancelled) note.textContent = `${toPersianDigits(cancelled)} مرسولهٔ لغوشده هم برای این سند ثبت شده است.`;
}

/** The shipment card, when the page has one (`sales_documents/detail.html`). */
export function setupPostalShipment() {
    const root = byId("postal-shipment-card");
    if (!root) return;
    const base = `/api/v1/sales-documents/${root.dataset.documentId}/`;

    async function reload() {
        try {
            render(await apiRequest(`${base}shipments/`));
        } catch (error) {
            byId("shipment-loading").hidden = true;
            say(errorReason(error));
        }
    }

    async function busy(button, work) {
        button.disabled = true;
        say("");
        try {
            await work();
        } catch (error) {
            say(errorReason(error));
        } finally {
            button.disabled = false;
        }
    }

    byId("shipment-pick-city").addEventListener("click", (event) => busy(event.currentTarget, async () => {
        byId("shipment-city-picker").hidden = false;
        const select = byId("shipment-province");
        if (select.options.length > 1) return;
        const data = await apiRequest(PLACES);
        data.results.forEach((row) => addOption(select, row.Code, row.pName));
    }));

    byId("shipment-province").addEventListener("change", async (event) => {
        const city = byId("shipment-city");
        city.replaceChildren();
        addOption(city, "", "خودکار از نشانی سند");
        if (!event.target.value) return;
        try {
            const data = await apiRequest(`${PLACES}?province=${encodeURIComponent(event.target.value)}`);
            data.results.forEach((row) => addOption(city, row.CityID, row.pName));
        } catch (error) {
            say(errorReason(error));
        }
    });

    byId("shipment-quote").addEventListener("click", (event) => busy(event.currentTarget, async () => {
        const result = await apiRequest(`${base}shipment-quote/`, {method: "POST", body: termsPayload()});
        const out = byId("shipment-quote-result");
        out.hidden = false;
        out.textContent = `هزینهٔ پست: ${money(result.shipping_cost)} — مالیات: ${money(result.shipping_tax)}`
            + ` — هزینهٔ مرجوعی: ${money(result.return_shipping_cost)}`;
    }));

    byId("shipment-form").addEventListener("submit", (event) => {
        event.preventDefault();
        busy(byId("shipment-submit"), async () => {
            const body = termsPayload();
            const email = byId("shipment-email").value.trim();
            if (email) body.recipient_email = email;
            await apiRequest(`${base}shipment-create/`, {method: "POST", body});
            say("مرسوله در پست ثبت شد و بارکد رهگیری دریافت شد.", true);
            await reload();
        });
    });

    byId("shipment-refresh").addEventListener("click", (event) => busy(event.currentTarget, async () => {
        await apiRequest(`${base}shipment-refresh/`, {method: "POST"});
        say("وضعیت از پست دریافت شد.", true);
        await reload();
    }));

    byId("shipment-ready").addEventListener("click", (event) => busy(event.currentTarget, async () => {
        await apiRequest(`${base}shipment-change/`, {method: "POST", body: {action: "ready"}});
        say("مرسوله «آمادهٔ ارسال» شد.", true);
        await reload();
    }));

    byId("shipment-cancel").addEventListener("click", (event) => busy(event.currentTarget, async () => {
        if (!(await confirmDialog("مرسولهٔ پستی لغو شود؟ این کار در سامانهٔ پست انجام می‌شود."))) return;
        await apiRequest(`${base}shipment-change/`, {method: "POST", body: {action: "cancel"}});
        say("مرسوله لغو شد.", true);
        await reload();
    }));

    reload();
}
