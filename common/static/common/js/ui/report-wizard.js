import {apiRequest} from "dolphin/core/api.js";
import {apiDateTime} from "dolphin/core/jalali.js";
import {errorText, showError} from "dolphin/core/messages.js";
import {setupChartRange} from "dolphin/ui/charts.js";
import {setupWizard} from "dolphin/ui/wizard.js";

/* --- the shared report wizard -------------------------------------------

   Both rebuilt reports — «گزارش اسناد فروش و پست» and «گزارش پیامک
   ورودی» — are the same shape: pick a window, narrow it, choose what to
   look at, read the answer. The product owner asked for both to become
   step-by-step wizards with no separate filter panel, a way back, and an
   export («فیلتر جدا نداشته باشند؛ به‌صورت مرحله‌به‌مرحله باشند که کاربر
   انتخاب کند چه چیزی را ببیند و در آخر نتیجه نمایش داده شود … امکان
   برگشت به مرحلهٔ قبل و خروجی گرفتن»).

   One driver for both, so the two cannot drift into two different
   wizards. What differs is declared by the caller: the endpoint, how to
   turn the chosen sections into a query, and how to draw the result.

   The stepping itself is `setupWizard` — the same component the four
   creation wizards use, including the `validateStep` hook added in
   2.12.0 — rather than a second stepper written for reports. */

/**
 * @param prefix    the id prefix every element on the page shares
 * @param endpoint  where the report is built
 * @param exportUrl where the workbook comes from, or null for no export
 * @param extraQuery  () -> object, this report's own filter fields
 * @param render      (report) -> void, draws it
 * @param isEmpty     (report) -> bool, "nothing to show"
 */
export function setupReportWizard({prefix, endpoint, exportUrl, extraQuery, render, isEmpty}) {
    const root = document.getElementById(`${prefix}-wizard`);
    if (!root) return null;

    const loading = document.getElementById(`${prefix}-loading`);
    const empty = document.getElementById(`${prefix}-empty`);
    const errorNote = document.getElementById(`${prefix}-error`);
    const content = document.getElementById(`${prefix}-content`);
    const exportButton = document.getElementById(`${prefix}-export`);

    // Step one is the shared range filter, not a pair of date boxes: a
    // reader picking «۳۰ روز» is doing the same thing here as on every
    // chart in the panel, and it should be the same control.
    const range = setupChartRange(
        document.getElementById(`${prefix}-range`),
        () => {},
        {initial: "30d", label: "بازهٔ زمانی گزارش"},
    );

    /** The sections this reader ticked on the "what to show" step. */
    function chosenSections() {
        return [...root.querySelectorAll("[data-report-section]")]
            .filter((box) => box.checked)
            .map((box) => box.dataset.reportSection);
    }

    function query() {
        const params = new URLSearchParams(range ? range.window() : {});
        Object.entries(extraQuery ? extraQuery() : {}).forEach(([name, value]) => {
            // A filter of several values (a checklist, 2.40.21) is the same
            // parameter repeated; the server reads every one of them.
            if (Array.isArray(value)) {
                value.map((item) => String(item ?? "").trim()).filter(Boolean).forEach((item) => params.append(name, item));
                return;
            }
            const text = String(value ?? "").trim();
            if (text) params.set(name, text);
        });
        return params;
    }

    function show(node) {
        [loading, empty, errorNote, content].forEach((each) => {
            if (each) each.hidden = each !== node;
        });
    }

    /** Hide the result sections this reader did not ask for. */
    function applySections() {
        const chosen = new Set(chosenSections());
        root.querySelectorAll("[data-report-panel]").forEach((panel) => {
            panel.hidden = !chosen.has(panel.dataset.reportPanel);
        });
    }

    async function build() {
        show(loading);
        try {
            const report = await apiRequest(`${endpoint}?${query()}`);
            if (isEmpty && isEmpty(report)) {
                show(empty);
                return;
            }
            render(report);
            applySections();
            show(content);
        } catch (error) {
            if (errorNote) {
                errorNote.textContent = errorText(error);
                show(errorNote);
            } else {
                show(null);
            }
            showError(error);
        }
    }

    // The window is required and the range control always has one, so
    // the only step that can be incomplete is the one asking what to
    // show — a report with no sections chosen is a blank page.
    // `setupWizard` looks for a `.stepper` *inside* what it is given,
    // so `#<prefix>-wizard` wraps the stepper rather than being it.
    const wizard = setupWizard(root, {
        onReachLastStep: () => build(),
        validateStep: (_index, step) => {
            if (!step || !step.querySelector("[data-report-section]")) return null;
            return chosenSections().length
                ? null
                : "دست‌کم یک بخش را برای نمایش انتخاب کنید.";
        },
    });

    // Re-ticking a section after the report is built re-hides or re-shows
    // it in place rather than rebuilding: the data is the same data.
    root.querySelectorAll("[data-report-section]").forEach((box) => {
        box.addEventListener("change", () => {
            if (content && !content.hidden) applySections();
        });
    });

    // Back a step and forward again must not silently keep a stale
    // answer on screen — `onReachLastStep` rebuilds every time the last
    // step is reached, which is what makes "go back, change it, come
    // forward" mean what it looks like.

    if (exportButton && exportUrl) {
        exportButton.addEventListener("click", () => {
            // The same window and the same filters the report on screen
            // was built from, so the workbook can never be a different
            // report than the one that was read.
            window.location.assign(`${exportUrl}?${query()}`);
        });
    } else if (exportButton) {
        exportButton.hidden = true;
    }

    return {wizard, build, query};
}

/**
 * A live, client-side text filter over a report's own already-rendered
 * result table(s) — the search box every list page's own card-header
 * carries, adapted for a report page: there is no server round trip to
 * make, since the whole table is already on the page once the report is
 * built. Hiding a row rather than removing it keeps `report.total`,
 * column widths and re-search all correct without re-rendering.
 */
export function bindReportTableSearch(input, tbodies) {
    if (!input) return;
    input.addEventListener("input", () => {
        const query = input.value.trim().toLowerCase();
        tbodies.forEach((tbody) => {
            if (!tbody) return;
            Array.from(tbody.rows).forEach((row) => {
                row.hidden = query !== "" && !row.textContent.toLowerCase().includes(query);
            });
        });
    });
}

export function reportQuery(form) {
    const data = new FormData(form);
    const query = new URLSearchParams();
    query.set("period_start", apiDateTime(String(data.get("period_start") || "")) || "");
    query.set("period_end", apiDateTime(String(data.get("period_end") || "")) || "");
    ["user_id", "sales_product_id"].forEach((name) => {
        const value = String(data.get(name) || "").trim();
        if (value) query.set(name, value);
    });
    return query;
}
