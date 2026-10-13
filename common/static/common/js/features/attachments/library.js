import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate} from "dolphin/core/jalali.js";
import {globalMessage, showError} from "dolphin/core/messages.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {removeWithMotion, trashButton} from "dolphin/ui/trash.js";

/** «۲٫۴ مگابایت» / «۸۵۰ کیلوبایت». */
function fileSize(bytes) {
    const size = Number(bytes) || 0;
    if (size >= 1024 * 1024) return `${toPersianDigits((size / 1024 / 1024).toFixed(1)).replace(".", "٫")} مگابایت`;
    return `${toPersianDigits(String(Math.max(1, Math.round(size / 1024))))} کیلوبایت`;
}

function fileIcon(contentType) {
    const pdf = contentType === "application/pdf";
    const icon = document.createElement("span");
    icon.className = `file-library-icon ${pdf ? "is-pdf" : "is-image"}`;
    icon.setAttribute("aria-hidden", "true");
    const glyph = document.createElement("i");
    glyph.className = `di-duotone ${pdf ? "di-document" : "di-picture"} fs-2`;
    glyph.append(...[1, 2].map((path) => Object.assign(document.createElement("span"), {className: `path${path}`})));
    icon.append(glyph);
    return icon;
}

/**
 * «اسناد و پیوست‌ها» (2.40.42, roadmap item 13): the UI kit's file manager
 * over the panel's real attachments — every file the reader may see, newest
 * first, searchable by name and narrowed by the record it hangs on or by kind.
 */
export async function setupAttachmentLibrary() {
    const form = document.getElementById("attachment-library-form");
    setupListFilter("attachment-library");
    const controller = setupPagedList({
        key: "attachment-library",
        form,
        search: document.getElementById("attachment-library-search"),
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page)});
            const search = document.getElementById("attachment-library-search").value.trim();
            if (search) query.set("search", search);
            [["parent", "attachment-library-parent"], ["kind", "attachment-library-kind"]].forEach(([name, id]) => {
                const value = document.getElementById(id).value;
                if (value) query.set(name, value);
            });
            return `/api/v1/attachments/library/?${query}`;
        },
        renderRow: (file) => {
            const row = document.createElement("tr");
            const name = document.createElement("td");
            const who = document.createElement("div");
            who.className = "d-flex align-items-center gap-3";
            const text = document.createElement("div");
            text.className = "d-flex flex-column min-w-0";
            const title = document.createElement("a");
            title.className = "text-gray-900 text-hover-primary fw-semibold text-truncate";
            title.href = `/api/v1/attachments/${file.id}/download/`;
            title.textContent = file.original_filename;
            const size = document.createElement("span");
            size.className = "text-muted fs-8";
            size.textContent = fileSize(file.size_bytes);
            text.append(title, size);
            who.append(fileIcon(file.content_type), text);
            name.append(who);

            const parent = document.createElement("td");
            const kind = document.createElement("span");
            kind.className = "badge badge-light fs-8 me-2";
            kind.textContent = file.parent_type_display;
            const link = document.createElement("a");
            link.href = file.parent_url;
            link.className = "text-gray-800 text-hover-primary";
            link.textContent = file.parent_name;
            parent.append(kind, link);

            const uploaded = document.createElement("td");
            uploaded.className = "text-gray-700";
            uploaded.textContent = [file.uploaded_by_name, displayDate(file.uploaded_at)].filter(Boolean).join(" · ");

            const actions = document.createElement("td");
            actions.className = "text-end text-nowrap";
            const download = document.createElement("a");
            download.className = "btn btn-sm btn-light-primary";
            download.href = `/api/v1/attachments/${file.id}/download/`;
            download.textContent = "دریافت";
            actions.append(download);
            if (file.can_delete) {
                const remove = trashButton(`حذف ${file.original_filename}`);
                remove.classList.add("ms-2");
                remove.addEventListener("click", async () => {
                    if (!await confirmDialog(`«${file.original_filename}» برای همیشه حذف شود؟`)) return;
                    remove.disabled = true;
                    try {
                        await apiRequest(`/api/v1/attachments/${file.id}/delete/`, {method: "POST"});
                        await removeWithMotion(row);
                        globalMessage("فایل حذف شد.", true);
                        controller.load(controller.page, {quiet: true});
                    } catch (error) {
                        remove.disabled = false;
                        showError(error);
                    }
                });
                actions.append(remove);
            }
            row.append(name, parent, uploaded, actions);
            return row;
        },
    });
    await controller?.load();
}
