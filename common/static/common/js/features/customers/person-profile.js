import {apiRequest} from "dolphin/core/api.js";
import {setupProfileCards} from "dolphin/features/customers/profile-cards.js";
import {customerProfileLoaders} from "dolphin/features/customers/profile-customer.js";
import {setupUserSessions, userProfileLoaders} from "dolphin/features/customers/profile-user.js";
import {setupTaskDialog} from "dolphin/features/customers/profile-work.js";
import {liveRecord} from "dolphin/ui/live-record.js";
import {openPermissionsDialog, setupPermissionsDialog} from "dolphin/ui/permissions-dialog.js";
import {registerPopover} from "dolphin/ui/popover.js";
import {setupProfileTabs} from "dolphin/ui/profile-tabs.js";

export function setupPersonProfile() {
    const personType = document.body.dataset.personType;
    const personId = document.body.dataset.personId;
    if (!personType || !personId) return;

    // «بیشتر» — the theme's dropdown, opened the way every other panel
    // in the shell is (`registerPopover`).
    const more = registerPopover({
        toggle: document.getElementById("profile-more-toggle"),
        panel: document.getElementById("profile-more-menu"),
    });
    document.getElementById("profile-more-menu")?.addEventListener("click", (event) => {
        if (event.target.closest("a, button")) more?.close();
    });

    // The permission matrix lives in a dialog shared with User
    // Management; any `data-profile-action="permissions"` opens it.
    if (document.getElementById("permissions-dialog")) setupPermissionsDialog();
    document.addEventListener("click", (event) => {
        const button = event.target.closest('[data-profile-action="permissions"]');
        if (!button) return;
        openPermissionsDialog(button.dataset.userId, button.dataset.userName);
    });

    const loaders = personType === "customer"
        ? customerProfileLoaders(personId)
        : userProfileLoaders(personId);
    setupProfileTabs(loaders);
    if (personType !== "customer") setupUserSessions(personId);
    const cards = setupProfileCards(personType, personId);
    setupTaskDialog(personType, personId);
    // Live (2.40.41): the stat cards and, on a customer, the record itself
    // redraw in place when something they count changes elsewhere.
    liveRecord({
        read: async () => {
            const [record, cardData] = await Promise.all([
                personType === "customer" ? apiRequest(`/api/v1/customers/${personId}/`) : null,
                cards ? cards.readCards() : null,
            ]);
            return {record, cards: cardData};
        },
        draw: ({record, cards: cardData}) => {
            if (record) document.dispatchEvent(new CustomEvent("dolphin:customer-record", {detail: record}));
            if (cardData) cards.paintCards(cardData);
        },
    });
    const scoreDialog = document.getElementById("profile-score-dialog");
    scoreDialog?.querySelectorAll("[data-close-dialog]").forEach((button) => {
        button.addEventListener("click", () => scoreDialog.close());
    });
}
