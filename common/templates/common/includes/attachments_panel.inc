{% load attachment_tags %}
{% comment %} توضیح کوتاه بالای فرم و محدودیت‌ها، همه از همان منبعی که سرور با آن
   اعتبارسنجی می‌کند خوانده می‌شوند (`common/templatetags/attachment_tags.py` →
   `attachments/models.py` و `attachments/services.py`)، نه از عددی که این‌جا
   دستی نوشته شده باشد. پس جمله‌ای که کاربر می‌خواند هرگز با قاعده‌ای که سرور
   اجرا می‌کند اختلاف پیدا نمی‌کند. {% endcomment %}
<section class="card mb-5 mb-xl-8" data-attachments-panel data-attachments-field="{{ attachments_field }}" data-can-delete="{{ can_delete_attachments|yesno:'true,false' }}" data-attachments-max-bytes="{% attachment_max_bytes %}" data-attachments-accept="{% attachment_accept %}">
<div class="card-body">
    <div class="d-flex flex-wrap flex-stack align-items-center mb-2"><h2 class="fs-3 fw-bold text-gray-900 mb-0">پیوست‌ها</h2></div>
    <p class="text-muted fs-7 mb-5">فایل‌های مربوط به این رکورد را این‌جا نگه دارید. فقط {% attachment_types_label %} پذیرفته می‌شود و حجم هر فایل حداکثر {% attachment_max_label %} است. نوع فایل از روی محتوای خودش بررسی می‌شود، نه از روی پسوند نام.</p>
    {% if can_upload %}
    <form data-attachments-upload-form class="d-flex flex-wrap align-items-center gap-3 mb-5" novalidate>
        <input type="file" accept="{% attachment_accept %}" required class="form-control form-control-solid" style="max-width: 24rem" data-attachments-file aria-describedby="attachments-rules-{{ attachments_field }}">
        <button class="btn btn-primary" type="submit">افزودن پیوست</button>
        <span id="attachments-rules-{{ attachments_field }}" class="sr-only">فقط {% attachment_types_label %}، حداکثر {% attachment_max_label %}.</span>
        <p class="text-danger fs-8 mt-1 mb-0 w-100" data-error-for="file"></p>
        <p class="text-danger fs-8 mt-1 mb-0 w-100" data-error-for="parent"></p>
    </form>
    {% endif %}
    <p data-attachments-empty class="text-center text-gray-700 py-10" hidden>پیوستی ثبت نشده است.</p>
    <div data-attachments-table-wrap class="table-responsive" hidden>
        <table class="table align-middle table-row-dashed fs-6 gy-4 mb-0">
            <thead><tr class="text-start text-gray-700 fw-bold fs-7 text-uppercase gs-0"><th>فایل</th><th>نوع</th><th>حجم</th><th>بارگذاری‌کننده</th><th>زمان</th><th>عملیات</th></tr></thead>
            <tbody data-attachments-table-body></tbody>
        </table>
    </div>
</div>
</section>
