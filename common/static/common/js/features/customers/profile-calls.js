import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate, pad2} from "dolphin/core/jalali.js";
import {errorText, showError} from "dolphin/core/messages.js";
import {localPhone} from "dolphin/ui/rows.js";
import {appendCell, pageRangeLabel} from "dolphin/ui/table.js";

// --- Telephony (2.23.0) ------------------------------------------------
//
// The PBX's own record of calls on a profile, placing a call through the
// PBX from the reader's own extension, and the incoming-call popup. The
// server decides every one of them again: this script only draws what
// the API chose to return.

const CALL_STATUS_ACCENT = {
    completed: "success", missed: "danger", failed: "danger",
    no_answer: "warning", busy: "warning", ringing: "info", answered: "info",
};

/** `155` → `۲:۳۵`, an hour or more → `۱:۰۲:۳۵`; nothing said → «—». */
function talkTime(seconds) {
    const total = Number(seconds) || 0;
    if (!total) return "—";
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const rest = total % 60;
    const text = hours ? `${hours}:${pad2(minutes)}:${pad2(rest)}` : `${minutes}:${pad2(rest)}`;
    return toPersianDigits(text);
}

function callBadge(call) {
    const badge = document.createElement("span");
    badge.className = `badge badge-light-${CALL_STATUS_ACCENT[call.status] || "secondary"}`;
    badge.textContent = call.status_label;
    return badge;
}

function pbxCallRow(call, {showPerson = false} = {}) {
    const row = document.createElement("tr");
    const what = document.createElement("td");
    const direction = document.createElement("span");
    direction.className = "d-block fw-semibold text-gray-900 mb-1";
    direction.textContent = call.direction_label;
    what.append(direction, callBadge(call));
    row.appendChild(what);
    if (showPerson) {
        const person = document.createElement("td");
        if (call.person_url) {
            const link = document.createElement("a");
            link.href = call.person_url;
            link.className = "text-gray-800 text-hover-primary fw-semibold";
            link.textContent = call.person_display;
            person.appendChild(link);
        } else {
            person.textContent = "—";
            person.title = call.person_id
                ? "این شماره به مخاطبی خارج از محدودهٔ دسترسی شما تعلق دارد."
                : "این شماره به مشتری یا همکاری در دلفین تطبیق داده نشد.";
        }
        row.appendChild(person);
    }
    const number = appendCell(row, localPhone(call.external_number || (call.direction === "inbound" ? call.caller : call.callee)));
    number.dir = "ltr";
    appendCell(row, call.extension ? `${toPersianDigits(call.extension)}${call.user_display ? ` — ${call.user_display}` : ""}` : "");
    appendCell(row, displayDate(call.started_at));
    appendCell(row, call.status === "completed" ? talkTime(call.billsec) : "");
    const actions = document.createElement("td");
    actions.className = "row-actions";
    if (call.has_recording) {
        const play = document.createElement("button");
        play.type = "button";
        play.className = "btn btn-sm btn-light-primary";
        play.textContent = "پخش ضبط";
        play.addEventListener("click", () => {
            // Asked for only now, not on page load: every listening is
            // audited, and a table of recordings must not preload audio.
            const audio = document.createElement("audio");
            audio.controls = true;
            audio.preload = "none";
            audio.src = `/api/v1/calls/${call.id}/recording/`;
            audio.className = "mw-100";
            audio.setAttribute("aria-label", `ضبط تماس ${displayDate(call.started_at)}`);
            audio.addEventListener("error", () => {
                const note = document.createElement("span");
                note.className = "text-danger fs-7";
                note.textContent = "ضبط این تماس در دسترس نیست.";
                audio.replaceWith(note);
            });
            play.replaceWith(audio);
            audio.play().catch(() => { /* the reader presses play */ });
        });
        actions.appendChild(play);
    }
    if (call.external_number && document.body.dataset.canOriginate === "1") {
        const again = document.createElement("button");
        again.type = "button";
        again.className = "btn btn-sm btn-light";
        again.textContent = "تماس";
        again.dataset.originateNumber = call.external_number;
        if (call.person_type && call.person_id) {
            again.dataset.originatePersonType = call.person_type;
            again.dataset.originatePersonId = String(call.person_id);
        }
        actions.appendChild(again);
    }
    if (!actions.childElementCount) actions.textContent = "—";
    row.appendChild(actions);
    return row;
}

/** One paginated table of PBX calls (`profiles/tabs/pbx_calls_table.inc`). */
export function loadPbxCalls(prefix, baseUrl) {
    const loading = document.getElementById(`${prefix}-loading`);
    if (!loading) return Promise.resolve();
    const empty = document.getElementById(`${prefix}-empty`);
    const wrap = document.getElementById(`${prefix}-table-wrap`);
    const body = document.getElementById(`${prefix}-table-body`);
    const pagination = document.getElementById(`${prefix}-pagination`);
    const previous = document.getElementById(`${prefix}-prev`);
    const next = document.getElementById(`${prefix}-next`);
    const showPerson = body.dataset.showPerson === "1";
    let currentPage = 1;

    async function load(page = 1) {
        loading.hidden = false;
        empty.hidden = true;
        wrap.hidden = true;
        pagination.hidden = true;
        try {
            const data = await apiRequest(`${baseUrl}${baseUrl.includes("?") ? "&" : "?"}page=${page}`);
            body.replaceChildren(...data.results.map((call) => pbxCallRow(call, {showPerson})));
            loading.hidden = true;
            if (!data.results.length) { empty.hidden = false; return; }
            wrap.hidden = false;
            currentPage = page;
            previous.disabled = !data.previous;
            next.disabled = !data.next;
            document.getElementById(`${prefix}-page-label`).textContent = pageRangeLabel(data, page);
            pagination.hidden = !data.previous && !data.next;
        } catch (error) {
            loading.hidden = true;
            showError(error);
        }
    }
    previous.addEventListener("click", () => load(currentPage - 1));
    next.addEventListener("click", () => load(currentPage + 1));
    return load();
}

/** The «عملکرد» tab's call figures for the same period as its report. */
export async function loadCallStats(userId, query) {
    const host = document.querySelector("[data-call-stats]");
    if (!host) return;
    const loading = document.getElementById("profile-call-stats-loading");
    const errorNode = document.getElementById("profile-call-stats-error");
    loading.hidden = false;
    errorNode.hidden = true;
    try {
        const params = new URLSearchParams({
            user: userId, period_start: query.get("period_start") || "", period_end: query.get("period_end") || "",
        });
        const stats = await apiRequest(`/api/v1/telephony/stats/?${params}`);
        const values = {
            inbound: toPersianDigits(String(stats.inbound)),
            inbound_answered: toPersianDigits(String(stats.inbound_answered)),
            missed: toPersianDigits(String(stats.missed)),
            outbound: toPersianDigits(String(stats.outbound)),
            talk_seconds: talkTime(stats.talk_seconds),
            average_talk_seconds: talkTime(stats.average_talk_seconds),
            follow_up: stats.missed_decided
                ? toPersianDigits(`${stats.missed_followed_up} از ${stats.missed_decided}`)
                : "—",
        };
        Object.entries(values).forEach(([name, text]) => {
            const node = host.querySelector(`[data-call-stat="${name}"]`);
            if (node) node.textContent = text;
        });
        const followUp = host.querySelector('[data-call-stat="follow_up"]');
        if (followUp) followUp.title = stats.missed_decided ? "" : "در این بازه تماس بی‌پاسخی که مهلت پیگیری‌اش گذشته باشد نبوده است.";
    } catch (error) {
        errorNode.textContent = errorText(error);
        errorNode.hidden = false;
    } finally {
        loading.hidden = true;
    }
}
