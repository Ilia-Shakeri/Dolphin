{% comment %} The per-user Read/Edit/Delete matrix dialog, driven by
   `setupPermissionsDialog()` in dolphin-app.js. Shared by User Management
   and the «دسترسی‌ها» tab of a user's profile (2.19.0), so the two can never
   drift apart. {% endcomment %}
<dialog id="permissions-dialog" aria-labelledby="permissions-title">
    <div class="d-flex flex-stack align-items-center mb-5">
        <h2 id="permissions-title">مجوزهای کاربر</h2>
        <button class="btn btn-icon btn-light" type="button" data-close-dialog aria-label="بستن">×</button>
    </div>
    <p class="mb-1"><span class="fw-semibold">کاربر:</span> <span id="permissions-user-name"></span></p>
    <p class="mb-1"><span class="fw-semibold">نقش فعلی:</span> <span id="permissions-user-role"></span></p>
    <p class="text-muted fs-7 mb-5" id="permissions-custom-note" hidden>ردیف‌های ستاره‌دار با پیش‌فرض این نقش فرق دارند.</p>
    <div id="permissions-loading" class="text-center text-gray-700 py-6">در حال دریافت مجوزها…</div>
    <p class="text-danger fs-7 mb-4" id="permissions-error" hidden></p>
    <div id="permissions-body" hidden>
        <div class="table-responsive">
            <table class="table align-middle table-row-dashed fs-6 gy-2 mb-0">
                <thead>
                    <tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0">
                        <th>بخش</th>
                        <th class="text-center">خواندن</th>
                        <th class="text-center">ویرایش</th>
                        <th class="text-center">حذف</th>
                    </tr>
                </thead>
                <tbody id="permissions-table-body"></tbody>
            </table>
        </div>
        <div class="d-flex justify-content-between flex-wrap gap-3 mt-6">
            <button id="permissions-reset" class="btn btn-light-danger" type="button">بازنشانی به پیش‌فرض نقش</button>
            <div class="d-flex flex-wrap gap-3">
                <button id="permissions-close" class="btn btn-light" type="button" data-close-dialog>بستن</button>
                <button id="permissions-cancel-edit" class="btn btn-light" type="button" hidden>انصراف از ویرایش</button>
                <button id="permissions-edit" class="btn btn-primary" type="button">ویرایش مجوزها</button>
                <button id="permissions-save" class="btn btn-primary" type="button" hidden>ذخیره تغییرات</button>
            </div>
        </div>
    </div>
</dialog>
