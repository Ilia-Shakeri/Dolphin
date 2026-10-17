{% comment %} Moving a lead or a campaign person to another stage (2.40.57, BIZ-002).
   `ui/pipeline.js` opens it when a move needs more than the stage: a reason from
   the list for a lost stage (and a note for «سایر»), or a reason to leave a final
   stage. Both workflows and the reasons come from `sales.pipeline.pipeline_payload`;
   the server checks every rule again. {% endcomment %}
{{ pipeline_config|json_script:"pipeline-config" }}
<dialog id="stage-change-dialog" aria-labelledby="stage-change-title">
    <div class="d-flex flex-stack align-items-center mb-2"><h2 id="stage-change-title" class="mb-0">تغییر مرحله</h2><button class="btn btn-icon btn-light" type="button" data-close-dialog aria-label="بستن">×</button></div>
    <p class="text-gray-700 fs-7 mb-5" id="stage-change-subject"></p>
    <form id="stage-change-form" novalidate>
        <div class="d-grid gap-5">
            <div id="stage-change-target-field"><label class="form-label fw-semibold required" for="stage-change-target">مرحلهٔ تازه</label><select class="form-select form-select-solid" id="stage-change-target" name="stage" required></select><p class="text-danger fs-8 mt-1 mb-0" data-error-for="stage"></p></div>
            <div id="stage-change-lost-field" hidden><label class="form-label fw-semibold required" for="stage-change-lost-reason">دلیل</label><select class="form-select form-select-solid" id="stage-change-lost-reason" name="lost_reason"></select><p class="text-danger fs-8 mt-1 mb-0" data-error-for="lost_reason"></p></div>
            <div id="stage-change-note-field"><label class="form-label fw-semibold" for="stage-change-note">توضیح</label><textarea class="form-control form-control-solid" id="stage-change-note" name="note" rows="2" maxlength="300"></textarea><p class="text-danger fs-8 mt-1 mb-0" data-error-for="note"></p></div>
            <div id="stage-change-reopen-field" hidden><label class="form-label fw-semibold required" for="stage-change-reason">دلیل بیرون آمدن از مرحلهٔ پایانی</label><textarea class="form-control form-control-solid" id="stage-change-reason" name="reason" rows="2" maxlength="500"></textarea><p class="text-muted fs-8 mt-1 mb-0">این دلیل در تاریخچهٔ مرحله می‌ماند.</p><p class="text-danger fs-8 mt-1 mb-0" data-error-for="reason"></p></div>
        </div>
        <div class="d-flex justify-content-end gap-3 mt-6"><button class="btn btn-primary" type="submit">ثبت مرحله</button></div>
    </form>
</dialog>
