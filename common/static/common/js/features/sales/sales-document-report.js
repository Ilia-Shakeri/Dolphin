import {toPersianDigits} from "dolphin/core/digits.js";
import {showError} from "dolphin/core/messages.js";
import {fillPostalStates, postalStateLabels} from "dolphin/features/sales/shared.js";
import {enhanceChecklistSelect} from "dolphin/ui/checklist-select.js";
import {fillProvinceSelect} from "dolphin/ui/iran-map.js";
import {bindReportTableSearch, setupReportWizard} from "dolphin/ui/report-wizard.js";
import {appendCell} from "dolphin/ui/table.js";

/**
 * A stored postal status as a reader should see it.
 *
 * The label when the vocabulary knows the value, and the stored text
 * unchanged otherwise — which is the same rule `sales.postal.label_for`
 * applies on the server, and the reason a row written before the
 * vocabulary existed still reads as what the operator actually typed.
 */
function postalStateLabel(value) {
    return postalStateLabels.get(value) || value || "نامشخص";
}

export async function setupSalesDocumentReport() {
    // Rebuilt as a wizard in 3.0.0 on the shared driver; what is left
    // here is what only this report knows — its own two filter fields,
    // how to draw its two tables, and when it has nothing to draw.
    const statusFilter = document.getElementById("document-report-status");
    try {
        // The postal vocabulary, so a filter cannot be a typo. "همه" is
        // the empty option: a report with no status filter is the
        // default and the common case.
        await fillPostalStates(statusFilter);
    } catch (error) {
        showError(error);
    }
    // The same 31-province list the customer map and form already read
    // from `iran-provinces.json` — a dropdown so this filter's exact
    // match (`reports/services.py`) can only ever be handed a spelling
    // that actually exists (product owner, 2026-09-21: «استان باید منو
    // دراپ‌داون باشه»).
    const provinceFilter = document.getElementById("document-report-province");
    const activeFilter = document.getElementById("document-report-active");
    await fillProvinceSelect(provinceFilter, "", {placeholder: null});
    // Several of each may be ticked (2.40.21); none ticked means all.
    [provinceFilter, statusFilter, activeFilter].forEach((select) => enhanceChecklistSelect(select, {emptyMeansAll: true}));
    const chosen = (select) => Array.from(select.selectedOptions, (option) => option.value);

    bindReportTableSearch(document.getElementById("sales-document-report-search"), [
        document.getElementById("sales-document-geography-body"),
        document.getElementById("sales-document-status-body"),
    ]);

    setupReportWizard({
        prefix: "sales-document-report",
        endpoint: "/api/v1/reports/sales-documents/",
        exportUrl: "/api/v1/exports/sales-documents.xlsx",
        extraQuery: () => ({
            province: chosen(provinceFilter),
            city: document.getElementById("document-report-city").value,
            postal_status: chosen(statusFilter),
            // Both ticked, or neither, is every document: no filter.
            is_active: chosen(activeFilter).length === 1 ? chosen(activeFilter)[0] : "",
        }),
        isEmpty: (report) => !report.total,
        render: (report) => {
            document.getElementById("sales-document-report-total").textContent =
                toPersianDigits(String(report.total));
            document.getElementById("sales-document-geography-body").replaceChildren(
                ...report.by_geography.map((item) => {
                    const row = document.createElement("tr");
                    [
                        item.province || "ثبت‌نشده",
                        item.city || "ثبت‌نشده",
                        toPersianDigits(String(item.count)),
                    ].forEach((value) => appendCell(row, value));
                    return row;
                }),
            );
            document.getElementById("sales-document-status-body").replaceChildren(
                ...report.by_postal_status.map((item) => {
                    const row = document.createElement("tr");
                    // The state's own Persian label, the same one the
                    // parcel's own page and its stepper use.
                    [
                        postalStateLabel(item.postal_status),
                        toPersianDigits(String(item.count)),
                    ].forEach((value) => appendCell(row, value));
                    return row;
                }),
            );
        },
    });
}
