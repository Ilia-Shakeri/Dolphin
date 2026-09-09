"""Which dashboard widgets show, and in what order — the admin-facing half
of `common.dashboard`'s "what does this role's home page show" question.

Kept as its own module rather than folded into `common.dashboard` for the
same reason `common.branding` stays separate from what reads it: one module
owns *whether an admin may reach this*, one owns *what every reader
actually receives*. `common.dashboard.dashboard_for` calls `apply_layout`
exactly once, at the end, after every KPI/trend/breakdown has already been
assembled and scoped to that reader — this module never decides what a role
may see, only what order it renders in and whether this deployment's admin
turned it off for everyone.

`WIDGET_CATALOG` is a static list, independent of `feature_enabled(...)` —
the settings page always offers every widget that could ever exist on some
deployment's dashboard, with a plain-language note of which module gates it,
rather than the list changing shape under an admin's feet as they toggle
features elsewhere. A key with its feature off simply never appears on the
actual dashboard regardless of this setting, the same as today.
"""

from django.db import transaction

from accounts.models import User
from auditlog.services import log_activity
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from common.models import DashboardSettings

#: `(key, label, gating feature label)` — the feature label is shown, not
#: enforced here; `common.dashboard.dashboard_for` already enforces the real
#: gate through `feature_enabled(...)` before a widget's key ever exists.
WIDGET_CATALOG = [
    ("sales_amount_this_month", "فروش این ماه", "فروش"),
    ("sales_count_this_month", "تعداد فروش این ماه", "فروش"),
    ("outstanding", "مطالبات باز", "فاکتور"),
    ("calls_this_week", "تماس‌های هفت روز اخیر", "سرنخ‌ها"),
    ("after_sales_open", "پرونده‌های باز خدمات پس از فروش", "خدمات پس از فروش"),
    ("after_sales_closed_this_month", "بسته‌شده در این ماه (پس از فروش)", "خدمات پس از فروش"),
    ("trend", "روند فروش ۱۲ هفته‌ای", "فروش"),
    ("breakdown", "نمودار تفکیک وضعیت", "سرنخ‌ها / پس از فروش"),
]

WIDGET_KEYS = frozenset(key for key, _label, _feature in WIDGET_CATALOG)


def get_dashboard_settings():
    """The singleton row, creating it (empty — nothing hidden, no order
    override) on first read. Never raises, same reasoning as
    `common.branding.get_brand_settings`.
    """
    row, _ = DashboardSettings.objects.get_or_create(singleton=DashboardSettings.SINGLETON)
    return row


def _lock_platform_admin(actor):
    locked = User.objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if locked is None or locked.role != User.Role.PLATFORM_ADMIN:
        raise BusinessPermissionDenied("تغییر چیدمان داشبورد فقط برای مدیر پلتفرم مجاز است.")
    return locked


def _clean_keys(value, *, field):
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise BusinessRuleError({field: "فهرست کلیدهای ویجت نامعتبر است."})
    unknown = [key for key in value if key not in WIDGET_KEYS]
    if unknown:
        raise BusinessRuleError({field: f"ویجت ناشناخته: {', '.join(unknown)}"})
    # De-duplicated, order preserved — a caller sending the same key twice
    # (a double-click, a retried request) must not corrupt the stored order.
    seen = set()
    cleaned = []
    for key in value:
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(key)
    return cleaned


@transaction.atomic
def update_dashboard_settings(*, actor, hidden_widgets=None, widget_order=None):
    """Update which widgets are hidden and/or their order. Either argument
    left `None` is left untouched, same "independent, optional" shape as
    `common.branding.update_brand_settings`.
    """
    locked_actor = _lock_platform_admin(actor)
    row = DashboardSettings.objects.select_for_update().get_or_create(singleton=DashboardSettings.SINGLETON)[0]
    changed_fields = []

    cleaned_hidden = _clean_keys(hidden_widgets, field="hidden_widgets")
    if cleaned_hidden is not None:
        row.hidden_widgets = cleaned_hidden
        changed_fields.append("hidden_widgets")

    cleaned_order = _clean_keys(widget_order, field="widget_order")
    if cleaned_order is not None:
        row.widget_order = cleaned_order
        changed_fields.append("widget_order")

    if not changed_fields:
        return row

    row.updated_by = locked_actor
    row.save(update_fields=[*changed_fields, "updated_by", "updated_at"])
    log_activity(
        actor=locked_actor,
        operation="dashboard_settings.updated",
        instance=row,
        changes={"fields": changed_fields},
    )
    return row


def _ordered(items, key_of, order):
    """`items` sorted by their position in `order`; an item whose key is
    absent from `order` keeps its original relative position, appended
    after every explicitly ordered item — reordering one widget in the
    settings page never requires re-listing every other one.
    """
    if not order:
        return items
    position = {key: index for index, key in enumerate(order)}
    explicit = [item for item in items if key_of(item) in position]
    implicit = [item for item in items if key_of(item) not in position]
    explicit.sort(key=lambda item: position[key_of(item)])
    return explicit + implicit


def apply_layout(dashboard_payload):
    """`common.dashboard.dashboard_for`'s own return value, with this
    deployment's hidden/reordered widgets applied — called once, after
    every KPI has already been scoped to the reader, so a widget an admin
    "hides" is genuinely hidden for everyone, and a widget nobody may see
    for permission/data-scope reasons was never in the list to begin with.

    A key saved by a since-removed KPI (a widget dropped in a later version)
    is silently ignored, never an error — the same "disabling never breaks
    the page" posture `common.deployment.registry` already documents for
    features generally.
    """
    settings_row = get_dashboard_settings()
    hidden = frozenset(settings_row.hidden_widgets)
    order = settings_row.widget_order

    kpis = [kpi for kpi in dashboard_payload["kpis"] if kpi["key"] not in hidden]
    kpis = _ordered(kpis, key_of=lambda kpi: kpi["key"], order=order)

    trend = dashboard_payload["trend"]
    if "trend" in hidden:
        trend = None

    breakdown = dashboard_payload["breakdown"]
    if "breakdown" in hidden:
        breakdown = None

    return {"kpis": kpis, "trend": trend, "breakdown": breakdown}
