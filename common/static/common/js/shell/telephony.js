import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate} from "dolphin/core/jalali.js";
import {clearMessages, globalMessage, showError} from "dolphin/core/messages.js";
import {onRealtime} from "dolphin/ui/realtime.js";
import {localPhone} from "dolphin/ui/rows.js";

/**
 * Click-to-call. Any control carrying `data-originate-number` — the
 * profile's «تماس», the header phone, a row's «تماس», the popup's «تماس
 * دوباره» — asks the PBX to ring the reader's own phone and then dial the
 * number. Without click-to-call those controls are plain `tel:` links
 * and this never runs for them.
 */
async function originateCall(trigger) {
    const number = trigger.dataset.originateNumber || trigger.dataset.number;
    const personType = trigger.dataset.originatePersonType || trigger.dataset.personType || "";
    const personId = trigger.dataset.originatePersonId || trigger.dataset.personId || "";
    if (!number || trigger.dataset.originating === "1") return;
    trigger.dataset.originating = "1";
    trigger.setAttribute("aria-busy", "true");
    clearMessages();
    try {
        const body = {number};
        if (personType && personId) {
            body.person_type = personType;
            body.person_id = Number(personId);
        }
        let request = await apiRequest("/api/v1/telephony/originate/", {method: "POST", body});
        globalMessage(`در حال برقراری تماس از داخلی ${toPersianDigits(request.extension)}…`, true);
        for (let tick = 0; tick < 40 && ["pending", "sending"].includes(request.status); tick += 1) {
            await new Promise((resolve) => window.setTimeout(resolve, 1000));
            request = await apiRequest(`/api/v1/telephony/originate/${request.id}/`);
        }
        if (request.status === "sent") {
            globalMessage(`تلفن داخلی ${toPersianDigits(request.extension)} زنگ می‌خورد؛ گوشی را بردارید تا شماره گرفته شود.`, true);
        } else {
            globalMessage(request.error || "تماس برقرار نشد.", false);
        }
    } catch (error) {
        showError(error);
    } finally {
        delete trigger.dataset.originating;
        trigger.removeAttribute("aria-busy");
    }
}

export function setupClickToCall() {
    document.addEventListener("click", (event) => {
        const trigger = event.target.closest('[data-originate-number], [data-profile-action="originate"]');
        if (!trigger) return;
        event.preventDefault();
        originateCall(trigger);
    });
}

/**
 * The incoming-call popup, on every page of someone with an extension
 * (`data-call-popup` on `<body>`). The inbox is asked every two seconds
 * while the tab is visible and not at all while it is hidden; a failing
 * server is asked less and less often. Each new popup's details are
 * fetched once. Built from the theme's own toast component.
 */
export function setupCallPopup() {
    if (document.body.dataset.callPopup !== "1") return;
    const POLL_MS = 2000;
    const stack = document.createElement("div");
    stack.className = "toast-container position-fixed end-0 px-5";
    stack.id = "call-popups";
    stack.setAttribute("aria-live", "polite");
    document.body.appendChild(stack);
    const shown = new Map();
    let timer = null;
    let failures = 0;
    let stopped = false;
    let busy = false;

    function symbol(person) {
        const holder = document.createElement("div");
        holder.className = "symbol symbol-45px symbol-circle flex-shrink-0";
        if (person && person.avatar_url) {
            const image = document.createElement("img");
            image.src = person.avatar_url;
            image.alt = "";
            holder.appendChild(image);
        } else {
            const label = document.createElement("span");
            label.className = "symbol-label bg-light-primary text-primary fw-bold fs-6";
            label.textContent = person ? person.initials : "؟";
            holder.appendChild(label);
        }
        return holder;
    }

    function actionButton(text, className) {
        const node = document.createElement("a");
        node.className = `btn btn-sm ${className}`;
        node.textContent = text;
        return node;
    }

    function render(detail) {
        const toast = document.createElement("div");
        toast.className = "toast show";
        toast.setAttribute("role", "alert");
        toast.dataset.callPopupId = String(detail.id);
        const header = document.createElement("div");
        header.className = "toast-header";
        const icon = document.createElement("i");
        const missed = detail.kind === "missed";
        icon.className = `di-duotone di-phone fs-2 me-3 text-${missed ? "danger" : "success"}`;
        icon.setAttribute("aria-hidden", "true");
        ["path1", "path2"].forEach((path) => {
            const span = document.createElement("span");
            span.className = path;
            icon.appendChild(span);
        });
        const title = document.createElement("strong");
        title.className = "me-auto";
        title.dataset.popupTitle = "";
        title.textContent = missed ? "تماس بی‌پاسخ" : (detail.call.status === "answered" ? "در حال مکالمه" : "تماس ورودی");
        const time = document.createElement("small");
        time.className = "text-muted ms-3";
        time.textContent = displayDate(detail.call.started_at).split(" ").pop();
        const close = document.createElement("button");
        close.type = "button";
        close.className = "btn-close ms-2";
        close.setAttribute("aria-label", "بستن");
        close.addEventListener("click", async () => {
            toast.remove();
            try {
                await apiRequest(`/api/v1/telephony/notifications/${detail.id}/dismiss/`, {method: "POST", body: {}});
            } catch (error) { /* it drops out of the inbox on its own */ }
        });
        header.append(icon, title, time, close);

        const body = document.createElement("div");
        body.className = "toast-body";
        const who = document.createElement("div");
        who.className = "d-flex align-items-center gap-3";
        const text = document.createElement("div");
        text.className = "flex-grow-1 min-w-0";
        const name = document.createElement(detail.person ? "a" : "span");
        name.className = "d-block fs-6 fw-bold text-gray-900 text-truncate";
        if (detail.person) {
            name.href = detail.person.url;
            name.classList.add("text-hover-primary");
            name.textContent = detail.person.name;
        } else {
            name.textContent = detail.known_elsewhere ? "مخاطب ثبت‌شده، خارج از محدودهٔ شما" : "شمارهٔ ناشناس";
        }
        text.appendChild(name);
        if (detail.person && detail.person.subtitle) {
            const subtitle = document.createElement("span");
            subtitle.className = "d-block text-muted fs-7 text-truncate";
            subtitle.textContent = detail.person.subtitle;
            text.appendChild(subtitle);
        }
        const number = document.createElement("span");
        number.className = "d-block fs-7 text-gray-700 text-start";
        number.dir = "ltr";
        number.textContent = localPhone(detail.call.e164 || detail.call.number);
        text.appendChild(number);
        who.append(symbol(detail.person), text);
        body.appendChild(who);

        const figures = (detail.person && detail.person.figures) || [];
        if (figures.length) {
            const list = document.createElement("div");
            list.className = "d-flex flex-wrap gap-2 mt-3";
            figures.forEach((figure) => {
                const badge = document.createElement("span");
                badge.className = `badge badge-light-${figure.accent || "secondary"} fw-semibold`;
                badge.textContent = `${figure.label}: ${figure.value}`;
                if (figure.tooltip) badge.title = figure.tooltip;
                list.appendChild(badge);
            });
            body.appendChild(list);
        }

        const actions = document.createElement("div");
        actions.className = "d-flex flex-wrap gap-2 mt-4";
        if (detail.person) {
            const open = actionButton("پروفایل", "btn-light-primary");
            open.href = detail.person.url;
            actions.appendChild(open);
        }
        if (detail.create_customer_url) {
            const create = actionButton("ثبت مشتری", "btn-light-success");
            create.href = detail.create_customer_url;
            actions.appendChild(create);
        }
        if (missed && detail.can_call_back) {
            const back = document.createElement("button");
            back.type = "button";
            back.className = "btn btn-sm btn-primary";
            back.textContent = "تماس دوباره";
            back.dataset.originateNumber = detail.call.e164;
            if (detail.person) {
                back.dataset.originatePersonType = detail.person.type;
                back.dataset.originatePersonId = String(detail.person.id);
            }
            actions.appendChild(back);
        }
        if (actions.childElementCount) body.appendChild(actions);
        toast.append(header, body);
        return toast;
    }

    async function tick() {
        window.clearTimeout(timer);
        if (stopped || busy || document.hidden) return;
        busy = true;
        try {
            const data = await apiRequest("/api/v1/telephony/notifications/");
            failures = 0;
            const wanted = new Set(data.results.map((item) => item.id));
            shown.forEach((node, id) => {
                if (!wanted.has(id)) { node.remove(); shown.delete(id); }
            });
            for (const item of data.results) {
                const existing = shown.get(item.id);
                if (existing) {
                    const title = existing.querySelector("[data-popup-title]");
                    if (title && item.kind === "ringing") title.textContent = item.status === "answered" ? "در حال مکالمه" : "تماس ورودی";
                    continue;
                }
                const detail = await apiRequest(`/api/v1/telephony/notifications/${item.id}/`);
                const node = render(detail);
                shown.set(item.id, node);
                stack.prepend(node);
            }
        } catch (error) {
            failures += 1;
            // Switched off, or this person lost the extension: stop asking.
            if (error.status === 403 || error.status === 404) stopped = true;
        } finally {
            busy = false;
        }
        if (!stopped && !document.hidden) {
            timer = window.setTimeout(tick, failures ? Math.min(60000, POLL_MS * 2 ** failures) : POLL_MS);
        }
    }

    document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
    // Live updates (2.38.0): a call that concerns me shows its popup at once;
    // the timer remains the fallback.
    onRealtime(["call"], tick, {whenBusy: true, delay: 50});
    tick();
}
