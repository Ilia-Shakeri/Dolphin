<section class="card mb-5 mb-xl-8" data-attachments-panel data-attachments-field="{{ attachments_field }}" data-can-delete="{{ can_delete_attachments|yesno:'true,false' }}">
<div class="card-body">
    <div class="d-flex flex-wrap flex-stack align-items-center mb-4"><h2 class="fs-3 fw-bold text-gray-900 mb-5">پیوست‌ها</h2></div>
    {% if can_upload %}
    <form data-attachments-upload-form class="d-flex flex-wrap align-items-center gap-3 mb-5" novalidate>
        <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" required class="form-control form-control-solid" style="max-width: 24rem" data-attachments-file>
        <button class="btn btn-primary" type="submit">افزودن پیوست</button>
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
