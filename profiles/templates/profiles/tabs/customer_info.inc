<form id="edit-customer-form" action="/api/v1/customers/{{ customer_id }}/" method="post" class="card mb-5 mb-xl-8" novalidate>
    {% csrf_token %}<div class="card-body"><h2 class="fs-3 fw-bold text-gray-900 mb-5">مشخصات مشتری</h2>
    <div data-info-loading class="text-center text-gray-700 py-10">در حال دریافت مشخصات…</div>
    <div class="row g-5" data-info-fields hidden>
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-customer-name">نام کامل</label><input class="form-control form-control-solid" id="edit-customer-name" name="full_name" required maxlength="255"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="full_name"></p></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-customer-job-title">سمت</label><input class="form-control form-control-solid" id="edit-customer-job-title" name="job_title" maxlength="120" placeholder="مثلاً مدیر خرید"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="job_title"></p></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-customer-national-id">کد ملی</label><input class="form-control form-control-solid" id="edit-customer-national-id" name="national_id" maxlength="32"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="national_id"></p></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-customer-economic-code">شماره اقتصادی</label><input class="form-control form-control-solid" id="edit-customer-economic-code" name="economic_code" maxlength="32"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="economic_code"></p></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-customer-email">ایمیل</label><input class="form-control form-control-solid" id="edit-customer-email" name="email" type="email" maxlength="254"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="email"></p></div>
        {% comment %} See `create-customer-province` (customers/list.html)
           for why this is a fixed list — the same reasoning applies to an
           existing customer's own record. {% endcomment %}
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-customer-province">استان</label><select class="form-select form-select-solid" id="edit-customer-province" name="province"><option value="">انتخاب استان</option></select><p class="text-danger fs-8 mt-1 mb-0" data-error-for="province"></p></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-customer-city">شهر</label><input class="form-control form-control-solid" id="edit-customer-city" name="city" maxlength="100"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="city"></p></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-customer-postal-code">کد پستی</label><input class="form-control form-control-solid" id="edit-customer-postal-code" name="postal_code" maxlength="32"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="postal_code"></p></div>
        <div class="col-md-6"><label class="form-label fw-semibold" for="edit-customer-category">دسته‌بندی</label><select class="form-select form-select-solid" id="edit-customer-category" name="category" data-customer-category-select><option value="">بدون دسته‌بندی</option></select><p class="text-danger fs-8 mt-1 mb-0" data-error-for="category"></p></div>
        {% if can_assign_customer_owner %}<div class="col-md-6"><label class="form-label fw-semibold" for="edit-customer-owner">مسئول مشتری</label><select class="form-select form-select-solid" id="edit-customer-owner" name="owner">{% for pk, name in customer_owner_choices %}<option value="{{ pk }}">{{ name }}</option>{% endfor %}</select><p class="text-danger fs-8 mt-1 mb-0" data-error-for="owner"></p></div>{% endif %}
        <div class="col-md-6"><label class="form-label fw-semibold" for="customer-created-by">ثبت‌کننده</label><input class="form-control form-control-solid" id="customer-created-by" type="text" disabled></div>
        {% comment %} فقط مدیر پلتفرم و مدیر فروشگاه وضعیت را تغییر می‌دهند؛ برای
           بقیه همان متن خواندنی قبلی می‌ماند. سرویس مستقل از این نشانه‌گذاری رد می‌کند. {% endcomment %}
        {% if can_change_activation %}
        <div class="col-md-6"><label class="form-label fw-semibold" for="customer-active-select">وضعیت</label><select class="form-select form-select-solid" id="customer-active-select"><option value="true">فعال</option><option value="false">غیرفعال</option></select><p class="text-danger fs-8 mt-1 mb-0" data-error-for="is_active"></p></div>
        {% else %}
        <div class="col-md-6"><label class="form-label fw-semibold" for="customer-active">وضعیت</label><input class="form-control form-control-solid" id="customer-active" type="text" disabled></div>
        {% endif %}
        <div class="col-12"><label class="form-label fw-semibold" for="edit-customer-address">نشانی</label><textarea class="form-control form-control-solid" id="edit-customer-address" name="address" maxlength="2000"></textarea><p class="text-danger fs-8 mt-1 mb-0" data-error-for="address"></p></div>
        <div class="col-12"><label class="form-label fw-semibold" for="edit-customer-notes">یادداشت</label><textarea class="form-control form-control-solid" id="edit-customer-notes" name="notes" maxlength="4000"></textarea><p class="text-danger fs-8 mt-1 mb-0" data-error-for="notes"></p></div>
    </div>
    <div class="d-flex justify-content-end gap-3 mt-6"><button class="btn btn-primary" type="submit">ذخیره تغییرات</button></div>
</div></form>
<section class="card mb-5 mb-xl-8"><div class="card-body">
    <div class="d-flex flex-wrap flex-stack align-items-center mb-4"><h2 class="fs-3 fw-bold text-gray-900 mb-5">تلفن‌ها</h2><button id="open-create-phone" class="btn btn-primary" type="button">تلفن جدید</button></div>
    <div id="phones-loading" class="text-center text-gray-700 py-10">در حال دریافت تلفن‌ها…</div><div id="phones-empty" class="text-center text-gray-700 py-10" hidden>تلفنی ثبت نشده است.</div>
    <div id="phones-table-wrap" class="table-responsive" hidden><table class="table align-middle table-row-dashed fs-6 gy-4 mb-0"><thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>شماره</th><th>نرمال‌شده</th><th>برچسب</th><th>اصلی</th><th>وضعیت</th><th>عملیات</th></tr></thead><tbody id="phones-table-body"></tbody></table></div>
</div></section>
<dialog id="phone-dialog" aria-labelledby="phone-dialog-title">
    <form id="phone-form" action="/api/v1/customer-phones/" method="post" novalidate>
        {% csrf_token %}<div class="d-flex flex-stack align-items-center mb-5"><h2 id="phone-dialog-title">تلفن مشتری</h2><button class="btn btn-icon btn-light" type="button" data-close-dialog aria-label="بستن">×</button></div>
        <div class="row g-5">
            <div class="col-md-6"><label class="form-label fw-semibold" for="phone-raw">شماره</label><input class="form-control form-control-solid" id="phone-raw" name="raw_phone" type="tel" required maxlength="40"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="raw_phone"></p></div>
            <div class="col-md-6"><label class="form-label fw-semibold" for="phone-label">برچسب</label><input class="form-control form-control-solid" id="phone-label" name="label" maxlength="40"><p class="text-danger fs-8 mt-1 mb-0" data-error-for="label"></p></div>
            <div class="col-12 d-flex align-items-center gap-3"><input class="form-check-input" id="phone-primary" name="is_primary" type="checkbox"><label class="form-label fw-semibold" for="phone-primary">شماره اصلی</label><p class="text-danger fs-8 mt-1 mb-0" data-error-for="is_primary"></p></div>
        </div>
        <div class="d-flex justify-content-end gap-3 mt-6"><button class="btn btn-primary" type="submit">ذخیره تلفن</button></div>
    </form>
</dialog>
