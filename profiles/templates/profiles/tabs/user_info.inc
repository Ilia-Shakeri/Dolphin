{% comment %} Two doors, one form. An administrator edits the account through
   `/api/v1/users/<id>/` (which may also rename it and move its workstream);
   a person editing their own profile saves through `/api/v1/auth/me/`, which
   accepts only their own profile fields. Neither form ever carries a role,
   an activation flag or a password — those have their own audited paths. {% endcomment %}
<form id="edit-user-form" action="{% if profile_edit_mode == 'admin' %}/api/v1/users/{{ target_user_id }}/{% else %}/api/v1/auth/me/{% endif %}" method="post" class="card mb-5 mb-xl-8" data-edit-mode="{{ profile_edit_mode }}" novalidate>
    {% csrf_token %}<div class="card-body">
    <h2 class="fs-3 fw-bold text-gray-900 mb-5">{% if profile_edit_mode == 'admin' %}ویرایش مشخصات{% else %}مشخصات من{% endif %}</h2>
    <div data-info-loading class="text-center text-gray-700 py-10">در حال دریافت مشخصات…</div>
    <div class="row g-5" data-info-fields hidden>
        {% if profile_edit_mode == 'admin' %}<div class="col-md-6"><label class="form-label fw-semibold" for="edit-username">نام کاربری</label><input class="form-control form-control-solid" id="edit-username" name="username" required maxlength="150" dir="ltr"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="username"></p></div>{% endif %}
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-first-name">نام</label><input class="form-control form-control-solid" id="edit-first-name" name="first_name" maxlength="150"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="first_name"></p></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-last-name">نام خانوادگی</label><input class="form-control form-control-solid" id="edit-last-name" name="last_name" maxlength="150"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="last_name"></p></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-job-title">سمت</label><input class="form-control form-control-solid" id="edit-job-title" name="job_title" maxlength="120" placeholder="مثلاً کارشناس فروش"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="job_title"></p></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-province">استان</label><select class="form-select form-select-solid" id="edit-province" name="province"><option value="">انتخاب استان</option>{% for name in province_names %}<option value="{{ name }}">{{ name }}</option>{% endfor %}</select><p class="text-danger fs-8 mt-1 mb-0" data-error-for="province"></p></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-email">ایمیل</label><input class="form-control form-control-solid" id="edit-email" name="email" type="email" maxlength="254" dir="ltr"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="email"></p></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-phone">تلفن</label><input class="form-control form-control-solid" id="edit-phone" name="phone" type="tel" maxlength="32" dir="ltr"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="phone"></p></div>
        {% if profile_edit_mode == 'admin' %}<div class="col-md-6"><label class="form-label fw-semibold" for="edit-workstream">حوزه کاری</label><select class="form-select form-select-solid" id="edit-workstream" name="workstream"><option value="sales">فروش و مرکز تماس</option><option value="after_sales">خدمات پس از فروش</option></select><p class="text-danger fs-8 mt-1 mb-0" data-error-for="workstream"></p></div>{% endif %}
    </div>
    <div class="d-flex justify-content-end gap-3 mt-6"><button class="btn btn-primary" type="submit">ذخیره تغییرات</button></div>
</div></form>
