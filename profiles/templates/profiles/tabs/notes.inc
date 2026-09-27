{% comment %} یادداشت‌ها — هر کس این پروفایل را می‌بیند و اختیار `notes.read` دارد
   آن‌ها را می‌خواند؛ نوشتن `notes.write` می‌خواهد؛ ویرایش فقط با نویسنده است و
   حذف با مدیر پلتفرم یا کسی که `notes.delete` دارد. هر یادداشت در «فعالیت‌ها» هم
   می‌نشیند. {% endcomment %}
<section class="card mb-5 mb-xl-8"><div class="card-body">
    <h2 class="fs-3 fw-bold text-gray-900 mb-5">یادداشت‌ها</h2>
    {% if can_write_notes %}
    <form id="profile-note-form" class="mb-8" novalidate>
        <label class="form-label fw-semibold" for="profile-note-body">یادداشت تازه</label>
        <textarea class="form-control form-control-solid" id="profile-note-body" name="body" rows="3" maxlength="4000" placeholder="مثلاً: نتیجهٔ جلسه، قرار بعدی، نکته‌ای که همکاران باید بدانند…"></textarea>
        <p class="text-danger fs-8 mt-1 mb-0" data-error-for="body"></p>
        <div class="d-flex justify-content-end mt-3"><button class="btn btn-sm btn-primary" type="submit">ثبت یادداشت</button></div>
    </form>
    {% endif %}
    <div id="profile-notes-loading" class="text-center text-gray-700 py-10">در حال دریافت یادداشت‌ها…</div>
    <div id="profile-notes-empty" class="text-center text-gray-700 py-10" hidden>هنوز یادداشتی ثبت نشده است.</div>
    <div id="profile-notes-error" class="text-center text-danger py-10" role="alert" hidden>دریافت یادداشت‌ها ممکن نشد.</div>
    <div id="profile-notes-list" class="d-flex flex-column gap-5" hidden></div>
    <div class="text-center mt-5"><button id="profile-notes-more" class="btn btn-sm btn-light" type="button" hidden>یادداشت‌های قدیمی‌تر</button></div>
</div></section>
