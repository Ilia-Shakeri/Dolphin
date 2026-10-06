import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate} from "dolphin/core/jalali.js";
import {showError, withSubmit} from "dolphin/core/messages.js";
import {onRealtime} from "dolphin/ui/realtime.js";
import {BADGE_CACHE_PREFIX, keepBadgeFresh} from "dolphin/shell/badges.js";

/**
 * The sidebar's chat badge, on every page — not only `/chat/` itself.
 *
 * `setupChat()` below updates it immediately from the thread list it
 * already has whenever *that* page changes it; this is the only thing
 * that keeps it truthful everywhere else, since the badge markup itself
 * lives in the shared sidebar template that every page renders.
 */
function updateChatUnreadBadge(totalUnread) {
    const badge = document.querySelector("[data-chat-unread-badge]");
    const count = document.querySelector("[data-chat-unread-count]");
    if (!badge || !count) return;
    badge.hidden = totalUnread <= 0;
    count.textContent = toPersianDigits(String(totalUnread));
}

//: Where the chat drawer keeps this tab's copy of the reader's threads
//: and recent messages between page loads (2.18.5). Keyed by the signed-in
//: user's id, so a different account in the same tab never reads it, and
//: cleared on logout (`clearChatCache`). `sessionStorage`, not `localStorage`:
//: it dies with the tab.
const CHAT_CACHE_PREFIX = "dolphin.chat.v1.";

export function clearChatCache() {
    try {
        Object.keys(sessionStorage)
            .filter((key) => key.startsWith(CHAT_CACHE_PREFIX) || key.startsWith(BADGE_CACHE_PREFIX))
            .forEach((key) => sessionStorage.removeItem(key));
    } catch (error) {
        // Storage refused (private mode): there is nothing to clear.
    }
}

export function setupChatUnreadPoll() {
    if (!document.querySelector("[data-chat-unread-badge]")) return;
    keepBadgeFresh({url: "/api/v1/chat/unread-count/", intervalMs: 20000, key: "chat", apply: updateChatUnreadBadge});
}

export function setupChat(prefix = "chat-drawer", options = {}) {
    // `prefix` picks which markup this instance drives: the header
    // drawer (`chat-drawer-*`, the default — every id below is
    // unchanged from before this was parametrised) or the full page
    // (`chat-page-*`, see `DolphinChatView`). Same engine either way —
    // same API calls, same cache key, same read/unread rules — only the
    // ids and, through `options`, whether there is a `data-dolphin-drawer`
    // container/toggle to coordinate with.
    const id = (name) => `${prefix}-${name}`;
    const drawer = options.container ? document.getElementById(options.container) : null;
    const toggle = options.toggle ? document.getElementById(options.toggle) : null;
    const threadListEl = document.getElementById(id("thread-list"));
    if (!threadListEl) return;
    // A page (no drawer to toggle) is "open" for as long as it exists in
    // the DOM; a drawer instance is open exactly when the theme's own
    // `drawer-on` class says so. Either way, both polls below still
    // check `document.hidden` — a backgrounded tab costs nothing.
    const isOpen = options.isOpen || (() => Boolean(drawer && drawer.classList.contains("drawer-on")));

    const threadsLoading = document.getElementById(id("threads-loading"));
    const threadsEmpty = document.getElementById(id("threads-empty"));
    const listTitle = document.getElementById(id("list-title"));
    const peerTitle = document.getElementById(id("peer-title"));
    const listPanel = document.getElementById(id("list-panel"));
    const conversationPanel = document.getElementById(id("conversation-panel"));
    const footer = document.getElementById(id("footer"));
    const messagesEl = document.getElementById(id("messages"));
    const messagesEmpty = document.getElementById(id("messages-empty"));
    const peerNameEl = document.getElementById(id("peer-name"));
    const peerRoleEl = document.getElementById(id("peer-role"));
    const backButton = document.getElementById(id("back"));
    const sendForm = document.getElementById(id("send-form"));
    const messageInput = document.getElementById(id("message-input"));
    const newDialog = document.getElementById(id("new-dialog"));
    const colleaguesLoading = document.getElementById(id("colleagues-loading"));
    const colleaguesEmpty = document.getElementById(id("colleagues-empty"));
    const colleaguesList = document.getElementById(id("colleagues-list"));
    // Only the page has room to show "nothing is open yet" beside the
    // list rather than in place of it; the drawer has no such element.
    const emptyState = document.getElementById(id("empty-state"));
    // The drawer's way to the full chats page (2.40.27): its title and a
    // toolbar button. With a conversation open they take it along, so the
    // page opens on the same one (`?thread=`, read below).
    const pageLinks = Array.from(document.querySelectorAll(`[data-chat-page-link="${prefix}"]`));
    function pointPageLinks(threadId) {
        pageLinks.forEach((link) => {
            const url = new URL(link.dataset.chatPageUrl || link.getAttribute("href"), window.location.origin);
            link.dataset.chatPageUrl ||= url.pathname;
            if (threadId) url.searchParams.set("thread", String(threadId));
            link.setAttribute("href", `${url.pathname}${url.search}`);
        });
    }

    const AVATAR_COLORS = ["primary", "success", "info", "warning", "danger"];
    function avatarColor(userId) {
        return AVATAR_COLORS[Math.abs(Number(userId)) % AVATAR_COLORS.length];
    }
    // 35px, matching the purchased theme's own drawer-chat avatar size
    // exactly (its message rows and its contact rows both use it).
    function avatarSymbol(name, userId) {
        const symbol = document.createElement("div");
        symbol.className = "symbol symbol-35px symbol-circle";
        const label = document.createElement("span");
        label.className = `symbol-label bg-light-${avatarColor(userId)} text-${avatarColor(userId)} fw-bold`;
        label.textContent = (name || "?").trim().charAt(0);
        symbol.appendChild(label);
        return symbol;
    }

    // How fast "live" is. Product owner, 2026-09-27: «وقتی چت باز می‌شود
    // نمایش چت‌های قبلی خیلی طول می‌کشد؛ باید خیلی سریع و زنده باشد».
    // Two seconds for the open conversation, five for the thread list,
    // both only while the drawer is open *and* the tab is visible — a
    // tab in the background costs nothing, and coming back to it polls at
    // once rather than waiting for the next tick.
    const ACTIVE_THREAD_POLL_MS = 2000;
    const THREAD_LIST_POLL_MS = 5000;
    //: How much of each conversation this tab keeps between page loads.
    const MESSAGE_CACHE_LIMIT = 40;
    const THREAD_CACHE_LIMIT = 8;

    const cacheKey = `${CHAT_CACHE_PREFIX}${document.body.dataset.chatUserId || ""}`;
    let activeThreadId = null;
    let lastMessageId = 0;
    let threads = [];
    let threadsKnown = false;
    let threadsInFlight = null;
    // threadId -> the newest messages of that conversation this tab has
    // seen, oldest first — what makes reopening a thread instant.
    const messageCache = new Map();
    const peeksInFlight = new Map();
    // Ids already drawn in the open conversation: a poll that overlaps a
    // send can return the same message the send already drew.
    const renderedIds = new Set();

    function readCache() {
        try {
            // Anything left by another account in this tab goes first.
            Object.keys(sessionStorage)
                .filter((key) => key.startsWith(CHAT_CACHE_PREFIX) && key !== cacheKey)
                .forEach((key) => sessionStorage.removeItem(key));
            const saved = JSON.parse(sessionStorage.getItem(cacheKey) || "null");
            if (!saved) return;
            if (Array.isArray(saved.threads)) {
                threads = saved.threads;
                threadsKnown = true;
            }
            Object.entries(saved.messages || {}).forEach(([threadId, messages]) => {
                if (Array.isArray(messages)) messageCache.set(Number(threadId), messages);
            });
        } catch (error) {
            // Unreadable or refused storage: start cold, as before 2.18.5.
        }
    }

    function writeCache() {
        try {
            const recent = Array.from(messageCache.entries()).slice(-THREAD_CACHE_LIMIT);
            sessionStorage.setItem(cacheKey, JSON.stringify({
                threads,
                messages: Object.fromEntries(recent.map(([threadId, messages]) => [
                    threadId, messages.slice(-MESSAGE_CACHE_LIMIT),
                ])),
            }));
        } catch (error) {
            // Storage full or refused: the in-memory copy still serves
            // this page; only the next page load starts cold.
        }
    }

    /** Merge newly fetched messages into one thread's cached copy. */
    function remember(threadId, messages, {replace = false} = {}) {
        if (!messages.length && !replace) return;
        const existing = replace ? [] : (messageCache.get(threadId) || []);
        const seen = new Set(existing.map((message) => message.id));
        const merged = existing.concat(messages.filter((message) => !seen.has(message.id)));
        merged.sort((a, b) => a.id - b.id);
        // Re-inserted so the Map's order is "most recently touched last",
        // which is what `writeCache` keeps when it trims.
        messageCache.delete(threadId);
        messageCache.set(threadId, merged.slice(-MESSAGE_CACHE_LIMIT));
        writeCache();
    }

    function showList() {
        activeThreadId = null;
        pointPageLinks(null);
        listTitle.classList.remove("d-none");
        peerTitle.classList.add("d-none");
        listPanel.classList.remove("d-none");
        listPanel.hidden = false;
        conversationPanel.classList.add("d-none");
        footer.classList.add("d-none");
        if (emptyState) emptyState.classList.remove("d-none");
        renderThreadList();
    }

    function showConversation() {
        listTitle.classList.add("d-none");
        peerTitle.classList.remove("d-none");
        listPanel.classList.add("d-none");
        conversationPanel.classList.remove("d-none");
        footer.classList.remove("d-none");
        if (emptyState) emptyState.classList.add("d-none");
    }

    function renderThreadList() {
        // A list this tab already knows is drawn at once — from the
        // previous page load if need be — and refreshed behind it, rather
        // than a "loading" line every time the drawer opens.
        threadsLoading.hidden = threadsKnown;
        threadListEl.replaceChildren();
        if (threadsKnown) updateChatUnreadBadge(threads.reduce((sum, thread) => sum + thread.unread_count, 0));
        threadsEmpty.hidden = !threadsKnown || threads.length > 0;
        threadListEl.hidden = threads.length === 0;
        threads.forEach((thread) => {
            const row = document.createElement("button");
            row.type = "button";
            row.className = "btn btn-flush d-flex align-items-center justify-content-between w-100 py-3 px-2 text-start rounded";
            row.dataset.chatThreadRow = String(thread.id);

            const left = document.createElement("div");
            left.className = "d-flex align-items-center overflow-hidden";
            left.appendChild(avatarSymbol(thread.peer.display_name, thread.peer.id));
            const details = document.createElement("div");
            details.className = "ms-3 text-start overflow-hidden";
            const nameLine = document.createElement("div");
            nameLine.className = "fs-6 fw-bold text-gray-900 text-truncate";
            nameLine.textContent = thread.peer.display_name;
            const previewLine = document.createElement("div");
            previewLine.className = "fs-7 text-muted text-truncate";
            previewLine.textContent = thread.last_message_body || "—";
            details.append(nameLine, previewLine);
            left.appendChild(details);
            row.appendChild(left);

            if (thread.unread_count > 0) {
                const badge = document.createElement("span");
                badge.className = "badge badge-circle badge-danger ms-2";
                badge.textContent = toPersianDigits(String(thread.unread_count));
                row.appendChild(badge);
            }
            row.addEventListener("click", () => openThread(thread.id));
            // Pointing at a conversation fetches it ahead, so the click
            // lands on messages already in hand.
            row.addEventListener("pointerenter", () => peekThread(thread.id));
            row.addEventListener("focus", () => peekThread(thread.id));
            threadListEl.appendChild(row);
        });
    }

    /** One fetch of the thread list at a time, shared by whoever asks. */
    function loadThreads() {
        if (threadsInFlight) return threadsInFlight;
        threadsInFlight = apiRequest("/api/v1/chat/threads/")
            .then((data) => {
                threads = data;
                threadsKnown = true;
                writeCache();
                if (!activeThreadId) renderThreadList();
                else updateChatUnreadBadge(threads.reduce((sum, thread) => sum + thread.unread_count, 0));
            })
            .catch((error) => {
                threadsLoading.hidden = true;
                if (!threadsKnown) showError(error);
            })
            .finally(() => { threadsInFlight = null; });
        return threadsInFlight;
    }

    /** Warm one thread's cache without marking it read (`?peek=1`). */
    function peekThread(threadId) {
        if (messageCache.has(threadId) || peeksInFlight.has(threadId)) return;
        const request = apiRequest(`/api/v1/chat/threads/${threadId}/messages/?peek=1`)
            .then((messages) => remember(threadId, messages, {replace: true}))
            .catch(() => {
                // A missed warm-up only means the click fetches instead.
            })
            .finally(() => peeksInFlight.delete(threadId));
        peeksInFlight.set(threadId, request);
    }

    function appendMessageBubble(message) {
        if (message.id != null) {
            if (renderedIds.has(message.id)) return null;
            renderedIds.add(message.id);
        }
        const row = document.createElement("div");
        row.className = `d-flex mb-6 ${message.mine ? "justify-content-end" : "justify-content-start"}`;
        const wrap = document.createElement("div");
        wrap.className = `d-flex flex-column ${message.mine ? "align-items-end" : "align-items-start"}`;

        const meta = document.createElement("div");
        meta.className = "d-flex align-items-center mb-2";
        const senderId = message.mine
            ? Number(document.body.dataset.chatUserId)
            : (threads.find((t) => t.id === activeThreadId)?.peer.id ?? 0);
        const senderName = message.mine ? "شما" : message.sender_display_name;
        if (message.mine) {
            const metaTime = document.createElement("span");
            metaTime.className = "fs-8 text-muted me-1";
            metaTime.textContent = message.pending ? "در حال ارسال…" : displayDate(message.created_at);
            const metaName = document.createElement("span");
            metaName.className = "fs-7 fw-bold text-gray-900 ms-1";
            metaName.textContent = senderName;
            meta.append(metaTime, metaName, avatarSymbol(senderName, senderId));
        } else {
            const metaName = document.createElement("span");
            metaName.className = "fs-7 fw-bold text-gray-900 me-1";
            metaName.textContent = senderName;
            const metaTime = document.createElement("span");
            metaTime.className = "fs-8 text-muted ms-1";
            metaTime.textContent = displayDate(message.created_at);
            meta.append(avatarSymbol(senderName, senderId), metaName, metaTime);
        }

        const bubble = document.createElement("div");
        bubble.className = `p-4 rounded fw-semibold mw-lg-300px ${message.mine ? "bg-light-primary text-end" : "bg-light-info text-start"}`;
        bubble.style.whiteSpace = "pre-wrap";
        bubble.style.wordBreak = "break-word";
        bubble.textContent = message.body;

        wrap.append(meta, bubble);
        row.appendChild(wrap);
        if (message.pending) row.classList.add("opacity-50");
        messagesEl.appendChild(row);
        return row;
    }

    function scrollMessagesToBottom() {
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function drawMessages(messages) {
        messages.forEach(appendMessageBubble);
        if (messages.length) {
            lastMessageId = Math.max(lastMessageId, messages[messages.length - 1].id);
            messagesEmpty.hidden = true;
        }
    }

    function markThreadReadLocally(threadId) {
        const row = threads.find((item) => item.id === threadId);
        if (row) row.unread_count = 0;
        updateChatUnreadBadge(threads.reduce((sum, item) => sum + item.unread_count, 0));
        writeCache();
    }

    async function openThread(threadId) {
        activeThreadId = threadId;
        pointPageLinks(threadId);
        lastMessageId = 0;
        renderedIds.clear();
        showConversation();
        const thread = threads.find((item) => item.id === threadId);
        if (thread) {
            peerNameEl.textContent = thread.peer.display_name;
            peerRoleEl.textContent = thread.peer.role_label;
        }
        messagesEl.replaceChildren();
        messagesEmpty.hidden = true;
        messageInput.focus();

        // What this tab already has is drawn now; the network only ever
        // adds what is newer than it.
        const cached = messageCache.get(threadId) || [];
        drawMessages(cached);
        scrollMessagesToBottom();
        const hadUnread = Boolean(thread && thread.unread_count > 0);

        try {
            if (!cached.length) {
                // Cold: the newest page — and a plain GET marks it read.
                const pending = peeksInFlight.get(threadId);
                if (pending) await pending;
                const warmed = messageCache.get(threadId);
                if (warmed && warmed.length) {
                    if (activeThreadId !== threadId) return;
                    drawMessages(warmed);
                    scrollMessagesToBottom();
                    if (hadUnread) await apiRequest(`/api/v1/chat/threads/${threadId}/read/`, {method: "POST"});
                } else {
                    const messages = await apiRequest(`/api/v1/chat/threads/${threadId}/messages/`);
                    if (activeThreadId !== threadId) return;
                    remember(threadId, messages, {replace: true});
                    drawMessages(messages);
                    messagesEmpty.hidden = messages.length > 0;
                    scrollMessagesToBottom();
                }
            } else {
                // Warm: only what arrived since, then the read mark.
                const newer = await apiRequest(`/api/v1/chat/threads/${threadId}/messages/?after_id=${lastMessageId}`);
                if (activeThreadId !== threadId) return;
                remember(threadId, newer);
                drawMessages(newer);
                if (newer.length) scrollMessagesToBottom();
                if (hadUnread || newer.length) await apiRequest(`/api/v1/chat/threads/${threadId}/read/`, {method: "POST"});
            }
            markThreadReadLocally(threadId);
        } catch (error) {
            showError(error);
        }
    }

    async function pollActiveThread() {
        if (!activeThreadId || !isOpen() || document.hidden) return;
        const threadId = activeThreadId;
        try {
            const messages = await apiRequest(
                `/api/v1/chat/threads/${threadId}/messages/?after_id=${lastMessageId}`,
            );
            if (!messages.length || activeThreadId !== threadId) return;
            remember(threadId, messages);
            drawMessages(messages);
            scrollMessagesToBottom();
            // A message that arrived while the thread was open is read the
            // moment it is drawn — mark it so the badge never lags what the
            // reader can already see on screen.
            await apiRequest(`/api/v1/chat/threads/${threadId}/read/`, {method: "POST"});
        } catch (error) {
            // A transient poll failure is not worth interrupting anyone
            // over; the next tick tries again.
        }
    }

    function pollThreads() {
        if (!isOpen() || document.hidden) return;
        loadThreads();
    }

    sendForm.addEventListener("submit", (event) => {
        event.preventDefault();
        if (!activeThreadId) return;
        const threadId = activeThreadId;
        const body = messageInput.value;
        if (!body.trim()) return;
        withSubmit(sendForm, async () => {
            // Drawn at once, dimmed, and replaced by the server's own
            // copy when it answers — a sent message should not wait on a
            // round trip to appear.
            messageInput.value = "";
            messagesEmpty.hidden = true;
            const pendingRow = appendMessageBubble({id: null, mine: true, pending: true, body});
            scrollMessagesToBottom();
            let message;
            try {
                message = await apiRequest(`/api/v1/chat/threads/${threadId}/messages/`, {
                    method: "POST", body: {body},
                });
            } catch (error) {
                if (pendingRow) pendingRow.remove();
                messageInput.value = body;
                throw error;
            }
            if (pendingRow) pendingRow.remove();
            if (activeThreadId === threadId) {
                appendMessageBubble(message);
                lastMessageId = Math.max(lastMessageId, message.id);
                scrollMessagesToBottom();
            }
            remember(threadId, [message]);
            loadThreads();
        });
    });

    messageInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            sendForm.requestSubmit();
        }
    });

    backButton.addEventListener("click", () => {
        showList();
        loadThreads();
    });

    async function loadColleagues() {
        try {
            const colleagues = await apiRequest("/api/v1/chat/colleagues/");
            colleaguesLoading.hidden = true;
            colleaguesEmpty.hidden = colleagues.length > 0;
            colleaguesList.hidden = colleagues.length === 0;
            colleaguesList.replaceChildren();
            colleagues.forEach((colleague) => {
                const row = document.createElement("button");
                row.type = "button";
                row.className = "btn btn-flush d-flex align-items-center w-100 py-3 px-2 text-start rounded";
                row.appendChild(avatarSymbol(colleague.display_name, colleague.id));
                const details = document.createElement("div");
                details.className = "ms-3 text-start";
                const nameLine = document.createElement("div");
                nameLine.className = "fs-6 fw-bold text-gray-900";
                nameLine.textContent = colleague.display_name;
                const roleLine = document.createElement("div");
                roleLine.className = "fs-7 text-muted";
                roleLine.textContent = colleague.role_label;
                details.append(nameLine, roleLine);
                row.appendChild(details);
                row.addEventListener("click", async () => {
                    try {
                        const thread = await apiRequest("/api/v1/chat/threads/", {
                            method: "POST", body: {other_user_id: colleague.id},
                        });
                        newDialog.close();
                        const exists = threads.some((item) => item.id === thread.id);
                        if (!exists) threads.unshift(thread);
                        threadsKnown = true;
                        openThread(thread.id);
                    } catch (error) {
                        showError(error);
                    }
                });
                colleaguesList.appendChild(row);
            });
        } catch (error) {
            colleaguesLoading.hidden = true;
            showError(error);
        }
    }

    document.getElementById(id("open-new")).addEventListener("click", () => {
        newDialog.showModal();
        loadColleagues();
    });
    newDialog.querySelectorAll("[data-close-dialog]").forEach((button) =>
        button.addEventListener("click", () => newDialog.close()));

    if (toggle) {
        // Intent before the click: a pointer over the chat icon, or
        // keyboard focus on it, starts the thread-list request, so
        // opening the drawer usually finds it already answered.
        ["pointerenter", "focus", "touchstart"].forEach((name) => {
            toggle.addEventListener(name, () => { if (!isOpen()) loadThreads(); }, {passive: true});
        });

        // The theme's own DolphinDrawer binds its open/close click on this
        // same button; this listener runs alongside it, not instead of
        // it, and only reacts to the drawer actually being open — a
        // click that closes it triggers no wasted request.
        toggle.addEventListener("click", () => {
            // DolphinDrawer flips its own `drawer-on` class synchronously
            // inside the same click handler, but listener order between
            // it and this one is not something to depend on — a
            // microtask delay reads the class after every same-tick
            // handler has run either way.
            Promise.resolve().then(() => {
                if (!isOpen()) return;
                if (!activeThreadId) renderThreadList();
                loadThreads();
                // The most recent conversations are the likeliest to be
                // opened next; fetch them ahead as well.
                threads.slice(0, 3).forEach((thread) => peekThread(thread.id));
            });
        });
    }

    // Back to a visible tab with the drawer open: catch up at once.
    document.addEventListener("visibilitychange", () => {
        if (document.hidden || !isOpen()) return;
        pollActiveThread();
        loadThreads();
    });

    readCache();
    showList();
    if (options.openFromUrl) {
        // Arrived from the drawer with a conversation open (2.40.27): open
        // it here too — once the list says it is one of the reader's own.
        const wanted = Number(new URLSearchParams(window.location.search).get("thread"));
        if (wanted > 0) {
            loadThreads().then(() => {
                if (threads.some((thread) => thread.id === wanted)) openThread(wanted);
            });
        }
    }
    // Live updates (2.38.0): a message in one of my conversations is read at
    // once; the timers below remain the fallback.
    onRealtime(["chat"], () => { pollThreads(); if (isOpen()) pollActiveThread(); }, {whenBusy: true, delay: 100});
    setInterval(pollThreads, THREAD_LIST_POLL_MS);
    setInterval(pollActiveThread, ACTIVE_THREAD_POLL_MS);
}
