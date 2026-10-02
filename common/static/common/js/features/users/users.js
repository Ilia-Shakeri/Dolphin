import {apiRequest} from "dolphin/core/api.js";
import {ROLE_LABELS} from "dolphin/core/config.js";
import {clearMessages, formPayload, showError, withSubmit} from "dolphin/core/messages.js";
import {bindLiveSearch, setupRowSelection} from "dolphin/ui/lists.js";
import {openPermissionsDialog, setupPermissionsDialog} from "dolphin/ui/permissions-dialog.js";
import {appendStatusCell, pageRangeLabel} from "dolphin/ui/table.js";
import {renderWizardReview, selectedOptionText, setupWizard} from "dolphin/ui/wizard.js";

function userRow(user) {
    const row = document.createElement("tr");
    const displayName = [user.first_name, user.last_name].filter(Boolean).join(" ") || "—";
    const workstream = user.workstream === "after_sales" ? "خدمات پس از فروش" : "فروش و مرکز ارتباطات";
    const cells = [user.username, displayName, `${ROLE_LABELS[user.role] || "—"} — ${workstream}`];
    cells.forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.appendChild(cell); });
    // The theme's badge, like every other list's status column (product-
    // owner request 2026-09-20). This page had kept a local `.status`
    // class that painted nothing but bold text, so user administration was
    // the one table where «غیرفعال» did not stand out from «فعال» at a
    // glance. `appendStatusCell` is the shared helper the customers,
    // products, categories, phones and warehouses tables already use.
    appendStatusCell(row, user.is_active);
    const actionCell = document.createElement("td");
    actionCell.className = "row-actions";
    // One profile since 2.19.0: what «پروفایل» and «جزئیات» used to
    // open separately are tabs of the same page now.
    const profileLink = document.createElement("a");
    profileLink.className = "btn btn-sm btn-light";
    profileLink.href = `/users/${user.id}/`;
    profileLink.textContent = "پروفایل";
    actionCell.appendChild(profileLink);
    const permissionsButton = document.createElement("button");
    permissionsButton.className = "btn btn-sm btn-light";
    permissionsButton.type = "button";
    permissionsButton.dataset.permissionsButton = "";
    permissionsButton.dataset.userId = String(user.id);
    permissionsButton.dataset.userName = displayName === "—" ? user.username : displayName;
    permissionsButton.textContent = "مجوزها";
    actionCell.appendChild(permissionsButton);
    row.appendChild(actionCell);
    return row;
}

export function setupUsers() {
    const searchInput = document.getElementById("user-search");
    const tableWrap = document.getElementById("users-table-wrap");
    const tableBody = document.getElementById("users-table-body");
    const loading = document.getElementById("users-loading");
    const empty = document.getElementById("users-empty");
    const pagination = document.getElementById("users-pagination");
    const prev = document.getElementById("users-prev");
    const next = document.getElementById("users-next");
    let currentPage = 1;
    let search = "";
    const selection = setupRowSelection({key: "users", body: tableBody, reload: () => loadUsers(currentPage)});

    async function loadUsers(page = 1) {
        loading.hidden = false;
        empty.hidden = true;
        tableWrap.hidden = true;
        pagination.hidden = true;
        clearMessages();
        selection.resetSelection();
        try {
            const query = new URLSearchParams({page: String(page)});
            if (search) query.set("search", search);
            const data = await apiRequest(`/api/v1/users/?${query}`);
            tableBody.replaceChildren(...data.results.map((item) => selection.decorateRow(item, userRow(item))));
            loading.hidden = true;
            if (!data.results.length) { empty.hidden = false; return; }
            tableWrap.hidden = false;
            currentPage = page;
            prev.disabled = !data.previous;
            next.disabled = !data.next;
            document.getElementById("users-page-label").textContent = pageRangeLabel(data, page);
            pagination.hidden = !data.previous && !data.next;
        } catch (error) {
            loading.hidden = true;
            showError(error);
        }
    }

    bindLiveSearch(searchInput, () => {
        search = searchInput.value.trim();
        loadUsers(1);
    });
    prev.addEventListener("click", () => loadUsers(currentPage - 1));
    next.addEventListener("click", () => loadUsers(currentPage + 1));

    const dialog = document.getElementById("create-user-dialog");
    const createForm = document.getElementById("create-user-form");
    function renderCreateUserReview() {
        renderWizardReview(document.getElementById("create-user-review"), [
            ["نام کاربری", document.getElementById("create-username").value],
            ["گذرواژه", "•".repeat(Math.min(document.getElementById("create-password").value.length, 12)) || "—"],
            ["نام", document.getElementById("create-first-name").value || "—"],
            ["نام خانوادگی", document.getElementById("create-last-name").value || "—"],
            ["ایمیل", document.getElementById("create-email").value || "—"],
            ["تلفن", document.getElementById("create-phone").value || "—"],
            ["نقش", selectedOptionText(document.getElementById("create-role"))],
            ["حوزه کاری", selectedOptionText(document.getElementById("create-workstream"))],
        ]);
    }
    const createUserWizard = setupWizard(dialog, {onReachLastStep: renderCreateUserReview});
    document.getElementById("open-create-user").addEventListener("click", () => {
        createForm.reset();
        clearMessages(createForm);
        syncCreateWorkstream();
        createUserWizard?.goFirst();
        dialog.showModal();
    });
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));

    // Only a Sales Agent may run the after-sales workstream — the same
    // rule `setupUserInfoTab` enforces on the profile form, applied here so picking
    // any other role locks the field back to the ordinary sales queue
    // instead of letting the create call fail on it.
    const createRole = document.getElementById("create-role");
    const createWorkstream = document.getElementById("create-workstream");
    function syncCreateWorkstream() {
        const afterSalesOption = createWorkstream.querySelector('option[value="after_sales"]');
        const isAgent = createRole.value === "sales_agent";
        afterSalesOption.disabled = !isAgent;
        if (!isAgent) createWorkstream.value = "sales";
    }
    createRole.addEventListener("change", syncCreateWorkstream);
    syncCreateWorkstream();

    createForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(createForm, async () => {
            const user = await apiRequest(createForm.action, {
                method: "POST",
                body: formPayload(createForm, ["username", "password", "first_name", "last_name", "email", "phone", "role", "workstream"]),
            });
            window.location.assign(`/users/${user.id}/`);
        });
    });

    setupPermissionsDialog();
    tableBody.addEventListener("click", (event) => {
        const button = event.target.closest("[data-permissions-button]");
        if (!button) return;
        openPermissionsDialog(button.dataset.userId, button.dataset.userName);
    });

    loadUsers();
}
