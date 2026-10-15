"""This company's instalment rules (2.40.51, owner decision 2026-10-14, Q15).

«همه را نیاز داریم و همگی فیچرهای اضافه هستند که اگر مشتری بخواهد باید فعال
شود. قابلیت شخصی‌سازی هم داشته باشند.» Each advanced instalment capability is
therefore its own manifest feature, off by default, and what it does is set
here, per company:

* `installment_reschedule` — change or extend an active plan's remaining
  schedule (`billing.installments.reschedule_plan`); nothing to configure;
* `installment_reminders` — SMS before the due date, on it, and after it
  (`billing.installment_reminders`): the days, the hour, the three texts;
* `installment_interest` (2.40.52) — simple or reducing, and the default
  annual rate an invoice takes when it names none (`billing.installment_charges`);
* `installment_late_fees` (2.40.52) — the grace in days, a percent of what is
  left or a fixed amount, and a cap. The day a fee is first set is kept
  (`late_fee_since`): no fee reaches a row due before it.

The three controls stay separate: the feature (the manifest), the
`installments.configure` capability (Platform Admin by default, grantable in
the permission matrix), and the stored row (`billing.models.InstallmentSettings`).
Turning a feature off keeps its settings.
"""

import unicodedata
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from accounts.access import has_any_capability
from auditlog.services import log_activity
from billing.models import (
    INSTALLMENT_TEMPLATE_MAX_LENGTH,
    INSTALLMENT_TEMPLATE_TOKENS,
    InstallmentSettings,
)
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessPermissionDenied, BusinessRuleError

CAPABILITY = "installments.configure"
RESCHEDULE = "installment_reschedule"
REMINDERS = "installment_reminders"
INTEREST = "installment_interest"
LATE_FEES = "installment_late_fees"
#: Every feature whose rules live on this row.
FEATURES = (RESCHEDULE, REMINDERS, INTEREST, LATE_FEES)

TEMPLATE_FIELDS = ("template_before", "template_due", "template_overdue")
NUMBER_FIELDS = {
    # field: (lowest, highest, Persian name)
    "remind_days_before": (0, 30, "روزهای پیش از سررسید"),
    "remind_days_after": (0, 60, "روزهای پس از سررسید"),
    "remind_send_hour": (7, 20, "ساعت ارسال"),
    "late_fee_grace_days": (0, 90, "روزهای مهلت"),
}
#: Money and percent fields: (highest, Persian name); the percent ones are
#: bounded to 100 by the service, the money ones only by the column.
DECIMAL_FIELDS = {
    "interest_default_rate": ("نرخ سالانهٔ پیش‌فرض"),
    "late_fee_value": ("مقدار جریمه"),
    "late_fee_cap": ("سقف جریمه"),
}
CHOICE_FIELDS = {
    "interest_method": dict(InstallmentSettings.InterestMethod.choices),
    "late_fee_mode": dict(InstallmentSettings.LateFeeMode.choices),
}


def get_settings():
    """The singleton row, created with the defaults on first read."""
    row, _ = InstallmentSettings.objects.get_or_create(singleton=InstallmentSettings.SINGLETON)
    return row


def enabled_features():
    return [feature for feature in FEATURES if feature_enabled(feature)]


def can_configure(user):
    """Settings worth showing: at least one of the features, and the capability."""
    return bool(enabled_features()) and has_any_capability(user, CAPABILITY)


def _clean_template(value, *, field):
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not text:
        raise BusinessRuleError({field: "متن پیامک را بنویسید."})
    if len(text) > INSTALLMENT_TEMPLATE_MAX_LENGTH:
        raise BusinessRuleError({field: f"متن پیامک نباید بیش از {INSTALLMENT_TEMPLATE_MAX_LENGTH} نویسه باشد."})
    # A brace that is not one of the known tokens would reach the customer as
    # it was typed; say so now rather than in a sent message.
    rest = text
    for token in INSTALLMENT_TEMPLATE_TOKENS:
        rest = rest.replace(token, "")
    if "{" in rest or "}" in rest:
        raise BusinessRuleError({field: "فقط این واژه‌ها در آکولاد پذیرفته می‌شوند: " + "، ".join(INSTALLMENT_TEMPLATE_TOKENS)})
    return text


def _clean_decimal(value, *, field):
    label = DECIMAL_FIELDS[field]
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise BusinessRuleError({field: f"{label} را به‌صورت عدد وارد کنید."}) from None
    if not number.is_finite() or number < 0 or number > Decimal("9999999999999999"):
        raise BusinessRuleError({field: f"{label} باید عددی مثبت باشد."})
    # A rate keeps two decimals; money is whole rials (owner decision 2026-10-14).
    if field == "interest_default_rate":
        if number > 100:
            raise BusinessRuleError({field: "نرخ سالانه نمی‌تواند بیش از ۱۰۰ درصد باشد."})
        return number.quantize(Decimal("0.01"))
    return number.quantize(Decimal("1")) if field == "late_fee_cap" else number.quantize(Decimal("0.01"))


def _clean_number(value, *, field):
    low, high, label = NUMBER_FIELDS[field]
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise BusinessRuleError({field: f"{label} باید عددی بین {low} تا {high} باشد."})
    return value


@transaction.atomic
def update_settings(*, actor, **changes):
    """Change any of the fields; one not passed stays as it is."""
    if not can_configure(actor):
        raise BusinessPermissionDenied("تنظیم قواعد اقساط مجاز نیست.")
    row = InstallmentSettings.objects.select_for_update().filter(singleton=InstallmentSettings.SINGLETON).first()
    if row is None:
        row = get_settings()
    changed = []
    for field, value in changes.items():
        if field in NUMBER_FIELDS:
            value = _clean_number(value, field=field)
        elif field in TEMPLATE_FIELDS:
            value = _clean_template(value, field=field)
        elif field == "remind_on_due":
            if not isinstance(value, bool):
                raise BusinessRuleError({field: "مقدار باید بله یا خیر باشد."})
        elif field in DECIMAL_FIELDS:
            value = _clean_decimal(value, field=field)
        elif field in CHOICE_FIELDS:
            if value not in CHOICE_FIELDS[field]:
                raise BusinessRuleError({field: "این گزینه پذیرفته نیست."})
        else:
            continue
        if getattr(row, field) != value:
            setattr(row, field, value)
            changed.append(field)
    # A percent fee is at most 100; a fixed one is whole rials.
    if row.late_fee_mode == InstallmentSettings.LateFeeMode.PERCENT and row.late_fee_value > 100:
        raise BusinessRuleError({"late_fee_value": "درصد جریمه نمی‌تواند بیش از ۱۰۰ باشد."})
    if row.late_fee_mode == InstallmentSettings.LateFeeMode.FIXED and row.late_fee_value != row.late_fee_value.quantize(Decimal("1")):
        raise BusinessRuleError({"late_fee_value": "مبلغ ثابت جریمه باید به ریال کامل باشد."})
    # The day a fee was first set: nothing due before it is ever charged.
    if row.late_fee_value > 0 and row.late_fee_since is None:
        row.late_fee_since = timezone.localdate()
        changed.append("late_fee_since")
    if changed:
        row.updated_by = actor
        row.save()
        log_activity(actor=actor, operation="installment_settings.updated", instance=row, changes={"fields": changed})
    return row


def serialize(row):
    from communications import sms

    return {
        "features": enabled_features(),
        # Reminders go out only through a configured SMS provider.
        "sms_provider_ready": sms.provider_is_available(),
        "remind_days_before": row.remind_days_before,
        "remind_on_due": row.remind_on_due,
        "remind_days_after": row.remind_days_after,
        "remind_send_hour": row.remind_send_hour,
        "template_before": row.template_before,
        "template_due": row.template_due,
        "template_overdue": row.template_overdue,
        "tokens": list(INSTALLMENT_TEMPLATE_TOKENS),
        "interest_method": row.interest_method,
        "interest_methods": [{"value": value, "label": label} for value, label in InstallmentSettings.InterestMethod.choices],
        "interest_default_rate": row.interest_default_rate,
        "late_fee_grace_days": row.late_fee_grace_days,
        "late_fee_mode": row.late_fee_mode,
        "late_fee_modes": [{"value": value, "label": label} for value, label in InstallmentSettings.LateFeeMode.choices],
        "late_fee_value": row.late_fee_value,
        "late_fee_cap": row.late_fee_cap,
        "late_fee_since": row.late_fee_since,
    }
