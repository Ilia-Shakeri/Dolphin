import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {displayDay} from "dolphin/core/jalali.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {money} from "dolphin/core/money.js";
import {campaignStatusBadge} from "dolphin/features/campaigns/campaigns.js";
import {setupPagedList} from "dolphin/ui/lists.js";
import {appendCell} from "dolphin/ui/table.js";

const NEXT_STATUS = {
    draft: [["active", "فعال‌سازی", "btn-primary"], ["archived", "بایگانی", "btn-light"]],
    active: [["paused", "توقف", "btn-light-warning"], ["finished", "پایان کمپین", "btn-light-primary"]],
    paused: [["active", "ادامه", "btn-primary"], ["finished", "پایان کمپین", "btn-light-primary"]],
    finished: [["active", "بازگشایی", "btn-light-primary"], ["archived", "بایگانی", "btn-light"]],
    archived: [],
};

const STAGE_CHOICES = [["new", "جدید"], ["contacted", "تماس گرفته‌شده"], ["engaged", "در تعامل"], ["lost", "ازدست‌رفته"]];

export function setupCampaignDetail() {
    const id = document.body.dataset.campaignId;
    const endpoint = `/api/v1/campaigns/${id}/`;
    const content = document.getElementById("campaign-content");
    const membersCard = document.getElementById("campaign-members-card");
    let campaign = null;
    let members = null;

    function renderFacts(value) {
        const facts = document.getElementById("campaign-facts");
        const entries = [
            ["شروع", value.starts_on ? displayDay(value.starts_on) : ""],
            ["پایان", value.ends_on ? displayDay(value.ends_on) : ""],
            ["هدف مخاطب", value.target_count === null ? "" : toPersianDigits(String(value.target_count))],
            ["بودجه", value.budget === undefined || value.budget === null ? "" : money(value.budget)],
            ["مسئولان", (value.responsibles_display || []).join("، ")],
            ["مخاطبان", toPersianDigits(String(value.member_count))],
        ];
        facts.replaceChildren(...entries.flatMap(([label, text]) => {
            const term = document.createElement("dt");
            term.className = "col-sm-3 fw-semibold text-muted mb-3";
            term.textContent = label;
            const detail = document.createElement("dd");
            detail.className = "col-sm-9 mb-3";
            detail.textContent = text || "—";
            return [term, detail];
        }));
    }

    function renderStatusActions(value) {
        const host = document.getElementById("campaign-status-actions");
        if (!host) return;
        host.replaceChildren(...(NEXT_STATUS[value.status] || []).map(([status, label, className]) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = `btn btn-sm ${className}`;
            button.textContent = label;
            button.addEventListener("click", async () => {
                button.disabled = true;
                try {
                    campaign = await apiRequest(`${endpoint}status/`, {method: "POST", body: {status}});
                    render(campaign);
                    globalMessage("وضعیت کمپین به‌روزرسانی شد.", true);
                } catch (error) {
                    showError(error);
                    button.disabled = false;
                }
            });
            return button;
        }));
    }

    function render(value) {
        document.getElementById("campaign-name").textContent = value.name;
        const status = document.getElementById("campaign-status");
        status.replaceWith(Object.assign(campaignStatusBadge(value.status, value.status_display), {id: "campaign-status"}));
        document.getElementById("campaign-channel").textContent = value.channel_display;
        renderFacts(value);
        renderStatusActions(value);
        document.title = `${value.name} | Dolphin`;
    }

    // --- members -------------------------------------------------------
    const lostDialog = document.getElementById("member-lost-dialog");
    const lostForm = document.getElementById("member-lost-form");
    let lostFor = null;

    async function changeStage(member, stage, lostReason = "") {
        await apiRequest(`/api/v1/campaign-members/${member.id}/stage/`, {method: "POST", body: {stage, lost_reason: lostReason}});
        members?.load();
    }

    function memberRow(member) {
        const row = document.createElement("tr");
        appendCell(row, member.full_name);
        appendCell(row, toPersianDigits(member.raw_phone));
        const stageCell = document.createElement("td");
        if (member.stage === "converted") {
            stageCell.append(campaignStatusBadge("active", member.stage_display));
        } else {
            const select = document.createElement("select");
            select.className = "form-select form-select-sm form-select-solid w-175px";
            select.setAttribute("aria-label", `مرحلهٔ ${member.full_name}`);
            STAGE_CHOICES.forEach(([value, label]) => select.append(new Option(label, value, false, value === member.stage)));
            select.addEventListener("change", async () => {
                if (select.value === "lost") {
                    lostFor = member;
                    select.value = member.stage;
                    lostForm.reset();
                    clearMessages(lostForm);
                    lostDialog.showModal();
                    return;
                }
                try { await changeStage(member, select.value); } catch (error) { select.value = member.stage; showError(error); }
            });
            stageCell.append(select);
        }
        row.append(stageCell);
        appendCell(row, member.assigned_to_display);
        appendCell(row, member.was_customer_on_entry ? "از قبل مشتری بوده" : (member.lost_reason || ""));
        return row;
    }

    lostDialog?.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => lostDialog.close()));
    lostForm?.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(lostForm, async () => {
            await changeStage(lostFor, "lost", lostForm.elements.lost_reason.value);
            lostDialog.close();
        });
    });

    members = setupPagedList({
        key: "campaign-members",
        form: null,
        search: null,
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page)});
            const stage = document.getElementById("campaign-members-stage").value;
            if (stage) query.set("stage", stage);
            return `${endpoint}members/?${query}`;
        },
        renderRow: memberRow,
    });
    document.getElementById("campaign-members-stage").addEventListener("change", () => members?.load(1));

    const addDialog = document.getElementById("add-member-dialog");
    const addForm = document.getElementById("add-member-form");
    if (addDialog && addForm) {
        document.getElementById("open-add-member").addEventListener("click", () => {
            addForm.reset();
            clearMessages(addForm);
            addDialog.showModal();
        });
        addDialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => addDialog.close()));
        addForm.addEventListener("submit", (event) => {
            event.preventDefault();
            withSubmit(addForm, async () => {
                const body = {full_name: addForm.elements.full_name.value, raw_phone: addForm.elements.raw_phone.value};
                if (addForm.elements.assigned_to.value) body.assigned_to = Number(addForm.elements.assigned_to.value);
                await apiRequest(`${endpoint}add-member/`, {method: "POST", body});
                addDialog.close();
                globalMessage("مخاطب به کمپین افزوده شد.", true);
                members?.load(1);
            });
        });
    }

    apiRequest(endpoint).then((value) => {
        campaign = value;
        document.getElementById("campaign-loading").hidden = true;
        content.hidden = false;
        membersCard.hidden = false;
        render(value);
        members?.load();
    }).catch((error) => {
        document.getElementById("campaign-loading").hidden = true;
        showError(error);
    });
}
