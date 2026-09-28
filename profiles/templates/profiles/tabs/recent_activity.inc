{% comment %} «آخرین رویدادها» on the overview tab. For a user: the newest few
   events of the timeline the «فعالیت‌ها» tab shows in full. For a customer
   (2.27.0): the whole timeline, in a box the same size as before that
   scrolls — a customer has no «فعالیت‌ها» tab any more, so there is nothing
   for an «همهٔ رویدادها» button to open. Rendered only where that timeline
   exists for this person type; the endpoint re-checks regardless. {% endcomment %}
{% if person.type != "customer" or "customer_timeline" in features %}
<section class="card h-100" data-recent-activity{% if person.type == "customer" %} data-recent-activity-all{% endif %}><div class="card-body d-flex flex-column">
    <div class="d-flex flex-stack align-items-center mb-5">
        <h2 class="fs-3 fw-bold text-gray-900 mb-0">آخرین رویدادها</h2>
        {% if person.type != "customer" %}<a class="btn btn-sm btn-light" href="?tab=activity" data-profile-tab-link="activity">همهٔ رویدادها</a>{% endif %}
    </div>
    <div data-recent-activity-loading class="text-center text-gray-700 py-10">در حال دریافت رویدادها…</div>
    <div data-recent-activity-empty class="text-center text-gray-700 py-10" hidden>هنوز رویدادی ثبت نشده است.</div>
    <div data-recent-activity-error class="text-center text-danger py-10" role="alert" hidden>دریافت رویدادها ممکن نشد.</div>
    <ol data-recent-activity-list class="customer-timeline list-unstyled mb-0{% if person.type == "customer" %} scroll-y mh-500px pe-3{% endif %}" hidden></ol>
    <p data-recent-activity-more class="text-muted fs-8 mt-4 mb-0" hidden></p>
</div></section>
{% endif %}
