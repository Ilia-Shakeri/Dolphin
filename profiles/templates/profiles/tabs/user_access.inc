{% comment %} Everything that changes what this account may do, gathered from the
   old «جزئیات کاربر» page: the controlled role change (with the keep/reset
   question for custom permissions), the per-user permission matrix (the same
   dialog User Management opens), the active sessions and activation. Rendered
   only for someone who administers this account; every action is re-checked
   by its own service. {% endcomment %}
{% if profile_can_change_roles %}<form id="change-role-form" action="/api/v1/users/{{ target_user_id }}/change-role/" method="post" class="card mb-5 mb-xl-8" novalidate>
    {% csrf_token %}<div class="card-body">
    <h2 class="fs-3 fw-bold text-gray-900 mb-5">تغییر نقش کنترل‌شده</h2>
    <label class="form-label fw-semibold" for="edit-role">نقش</label>
    <select class="form-select form-select-solid" id="edit-role" name="role" required>
        {% for value, label in assignable_roles %}<option value="{{ value }}">{{ label }}</option>{% endfor %}
    </select>
    <p class="text-danger fs-8 mt-1 mb-0" data-error-for="role"></p>
    <div class="d-flex justify-content-end gap-3 mt-6"><button class="btn btn-primary" type="submit">تغییر نقش</button></div>
</div></form>
<dialog id="role-change-access-dialog" aria-labelledby="role-change-access-title">
    <h2 id="role-change-access-title" class="mb-4">مجوزهای اختصاصی این کاربر</h2>
    <p class="text-muted">این کاربر مجوزهایی جدا از پیش‌فرض نقش فعلی‌اش دارد. با تغییر نقش، این مجوزهای اختصاصی چه سرنوشتی داشته باشند؟</p>
    <div class="d-flex flex-column gap-3 mt-5">
        <button id="role-change-keep" class="btn btn-light-primary text-start" type="button">حفظ مجوزهای اختصاصی فعلی (پیشنهادی)</button>
        <button id="role-change-reset" class="btn btn-light-danger text-start" type="button">بازنشانی به پیش‌فرض نقش تازه</button>
        <button class="btn btn-light" type="button" data-close-dialog>انصراف از تغییر نقش</button>
    </div>
</dialog>
{% comment %} «تغییر گذرواژه» و «نشست‌های فعال» — دو مودال که از منوی سه‌نقطهٔ
   بالای پروفایل («عملیات بیشتر») باز می‌شوند (2.40.35، مالک محصول: «تغییر
   گذرواژه باید به سه نقطه بالا سمت چپ انتقال یابد؛ دکمهٔ نشست‌های فعال هم
   باید در یک مودال باز شود»). `profile-tabs.js` هر `dialog` این بخش را به
   `body` می‌برد، پس از هر زبانه‌ای باز می‌شوند. {% endcomment %}
{% if profile_can_set_password %}<dialog id="set-password-dialog" aria-labelledby="set-password-title">
<form id="set-password-form" action="/api/v1/users/{{ target_user_id }}/set-password/" novalidate>
    <div class="d-flex align-items-center justify-content-between mb-2">
        <h2 class="fs-3 fw-bold text-gray-900 mb-0 d-flex align-items-center gap-2" id="set-password-title"><i class="di-duotone di-key fs-2 text-primary" aria-hidden="true"><span class="path1"></span><span class="path2"></span></i>تغییر گذرواژه</h2>
        <button type="button" class="btn btn-sm btn-icon btn-light" data-close-dialog aria-label="بستن"><i class="di-duotone di-cross fs-2"><span class="path1"></span><span class="path2"></span></i></button>
    </div>
    <p class="text-muted mb-5">{% if is_own_profile %}گذرواژهٔ تازهٔ حساب خودتان؛ نشست‌های دیگر شما پایان می‌یابد و همین نشست می‌ماند.{% else %}گذرواژهٔ تازه را به خود کاربر بدهید. همهٔ نشست‌های فعال او پایان می‌یابد و باید با گذرواژهٔ تازه وارد شود.{% endif %}</p>
    <div class="row g-5">
        <div class="col-md-6"><label class="form-label fw-semibold required" for="set-password-new">گذرواژهٔ تازه</label><input class="form-control form-control-solid" id="set-password-new" name="password" type="password" required minlength="8" autocomplete="new-password" dir="ltr"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="password"></p></div>
        <div class="col-md-6"><label class="form-label fw-semibold required" for="set-password-confirm">تکرار گذرواژهٔ تازه</label><input class="form-control form-control-solid" id="set-password-confirm" name="password_confirm" type="password" required minlength="8" autocomplete="new-password" dir="ltr"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="password_confirm"></p></div>
    </div>
    <div class="d-flex justify-content-end gap-3 mt-6"><button class="btn btn-primary" type="submit">تغییر گذرواژه</button></div>
</form>
</dialog>{% endif %}
<section class="card mb-5 mb-xl-8"><div class="card-body d-flex flex-wrap flex-stack align-items-center gap-4">
    <div>
        <h2 class="fs-3 fw-bold text-gray-900 mb-2">مجوزهای بخش‌ها</h2>
        <p class="text-muted mb-0">خواندن، ویرایش و حذف در هر بخش، جدا از پیش‌فرض نقش همین کاربر.</p>
    </div>
    <button class="btn btn-light-primary" type="button" data-profile-action="permissions" data-user-id="{{ target_user_id }}" data-user-name="{{ person.name }}">مشاهده و ویرایش مجوزها</button>
</div></section>
{% include "common/includes/permissions_dialog.inc" %}
<dialog id="user-sessions-dialog" aria-labelledby="user-sessions-title">
    <div class="d-flex align-items-center justify-content-between mb-2">
        <h2 class="fs-3 fw-bold text-gray-900 mb-0 d-flex align-items-center gap-2" id="user-sessions-title"><i class="di-duotone di-lock fs-2 text-primary" aria-hidden="true"><span class="path1"></span><span class="path2"></span><span class="path3"></span></i>نشست‌های فعال</h2>
        <button type="button" class="btn btn-sm btn-icon btn-light" data-close-dialog aria-label="بستن"><i class="di-duotone di-cross fs-2"><span class="path1"></span><span class="path2"></span></i></button>
    </div>
    <div class="d-flex flex-wrap flex-stack align-items-center gap-4 mb-4">
        <p class="text-muted mb-0 flex-grow-1">هر نشست یک ورود فعال این کاربر است. پایان‌دادن نشست، کاربر را از آن مرورگر خارج می‌کند و حساب او را غیرفعال نمی‌کند.</p>
        <button id="revoke-user-sessions" class="btn btn-light-danger" type="button">پایان همه نشست‌ها</button>
    </div>
    <div id="user-sessions-loading" class="text-center text-gray-700 py-10">در حال دریافت نشست‌ها…</div>
    <div id="user-sessions-empty" class="text-center text-gray-700 py-10" hidden>نشست فعالی برای این کاربر ثبت نشده است.</div>
    <div id="user-sessions-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0"><thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>شناسه نشست</th><th>انقضا</th></tr></thead><tbody id="user-sessions-table-body"></tbody></table></div>
</dialog>{% endif %}
<section class="card mb-5 mb-xl-8 border border-danger border-dashed"><div class="card-body">
    <h2 class="fs-3 fw-bold text-gray-900 mb-5">وضعیت دسترسی</h2>
    <p>کاربر غیرفعال اجازه ورود ندارد و بعدا می‌تواند در همین صفحه دوباره فعال شود. آخرین مدیر فعال پلتفرم قابل غیرفعال‌سازی نیست.</p>
    <button id="toggle-user-active" class="btn btn-danger" type="button" disabled>تغییر وضعیت کاربر</button>
</div></section>
