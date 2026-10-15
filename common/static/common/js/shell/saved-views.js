import {apiRequest} from "dolphin/core/api.js";
import {globalMessage, showError} from "dolphin/core/messages.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";

/**
 * Saved list views (2.40.54, feature `customization`; owner decision
 * 2026-10-14: «نماهای ذخیره‌شدهٔ جدول، شخصی یا تیمی»).
 *
 * Every list page's filter panel — the hand-built ones (`<key>-filter-panel`)
 * and the generic `.list-filters-panel` — gets a «نماها» block: a choice of
 * the reader's own and shared views, which fills the filter form back and
 * applies it, and a way to save the form as it stands now. A view only fills
 * the page's own form; what the list then shows is still that page's own
 * scope. Rules: `customization.saved_views`.
 */
function formFields(form) {
    return [...form.elements].filter((field) => field.id && !["button", "submit", "reset", "file"].includes(field.type));
}

function pageSearch(panel) {
    const key = panel.id?.endsWith("-filter-panel") ? panel.id.slice(0, -"-filter-panel".length) : "";
    return key ? document.getElementById(`${key}-search`) : null;
}

function capture(form, search) {
    const state = {};
    formFields(form).forEach((field) => {
        state[field.id] = field.type === "checkbox" ? String(field.checked) : field.value;
    });
    if (search?.id) state[search.id] = search.value;
    return state;
}

function restore(form, search, state) {
    formFields(form).forEach((field) => {
        if (!(field.id in state)) return;
        if (field.type === "checkbox") field.checked = state[field.id] === "true";
        else field.value = state[field.id];
        field.dispatchEvent(new Event("change", {bubbles: true}));
    });
    if (search?.id && search.id in state) search.value = state[search.id];
}

let viewDialog = null;

/** The name of a view to save, and whether to share it: `{name, shared}` or `null`. */
function askForView(canShare) {
    if (!viewDialog) {
        viewDialog = document.createElement("dialog");
        viewDialog.id = "saved-view-dialog";
        viewDialog.setAttribute("aria-labelledby", "saved-view-dialog-title");
        viewDialog.innerHTML = '<h2 id="saved-view-dialog-title" class="fs-4 fw-bold mb-5">ذخیرهٔ نما</h2>'
            + '<form method="dialog" novalidate>'
            + '<label class="form-label fw-semibold required" for="saved-view-name">نام نما</label>'
            + '<input class="form-control form-control-solid" id="saved-view-name" maxlength="60" required>'
            + '<div class="form-check form-check-custom form-check-solid form-switch mt-5" data-share-row>'
            + '<input class="form-check-input" type="checkbox" id="saved-view-shared">'
            + '<label class="form-check-label" for="saved-view-shared">نمایش برای همهٔ کسانی که این صفحه را می‌بینند</label></div>'
            + '<div class="d-flex justify-content-end gap-3 mt-6">'
            + '<button class="btn btn-light" type="button" data-cancel>انصراف</button>'
            + '<button class="btn btn-primary" type="submit">ذخیره</button></div></form>';
        document.body.append(viewDialog);
    }
    const dialog = viewDialog;
    const name = dialog.querySelector("#saved-view-name");
    const shared = dialog.querySelector("#saved-view-shared");
    name.value = "";
    shared.checked = false;
    dialog.querySelector("[data-share-row]").hidden = !canShare;
    return new Promise((resolve) => {
        let answer = null;
        const form = dialog.querySelector("form");
        const onSubmit = (event) => {
            if (!name.value.trim()) {
                event.preventDefault();
                name.focus();
                return;
            }
            answer = {name: name.value.trim(), shared: canShare && shared.checked};
        };
        const onCancel = () => dialog.close();
        const onClose = () => {
            form.removeEventListener("submit", onSubmit);
            dialog.querySelector("[data-cancel]").removeEventListener("click", onCancel);
            dialog.removeEventListener("close", onClose);
            resolve(answer);
        };
        form.addEventListener("submit", onSubmit);
        dialog.querySelector("[data-cancel]").addEventListener("click", onCancel);
        dialog.addEventListener("close", onClose);
        dialog.showModal();
        name.focus();
    });
}

function attach(panel, form, page) {
    const block = document.createElement("div");
    block.className = "saved-views border-top border-gray-200 mt-5 pt-4";
    const label = document.createElement("label");
    label.className = "form-label";
    label.textContent = "نماهای ذخیره‌شده";
    const select = document.createElement("select");
    select.className = "form-select form-select-solid form-select-sm";
    select.id = `${form.id}-saved-view`;
    label.setAttribute("for", select.id);
    const actions = document.createElement("div");
    actions.className = "d-flex flex-wrap gap-2 mt-3";
    const save = document.createElement("button");
    save.type = "button";
    save.className = "btn btn-sm btn-light-primary";
    save.textContent = "ذخیرهٔ همین فیلترها";
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "btn btn-sm btn-light";
    remove.textContent = "حذف نما";
    remove.hidden = true;
    actions.append(save, remove);
    block.append(label, select, actions);
    form.after(block);
    const search = pageSearch(panel);
    let views = [];
    let canShare = false;

    function draw(chosen = "") {
        select.replaceChildren(new Option(views.length ? "یک نما انتخاب کنید" : "هنوز نمایی ذخیره نشده", ""));
        views.forEach((view) => {
            const suffix = view.shared ? (view.mine ? " (مشترک)" : ` (مشترک، ${view.owner_display})`) : "";
            select.append(new Option(`${view.name}${suffix}`, String(view.id)));
        });
        select.value = chosen;
        const current = views.find((view) => String(view.id) === select.value);
        remove.hidden = !current || !(current.mine || (current.shared && canShare));
    }

    async function load(chosen = "") {
        try {
            const data = await apiRequest(`/api/v1/saved-views/?page=${encodeURIComponent(page)}`);
            views = data.views;
            canShare = data.can_share;
            draw(chosen);
        } catch (error) {
            block.hidden = true;
        }
    }

    select.addEventListener("change", () => {
        const view = views.find((item) => String(item.id) === select.value);
        draw(select.value);
        if (!view) return;
        restore(form, search, view.state);
        form.requestSubmit();
    });

    save.addEventListener("click", async () => {
        const answer = await askForView(canShare);
        if (!answer) return;
        try {
            const view = await apiRequest("/api/v1/saved-views/", {
                method: "POST", body: {page, name: answer.name, state: capture(form, search), shared: answer.shared},
            });
            globalMessage(`نمای «${view.name}» ذخیره شد.`, true);
            await load(String(view.id));
        } catch (error) {
            showError(error);
        }
    });

    remove.addEventListener("click", async () => {
        const view = views.find((item) => String(item.id) === select.value);
        if (!view || !(await confirmDialog(`نمای «${view.name}» حذف شود؟`))) return;
        try {
            await apiRequest(`/api/v1/saved-views/${view.id}/`, {method: "DELETE"});
            globalMessage("نما حذف شد.", true);
            await load();
        } catch (error) {
            showError(error);
        }
    });

    load();
}

export function setupSavedViews(pageId) {
    if (document.body.dataset.savedViews !== "1" || !pageId) return;
    const safePage = String(pageId).toLowerCase().replace(/[^a-z0-9-]/g, "-").slice(0, 40);
    const panels = new Set([
        ...document.querySelectorAll('[id$="-filter-panel"]'),
        ...document.querySelectorAll(".list-filters-panel"),
    ]);
    panels.forEach((panel) => {
        const form = panel.querySelector("form");
        if (!form?.id || panel.querySelector(".saved-views")) return;
        const formKey = form.id.toLowerCase().replace(/[^a-z0-9-]/g, "-").slice(0, 60);
        attach(panel, form, `${safePage}:${formKey}`);
    });
}
