import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {globalMessage, showError} from "dolphin/core/messages.js";
import {loadAllPages} from "dolphin/ui/lists.js";

const ENDPOINT = "/api/v1/customer-categories/";

/**
 * Fill a `<select data-customer-category-select>` with the active categories.
 *
 * The option value is the category's name — the form still submits the
 * `category` text the customer API has always taken, and the server links it
 * to the managed category. A customer whose current category has since been
 * deactivated keeps it as an extra, marked option, so editing some other
 * field never silently clears it.
 */
export async function fillCustomerCategorySelect(select, current = "") {
    if (!select) return;
    const categories = await loadAllPages(`${ENDPOINT}?is_active=true`);
    const names = categories.map((category) => category.name);
    const keep = select.options[0];
    select.replaceChildren(keep);
    const add = (name, label = name) => {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = label;
        select.append(option);
    };
    names.forEach((name) => add(name));
    if (current && !names.includes(current)) add(current, `${current} (غیرفعال)`);
    select.value = current || "";
}

/**
 * The «مدیریت دسته‌بندی‌ها» dialog: add, rename, deactivate/reactivate, and
 * move a category's customers to another one. Every action is the API's; this
 * only draws the list and calls it.
 */
export function setupCategoryManager({onChange = () => {}} = {}) {
    const dialog = document.getElementById("customer-categories-dialog");
    const open = document.getElementById("open-customer-categories");
    if (!dialog || !open) return;
    const body = dialog.querySelector("[data-category-rows]");
    const form = dialog.querySelector("[data-category-add]");
    const empty = dialog.querySelector("[data-category-empty]");
    let rows = [];

    const button = (label, className, handler) => {
        const node = document.createElement("button");
        node.type = "button";
        node.className = `btn btn-sm ${className}`;
        node.textContent = label;
        node.addEventListener("click", async () => {
            node.disabled = true;
            try { await handler(); } catch (error) { showError(error); } finally { node.disabled = false; }
        });
        return node;
    };

    async function refresh() {
        rows = await loadAllPages(ENDPOINT);
        body.replaceChildren(...rows.map(row));
        empty.hidden = rows.length > 0;
    }

    function row(category) {
        const tr = document.createElement("tr");
        const name = document.createElement("td");
        const input = document.createElement("input");
        input.className = "form-control form-control-sm form-control-solid";
        input.value = category.name;
        input.maxLength = 100;
        input.setAttribute("aria-label", "نام دسته‌بندی");
        name.append(input);
        const count = document.createElement("td");
        count.textContent = toPersianDigits(String(category.customer_count));
        const state = document.createElement("td");
        const badge = document.createElement("span");
        badge.className = `badge ${category.is_active ? "badge-light-success" : "badge-light-danger"}`;
        badge.textContent = category.is_active ? "فعال" : "غیرفعال";
        state.append(badge);
        const actions = document.createElement("td");
        actions.className = "d-flex flex-wrap gap-2";
        actions.append(
            button("ذخیرهٔ نام", "btn-light-primary", async () => {
                if (input.value.trim() === category.name) return;
                await apiRequest(`${ENDPOINT}${category.id}/`, {method: "PATCH", body: {name: input.value}});
                globalMessage("نام دسته‌بندی ذخیره شد.", true);
                await refresh();
                onChange();
            }),
            button(category.is_active ? "غیرفعال‌سازی" : "فعال‌سازی", "btn-light", async () => {
                await apiRequest(`${ENDPOINT}${category.id}/${category.is_active ? "deactivate" : "reactivate"}/`, {method: "POST"});
                await refresh();
                onChange();
            }),
        );
        const others = rows.filter((other) => other.id !== category.id && other.is_active);
        if (category.customer_count && others.length) {
            const target = document.createElement("select");
            target.className = "form-select form-select-sm form-select-solid w-150px";
            target.setAttribute("aria-label", "انتقال مشتریان به");
            target.append(new Option("انتقال مشتریان به…", ""));
            others.forEach((other) => target.append(new Option(other.name, String(other.id))));
            const move = button("انتقال", "btn-light-warning", async () => {
                if (!target.value) return;
                const result = await apiRequest(`${ENDPOINT}${category.id}/transfer/`, {method: "POST", body: {target: Number(target.value)}});
                globalMessage(`${toPersianDigits(String(result.moved))} مشتری منتقل شد و این دسته‌بندی غیرفعال شد.`, true);
                await refresh();
                onChange();
            });
            actions.append(target, move);
        }
        tr.append(name, count, state, actions);
        return tr;
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const field = form.elements.name;
        try {
            await apiRequest(ENDPOINT, {method: "POST", body: {name: field.value}});
            field.value = "";
            await refresh();
            onChange();
        } catch (error) {
            showError(error, form);
        }
    });
    dialog.querySelectorAll("[data-close-dialog]").forEach((node) => node.addEventListener("click", () => dialog.close()));
    open.addEventListener("click", async () => {
        dialog.showModal();
        try { await refresh(); } catch (error) { showError(error); }
    });
}
