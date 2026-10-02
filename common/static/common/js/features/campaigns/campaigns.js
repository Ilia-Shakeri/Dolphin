import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDate, displayDay} from "dolphin/core/jalali.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {moneyOrNull} from "dolphin/core/money.js";
import {setupPagedList} from "dolphin/ui/lists.js";
import {appendCell, appendDetailLink} from "dolphin/ui/table.js";

const STATUS_BADGES = {
    draft: "badge-light",
    active: "badge-light-success",
    paused: "badge-light-warning",
    finished: "badge-light-primary",
    archived: "badge-light-danger",
};

export function campaignStatusBadge(status, label) {
    const badge = document.createElement("span");
    badge.className = `badge ${STATUS_BADGES[status] || "badge-light"}`;
    badge.textContent = label;
    return badge;
}

function campaignRow(campaign) {
    const row = document.createElement("tr");
    appendCell(row, campaign.name);
    appendCell(row, campaign.channel_display);
    const state = document.createElement("td");
    state.append(campaignStatusBadge(campaign.status, campaign.status_display));
    row.append(state);
    appendCell(row, toPersianDigits(String(campaign.member_count)));
    appendCell(row, campaign.starts_on ? displayDay(campaign.starts_on) : "");
    appendCell(row, campaign.ends_on ? displayDay(campaign.ends_on) : "");
    appendDetailLink(row, `/campaigns/${campaign.id}/`);
    return row;
}

export function setupCampaigns() {
    const form = document.getElementById("campaigns-search-form");
    const controller = setupPagedList({
        key: "campaigns",
        form,
        search: document.getElementById("campaigns-search"),
        endpoint: (page) => {
            const query = new URLSearchParams({page: String(page)});
            const search = document.getElementById("campaigns-search").value.trim();
            if (search) query.set("search", search);
            ["status", "channel"].forEach((name) => {
                const value = document.getElementById(`campaigns-${name}`).value;
                if (value) query.set(name, value);
            });
            return `/api/v1/campaigns/?${query}`;
        },
        renderRow: campaignRow,
    });
    controller?.load();

    const dialog = document.getElementById("create-campaign-dialog");
    const createForm = document.getElementById("create-campaign-form");
    if (!dialog || !createForm) return;
    document.getElementById("open-create-campaign").addEventListener("click", () => {
        createForm.reset();
        clearMessages(createForm);
        dialog.showModal();
    });
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    createForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(createForm, async () => {
            const field = (name) => createForm.elements[name];
            const body = {
                name: field("name").value,
                channel: field("channel").value,
                responsibles: Array.from(field("responsibles").selectedOptions).map((option) => Number(option.value)),
            };
            const starts = apiDate(field("starts_on").value);
            const ends = apiDate(field("ends_on").value);
            if (starts) body.starts_on = starts;
            if (ends) body.ends_on = ends;
            const target = field("target_count").value.trim();
            if (target) body.target_count = Number(target);
            const budget = moneyOrNull(field("budget").value);
            if (budget !== null) body.budget = budget;
            const campaign = await apiRequest("/api/v1/campaigns/", {method: "POST", body});
            dialog.close();
            globalMessage("کمپین ساخته شد.", true);
            window.location.assign(`/campaigns/${campaign.id}/`);
        });
    });
}
