/* Iran Post shipment card on a sales document (2.29.0).
 * Talks only to /api/v1/sales-documents/<id>/shipment-*; the server owns every
 * rule (limits, place matching, status mapping). This file shows what the API
 * returns and sends what the operator typed. */
(function () {
    "use strict";
    var root = document.getElementById("postal-shipment-card");
    if (!root) return;
    var base = "/api/v1/sales-documents/" + root.dataset.documentId + "/";
    var placesBase = "/api/v1/sales-documents/shipping-places/";
    var PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
    function $(id) { return document.getElementById(id); }
    function digits(text) { return String(text).replace(/\d/g, function (d) { return PERSIAN_DIGITS[d]; }); }
    function rial(value) {
        if (value === null || value === undefined) return "—";
        return digits(Number(value).toLocaleString("en-US")).replace(/,/g, "٬") + " ریال";
    }
    function csrf() {
        var match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }
    function firstMessage(value) {
        if (!value) return "";
        if (typeof value === "string") return value;
        if (Array.isArray(value)) {
            for (var i = 0; i < value.length; i++) {
                var m = firstMessage(value[i]);
                if (m) return m;
            }
            return "";
        }
        if (typeof value === "object") {
            var keys = Object.keys(value);
            for (var j = 0; j < keys.length; j++) {
                var f = firstMessage(value[keys[j]]);
                if (f) return f;
            }
        }
        return "";
    }
    async function call(path, options) {
        options = options || {};
        var method = options.method || "GET";
        var headers = {Accept: "application/json"};
        if (method !== "GET") headers["X-CSRFToken"] = csrf();
        if (options.body !== undefined) headers["Content-Type"] = "application/json";
        var response = await fetch(path, {
            method: method, headers: headers, credentials: "same-origin",
            body: options.body === undefined ? undefined : JSON.stringify(options.body)
        });
        var data = null;
        try { data = await response.json(); } catch (_) { data = null; }
        if (!response.ok) throw new Error(firstMessage(data) || "درخواست انجام نشد. دوباره تلاش کنید.");
        return data;
    }
    function say(message, ok) {
        var box = $("shipment-message");
        box.textContent = message || "";
        box.hidden = !message;
        box.className = "alert " + (ok ? "alert-success" : "alert-danger") + " py-3 mb-5";
    }
    function option(select, value, label) {
        var node = document.createElement("option");
        node.value = value;
        node.textContent = label;
        select.appendChild(node);
    }
    function termsPayload() {
        var payload = {
            weight_grams: Number($("shipment-weight").value),
            service_type: Number($("shipment-service").value),
            pay_type: Number($("shipment-pay").value)
        };
        if ($("shipment-city").value) payload.city_id = Number($("shipment-city").value);
        return payload;
    }
    function fillFacts(shipment) {
        var rows = [
            ["بارکد رهگیری", shipment.parcel_code || "—", true],
            ["شناسهٔ مرسوله", shipment.shenase || "—", true],
            ["نوع سرویس", shipment.service_type_display, false],
            ["نوع پرداخت", shipment.pay_type_display, false],
            ["وزن", digits(shipment.weight_grams) + " گرم", false],
            ["ارزش کالا", rial(shipment.goods_price_rial), false],
            ["هزینهٔ پست", rial(shipment.shipping_cost_rial), false],
            ["مالیات پست", rial(shipment.shipping_tax_rial), false]
        ];
        var list = $("shipment-facts");
        list.replaceChildren();
        rows.forEach(function (row) {
            var line = document.createElement("div");
            line.className = "d-flex flex-wrap justify-content-between py-2 border-bottom border-gray-200";
            var name = document.createElement("span");
            name.className = "text-gray-600";
            name.textContent = row[0];
            var val = document.createElement("span");
            val.className = "fw-semibold text-gray-900";
            val.textContent = row[1];
            if (row[2]) val.dir = "ltr";
            line.append(name, val);
            list.appendChild(line);
        });
        $("shipment-status").textContent = shipment.status_display;
        $("shipment-synced").textContent = shipment.last_synced_at
            ? new Date(shipment.last_synced_at).toLocaleString("fa-IR") : "هنوز از پست پرسیده نشده";
    }
    function render(payload) {
        var active = payload.results.filter(function (row) { return !row.is_cancelled; })[0];
        var registered = Boolean(active && active.parcel_code);
        $("shipment-loading").hidden = true;
        $("shipment-not-connected").hidden = payload.connected;
        $("shipment-form").hidden = !payload.connected || registered;
        $("shipment-active").hidden = !registered;
        if (registered) fillFacts(active);
        if (!$("shipment-service").options.length) {
            payload.service_types.forEach(function (row) { option($("shipment-service"), row.value, row.label); });
            payload.pay_types.forEach(function (row) { option($("shipment-pay"), row.value, row.label); });
            $("shipment-service").value = "1";
            $("shipment-pay").value = "1";
        }
        var cancelled = payload.results.filter(function (row) { return row.is_cancelled; }).length;
        $("shipment-cancelled-note").hidden = !cancelled;
        if (cancelled) $("shipment-cancelled-note").textContent = digits(cancelled) + " مرسولهٔ لغوشده هم برای این سند ثبت شده است.";
    }
    async function reload() {
        try {
            render(await call(base + "shipments/"));
        } catch (error) {
            $("shipment-loading").hidden = true;
            say(error.message, false);
        }
    }
    async function busy(button, work) {
        button.disabled = true;
        say("");
        try { await work(); }
        catch (error) { say(error.message, false); }
        finally { button.disabled = false; }
    }
    $("shipment-pick-city").addEventListener("click", function (event) {
        busy(event.currentTarget, async function () {
            $("shipment-city-picker").hidden = false;
            var select = $("shipment-province");
            if (select.options.length > 1) return;
            var data = await call(placesBase);
            data.results.forEach(function (row) { option(select, row.Code, row.pName); });
        });
    });
    $("shipment-province").addEventListener("change", async function (event) {
        var city = $("shipment-city");
        city.replaceChildren();
        option(city, "", "خودکار از نشانی سند");
        if (!event.target.value) return;
        try {
            var data = await call(placesBase + "?province=" + encodeURIComponent(event.target.value));
            data.results.forEach(function (row) { option(city, row.CityID, row.pName); });
        } catch (error) {
            say(error.message, false);
        }
    });
    $("shipment-quote").addEventListener("click", function (event) {
        busy(event.currentTarget, async function () {
            var result = await call(base + "shipment-quote/", {method: "POST", body: termsPayload()});
            var out = $("shipment-quote-result");
            out.hidden = false;
            out.textContent = "هزینهٔ پست: " + rial(result.shipping_cost) + " — مالیات: " + rial(result.shipping_tax) +
                " — هزینهٔ مرجوعی: " + rial(result.return_shipping_cost);
        });
    });
    $("shipment-form").addEventListener("submit", function (event) {
        event.preventDefault();
        busy($("shipment-submit"), async function () {
            var body = termsPayload();
            var email = $("shipment-email").value.trim();
            if (email) body.recipient_email = email;
            await call(base + "shipment-create/", {method: "POST", body: body});
            say("مرسوله در پست ثبت شد و بارکد رهگیری دریافت شد.", true);
            await reload();
        });
    });
    $("shipment-refresh").addEventListener("click", function (event) {
        busy(event.currentTarget, async function () {
            await call(base + "shipment-refresh/", {method: "POST"});
            say("وضعیت از پست دریافت شد.", true);
            await reload();
        });
    });
    $("shipment-ready").addEventListener("click", function (event) {
        busy(event.currentTarget, async function () {
            await call(base + "shipment-change/", {method: "POST", body: {action: "ready"}});
            say("مرسوله «آمادهٔ ارسال» شد.", true);
            await reload();
        });
    });
    $("shipment-cancel").addEventListener("click", function (event) {
        busy(event.currentTarget, async function () {
            if (!window.confirm("مرسولهٔ پستی لغو شود؟ این کار در سامانهٔ پست انجام می‌شود.")) return;
            await call(base + "shipment-change/", {method: "POST", body: {action: "cancel"}});
            say("مرسوله لغو شد.", true);
            await reload();
        });
    });
    reload();
})();
