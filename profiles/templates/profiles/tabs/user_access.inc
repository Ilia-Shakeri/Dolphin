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
<section class="card mb-5 mb-xl-8"><div class="card-body d-flex flex-wrap flex-stack align-items-center gap-4">
    <div>
        <h2 class="fs-3 fw-bold text-gray-900 mb-2">مجوزهای بخش‌ها</h2>
        <p class="text-muted mb-0">خواندن، ویرایش و حذف در هر بخش، جدا از پیش‌فرض نقش همین کاربر.</p>
    </div>
    <button class="btn btn-light-primary" type="button" data-profile-action="permissions" data-user-id="{{ target_user_id }}" data-user-name="{{ person.name }}">مشاهده و ویرایش مجوزها</button>
</div></section>
{% include "common/includes/permissions_dialog.inc" %}
<section class="card mb-5 mb-xl-8"><div class="card-body">
    <div class="d-flex flex-wrap flex-stack align-items-center mb-4">
        <div><h2 class="fs-3 fw-bold text-gray-900 mb-5">نشست‌های فعال</h2><p class="text-muted">هر نشست یک ورود فعال این کاربر است. پایان‌دادن نشست، کاربر را از آن مرورگر خارج می‌کند و حساب او را غیرفعال نمی‌کند.</p></div>
        <button id="revoke-user-sessions" class="btn btn-danger" type="button">پایان همه نشست‌ها</button>
    </div>
    <div id="user-sessions-loading" class="text-center text-gray-700 py-10">در حال دریافت نشست‌ها…</div>
    <div id="user-sessions-empty" class="text-center text-gray-700 py-10" hidden>نشست فعالی برای این کاربر ثبت نشده است.</div>
    <div id="user-sessions-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0"><thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>شناسه نشست</th><th>انقضا</th></tr></thead><tbody id="user-sessions-table-body"></tbody></table></div>
</div></section>{% endif %}
<section class="card mb-5 mb-xl-8 border border-danger border-dashed"><div class="card-body">
    <h2 class="fs-3 fw-bold text-gray-900 mb-5">وضعیت دسترسی</h2>
    <p>کاربر غیرفعال اجازه ورود ندارد و بعدا می‌تواند در همین صفحه دوباره فعال شود. آخرین مدیر فعال پلتفرم قابل غیرفعال‌سازی نیست.</p>
    <button id="toggle-user-active" class="btn btn-danger" type="button" disabled>تغییر وضعیت کاربر</button>
</div></section>
