import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDate, displayDay} from "dolphin/core/jalali.js";
import {clearMessages, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {confirmDialog} from "dolphin/ui/dialogs.js";
import {appendCell} from "dolphin/ui/table.js";

/**
 * Settings → «پس از فروش» (2.40.60, BIZ-008): case types, stage lists,
 * deadlines, the working week and holidays. Every rule is
 * `aftersales.workflow`'s; each answer is the whole payload, redrawn as it is.
 */
const BASE = "/api/v1/after-sales-settings/";
const PRIORITY = {normal: "عادی", urgent: "فوری", critical: "بحرانی"};
//: Python weekdays in the order an Iranian week is read: Saturday first.
const WEEK = [[5, "شنبه"], [6, "یکشنبه"], [0, "دوشنبه"], [1, "سه‌شنبه"], [2, "چهارشنبه"], [3, "پنجشنبه"], [4, "جمعه"]];

export function setupAfterSalesSection() {
    const typesBody = document.getElementById("case-types-body");
    if (!typesBody) return;
    const stageList = document.getElementById("case-stage-list");
    const slaScope = document.getElementById("case-sla-scope");
    const typeDialog = document.getElementById("case-type-dialog");
    const typeForm = document.getElementById("case-type-form");
    const stageDialog = document.getElementById("case-stage-dialog");
    const stageForm = document.getElementById("case-stage-form");
    let data = null;
    let editingType = null;
    let editingStage = null;

    const button = (label, onClick, className = "btn btn-sm btn-light") => {
        const node = document.createElement("button");
        node.type = "button";
        node.className = className;
        node.textContent = label;
        node.addEventListener("click", onClick);
        return node;
    };
    const iconButton = (icon, label, onClick, disabled) => {
        const node = button("", onClick, "btn btn-sm btn-icon btn-light");
        node.setAttribute("aria-label", label);
        node.disabled = disabled;
        const glyph = document.createElement("i");
        glyph.className = `di-outline ${icon} fs-4`;
        glyph.setAttribute("aria-hidden", "true");
        node.append(glyph);
        return node;
    };
    const badge = (on) => {
        const cell = document.createElement("td");
        const node = document.createElement("span");
        node.className = `badge badge-light-${on ? "success" : "secondary"}`;
        node.textContent = on ? "روشن" : "خاموش";
        cell.append(node);
        return cell;
    };
    async function send(path, method, body, message) {
        try {
            render(await apiRequest(`${BASE}${path}`, {method, body}));
            if (message) globalMessage(message, true);
        } catch (error) { showError(error); }
    }

    function renderTypes() {
        typesBody.replaceChildren(...data.types.map((item) => {
            const row = document.createElement("tr");
            appendCell(row, item.label);
            appendCell(row, PRIORITY[item.default_priority]);
            appendCell(row, item.own_stages ? "فهرست خودش" : "فهرست پیش‌فرض");
            row.append(badge(item.is_active));
            const actions = document.createElement("td");
            actions.className = "text-end text-nowrap";
            if (!item.own_stages) {
                actions.append(button("فهرست مرحلهٔ خودش", () => send(`types/${item.id}/stages/`, "POST", {}, "فهرست مرحلهٔ این نوع ساخته شد.")), " ");
            }
            actions.append(button("ویرایش", () => openType(item)));
            row.append(actions);
            return row;
        }));
    }

    function stagesOfList() {
        return stageList.value ? (data.type_stages[stageList.value] || []) : data.default_stages;
    }

    function renderStages() {
        const chosen = stageList.value;
        stageList.replaceChildren(new Option("فهرست پیش‌فرض", ""), ...data.types
            .filter((item) => item.own_stages)
            .map((item) => new Option(`فهرست ${item.label}`, String(item.id))));
        stageList.value = [...stageList.options].some((option) => option.value === chosen) ? chosen : "";
        const stages = stagesOfList();
        const open = stages.filter((stage) => stage.kind === "open");
        document.getElementById("case-stages-body").replaceChildren(...stages.map((stage) => {
            const row = document.createElement("tr");
            appendCell(row, stage.label);
            appendCell(row, stage.kind === "closed" ? "پایانی" : "باز");
            row.append(badge(stage.is_active));
            const actions = document.createElement("td");
            actions.className = "text-end text-nowrap";
            const index = open.indexOf(stage);
            const fixed = stage.kind === "closed";
            actions.append(
                iconButton("di-arrow-up", `بالا بردن «${stage.label}»`, () => send(`stages/${stage.id}/move/`, "POST", {direction: "up"}), fixed || index === 0), " ",
                iconButton("di-arrow-down", `پایین بردن «${stage.label}»`, () => send(`stages/${stage.id}/move/`, "POST", {direction: "down"}), fixed || index === open.length - 1), " ",
                button("ویرایش", () => openStage(stage)),
            );
            row.append(actions);
            return row;
        }));
    }

    function limitInputs(policy, name, priority) {
        const cell = document.createElement("td");
        if (name === "plan" && priority !== "critical") { cell.textContent = "—"; return cell; }
        const wrap = document.createElement("div");
        wrap.className = "d-flex gap-2";
        const value = document.createElement("input");
        value.className = "form-control form-control-sm form-control-solid w-75px";
        value.type = "text";
        value.inputMode = "numeric";
        value.dir = "ltr";
        value.value = policy?.[`${name}_value`] ?? "";
        value.dataset.limit = name;
        value.setAttribute("aria-label", `${PRIORITY[priority]}: مقدار`);
        const unit = document.createElement("select");
        unit.className = "form-select form-select-sm form-select-solid w-100px";
        unit.append(new Option("ساعت", "hour"), new Option("روز", "day"));
        unit.value = policy?.[`${name}_unit`] || "hour";
        unit.dataset.unit = name;
        unit.setAttribute("aria-label", `${PRIORITY[priority]}: واحد`);
        wrap.append(value, unit);
        cell.append(wrap);
        return cell;
    }

    function renderSla() {
        const chosen = slaScope.value;
        slaScope.replaceChildren(new Option("قاعدهٔ شرکت", ""), ...data.types.map((item) => new Option(`نوع ${item.label}`, String(item.id))));
        slaScope.value = [...slaScope.options].some((option) => option.value === chosen) ? chosen : "";
        const scope = slaScope.value ? Number(slaScope.value) : null;
        document.getElementById("case-sla-body").replaceChildren(...Object.keys(PRIORITY).map((priority) => {
            const own = data.policies.find((item) => item.priority === priority && item.case_type === scope);
            const shown = own || data.policies.find((item) => item.priority === priority && item.case_type === null);
            const row = document.createElement("tr");
            appendCell(row, PRIORITY[priority] + (scope && !own ? " (قاعدهٔ شرکت)" : ""));
            ["response", "plan", "resolution"].forEach((name) => row.append(limitInputs(shown, name, priority)));
            const actions = document.createElement("td");
            actions.className = "text-end text-nowrap";
            actions.append(button("ذخیره", () => {
                const body = {priority, case_type: scope};
                ["response", "plan", "resolution"].forEach((name) => {
                    const value = row.querySelector(`[data-limit="${name}"]`);
                    if (!value) return;
                    body[name] = {value: value.value.trim() === "" ? null : Number(value.value), unit: row.querySelector(`[data-unit="${name}"]`).value};
                });
                send("sla/", "PUT", body, "مهلت ذخیره شد.");
            }, "btn btn-sm btn-light-primary"));
            if (scope && own) actions.append(" ", button("قاعدهٔ شرکت", () => send("sla/", "PUT", {priority, case_type: scope, clear: true}, "این نوع دوباره قاعدهٔ شرکت را دارد.")));
            row.append(actions);
            return row;
        }));
    }

    function renderCalendar() {
        const hours = data.calendar.hours;
        document.getElementById("case-calendar-body").replaceChildren(...WEEK.map(([day, label]) => {
            const row = document.createElement("tr");
            row.dataset.day = String(day);
            appendCell(row, label);
            const pair = hours[String(day)];
            const openCell = document.createElement("td");
            const open = document.createElement("input");
            open.type = "checkbox";
            open.className = "form-check-input";
            open.checked = Boolean(pair);
            open.setAttribute("aria-label", `${label} باز است`);
            openCell.append(open);
            row.append(openCell);
            [0, 1].forEach((index) => {
                const cell = document.createElement("td");
                const input = document.createElement("input");
                input.type = "time";
                input.className = "form-control form-control-sm form-control-solid w-125px";
                input.value = pair ? pair[index] : (index ? "16:00" : "08:00");
                input.setAttribute("aria-label", `${label}: ${index ? "پایان" : "شروع"}`);
                cell.append(input);
                row.append(cell);
            });
            return row;
        }));
        document.getElementById("case-calendar-skip").checked = data.calendar.skip_holidays;
    }

    function renderHolidays() {
        const body = document.getElementById("case-holidays-body");
        document.getElementById("case-holidays-empty").hidden = data.holidays.length > 0;
        body.replaceChildren(...data.holidays.map((item) => {
            const row = document.createElement("tr");
            appendCell(row, displayDay(item.day));
            appendCell(row, item.title);
            const actions = document.createElement("td");
            actions.className = "text-end";
            actions.append(button("برداشتن", async () => {
                if (!await confirmDialog(`«${item.title}» از فهرست تعطیلات برداشته شود؟`)) return;
                send(`holidays/${item.id}/`, "DELETE", undefined, "روز برداشته شد.");
            }));
            row.append(actions);
            return row;
        }));
    }

    function render(value) {
        data = value;
        renderTypes();
        renderStages();
        renderSla();
        renderCalendar();
        renderHolidays();
    }

    function openType(item = null) {
        editingType = item;
        typeForm.reset();
        clearMessages(typeForm);
        document.getElementById("case-type-label").value = item?.label || "";
        document.getElementById("case-type-priority").value = item?.default_priority || "normal";
        document.getElementById("case-type-active-wrap").hidden = !item;
        document.getElementById("case-type-active").checked = item ? item.is_active : true;
        typeDialog.showModal();
    }

    function openStage(stage = null) {
        editingStage = stage;
        stageForm.reset();
        clearMessages(stageForm);
        document.getElementById("case-stage-label").value = stage?.label || "";
        document.getElementById("case-stage-active-wrap").hidden = !stage || stage.kind === "closed";
        document.getElementById("case-stage-active").checked = stage ? stage.is_active : true;
        stageDialog.showModal();
    }

    typeForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(typeForm, async () => {
            const body = {label: document.getElementById("case-type-label").value, default_priority: document.getElementById("case-type-priority").value};
            if (editingType) body.is_active = document.getElementById("case-type-active").checked;
            render(await apiRequest(`${BASE}types/${editingType ? `${editingType.id}/` : ""}`, {method: editingType ? "PATCH" : "POST", body}));
            typeDialog.close();
            globalMessage("نوع پرونده ذخیره شد.", true);
        });
    });
    stageForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(stageForm, async () => {
            const body = {label: document.getElementById("case-stage-label").value};
            if (editingStage) {
                if (!document.getElementById("case-stage-active-wrap").hidden) body.is_active = document.getElementById("case-stage-active").checked;
                render(await apiRequest(`${BASE}stages/${editingStage.id}/`, {method: "PATCH", body}));
            } else {
                render(await apiRequest(`${BASE}stages/`, {method: "POST", body: {...body, case_type: stageList.value ? Number(stageList.value) : null}}));
            }
            stageDialog.close();
            globalMessage("مرحله ذخیره شد.", true);
        });
    });

    const calendarForm = document.getElementById("case-calendar-form");
    calendarForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(calendarForm, async () => {
            const hours = {};
            calendarForm.querySelectorAll("#case-calendar-body tr").forEach((row) => {
                const [open, start, end] = row.querySelectorAll("input");
                if (open.checked) hours[row.dataset.day] = [start.value, end.value];
            });
            render(await apiRequest(`${BASE}calendar/`, {method: "PATCH", body: {hours, skip_holidays: document.getElementById("case-calendar-skip").checked}}));
            globalMessage("ساعت‌های کاری ذخیره شد. مهلت پرونده‌های تازه با آن حساب می‌شود.", true);
        });
    });
    const holidayForm = document.getElementById("case-holiday-form");
    holidayForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(holidayForm, async () => {
            const day = apiDate(document.getElementById("case-holiday-day").value);
            render(await apiRequest(`${BASE}holidays/`, {method: "POST", body: {day: day || "", title: document.getElementById("case-holiday-title").value}}));
            holidayForm.reset();
            globalMessage("روز به تعطیلات افزوده شد.", true);
        });
    });
    const fixedForm = document.getElementById("case-fixed-holidays-form");
    fixedForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(fixedForm, async () => {
            const answer = await apiRequest(`${BASE}holidays/fixed/`, {method: "POST", body: {jalali_year: Number(document.getElementById("case-fixed-year").value)}});
            render(answer);
            globalMessage(`${toPersianDigits(String(answer.added))} روز افزوده شد.`, true);
        });
    });

    stageList.addEventListener("change", renderStages);
    slaScope.addEventListener("change", renderSla);
    document.getElementById("case-type-add").addEventListener("click", () => openType());
    document.getElementById("case-stage-add").addEventListener("click", () => openStage());
    [typeDialog, stageDialog].forEach((dialog) => dialog.querySelectorAll("[data-close-dialog]").forEach((node) => node.addEventListener("click", () => dialog.close())));

    apiRequest(BASE).then(render).catch(showError);
}
