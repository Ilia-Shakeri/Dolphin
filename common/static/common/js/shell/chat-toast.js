import {apiRequest} from "dolphin/core/api.js";
import {onRealtime} from "dolphin/ui/realtime.js";

/**
 * A new chat message, announced at the bottom-left of the page (2.40.34,
 * product owner: «نوتیفیکیشن پیام‌های جدید به‌صورت پاپ‌آپ در پایین سمت چپ
 * صفحه نشان داده شود — لایو باشد»).
 *
 * Driven by the same live stream the chat itself uses: a `chat` event re-reads
 * the reader's own threads (the API's scope, as everywhere), and a thread whose
 * unread count grew since the last read gets a card — the sender, the start of
 * the message, and a click that opens that conversation in the chat drawer.
 * Not for what was already unread when the page opened, not for the
 * conversation the reader has open right now, and at most three cards at once;
 * each leaves by itself after a few seconds unless the pointer rests on it.
 */
const SHOW_MS = 6500;
const MAX_CARDS = 3;

export function setupChatToasts() {
    if (!document.querySelector("[data-chat-unread-badge]")) return;
    const host = document.createElement("div");
    host.className = "chat-toasts";
    host.setAttribute("aria-live", "polite");
    host.setAttribute("aria-label", "پیام‌های تازه");
    document.body.append(host);

    let known = null; // threadId -> {unread, at}

    async function read() {
        let threads;
        try {
            threads = await apiRequest("/api/v1/chat/threads/");
        } catch (error) {
            return;
        }
        const next = new Map(threads.map((thread) => [thread.id, {unread: thread.unread_count, at: thread.last_message_at}]));
        if (known) {
            threads.forEach((thread) => {
                const before = known.get(thread.id);
                const grew = thread.unread_count > (before ? before.unread : 0);
                const newer = !before || before.at !== thread.last_message_at;
                if (grew && newer && String(thread.id) !== document.body.dataset.chatOpenThread) show(thread);
            });
        }
        known = next;
    }

    function show(thread) {
        while (host.children.length >= MAX_CARDS) host.firstElementChild.remove();
        const card = document.createElement("button");
        card.type = "button";
        card.className = "chat-toast";
        const avatar = document.createElement("span");
        avatar.className = "chat-toast-avatar";
        avatar.textContent = (thread.peer?.display_name || "?").trim().charAt(0);
        const text = document.createElement("span");
        text.className = "chat-toast-text";
        const name = document.createElement("span");
        name.className = "chat-toast-name";
        name.textContent = thread.peer?.display_name || "پیام تازه";
        const body = document.createElement("span");
        body.className = "chat-toast-body";
        const preview = (thread.last_message_body || "").trim();
        body.textContent = preview.length > 90 ? `${preview.slice(0, 90)}…` : preview;
        text.append(name, body);
        const close = document.createElement("span");
        close.className = "chat-toast-close";
        close.setAttribute("aria-hidden", "true");
        close.textContent = "×";
        card.append(avatar, text, close);
        card.setAttribute("aria-label", `پیام تازه از ${name.textContent}: ${body.textContent}`);

        let timer = setTimeout(leave, SHOW_MS);
        card.addEventListener("pointerenter", () => clearTimeout(timer));
        card.addEventListener("pointerleave", () => { timer = setTimeout(leave, 2500); });
        card.addEventListener("click", (event) => {
            leave();
            if (event.target === close) return;
            document.dispatchEvent(new CustomEvent("dolphin:chat-open-thread", {detail: {threadId: thread.id}}));
        });

        function leave() {
            clearTimeout(timer);
            card.classList.add("is-leaving");
            setTimeout(() => card.remove(), 260);
        }

        host.append(card);
    }

    read();
    onRealtime(["chat"], read, {whenBusy: true, delay: 300});
}
