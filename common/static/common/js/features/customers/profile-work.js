import {apiRequest} from "dolphin/core/api.js";
import {apiDateTime, displayDate} from "dolphin/core/jalali.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {appendCell, pageRangeLabel} from "dolphin/ui/table.js";
import {removeWithMotion, trashButton} from "dolphin/ui/trash.js";

const TASK_STATUS_BADGE = {open: "badge-light-primary", done: "badge-light-success", cancelled: "badge-light"};

/**
 * «وظایف»: a customer's tasks are the ones about them, a colleague's the
 * ones assigned to them — within the reader's own task scope.
 */
export function setupTasksTab(personType, personId) {
    const loadingNode = document.getElementById("profile-tasks-loading");
    const empty = document.getElementById("profile-tasks-empty");
    const wrap = document.getElementById("profile-tasks-table-wrap");
    const body = document.getElementById("profile-tasks-table-body");
    const pagination = document.getElementById("profile-tasks-pagination");
    const previous = document.getElementById("profile-tasks-prev");
    const next = document.getElementById("profile-tasks-next");
    const status = document.getElementById("profile-tasks-status");
    let currentPage = 1;

    async function act(task, verb, button) {
        if (verb === "cancel" && !await confirmDialog("این وظیفه لغو شود؟")) return;
        button.disabled = true;
        clearMessages();
        try {
            const url = {
                complete: `/api/v1/tasks/${task.id}/complete/`,
                cancel: `/api/v1/tasks/${task.id}/cancel/`,
                reopen: `/api/v1/tasks/${task.id}/reopen/`,
            }[verb];
            await apiRequest(url, {method: "POST", body: {}});
            globalMessage({complete: "وظیفه انجام‌شده ثبت شد.", cancel: "وظیفه لغو شد.", reopen: "وظیفه دوباره باز شد."}[verb], true);
            await load(currentPage);
        } catch (error) {
            button.disabled = false;
            showError(error);
        }
    }

    function actionButton(label, className, handler) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `btn btn-sm ${className}`;
        button.textContent = label;
        button.addEventListener("click", () => handler(button));
        return button;
    }

    function taskRow(task) {
        const row = document.createElement("tr");
        const title = document.createElement("td");
        const strong = document.createElement("span");
        strong.className = "d-block fw-semibold text-gray-900";
        strong.textContent = task.title;
        title.appendChild(strong);
        if (task.notes) {
            const notes = document.createElement("span");
            notes.className = "d-block text-muted fs-7 text-break";
            notes.textContent = task.notes;
            title.appendChild(notes);
        }
        row.appendChild(title);
        appendCell(row, task.assignee_display);
        const due = appendCell(row, task.due_at ? displayDate(task.due_at) : "");
        if (task.overdue) {
            const badge = document.createElement("span");
            badge.className = "badge badge-light-danger fs-8 ms-2";
            badge.textContent = "سررسید گذشته";
            due.appendChild(badge);
        }
        const statusCell = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = `badge ${TASK_STATUS_BADGE[task.status] || "badge-light"}`;
        badge.textContent = task.status_display;
        statusCell.appendChild(badge);
        row.appendChild(statusCell);
        const actions = document.createElement("td");
        actions.className = "row-actions";
        if (task.status === "open") {
            actions.append(
                actionButton("انجام شد", "btn-light-success", (button) => act(task, "complete", button)),
                actionButton("لغو", "btn-light", (button) => act(task, "cancel", button)),
            );
        } else {
            actions.append(actionButton("بازکردن دوباره", "btn-light", (button) => act(task, "reopen", button)));
        }
        row.appendChild(actions);
        return row;
    }

    async function load(page = 1) {
        loadingNode.hidden = false;
        empty.hidden = true;
        wrap.hidden = true;
        pagination.hidden = true;
        try {
            const query = new URLSearchParams({page: String(page)});
            if (status.value) query.set("status", status.value);
            if (personType === "user") {
                query.set("assignee", String(personId));
            } else {
                query.set("person_type", personType);
                query.set("person_id", String(personId));
            }
            const data = await apiRequest(`/api/v1/tasks/?${query}`);
            body.replaceChildren(...data.results.map(taskRow));
            loadingNode.hidden = true;
            if (!data.results.length) { empty.hidden = false; return; }
            wrap.hidden = false;
            currentPage = page;
            previous.disabled = !data.previous;
            next.disabled = !data.next;
            document.getElementById("profile-tasks-page-label").textContent = pageRangeLabel(data, page);
            pagination.hidden = !data.previous && !data.next;
        } catch (error) {
            loadingNode.hidden = true;
            showError(error);
        }
    }

    previous.addEventListener("click", () => load(currentPage - 1));
    next.addEventListener("click", () => load(currentPage + 1));
    status.addEventListener("change", () => load(1));
    document.addEventListener("profile:task-created", () => load(1));
    return load();
}

/** «وظیفهٔ تازه» — from the header's quick action or the tasks tab. */
export function setupTaskDialog(personType, personId) {
    const dialog = document.getElementById("profile-task-dialog");
    const form = document.getElementById("profile-task-form");
    if (!dialog || !form) return;
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    document.addEventListener("click", (event) => {
        if (!event.target.closest('[data-profile-action="add-task"]')) return;
        form.reset();
        clearMessages(form);
        dialog.showModal();
        document.getElementById("profile-task-title-input").focus();
    });
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const data = new FormData(form);
            const typed = String(data.get("due_at") || "").trim();
            const due = typed ? apiDateTime(typed) : null;
            if (typed && !due) throw new Error("سررسید خوانده نشد؛ قالب باید ۱۴۰۵/۰۵/۲۵ ۱۴:۳۰ باشد.");
            await apiRequest(form.action, {
                method: "POST",
                body: {
                    title: String(data.get("title") || ""),
                    notes: String(data.get("notes") || ""),
                    due_at: due,
                    assignee: Number(data.get("assignee")),
                    person_type: personType,
                    person_id: Number(personId),
                },
            });
            dialog.close();
            globalMessage("وظیفه ثبت شد.", true);
            document.dispatchEvent(new CustomEvent("profile:task-created"));
        });
    });
}

/** «یادداشت‌ها» — newest first, written here, edited by their author. */
export function setupNotesTab(personType, personId) {
    const list = document.getElementById("profile-notes-list");
    if (!list) return null;
    const loadingNode = document.getElementById("profile-notes-loading");
    const empty = document.getElementById("profile-notes-empty");
    const failed = document.getElementById("profile-notes-error");
    const more = document.getElementById("profile-notes-more");
    const form = document.getElementById("profile-note-form");
    let nextUrl = null;

    function refreshEmpty() {
        const any = list.children.length > 0;
        list.hidden = !any;
        empty.hidden = any;
    }

    function noteCard(note) {
        const item = document.createElement("article");
        item.className = "border border-gray-300 border-dashed rounded p-5";
        const head = document.createElement("div");
        head.className = "d-flex flex-wrap align-items-center justify-content-between gap-2 mb-2";
        const who = document.createElement("div");
        const author = document.createElement("span");
        author.className = "fw-bold text-gray-900 me-2";
        author.textContent = note.author_display;
        const when = document.createElement("span");
        when.className = "text-muted fs-7";
        // `created_at` and `updated_at` are stamped microseconds apart
        // on creation; only a real later edit is worth saying so.
        const edited = new Date(note.updated_at) - new Date(note.created_at) > 1000;
        when.textContent = displayDate(note.created_at) + (edited ? " (ویرایش‌شده)" : "");
        who.append(author, when);
        const tools = document.createElement("div");
        tools.className = "d-flex gap-2";
        const text = document.createElement("p");
        text.className = "text-gray-800 mb-0 text-break";
        text.style.whiteSpace = "pre-line";
        text.textContent = note.body;

        if (note.can_edit) {
            const edit = document.createElement("button");
            edit.type = "button";
            edit.className = "btn btn-sm btn-light";
            edit.textContent = "ویرایش";
            edit.addEventListener("click", () => {
                const editor = document.createElement("form");
                editor.noValidate = true;
                const area = document.createElement("textarea");
                area.className = "form-control form-control-solid";
                area.name = "body";
                area.rows = 3;
                area.maxLength = 4000;
                area.value = note.body;
                area.setAttribute("aria-label", "متن یادداشت");
                const error = document.createElement("p");
                error.className = "text-danger fs-8 mt-1 mb-0";
                error.dataset.errorFor = "body";
                const buttons = document.createElement("div");
                buttons.className = "d-flex justify-content-end gap-2 mt-3";
                const cancel = document.createElement("button");
                cancel.type = "button";
                cancel.className = "btn btn-sm btn-light";
                cancel.textContent = "انصراف";
                const save = document.createElement("button");
                save.type = "submit";
                save.className = "btn btn-sm btn-primary";
                save.textContent = "ذخیره";
                buttons.append(cancel, save);
                editor.append(area, error, buttons);
                text.replaceWith(editor);
                area.focus();
                cancel.addEventListener("click", () => editor.replaceWith(text));
                editor.addEventListener("submit", (event) => {
                    event.preventDefault();
                    withSubmit(editor, async () => {
                        const saved = await apiRequest(`/api/v1/person-notes/${note.id}/`, {method: "PATCH", body: {body: area.value}});
                        item.replaceWith(noteCard(saved));
                        globalMessage("یادداشت ذخیره شد.", true);
                    });
                });
            });
            tools.appendChild(edit);
        }
        if (note.can_delete) {
            const remove = trashButton("حذف یادداشت");
            remove.classList.add("btn-sm");
            remove.addEventListener("click", async () => {
                if (!await confirmDialog("این یادداشت برای همیشه حذف شود؟")) return;
                remove.disabled = true;
                clearMessages();
                try {
                    await apiRequest(`/api/v1/person-notes/${note.id}/`, {method: "DELETE"});
                    await removeWithMotion(item);
                    refreshEmpty();
                    globalMessage("یادداشت حذف شد.", true);
                } catch (error) {
                    remove.disabled = false;
                    showError(error);
                }
            });
            tools.appendChild(remove);
        }
        head.append(who, tools);
        item.append(head, text);
        return item;
    }

    async function load(url) {
        try {
            const data = await apiRequest(url);
            list.append(...data.results.map(noteCard));
            nextUrl = data.next;
            more.hidden = !nextUrl;
            loadingNode.hidden = true;
            refreshEmpty();
        } catch (error) {
            loadingNode.hidden = true;
            failed.hidden = false;
        }
    }

    more.addEventListener("click", () => { if (nextUrl) load(nextUrl); });
    form?.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const note = await apiRequest(`/api/v1/profiles/${personType}/${personId}/notes/`, {
                method: "POST",
                body: {body: form.elements.namedItem("body").value},
            });
            list.prepend(noteCard(note));
            form.reset();
            refreshEmpty();
            globalMessage("یادداشت ثبت شد.", true);
        });
    });
    return load(`/api/v1/profiles/${personType}/${personId}/notes/`);
}
