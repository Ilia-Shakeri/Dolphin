import {apiRequest} from "dolphin/core/api.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {stageBadge} from "dolphin/ui/pipeline.js";
import {appendCell} from "dolphin/ui/table.js";

/**
 * Settings → «شخصی‌سازی»: the stage workflows and the lost reasons (2.40.57,
 * BIZ-002). A stage or a reason is added, renamed, moved and turned off —
 * never deleted, so no record loses the stage it is in. Every rule is
 * `sales.pipeline`'s; this only shows what the server answers.
 */
export function setupPipelineSection() {
    const stagesBody = document.getElementById("pipeline-stages-body");
    if (!stagesBody) return;
    const reasonsBody = document.getElementById("lost-reasons-body");
    const section = document.getElementById("pipeline-section-select");
    const stageDialog = document.getElementById("pipeline-stage-dialog");
    const stageForm = document.getElementById("pipeline-stage-form");
    const reasonDialog = document.getElementById("lost-reason-dialog");
    const reasonForm = document.getElementById("lost-reason-form");
    let data = null;
    let editingStage = null;
    let editingReason = null;

    function iconButton(icon, label, onClick, disabled) {
        const node = document.createElement("button");
        node.type = "button";
        node.className = "btn btn-sm btn-icon btn-light";
        node.setAttribute("aria-label", label);
        node.disabled = disabled;
        const glyph = document.createElement("i");
        glyph.className = `di-outline ${icon} fs-4`;
        glyph.setAttribute("aria-hidden", "true");
        node.append(glyph);
        node.addEventListener("click", onClick);
        return node;
    }

    function textButton(label, onClick) {
        const node = document.createElement("button");
        node.type = "button";
        node.className = "btn btn-sm btn-light";
        node.textContent = label;
        node.addEventListener("click", onClick);
        return node;
    }

    function onOff(active) {
        const cell = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = `badge badge-light-${active ? "success" : "secondary"}`;
        badge.textContent = active ? "روشن" : "خاموش";
        cell.append(badge);
        return cell;
    }

    function renderStages() {
        const stages = data.stages[section.value] || [];
        const open = stages.filter((stage) => stage.kind === "open");
        stagesBody.replaceChildren(...stages.map((stage) => {
            const row = document.createElement("tr");
            appendCell(row, stage.label);
            const kind = document.createElement("td");
            kind.append(stageBadge(stage.kind_display, stage.kind));
            row.append(kind);
            appendCell(row, stage.qualifies ? "بله" : "—");
            row.append(onOff(stage.is_active));
            const actions = document.createElement("td");
            actions.className = "text-end text-nowrap";
            const index = open.indexOf(stage);
            // A final stage keeps its place at the end: its arrows are shown
            // off, so every row lines up and the rule is visible.
            const fixed = stage.kind !== "open";
            actions.append(
                iconButton("di-arrow-up", `بالا بردن «${stage.label}»`, () => moveStage(stage, "up"), fixed || index === 0), " ",
                iconButton("di-arrow-down", `پایین بردن «${stage.label}»`, () => moveStage(stage, "down"), fixed || index === open.length - 1), " ",
                textButton("ویرایش", () => openStage(stage)),
            );
            row.append(actions);
            return row;
        }));
        document.getElementById("pipeline-stages-loading").hidden = true;
        document.getElementById("pipeline-stages-table-wrap").hidden = false;
    }

    function renderReasons() {
        const reasons = data.lost_reasons;
        reasonsBody.replaceChildren(...reasons.map((reason, index) => {
            const row = document.createElement("tr");
            appendCell(row, reason.label);
            appendCell(row, reason.needs_note ? "اجباری" : "اختیاری");
            row.append(onOff(reason.is_active));
            const actions = document.createElement("td");
            actions.className = "text-end text-nowrap";
            actions.append(
                iconButton("di-arrow-up", `بالا بردن «${reason.label}»`, () => moveReason(reason, "up"), index === 0), " ",
                iconButton("di-arrow-down", `پایین بردن «${reason.label}»`, () => moveReason(reason, "down"), index === reasons.length - 1), " ",
                textButton("ویرایش", () => openReason(reason)),
            );
            row.append(actions);
            return row;
        }));
        document.getElementById("lost-reasons-loading").hidden = true;
        document.getElementById("lost-reasons-table-wrap").hidden = false;
    }

    function render(value) {
        data = value;
        renderStages();
        renderReasons();
    }

    async function run(task) {
        try { render(await task()); } catch (error) { showError(error); }
    }

    const moveStage = (stage, direction) => run(() => apiRequest(`/api/v1/pipeline/stages/${stage.id}/move/`, {method: "POST", body: {direction}}));
    const moveReason = (reason, direction) => run(() => apiRequest(`/api/v1/pipeline/lost-reasons/${reason.id}/move/`, {method: "POST", body: {direction}}));

    function openStage(stage = null) {
        editingStage = stage;
        stageForm.reset();
        clearMessages(stageForm);
        document.getElementById("pipeline-stage-label").value = stage?.label || "";
        const qualifies = document.getElementById("pipeline-stage-qualifies");
        qualifies.checked = Boolean(stage?.qualifies);
        qualifies.disabled = stage?.kind === "lost";
        // The final stages stay on: their switch is not offered.
        document.getElementById("pipeline-stage-active-wrap").hidden = !stage || stage.kind !== "open";
        document.getElementById("pipeline-stage-active").checked = stage ? stage.is_active : true;
        stageDialog.showModal();
    }

    function openReason(reason = null) {
        editingReason = reason;
        reasonForm.reset();
        clearMessages(reasonForm);
        document.getElementById("lost-reason-label").value = reason?.label || "";
        const needsNote = document.getElementById("lost-reason-needs-note");
        needsNote.checked = Boolean(reason?.needs_note);
        // «سایر» always asks for a note and is always on.
        const fixed = reason?.key === "other";
        needsNote.disabled = fixed;
        document.getElementById("lost-reason-active-wrap").hidden = !reason || fixed;
        document.getElementById("lost-reason-active").checked = reason ? reason.is_active : true;
        reasonDialog.showModal();
    }

    stageForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(stageForm, async () => {
            const body = {label: document.getElementById("pipeline-stage-label").value};
            const qualifies = document.getElementById("pipeline-stage-qualifies");
            if (!qualifies.disabled) body.qualifies = qualifies.checked;
            if (editingStage) {
                if (!document.getElementById("pipeline-stage-active-wrap").hidden) {
                    body.is_active = document.getElementById("pipeline-stage-active").checked;
                }
                render(await apiRequest(`/api/v1/pipeline/stages/${editingStage.id}/`, {method: "PATCH", body}));
            } else {
                render(await apiRequest("/api/v1/pipeline/stages/", {method: "POST", body: {...body, pipeline: section.value}}));
            }
            stageDialog.close();
            globalMessage("مرحله ذخیره شد.", true);
        });
    });

    reasonForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(reasonForm, async () => {
            const body = {label: document.getElementById("lost-reason-label").value};
            const needsNote = document.getElementById("lost-reason-needs-note");
            if (!needsNote.disabled) body.needs_note = needsNote.checked;
            if (editingReason) {
                if (!document.getElementById("lost-reason-active-wrap").hidden) {
                    body.is_active = document.getElementById("lost-reason-active").checked;
                }
                render(await apiRequest(`/api/v1/pipeline/lost-reasons/${editingReason.id}/`, {method: "PATCH", body}));
            } else {
                render(await apiRequest("/api/v1/pipeline/lost-reasons/", {method: "POST", body}));
            }
            reasonDialog.close();
            globalMessage("دلیل ذخیره شد.", true);
        });
    });

    section.addEventListener("change", () => { if (data) renderStages(); });
    document.getElementById("pipeline-stage-add").addEventListener("click", () => openStage());
    document.getElementById("lost-reason-add").addEventListener("click", () => openReason());
    [stageDialog, reasonDialog].forEach((dialog) => dialog.querySelectorAll("[data-close-dialog]")
        .forEach((node) => node.addEventListener("click", () => dialog.close())));

    apiRequest("/api/v1/pipeline/").then(render).catch((error) => {
        document.getElementById("pipeline-stages-loading").textContent = "مرحله‌ها دریافت نشد.";
        document.getElementById("lost-reasons-loading").textContent = "دلیل‌ها دریافت نشد.";
        showError(error);
    });
}
