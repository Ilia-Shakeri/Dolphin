import {apiRequest} from "dolphin/core/api.js";
import {clearMessages, withSubmit} from "dolphin/core/messages.js";

/**
 * Lead and campaign-person stages (2.40.57, BIZ-002) — what a page shows and
 * how a stage is moved.
 *
 * The page embeds both workflows and the lost reasons
 * (`includes/stage_change_dialog.inc` → `#pipeline-config`, from
 * `sales.pipeline.pipeline_payload`). The rules themselves are the server's
 * (`sales.pipeline`): this only asks for what a move needs — a reason from the
 * list for a lost stage, a note for «سایر», a reason to leave a final stage —
 * and shows the server's own refusal under the field it names.
 */

let config = null;

export function pipelineConfig() {
    if (config) return config;
    try {
        config = JSON.parse(document.getElementById("pipeline-config")?.textContent || "null");
    } catch (error) {
        config = null;
    }
    config = config || {stages: {lead: [], campaign: []}, lost_reasons: []};
    return config;
}

export function stagesOf(pipeline) {
    return pipelineConfig().stages[pipeline] || [];
}

export function stageOf(pipeline, key) {
    return stagesOf(pipeline).find((stage) => stage.key === key) || null;
}

/** The theme accent a stage wears: open stages blue, won green, lost red. */
export function stageAccent(kind) {
    return {won: "success", lost: "danger"}[kind] || "primary";
}

/** A stage as a badge — from the record's own `stage_display`/`stage_kind`. */
export function stageBadge(label, kind) {
    const badge = document.createElement("span");
    badge.className = `badge badge-light-${stageAccent(kind)}`;
    badge.textContent = label || "—";
    return badge;
}

/** Fill a `<select>` with a workflow's stages; `only` narrows which. */
export function fillStageSelect(select, pipeline, {only = () => true, keep = []} = {}) {
    stagesOf(pipeline)
        .filter((stage) => (stage.is_active && only(stage)) || keep.includes(stage.key))
        .forEach((stage) => select.append(new Option(stage.label, stage.key)));
}

function needsDetails(current, target) {
    return target?.kind === "lost" || (current && current.kind !== "open");
}

/**
 * Move one record to another stage.
 *
 * `url` is the record's own `stage/` action. With `target` the move is to that
 * stage — straight away when nothing more is needed, through the dialog when
 * a reason is; without it the dialog offers the stages to choose from.
 * Resolves to the updated record, or `null` when the reader closed the dialog.
 */
export function moveStage({url, pipeline, current, target = null, name = ""}) {
    const currentStage = stageOf(pipeline, current);
    const targetStage = target ? stageOf(pipeline, target) : null;
    if (targetStage && !needsDetails(currentStage, targetStage)) {
        return apiRequest(url, {method: "POST", body: {stage: targetStage.key}});
    }
    const dialog = document.getElementById("stage-change-dialog");
    const form = document.getElementById("stage-change-form");
    if (!dialog || !form) return Promise.resolve(null);
    const choose = document.getElementById("stage-change-target");
    const chooseField = document.getElementById("stage-change-target-field");
    const reasonSelect = document.getElementById("stage-change-lost-reason");
    const lostField = document.getElementById("stage-change-lost-field");
    const noteField = document.getElementById("stage-change-note-field");
    const note = document.getElementById("stage-change-note");
    const reopenField = document.getElementById("stage-change-reopen-field");
    const reopen = document.getElementById("stage-change-reason");

    form.reset();
    clearMessages(form);
    // «نام — جدید ← بازنده» when the stage is already chosen (a drop, a select).
    const from = currentStage?.label || current || "—";
    const where = targetStage ? `${from} ← ${targetStage.label}` : `مرحلهٔ کنونی: ${from}`;
    document.getElementById("stage-change-subject").textContent = name ? `${name} — ${where}` : where;
    choose.replaceChildren(new Option("یک مرحله انتخاب کنید", ""));
    fillStageSelect(choose, pipeline, {only: (stage) => stage.manual && stage.key !== current});
    choose.value = targetStage?.key || "";
    chooseField.hidden = Boolean(targetStage);
    reasonSelect.replaceChildren(new Option("یک دلیل انتخاب کنید", ""));
    pipelineConfig().lost_reasons.filter((reason) => reason.is_active)
        .forEach((reason) => reasonSelect.append(new Option(reason.label, reason.key)));

    const sync = () => {
        const chosen = stageOf(pipeline, choose.value);
        const lost = chosen?.kind === "lost";
        lostField.hidden = !lost;
        reasonSelect.required = lost;
        const reason = pipelineConfig().lost_reasons.find((item) => item.key === reasonSelect.value);
        note.required = Boolean(lost && reason?.needs_note);
        noteField.querySelector("label").classList.toggle("required", note.required);
        reopenField.hidden = !(currentStage && currentStage.kind !== "open");
        reopen.required = !reopenField.hidden;
    };
    choose.onchange = sync;
    reasonSelect.onchange = sync;
    sync();

    return new Promise((resolve) => {
        let result = null;
        const onClose = () => {
            dialog.removeEventListener("close", onClose);
            form.removeEventListener("submit", onSubmit);
            resolve(result);
        };
        const onSubmit = (event) => {
            event.preventDefault();
            withSubmit(form, async () => {
                const body = {stage: choose.value, note: note.value, reason: reopen.value};
                if (!lostField.hidden) body.lost_reason = reasonSelect.value;
                result = await apiRequest(url, {method: "POST", body});
                dialog.close();
            });
        };
        dialog.addEventListener("close", onClose);
        form.addEventListener("submit", onSubmit);
        dialog.querySelectorAll("[data-close-dialog]").forEach((button) => { button.onclick = () => dialog.close(); });
        dialog.showModal();
        (chooseField.hidden ? (lostField.hidden ? reopen : reasonSelect) : choose).focus();
    });
}

/** One history row's sentence: «جدید ← تماس اولیه». */
export function historyLine(change) {
    return change.from_label ? `${change.from_label} ← ${change.to_label}` : change.to_label;
}
