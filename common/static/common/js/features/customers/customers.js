import {apiRequest} from "dolphin/core/api.js";
import {toPersianDigits} from "dolphin/core/digits.js";
import {apiDate, displayDay} from "dolphin/core/jalali.js";
import {clearMessages, formPayload, globalMessage, showError, withSubmit} from "dolphin/core/messages.js";
import {bucketLabel} from "dolphin/features/customers/shared.js";
import {renderAreaChart, renderBarChart, renderDonutChart, setupChartRange} from "dolphin/ui/charts.js";
import {fillCustomerCategorySelect, setupCategoryManager} from "dolphin/ui/customer-categories.js";
import {customerKindBadge} from "dolphin/ui/customer-kind.js";
import {fillProvinceSelect, loadIranMap} from "dolphin/ui/iran-map.js";
import {setupPagedList} from "dolphin/ui/lists.js";
import {setupListFilter} from "dolphin/ui/popover.js";
import {appendCell, appendDetailLink, appendStatusCell} from "dolphin/ui/table.js";
import {renderWizardReview, setupWizard} from "dolphin/ui/wizard.js";

function customerRow(customer) {
    const row = document.createElement("tr");
    appendCell(row, customer.full_name);
    appendCell(row, customer.primary_phone?.normalized_phone || customer.primary_phone?.raw_phone || "—").dir = "ltr";
    appendCell(row, customer.category);
    appendCell(row, customer.postal_code);
    appendCell(row, customer.city);
    appendStatusCell(row, (customer.is_active));
    appendCell(row, customer.created_by_display || customer.created_by);
    appendCell(row, displayDay(customer.created_at));
    appendDetailLink(row, `/customers/${customer.id}/`);
    return row;
}

export function setupCustomers() {
    const form = document.getElementById("customer-search-form");
    setupListFilter("customer");
    // Which of the two books is on screen. A marketer never sees the
    // switch, and `customers_for` confines them to this book in the
    // database regardless of what the page asks for.
    let kind = "individual";
    const controller = setupPagedList({
        key: "customers",
        form,
        search: document.getElementById("customer-search"),
        endpoint(page) {
            const ordering = document.getElementById("customer-ordering").value;
            // "registered" is a UI-only choice that means "sort by
            // registration date and let me pick a window"; the API knows
            // only its own ordering fields.
            const query = new URLSearchParams({
                page: String(page),
                ordering: ordering === "registered" ? "-created_at" : ordering,
            });
            const search = document.getElementById("customer-search").value.trim();
            if (search) query.set("search", search);
            if (ordering === "registered") {
                const from = apiDate(document.getElementById("customer-created-from").value);
                const to = apiDate(document.getElementById("customer-created-to").value);
                if (from) query.set("created_from", from);
                if (to) query.set("created_to", to);
            }
            query.set("kind", kind);
            // The four narrowing filters (product-owner request
            // 2026-09-19). Each is sent only when it has a value, so an
            // untouched filter panel produces exactly the URL it produced
            // before — «همه» is the absence of the parameter, not a
            // parameter meaning "everything".
            [
                ["province", "customer-province-filter"],
                ["city", "customer-city-filter"],
                ["category", "customer-category-filter"],
                ["is_active", "customer-active-filter"],
            ].forEach(([name, id]) => {
                const value = document.getElementById(id)?.value.trim();
                if (value) query.set(name, value);
            });
            return `/api/v1/customers/?${query}`;
        },
        renderRow: customerRow,
    });
    // The window controls only make sense under the registration sort, so
    // they appear with it and stay out of the way otherwise.
    const orderingSelect = document.getElementById("customer-ordering");
    const dateRange = document.getElementById("customer-date-range");
    const syncDateRange = () => {
        const active = orderingSelect.value === "registered";
        dateRange.hidden = !active;
    };
    orderingSelect.addEventListener("change", syncDateRange);
    syncDateRange();

    /**
     * The حقیقی / حقوقی switch.
     *
     * One table, two books: the same columns and the same filters read a
     * different list, rather than a second page duplicating all of it. The
     * pressed state is carried on `aria-pressed` as well as the class, so
     * the switch is not colour-only.
     */
    const kindButtons = Array.from(document.querySelectorAll("[data-customer-kind]"));
    kindButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const chosen = button.dataset.customerKind;
            if (chosen === kind) return;
            kind = chosen;
            kindButtons.forEach((other) => {
                const active = other === button;
                // Light-primary, not solid: the solid button beside these
                // is «مشتری جدید», and two of them would compete.
                other.classList.toggle("btn-light-primary", active);
                other.classList.toggle("btn-light", !active);
                other.setAttribute("aria-pressed", String(active));
            });
            clearMessages();
            controller.load(1);
        });
    });

    setupCustomerListTransfer(() => kind);
    setupCustomerCharts();
    controller.load();
    const dialog = document.getElementById("create-customer-dialog");
    const createForm = document.getElementById("create-customer-form");
    const categorySelect = document.getElementById("create-customer-category");
    const loadCategories = () => fillCustomerCategorySelect(categorySelect, categorySelect.value).catch(showError);
    loadCategories();
    setupCategoryManager({onChange: loadCategories});
    const kindInput = document.getElementById("create-customer-kind");
    const economicReveal = document.getElementById("create-customer-economic-reveal");
    // The economic code belongs to a legal customer only: for an individual
    // the field is hidden and switched off, so nothing typed there is sent.
    const syncKind = () => {
        const legal = kindInput.value === "legal";
        economicReveal.classList.toggle("is-open", legal);
        economicReveal.toggleAttribute("inert", !legal);
        economicReveal.querySelectorAll("input").forEach((field) => { field.disabled = !legal; });
    };
    kindInput.addEventListener("change", syncKind);
    syncKind();
    function renderCustomerReview() {
        const kindField = document.getElementById("create-customer-kind");
        const phoneRaw = document.getElementById("create-customer-phone").value.trim();
        renderWizardReview(document.getElementById("create-customer-review"), [
            ["نام کامل", createForm.full_name.value || "—"],
            ["نوع مشتری", customerKindBadge(kindField.value)],
            ["کد ملی", createForm.national_id.value || "—"],
            ...(kindField.value === "legal" ? [["شماره اقتصادی", createForm.economic_code.value || "—"]] : []),
            ["ایمیل", createForm.email.value || "—"],
            ["دسته‌بندی", createForm.category.value || "—"],
            ["استان", createForm.province.value || "—"],
            ["شهر", createForm.city.value || "—"],
            ["کد پستی", createForm.postal_code.value || "—"],
            ["تلفن آغازین", phoneRaw || "—"],
            ["برچسب تلفن", createForm.phone_label.value || "—"],
            ["شماره اصلی", document.getElementById("create-customer-phone-primary").checked ? "بله" : "خیر"],
            ["نشانی", createForm.address.value || "—"],
            ["یادداشت", createForm.notes.value || "—"],
        ]);
    }
    const wizard = setupWizard(dialog, {onReachLastStep: renderCustomerReview});
    fillProvinceSelect(document.getElementById("create-customer-province"));
    // The filter's own province list comes from the same canonical file as
    // the creation form's and as the map below the table, with «همهٔ
    // استان‌ها» kept as its first option — so "filter by استان" can only
    // ever name a province the map itself can place.
    fillProvinceSelect(document.getElementById("customer-province-filter"), "", {
        placeholder: "همهٔ استان‌ها",
    });
    document.getElementById("open-create-customer").addEventListener("click", () => {
        createForm.reset();
        clearMessages(createForm);
        // `reset()` above put the select back to its first option — this
        // form's own placeholder, since the dropdown carries no
        // browser-remembered default the way a text field's own empty
        // string already was.
        document.getElementById("create-customer-province").value = "";
        wizard?.goFirst();
        dialog.showModal();
    });
    // «ثبت مشتری» from the incoming-call popup (2.23.0): the create form,
    // opened with the caller's number already in it.
    const newPhone = new URLSearchParams(window.location.search).get("new_phone");
    if (newPhone) {
        document.getElementById("open-create-customer").click();
        createForm.phone_raw.value = newPhone.startsWith("+98") ? `0${newPhone.slice(3)}` : newPhone;
    }
    dialog.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    createForm.addEventListener("submit", (event) => {
        event.preventDefault();
        withSubmit(createForm, async () => {
            const payload = formPayload(createForm, ["full_name", "national_id", "economic_code", "email", "province", "city", "postal_code", "category", "address", "notes"]);
            const kindField = document.getElementById("create-customer-kind");
            payload.kind = kindField.value;
            if (payload.kind !== "legal") delete payload.economic_code;
            const ownerField = document.getElementById("create-customer-owner");
            if (ownerField?.value) payload.owner = Number(ownerField.value);
            const rawPhone = String(new FormData(createForm).get("phone_raw") || "").trim();
            if (rawPhone) payload.phone = {
                raw_phone: rawPhone,
                label: String(new FormData(createForm).get("phone_label") || ""),
                is_primary: document.getElementById("create-customer-phone-primary").checked,
            };
            const customer = await apiRequest(createForm.action, {method: "POST", body: payload});
            dialog.close();
            controller.load(1);
            window.location.assign(`/customers/${customer.id}/`);
        });
    });
}

/**
 * The «خروجی لیست» and «ورودی لیست» dialogs.
 *
 * Both ask the same first question — which list — because both act on one
 * book at a time. Export then offers a download; import offers a file and a
 * upload button. The export columns and the import columns are the same row,
 * so the operator exports a list, writes on that file, and returns it.
 *
 * `currentKind` seeds each dialog with the book already on screen, which is
 * almost always the one meant.
 */
function setupCustomerListTransfer(currentKind) {
    const exportDialog = document.getElementById("export-customers-dialog");
    const exportOpen = document.getElementById("open-export-customers");
    const exportKind = document.getElementById("export-customers-kind");
    const download = document.getElementById("download-customers");

    function bindClose(dialog) {
        dialog?.querySelectorAll("[data-close-dialog]").forEach((button) =>
            button.addEventListener("click", () => dialog.close()),
        );
    }

    if (exportDialog && exportOpen) {
        bindClose(exportDialog);
        exportOpen.addEventListener("click", () => {
            // Seed with the book on screen, but only if this reader has
            // that option at all.
            if (Array.from(exportKind.options).some((option) => option.value === currentKind())) {
                exportKind.value = currentKind();
            }
            exportDialog.showModal();
        });
        download.addEventListener("click", () => {
            // A plain navigation: the browser's own download, with the
            // session cookie attached, and no blob held in memory.
            window.location.assign(
                `/api/v1/exports/customers.xlsx?kind=${encodeURIComponent(exportKind.value)}`,
            );
            exportDialog.close();
        });
    }

    const importDialog = document.getElementById("import-customers-dialog");
    const importOpen = document.getElementById("open-import-customers");
    if (!importDialog || !importOpen) return;
    const importKind = document.getElementById("import-customers-kind");
    const picker = document.getElementById("import-customers-file");
    const upload = document.getElementById("upload-customers");

    bindClose(importDialog);
    importOpen.addEventListener("click", () => {
        importKind.value = currentKind();
        picker.value = "";
        clearMessages(importDialog);
        importDialog.showModal();
    });
    upload.addEventListener("click", async () => {
        const file = picker.files && picker.files[0];
        if (!file) {
            const slot = importDialog.querySelector('[data-error-for="file"]');
            if (slot) slot.textContent = "یک فایل اکسل انتخاب کنید.";
            return;
        }
        const body = new FormData();
        body.append("file", file);
        body.append("kind", importKind.value);
        upload.disabled = true;
        clearMessages(importDialog);
        try {
            const result = await apiRequest("/api/v1/customers/import-xlsx/", {
                method: "POST", body, raw: true,
            });
            importDialog.close();
            const parts = [`${toPersianDigits(String(result.created))} مشتری ثبت شد.`];
            if (result.duplicates) {
                parts.push(`${toPersianDigits(String(result.duplicates))} مشتری تکراری بود و اضافه نشد.`);
            }
            if (result.invalid) {
                parts.push(`${toPersianDigits(String(result.invalid))} ردیف نامعتبر بود و رد شد.`);
            }
            // A run that created nothing is not a success message.
            globalMessage(parts.join(" "), result.created > 0);
        } catch (error) {
            showError(error, importDialog);
        } finally {
            upload.disabled = false;
        }
    });
}

/** Which of the five bands a count falls in, 0 meaning "no customers". */
function choroplethStep(count, max) {
    if (!count) return 0;
    if (max <= 1) return 5;
    // Ceil so any non-zero count lands in band 1 or above — a province
    // with one customer must never be shaded as though it had none.
    return Math.min(5, Math.max(1, Math.ceil((count / max) * 5)));
}

async function renderProvinceMap(host, empty, report) {
    if (!host) return;
    let map;
    try {
        map = await loadIranMap();
    } catch (error) {
        host.hidden = true;
        if (empty) {
            empty.textContent = "نقشهٔ استان‌ها بارگذاری نشد.";
            empty.hidden = false;
        }
        return;
    }

    const counts = new Map(report.results.map((row) => [row.key, row]));
    const max = report.results.reduce((top, row) => Math.max(top, row.count), 0);

    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", map.viewBox);
    svg.setAttribute("class", "province-map-canvas");
    svg.setAttribute("role", "img");
    svg.setAttribute(
        "aria-label",
        `نقشهٔ پراکندگی ${toPersianDigits(String(report.placed))} مشتری در ${toPersianDigits(String(report.distinct_provinces))} استان`,
    );

    Object.entries(map.provinces).forEach(([key, province]) => {
        const row = counts.get(key);
        const count = row ? row.count : 0;
        const path = document.createElementNS(svgNS, "path");
        path.setAttribute("d", province.path);
        path.setAttribute("class", `province-map-region province-map-step-${choroplethStep(count, max)}`);
        path.dataset.province = key;
        path.dataset.count = String(count);
        path.dataset.name = province.name;
        path.setAttribute("tabindex", "0");
        // The accessible name carries the same two facts the tooltip shows,
        // so a keyboard or screen-reader user is not left with a shape.
        const title = document.createElementNS(svgNS, "title");
        title.textContent = `${province.name}: ${toPersianDigits(String(count))} مشتری`;
        path.append(title);
        svg.append(path);
    });

    const tooltip = document.createElement("div");
    tooltip.className = "province-map-tooltip";
    tooltip.hidden = true;

    function showTooltip(region) {
        const count = Number(region.dataset.count);
        const share = report.placed ? Math.round((count / report.placed) * 1000) / 10 : 0;
        tooltip.replaceChildren();
        const name = document.createElement("span");
        name.className = "province-map-tooltip-name";
        name.textContent = region.dataset.name;
        const value = document.createElement("span");
        value.className = "province-map-tooltip-value";
        value.textContent = count
            ? `${toPersianDigits(String(count))} مشتری (${toPersianDigits(String(share))}٪)`
            : "بدون مشتری";
        tooltip.append(name, value);
        tooltip.hidden = false;
    }

    function positionTooltip(event) {
        const box = host.getBoundingClientRect();
        // Clamped to the card so a province near the edge does not push the
        // tooltip outside it and trigger a horizontal scrollbar.
        const x = Math.min(Math.max(event.clientX - box.left, 8), box.width - 8);
        const y = Math.min(Math.max(event.clientY - box.top, 8), box.height - 8);
        tooltip.style.insetInlineStart = `${x}px`;
        tooltip.style.top = `${y}px`;
    }

    svg.addEventListener("pointermove", (event) => {
        const region = event.target.closest?.(".province-map-region");
        if (!region) {
            tooltip.hidden = true;
            return;
        }
        showTooltip(region);
        positionTooltip(event);
    });
    svg.addEventListener("pointerleave", () => {
        tooltip.hidden = true;
    });
    // Focus, not just hover: the regions are tabbable above, so the same
    // reading has to be available without a pointer.
    svg.addEventListener("focusin", (event) => {
        const region = event.target.closest?.(".province-map-region");
        if (!region) return;
        showTooltip(region);
        const box = host.getBoundingClientRect();
        const spot = region.getBoundingClientRect();
        tooltip.style.insetInlineStart = `${spot.left + spot.width / 2 - box.left}px`;
        tooltip.style.top = `${spot.top + spot.height / 2 - box.top}px`;
    });
    svg.addEventListener("focusout", () => {
        tooltip.hidden = true;
    });

    const legend = document.createElement("div");
    legend.className = "province-map-legend";
    const legendLabel = document.createElement("span");
    legendLabel.className = "fs-8 text-muted";
    legendLabel.textContent = "کمتر";
    legend.append(legendLabel);
    [1, 2, 3, 4, 5].forEach((step) => {
        const swatch = document.createElement("span");
        swatch.className = `province-map-swatch province-map-step-${step}`;
        legend.append(swatch);
    });
    const legendMax = document.createElement("span");
    legendMax.className = "fs-8 text-muted";
    legendMax.textContent = `بیشتر (${toPersianDigits(String(max))})`;
    legend.append(legendMax);

    host.replaceChildren(svg, tooltip, legend);
    host.hidden = false;
    if (empty) empty.hidden = true;
}

/**
 * The two charts under the customers table.
 *
 * Both read endpoints built on `customers_for`, so what they count is
 * exactly what the table above lists. Neither is fatal: a deployment whose
 * role cannot reach the reports still gets its customer list, and the chart
 * simply reports that it has nothing rather than taking the page down.
 */
function setupCustomerCharts() {
    const cityChart = document.getElementById("customer-city-chart");
    const growthChart = document.getElementById("customer-growth-chart");
    if (!cityChart && !growthChart) return;

    async function loadCities() {
        const empty = document.getElementById("customer-city-chart-empty");
        try {
            // The map first — it is what this card is now — falling back to
            // the old ranking only where the map cannot say anything,
            // which is a book whose provinces were never filled in.
            const provinces = await apiRequest("/api/v1/reports/customer-provinces/");
            if (provinces.placed > 0) {
                await renderProvinceMap(cityChart, empty, provinces);
                const note = document.getElementById("customer-city-chart-note");
                if (note) {
                    note.textContent = provinces.unmatched
                        ? `${toPersianDigits(String(provinces.unmatched))} مشتری استان ثبت‌شده‌ای ندارند و روی نقشه نیامده‌اند.`
                        : "";
                    note.hidden = !provinces.unmatched;
                }
                return;
            }
            const report = await apiRequest("/api/v1/reports/customer-cities/");
            const rows = report.results.map((row) => ({
                label: row.label,
                value: row.count,
                // Count and share together: the count is the fact, the
                // share is what makes two cities comparable.
                display: `${toPersianDigits(String(row.count))} (${toPersianDigits(String(row.percent))}٪)`,
            }));
            const ariaLabel = `نمودار پراکندگی ${toPersianDigits(String(report.total))} مشتری در ${toPersianDigits(String(report.distinct_cities))} شهر`;
            // A few cities are parts of one customer book, which is what a
            // ring shows; many are a ranking, which is what bars show. Same
            // rule as the list charts, so the two never disagree about the
            // same shape of data.
            const populated = rows.filter((row) => row.value > 0);
            if (populated.length && populated.length <= 6) {
                renderDonutChart(cityChart, empty, rows, {
                    ariaLabel,
                    total: toPersianDigits(String(report.total)),
                    totalLabel: "مشتری",
                });
            } else {
                renderBarChart(cityChart, empty, rows, {
                    // Already ordered largest-first by the endpoint, with
                    // its two aggregate rows deliberately last. Re-sorting
                    // here would lift "سایر شهرها" into the middle of the
                    // real cities.
                    sort: false,
                    ariaLabel,
                });
            }
        } catch (error) {
            if (cityChart) cityChart.hidden = true;
            if (empty) {
                empty.textContent = "نمودار پراکندگی شهری در دسترس نیست.";
                empty.hidden = false;
            }
        }
    }

    // One shared control, not this page's own pair of granularity
    // buttons. It sends a window and no granularity at all: how wide a
    // bucket should be is derived from the window by `reports/ranges.py`,
    // which is the same answer every other chart in the panel gets.
    const growthRange = setupChartRange(
        document.getElementById("customer-growth-controls"),
        () => loadGrowth(),
        {initial: "1y", label: "بازهٔ زمانی نمودار رشد"},
    );

    async function loadGrowth() {
        const empty = document.getElementById("customer-growth-chart-empty");
        const query = new URLSearchParams(growthRange ? growthRange.window() : {});
        try {
            const report = await apiRequest(`/api/v1/reports/customer-growth/?${query}`);
            const points = report.results.map((row) => ({
                label: bucketLabel(row.bucket, report.granularity),
                value: row.cumulative,
                display: `${toPersianDigits(String(row.cumulative))} مشتری (${toPersianDigits(String(row.count))} تازه)`,
            }));
            const added = report.closing_total - report.opening_total;
            renderAreaChart(growthChart, empty, points, {
                ariaLabel: `نمودار رشد مشتریان از ${toPersianDigits(String(report.opening_total))} به ${toPersianDigits(String(report.closing_total))}`,
                summary: `در این بازه ${toPersianDigits(String(added))} مشتری تازه ثبت شد؛ مجموع از ${toPersianDigits(String(report.opening_total))} به ${toPersianDigits(String(report.closing_total))} رسید.`,
                resetButton: growthRange && growthRange.resetHost,
            });
        } catch (error) {
            if (growthChart) growthChart.hidden = true;
            if (empty) {
                empty.textContent = "نمودار رشد در دسترس نیست.";
                empty.hidden = false;
            }
        }
    }

    loadCities();
    loadGrowth();
}
