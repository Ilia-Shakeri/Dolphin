{% load jalali_tags %}
{% comment %} کارت‌های آماری #۴ تا #۷ و نوار تکمیل پروفایل (۲.۲۰.۰) — همان «Stats» و
   «پردازش» سربرگ Metronic (pages/user-profile/overview.html). فقط کارت‌هایی که
   خواننده اجازهٔ دیدنشان را دارد رندر می‌شوند؛ مقدارشان از
   `/api/v1/profiles/<type>/<id>/cards/` می‌آید و کارتِ پنهان اصلاً محاسبه نمی‌شود. {% endcomment %}
{% if stat_cards or completion %}
<div class="d-flex flex-wrap flex-stack gap-3">
    <div class="d-flex flex-column flex-grow-1 pe-lg-8">
        {% if stat_cards %}
        <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
            <label class="text-gray-500 fs-7 fw-semibold" for="profile-card-period">بازه</label>
            <select id="profile-card-period" class="form-select form-select-sm form-select-solid w-auto">
                {% for key, label in card_periods %}<option value="{{ key }}"{% if key == default_card_period %} selected{% endif %}>{{ label }}</option>{% endfor %}
            </select>
        </div>
        <div class="d-flex flex-wrap" data-profile-cards>
            {% for card in stat_cards %}
            <div class="border border-gray-300 border-dashed rounded min-w-125px py-3 px-4 me-6 mb-3 profile-stat-card" data-profile-card="{{ card.key }}"{% if card.explains %} role="button" tabindex="0" data-score-card aria-haspopup="dialog" aria-controls="profile-score-dialog"{% endif %}>
                <div class="d-flex align-items-center">
                    <i class="ki-duotone {{ card.icon }} fs-3 me-2 text-gray-500" data-card-icon aria-hidden="true">{% for n in card.paths %}<span class="path{{ n }}"></span>{% endfor %}</i>
                    <div class="fs-2 fw-bold text-gray-900" data-card-value aria-live="polite">…</div>
                    <span class="badge badge-light fs-8 ms-2" data-card-trend hidden></span>
                </div>
                <div class="fw-semibold fs-6 text-gray-500">{{ card.label }}</div>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </div>
    {% if completion %}
    <div class="d-flex align-items-center w-200px w-sm-300px flex-column mt-3" data-profile-completion>
        <div class="d-flex justify-content-between w-100 mt-auto mb-2">
            <span class="fw-semibold fs-6 text-gray-500" id="profile-completion-label">تکمیل پروفایل</span>
            <span class="fw-bold fs-6">{{ completion.percent|persian_digits }}٪</span>
        </div>
        <div class="h-5px mx-3 w-100 bg-light mb-3">
            <div class="{% if completion.percent >= 80 %}bg-success{% elif completion.percent >= 50 %}bg-warning{% else %}bg-danger{% endif %} rounded h-5px" role="progressbar" style="width: {{ completion.percent }}%;" aria-valuenow="{{ completion.percent }}" aria-valuemin="0" aria-valuemax="100" aria-labelledby="profile-completion-label"></div>
        </div>
        {% if completion.missing %}
        <details class="w-100 fs-7 profile-completion-missing">
            <summary class="text-gray-600">{{ completion.missing|length|persian_digits }} مورد تکمیل نشده</summary>
            <ul class="list-unstyled mt-2 mb-0">
                {% for item in completion.missing %}
                <li class="mb-1">{% if item.input_id %}<a class="text-primary" href="?tab=info" data-profile-tab-link="info" data-focus="{{ item.input_id }}">{{ item.label }}</a>{% else %}<span class="text-gray-600">{{ item.label }}</span>{% endif %}</li>
                {% endfor %}
            </ul>
        </details>
        {% endif %}
    </div>
    {% endif %}
</div>
{% endif %}
