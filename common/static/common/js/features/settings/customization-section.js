import {apiRequest} from "dolphin/core/api.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {appendCell} from "dolphin/ui/table.js";

/**
 * Settings → «شخصی‌سازی» (2.40.53): the company's own fields. A field is
 * added, renamed, given choices, placed in forms, lists, filters and search,
 * moved up or down, and turned off — never deleted, so no value is lost.
 * Every rule is `customization.services`.
 */
const PLACES = [["required", "اجباری"], ["show_in_list", "ستون"], ["filterable", "فیلتر"], ["searchable", "جست‌وجو"]];

export function setupCustomizationSection() {
    const body = document.getElementById("custom-fields-body");
    if (!body) return;
    const dialog = document.getElementById("custom-field-dialog");
    const form = document.getElementById("custom-field-form");
    const typeSelect = document.getElementById("custom-field-type");
    const choicesField = document.getElementById("custom-field-choices-field");
    let editing = null;

    const syncChoices = () => { choicesField.hidden = typeSelect.value !== "choice"; };
    typeSelect.addEventListener("change", syncChoices);

    function button(label, onClick, className = "btn btn-sm btn-light") {
        const node = document.createElement("button");
        node.type = "button";
        node.className = className;
        node.textContent = label;
        node.addEventListener("click", onClick);
        return node;
    }

    function iconButton(icon, label, onClick) {
        const node = button("", onClick, "btn btn-sm btn-icon btn-light");
        node.setAttribute("aria-label", label);
        const glyph = document.createElement("i");
        glyph.className = `di-outline ${icon} fs-4`;
        glyph.setAttribute("aria-hidden", "true");
        node.append(glyph);
        return node;
    }

    function render(data) {
        if (!typeSelect.options.length) {
            data.field_types.forEach((item) => typeSelect.append(new Option(item.label, item.value)));
        }
        const fields = data.fields.filter((field) => field.entity === "customer");
        document.getElementById("custom-fields-loading").hidden = true;
        document.getElementById("custom-fields-empty").hidden = fields.length > 0;
        document.getElementById("custom-fields-table-wrap").hidden = !fields.length;
        body.replaceChildren(...fields.map((field, index) => {
            const row = document.createElement("tr");
            appendCell(row, field.label);
            appendCell(row, field.field_type === "choice" ? `${field.field_type_display}: ${field.choices.join("، ")}` : field.field_type_display);
            appendCell(row, PLACES.filter(([flag]) => field[flag]).map(([, label]) => label).join("، ") || "فقط فرم و پروفایل");
            const status = document.createElement("td");
            const badge = document.createElement("span");
            badge.className = `badge badge-light-${field.is_active ? "success" : "secondary"}`;
            badge.textContent = field.is_active ? "فعال" : "خاموش";
            status.append(badge);
            row.append(status);
            const actions = document.createElement("td");
            actions.className = "text-end text-nowrap";
            const up = iconButton("di-arrow-up", `بالا بردن «${field.label}»`, () => move(field, "up"));
            up.disabled = index === 0;
            const down = iconButton("di-arrow-down", `پایین بردن «${field.label}»`, () => move(field, "down"));
            down.disabled = index === fields.length - 1;
            actions.append(up, " ", down, " ", button("ویرایش", () => open(field)));
            row.append(actions);
            return row;
        }));
    }

    async function load() {
        try {
            render(await apiRequest("/api/v1/custom-fields/"));
        } catch (error) {
            document.getElementById("custom-fields-loading").textContent = "فیلدها دریافت نشد.";
            showError(error);
        }
    }

    async function move(field, direction) {
        try {
            render(await apiRequest(`/api/v1/custom-fields/${field.id}/move/`, {method: "POST", body: {direction}}));
        } catch (error) {
            showError(error);
        }
    }

    function open(field = null) {
        editing = field;
        clearMessages(form);
        form.reset();
        document.getElementById("custom-field-label").value = field?.label || "";
        typeSelect.value = field?.field_type || "text";
        typeSelect.disabled = Boolean(field);
        document.getElementById("custom-field-type-note").hidden = !field;
        document.getElementById("custom-field-choices").value = (field?.choices || []).join("\n");
        PLACES.forEach(([flag]) => { document.getElementById(`custom-field-${flag.replaceAll("_", "-")}`).checked = Boolean(field?.[flag]); });
        document.getElementById("custom-field-active-wrap").hidden = !field;
        document.getElementById("custom-field-active").checked = field ? field.is_active : true;
        syncChoices();
        dialog.showModal();
    }

    document.getElementById("custom-field-add").addEventListener("click", () => open());
    dialog.querySelectorAll("[data-close-dialog]").forEach((node) => node.addEventListener("click", () => dialog.close()));

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(form, async () => {
            const payload = {label: document.getElementById("custom-field-label").value};
            PLACES.forEach(([flag]) => { payload[flag] = document.getElementById(`custom-field-${flag.replaceAll("_", "-")}`).checked; });
            const type = editing ? editing.field_type : typeSelect.value;
            if (type === "choice") payload.choices = document.getElementById("custom-field-choices").value.split("\n");
            let data;
            if (editing) {
                payload.is_active = document.getElementById("custom-field-active").checked;
                data = await apiRequest(`/api/v1/custom-fields/${editing.id}/`, {method: "PATCH", body: payload});
            } else {
                data = await apiRequest("/api/v1/custom-fields/", {method: "POST", body: {...payload, entity: "customer", field_type: type}});
            }
            dialog.close();
            render(data);
            globalMessage("فیلد ذخیره شد. فرم‌ها و فهرست مشتریان با بارگذاری دوباره آن را نشان می‌دهند.", true);
        });
    });

    load();
}
