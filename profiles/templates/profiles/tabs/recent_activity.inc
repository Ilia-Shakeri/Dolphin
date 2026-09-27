{% comment %} «آخرین رویدادها» on the overview tab: the newest few events of the
   same timeline the «فعالیت‌ها» tab shows in full. Rendered only where that
   timeline exists for this person type; the endpoint re-checks regardless. {% endcomment %}
{% if person.type != "customer" or "customer_timeline" in features %}
<section class="card h-100" data-recent-activity><div class="card-body">
    <div class="d-flex flex-stack align-items-center mb-5">
        <h2 class="fs-3 fw-bold text-gray-900 mb-0">آخرین رویدادها</h2>
        <a class="btn btn-sm btn-light" href="?tab=activity" data-profile-tab-link="activity">همهٔ رویدادها</a>
    </div>
    <div data-recent-activity-loading class="text-center text-gray-700 py-10">در حال دریافت رویدادها…</div>
    <div data-recent-activity-empty class="text-center text-gray-700 py-10" hidden>هنوز رویدادی ثبت نشده است.</div>
    <div data-recent-activity-error class="text-center text-danger py-10" role="alert" hidden>دریافت رویدادها ممکن نشد.</div>
    <ol data-recent-activity-list class="customer-timeline list-unstyled mb-0" hidden></ol>
</div></section>
{% endif %}
