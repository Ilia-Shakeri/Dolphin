import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDate} from "dolphin/core/jalali.js";
import {clearMessages, errorText, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {appendCell} from "dolphin/ui/table.js";

/**
 * The «پشتیبان‌گیری و بازگردانی» section of `/settings/` (a card and a
 * dialog since 2.23.2).
 *
 * Rendered only for a Platform Admin on a deployment whose
 * `panel_backup` feature is on, so this returns immediately everywhere
 * else. The card shows a summary; «مدیریت پشتیبان‌ها» opens one dialog
 * whose home lists three sections — history and download, a new backup,
 * a restore — each opened inside the same dialog, with «بازگشت» home.
 *
 * Nothing here performs a backup or a restore; see `common/backups.py`
 * for why the web container cannot. Every button asks, and the job list
 * shows what the agent did about it — including "waiting", which is what
 * a deployment that has not started the agent will keep seeing, on
 * purpose.
 */
export function setupBackupSection() {
    const section = document.getElementById("panel-backups");
    const dialog = document.getElementById("backup-dialog");
    if (!section || !dialog) return;
    const loading = document.getElementById("backup-loading");
    const unavailable = document.getElementById("backup-unavailable");
    const summary = document.getElementById("backup-summary");
    const rows = document.getElementById("backup-rows");
    const empty = document.getElementById("backup-empty");
    const jobRows = document.getElementById("backup-job-rows");
    const jobsEmpty = document.getElementById("backup-jobs-empty");
    const createForm = document.getElementById("backup-create-form");
    const createStatus = document.getElementById("backup-create-status");
    const restoreForm = document.getElementById("backup-restore-form");
    const archiveSelect = document.getElementById("backup-restore-archive");
    const back = dialog.querySelector("[data-backup-back]");
    const title = document.getElementById("backup-dialog-title");
    const TITLES = {
        home: "پشتیبان‌گیری و بازگردانی",
        history: "تاریخچه و دانلود",
        create: "پشتیبان‌گیری تازه",
        restore: "بازگردانی",
    };

    //: While a request is in flight the list is polled, and only then:
    //: a settings page left open all afternoon should not keep asking a
    //: question whose answer stopped changing.
    const POLL_MS = 4000;
    let pollTimer = null;
    let available = false;
    //: The backup this page asked for and should download once the agent
    //: reports it done, if «وقتی آماده شد، دانلود شود» was ticked.
    let awaitingDownload = null;

    function fileSize(bytes) {
        if (bytes === null || bytes === undefined) return "—";
        const units = ["بایت", "کیلوبایت", "مگابایت", "گیگابایت"];
        let value = Number(bytes);
        let unit = 0;
        while (value >= 1024 && unit < units.length - 1) {
            value /= 1024;
            unit += 1;
        }
        const shown = unit === 0 ? String(Math.round(value)) : value.toFixed(1);
        return `${toPersianDigits(shown)} ${units[unit]}`;
    }

    function show(view) {
        dialog.querySelectorAll("[data-backup-view]").forEach((node) => {
            node.hidden = node.dataset.backupView !== view;
        });
        back.hidden = view === "home";
        title.textContent = TITLES[view] || TITLES.home;
        clearMessages(createForm);
        clearMessages(restoreForm);
    }

    function downloadArchive(archive) {
        const link = document.createElement("a");
        link.href = `/api/v1/backups/download/${archive.name}`;
        // `download` rather than a new tab: the response already carries
        // Content-Disposition, and a 400 MB octet-stream opened as a
        // navigation is a blank tab on some browsers.
        link.setAttribute("download", archive.name);
        document.body.appendChild(link);
        link.click();
        link.remove();
    }

    function renderArchives(archives) {
        rows.replaceChildren();
        archives.forEach((archive) => {
            const row = document.createElement("tr");
            appendCell(row, archive.taken_at ? displayDate(archive.taken_at) : archive.name);
            appendCell(row, archive.note || "");
            const size = appendCell(row, fileSize(archive.size_bytes));
            size.dir = "ltr";
            // An archive with no `.sha256` beside it was not published by
            // a Dolphin backup job. It is still listed — hiding a file
            // that is really there would be worse — but it is named for
            // what it is, and it is not offered for a restore.
            const checksum = document.createElement("td");
            const badge = document.createElement("span");
            badge.className = archive.has_checksum ? "badge badge-light-success" : "badge badge-light-warning";
            badge.textContent = archive.has_checksum ? "دارد" : "ندارد";
            checksum.appendChild(badge);
            row.appendChild(checksum);

            const actions = document.createElement("td");
            actions.className = "row-actions";
            const download = document.createElement("a");
            download.className = "btn btn-sm btn-light";
            download.href = `/api/v1/backups/download/${archive.name}`;
            download.setAttribute("download", archive.name);
            download.textContent = "دانلود";
            actions.appendChild(download);
            if (archive.has_checksum) {
                const restore = document.createElement("button");
                restore.type = "button";
                restore.className = "btn btn-sm btn-light-danger";
                restore.textContent = "بازگردانی";
                restore.addEventListener("click", () => {
                    show("restore");
                    restoreForm.elements.source.value = "server";
                    restoreForm.dispatchEvent(new Event("change"));
                    archiveSelect.value = archive.name;
                });
                actions.appendChild(restore);
            }
            row.appendChild(actions);
            rows.appendChild(row);
        });
        empty.hidden = archives.length > 0;

        const chosen = archiveSelect.value;
        archiveSelect.replaceChildren(...archives.filter((archive) => archive.has_checksum).map((archive) => {
            const option = document.createElement("option");
            option.value = archive.name;
            const when = archive.taken_at ? displayDate(archive.taken_at) : archive.name;
            option.textContent = `${when} — ${fileSize(archive.size_bytes)}${archive.note ? ` — ${archive.note}` : ""}`;
            return option;
        }));
        if (chosen) archiveSelect.value = chosen;
    }

    const JOB_BADGE = {
        waiting: "badge-light-primary",
        done: "badge-light-success",
        failed: "badge-light-danger",
        expired: "badge-light-warning",
    };

    function renderJobs(jobs) {
        jobRows.replaceChildren();
        jobs.forEach((job) => {
            const row = document.createElement("tr");
            appendCell(row, job.kind_display || job.kind);
            appendCell(row, job.requested_at ? displayDate(job.requested_at) : "—");
            appendCell(row, job.requested_by || "—");
            const status = document.createElement("td");
            const badge = document.createElement("span");
            badge.className = `badge ${JOB_BADGE[job.status] || "badge-light"}`;
            badge.textContent = job.status_display || job.status;
            status.appendChild(badge);
            row.appendChild(status);
            // The safety backup's own name is the single most useful
            // thing on this row after a restore, so it is shown beside
            // the message rather than left in the audit log.
            const detail = [job.note, job.message, job.archive_name ? `پشتیبان: ${job.archive_name}` : ""]
                .filter(Boolean).join(" — ");
            appendCell(row, detail || "—");
            jobRows.appendChild(row);
        });
        jobsEmpty.hidden = jobs.length > 0;
    }

    function renderSummary(archives, jobs) {
        const latest = archives[0];
        const total = archives.reduce((sum, archive) => sum + (Number(archive.size_bytes) || 0), 0);
        const waiting = jobs.filter((job) => job.status === "waiting").length;
        const set = (key, value) => {
            const node = summary.querySelector(`[data-backup-summary="${key}"]`);
            if (node) node.textContent = value;
        };
        set("latest", latest && latest.taken_at ? displayDate(latest.taken_at) : "—");
        set("count", toPersianDigits(String(archives.length)));
        set("size", archives.length ? fileSize(total) : "—");
        set("waiting", toPersianDigits(String(waiting)));
    }

    function followCreatedBackup(jobs) {
        if (!awaitingDownload) return;
        const job = jobs.find((item) => item.token === awaitingDownload.token);
        if (!job || job.status === "waiting") return;
        createStatus.hidden = false;
        if (job.status === "done" && job.archive_name) {
            createStatus.className = "alert alert-light-success p-4 fs-7 mb-5";
            createStatus.textContent = awaitingDownload.download
                ? "پشتیبان ساخته شد؛ دانلود آن شروع شد."
                : "پشتیبان ساخته شد و در «تاریخچه و دانلود» آمده است.";
            if (awaitingDownload.download) downloadArchive({name: job.archive_name});
        } else {
            createStatus.className = "alert alert-light-danger p-4 fs-7 mb-5";
            createStatus.textContent = job.message || "ساخت پشتیبان ناموفق بود.";
        }
        awaitingDownload = null;
    }

    async function refresh() {
        let data;
        try {
            data = await apiRequest("/api/v1/backups/");
        } catch (error) {
            loading.hidden = true;
            unavailable.hidden = false;
            unavailable.textContent = errorText(error);
            return;
        }
        loading.hidden = true;
        if (!data.available) {
            available = false;
            summary.hidden = true;
            unavailable.hidden = false;
            unavailable.textContent = data.detail || "حجم پشتیبان‌ها روی این استقرار در دسترس نیست.";
            return;
        }
        available = true;
        unavailable.hidden = true;
        summary.hidden = false;
        const archives = data.archives || [];
        const jobs = data.jobs || [];
        renderSummary(archives, jobs);
        renderArchives(archives);
        renderJobs(jobs);
        followCreatedBackup(jobs);

        const pending = jobs.some((job) => job.status === "waiting");
        window.clearTimeout(pollTimer);
        if (pending) pollTimer = window.setTimeout(refresh, POLL_MS);
    }

    document.getElementById("backup-open")?.addEventListener("click", () => {
        if (!available) {
            globalMessage(unavailable.textContent || "حجم پشتیبان‌ها روی این استقرار در دسترس نیست.");
            return;
        }
        show("home");
        dialog.showModal();
        refresh();
    });
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    dialog.querySelectorAll("[data-backup-open]").forEach((button) => {
        button.addEventListener("click", () => show(button.dataset.backupOpen));
    });
    back.addEventListener("click", () => show("home"));

    createForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(createForm, async () => {
            const job = await apiRequest("/api/v1/backups/", {
                method: "POST",
                body: {note: document.getElementById("backup-note").value},
            });
            awaitingDownload = {token: job.token, download: document.getElementById("backup-download-when-ready").checked};
            createForm.elements.note.value = "";
            createStatus.hidden = false;
            createStatus.className = "alert alert-light-primary p-4 fs-7 mb-5";
            createStatus.textContent = "درخواست ثبت شد؛ عامل پشتیبان در حال ساخت آن است…";
            await refresh();
        });
    });

    restoreForm.addEventListener("change", () => {
        const source = restoreForm.elements.source.value;
        restoreForm.querySelectorAll("[data-restore-source]").forEach((node) => {
            node.hidden = node.dataset.restoreSource !== source;
        });
    });

    restoreForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearMessages(restoreForm);
        const submit = document.getElementById("backup-restore-submit");
        const body = new FormData();
        body.set("confirm", restoreForm.elements.confirm.value);
        if (restoreForm.elements.source.value === "server") {
            body.set("archive_name", archiveSelect.value);
        } else {
            const file = document.getElementById("backup-restore-file").files[0];
            if (file) body.set("archive", file);
        }
        submit.classList.add("disabled");
        try {
            // `raw`, so the FormData keeps its own multipart boundary —
            // a dump is far too large to serialise any other way, and
            // apiRequest already knows not to set Content-Type for one.
            await apiRequest("/api/v1/backups/restore/", {method: "POST", body, raw: true});
        } catch (error) {
            showError(error, restoreForm);
            return;
        } finally {
            submit.classList.remove("disabled");
        }
        restoreForm.reset();
        restoreForm.dispatchEvent(new Event("change"));
        show("history");
        globalMessage("درخواست بازگردانی ثبت شد. وضعیت آن در «درخواست‌های اخیر» دیده می‌شود.", true);
        refresh();
    });

    refresh();
}
