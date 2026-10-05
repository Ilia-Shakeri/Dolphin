{% comment %} The profile's two dialogs (2.20.0): why the score is what it is, and
   a new task. Each is rendered only when the reader may use it. {% endcomment %}
{% for card in stat_cards %}{% if card.explains %}
<dialog id="profile-score-dialog" aria-labelledby="profile-score-title">
    <div class="d-flex flex-stack align-items-center mb-5">
        <h2 id="profile-score-title" class="mb-0">امتیاز {{ person.name }}</h2>
        <button class="btn btn-icon btn-light" type="button" data-close-dialog aria-label="بستن">×</button>
    </div>
    <div data-score-loading class="text-center text-gray-700 py-6">در حال دریافت امتیاز…</div>
    <p data-score-error class="text-danger mb-0" role="alert" hidden>دریافت امتیاز ممکن نشد.</p>
    <p data-score-empty class="text-gray-700 mb-0" hidden>هیچ‌کدام از عامل‌های امتیاز برای این شخص قابل سنجش نیست.</p>
    <div data-score-body hidden>
        <div class="d-flex align-items-center gap-3 mb-4">
            <span class="fs-2hx fw-bold text-gray-900" data-score-value></span>
            <span class="badge fs-7" data-score-level></span>
            <span class="text-muted fs-7" data-score-when></span>
        </div>
        <p class="text-muted fs-7">امتیاز از ۱۰۰ و بر پایهٔ قاعده است: هر عامل به نسبت وزنش امتیاز می‌گیرد. عاملی که برای این شخص قابل سنجش نیست کنار گذاشته می‌شود و امتیاز روی بقیه محاسبه می‌شود.</p>
        <div class="table-responsive"><table class="table align-middle table-row-dashed fs-7 gy-3 mb-0">
            <thead><tr class="text-start text-gray-700 fw-bold fs-8 text-uppercase gs-0"><th>عامل</th><th>امتیاز / وزن</th><th>دلیل</th></tr></thead>
            <tbody data-score-breakdown></tbody>
        </table></div>
        <h3 class="fs-6 fw-bold mt-6 mb-3">سابقهٔ امتیاز</h3>
        <ol class="list-unstyled mb-0 d-flex flex-wrap gap-2" data-score-history></ol>
    </div>
</dialog>
{% endif %}{% endfor %}
{% if can_add_task %}
<dialog id="profile-task-dialog" aria-labelledby="profile-task-title">
    <form id="profile-task-form" action="/api/v1/tasks/" method="post" novalidate>
        {% csrf_token %}
        <div class="d-flex flex-stack align-items-center mb-5">
            <h2 id="profile-task-title" class="mb-0">وظیفهٔ تازه</h2>
            <button class="btn btn-icon btn-light" type="button" data-close-dialog aria-label="بستن">×</button>
        </div>
        <p class="text-muted fs-7">دربارهٔ {{ person.type_label }}: {{ person.name }}</p>
        <div class="row g-5">
            <div class="col-12"><label class="form-label fw-semibold required" for="profile-task-title-input">عنوان</label><input class="form-control form-control-solid" id="profile-task-title-input" name="title" required maxlength="200"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="title"></p></div>
            <div class="col-md-6"><label class="form-label fw-semibold" for="profile-task-due">سررسید</label><input class="form-control form-control-solid" id="profile-task-due" name="due_at" type="text" data-jalali="datetime" placeholder="۱۴۰۵/۰۷/۰۵ ۱۰:۰۰"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="due_at"></p></div>
            <div class="col-md-6"><label class="form-label fw-semibold" for="profile-task-assignee">مسئول</label><select class="form-select form-select-solid" id="profile-task-assignee" name="assignee">{% for pk, name in task_assignees %}<option value="{{ pk }}"{% if pk == default_task_assignee %} selected{% endif %}>{{ name }}</option>{% endfor %}</select><p class="text-danger fs-8 mt-1 mb-0" data-error-for="assignee"></p></div>
            <div class="col-12"><label class="form-label fw-semibold" for="profile-task-notes">توضیح</label><textarea class="form-control form-control-solid" id="profile-task-notes" name="notes" maxlength="2000" rows="3"></textarea><p class="text-danger fs-8 mt-1 mb-0" data-error-for="notes"></p><p class="text-danger fs-8 mt-1 mb-0" data-error-for="person"></p></div>
        </div>
        <div class="d-flex justify-content-end gap-3 mt-6"><button class="btn btn-primary" type="submit">ثبت وظیفه</button></div>
    </form>
</dialog>
{% endif %}
