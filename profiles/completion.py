"""How complete a person's record is — the header's «تکمیل پروفایل» bar (2.20.0).

Each person type lists the fields that make a record useful and how much each
counts (they add up to 100). The bar shows the share filled in; the list of
what is missing links straight to that field on the «اطلاعات» tab, focused,
when the reader may edit it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CompletionField:
    key: str
    label: str
    weight: int
    #: The input on the «اطلاعات» tab that fills it.
    input_id: str


CUSTOMER_FIELDS = (
    CompletionField("full_name", "نام کامل", 10, "edit-customer-name"),
    CompletionField("phone", "تلفن", 15, "open-create-phone"),
    CompletionField("email", "ایمیل", 10, "edit-customer-email"),
    CompletionField("job_title", "سمت", 10, "edit-customer-job-title"),
    CompletionField("identity", "کد ملی / شماره اقتصادی", 10, "edit-customer-national-id"),
    CompletionField("province", "استان", 10, "edit-customer-province"),
    CompletionField("city", "شهر", 5, "edit-customer-city"),
    CompletionField("postal_code", "کد پستی", 10, "edit-customer-postal-code"),
    CompletionField("address", "نشانی", 10, "edit-customer-address"),
    CompletionField("category", "دسته‌بندی", 10, "edit-customer-category"),
)

USER_FIELDS = (
    CompletionField("first_name", "نام", 15, "edit-first-name"),
    CompletionField("last_name", "نام خانوادگی", 15, "edit-last-name"),
    CompletionField("phone", "تلفن", 20, "edit-phone"),
    CompletionField("email", "ایمیل", 15, "edit-email"),
    CompletionField("job_title", "سمت", 15, "edit-job-title"),
    CompletionField("province", "استان", 10, "edit-province"),
    CompletionField("avatar", "تصویر پروفایل", 10, ""),
)


def _customer_filled(customer):
    has_phone = any(phone.is_active for phone in customer.phones.all())
    identity = customer.economic_code if customer.kind == "legal" else customer.national_id
    return {
        "full_name": bool(customer.full_name.strip()),
        "phone": has_phone,
        "email": bool(customer.email),
        "job_title": bool(customer.job_title),
        "identity": bool(identity),
        "province": bool(customer.province),
        "city": bool(customer.city),
        "postal_code": bool(customer.postal_code),
        "address": bool(customer.address),
        "category": bool(customer.category),
    }


def _user_filled(user):
    from accounts.models import UserAvatar

    return {
        "first_name": bool(user.first_name),
        "last_name": bool(user.last_name),
        "phone": bool(user.phone),
        "email": bool(user.email),
        "job_title": bool(user.job_title),
        "province": bool(user.province),
        # An uploaded photo or an explicitly chosen default avatar — the
        # hashed fallback everyone starts with is not a choice.
        "avatar": bool(user.chosen_default_avatar) or UserAvatar.objects.filter(pk=user.pk).exists(),
    }


def completion_for(person_type, person, *, can_edit=False):
    """`{"percent", "missing": [{"key", "label", "input_id"}]}`."""
    if person_type == "customer":
        fields, filled = CUSTOMER_FIELDS, _customer_filled(person)
    elif person_type == "user":
        fields, filled = USER_FIELDS, _user_filled(person)
    else:
        return None
    percent = sum(field.weight for field in fields if filled[field.key])
    missing = [
        {"key": field.key, "label": field.label, "input_id": field.input_id if can_edit else ""}
        for field in fields
        if not filled[field.key]
    ]
    return {"percent": percent, "missing": missing}
