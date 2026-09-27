{% comment %} تاریخچهٔ یک شخص به ترتیب زمان. برای مشتری همان تایم‌لاین ۳۶۰ درجه
   است (تماس، سرنخ، سفارش، فاکتور، پرداخت، سند فروش، پروندهٔ پس‌ازفروش، پیوست و
   پیامک)؛ برای کاربر کارهایی که خودش کرده. هر منبع با ویژگی و دامنهٔ خودش در
   سرور فیلتر می‌شود. {% endcomment %}
<section class="card mb-5 mb-xl-8" id="profile-timeline"><div class="card-body">
    <div class="d-flex flex-wrap flex-stack align-items-center mb-4">
        <div>
            <h2 class="fs-3 fw-bold text-gray-900 mb-1">{% if person.type == "customer" %}تاریخچهٔ مشتری{% else %}فعالیت‌های {{ person.name }}{% endif %}</h2>
            <p class="text-muted fs-7 mb-0">{% if person.type == "customer" %}هر رویدادی که این مشتری داشته، به ترتیب زمان.{% else %}تماس‌ها، سرنخ‌ها، مشتریان، فروش‌ها و پرونده‌های این کاربر، به ترتیب زمان.{% endif %}</p>
        </div>
    </div>
    <div id="profile-timeline-loading" class="text-center text-gray-700 py-10">در حال دریافت تاریخچه…</div>
    <div id="profile-timeline-empty" class="text-center text-gray-700 py-10" hidden>هنوز رویدادی ثبت نشده است.</div>
    <div id="profile-timeline-error" class="text-center text-danger py-10" role="alert" hidden>دریافت تاریخچه ممکن نشد.</div>
    <ol id="profile-timeline-list" class="customer-timeline list-unstyled mb-0" hidden></ol>
    <p id="profile-timeline-more" class="text-muted fs-8 mt-4 mb-0" hidden></p>
</div></section>
