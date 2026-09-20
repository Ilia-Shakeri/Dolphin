"""Which dashboard widgets show, in what order, and how wide.

Two layers, and keeping them apart is the whole design:

* **the deployment default** (`common.models.DashboardSettings`, one row) —
  what this customer's dashboard looks like for everybody who never changed
  it, and, for a hidden widget, what nobody may put back;
* **one reader's own arrangement** (`common.models.UserDashboardLayout`, one
  row per user) — the order, the widths and the extra widgets *they* chose
  to hide, edited in place on the dashboard itself.

`common.dashboard.dashboard_for` calls `apply_layout` exactly once, at the
end, after every KPI/trend/breakdown has already been assembled and scoped to
that reader — this module never decides what a role *may* see, only what
order it renders in and how wide it is. A user's overlay may therefore only
ever narrow the result: a widget the deployment hid is not in the payload for
`apply_layout` to restore, and a widget the reader's permissions withheld was
never there to begin with.

Until 2.8.0 the deployment default had its own settings page and the reader
had nothing. The product owner asked for the reverse emphasis: the page is
gone and every user arranges their own dashboard inline, from a pencil
control on the dashboard itself. The deployment row is deliberately *kept*
— disabling a feature must never delete data (CLAUDE.md §7), an existing
customer's saved company layout is still the starting point everybody
inherits, and `apply_layout` still enforces its hidden set as a floor.

`WIDGET_CATALOG` is a static list, independent of `feature_enabled(...)`:
the editor always knows every widget that could ever exist on some
deployment's dashboard, with a plain-language note of which module gates it,
rather than the list changing shape underfoot as features are toggled
elsewhere. A key whose feature is off simply never appears on the actual
dashboard regardless of what is saved here.
"""

from django.db import transaction

from common.exceptions import BusinessRuleError
from common.models import DashboardSettings, UserDashboardLayout

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
    ("lead_conversion_rate", "گیج نرخ تبدیل سرنخ", "سرنخ‌ها"),
    ("receivables_collection_rate", "گیج نرخ وصول مطالبات", "فاکتور"),
    ("after_sales_closure_rate", "گیج نرخ بسته‌شدن پرونده‌ها", "خدمات پس از فروش"),
    ("agent_share", "سهم هر بازاریاب از فروش", "فروش"),
]

WIDGET_KEYS = frozenset(key for key, _label, _feature in WIDGET_CATALOG)

#: The prefix that marks the *other* kind of dashboard box.
#:
#: The row of capability tiles at the top of the page («مشتریان مجاز», «صف
#: سرنخ من», …) is not in `WIDGET_CATALOG` and cannot be: which tiles exist
#: depends on the reader's own capabilities and on which modules the
#: deployment enables, so there is no static list of them to write down. They
#: are still dashboard boxes, and the product owner asked for the editor to
#: cover every box on the page («ویرایش شامل همهٔ باکس‌های داشبورد شود»,
#: 2026-09-20) — so they get a key derived from the capability they show,
#: and the same order/size/hidden overlay applies to them.
#:
#: Deriving rather than declaring is what makes this safe: a key only ever
#: means "the tile for this capability", and a tile is only ever rendered for
#: a capability the reader already holds. Saving `capability:anything.at.all`
#: therefore arranges nothing, which is why the validation below checks the
#: key's *shape* and not a list of names.
CAPABILITY_WIDGET_PREFIX = "capability:"


def capability_widget_key(capability):
    """The layout key for the tile showing `capability`."""
    return f"{CAPABILITY_WIDGET_PREFIX}{capability}"


def _is_capability_key(key):
    """Whether `key` is a well-formed capability-tile key.

    `module.action`, the shape every capability in this product has
    (`common.permissions`), so a stored key can never be mistaken for a
    catalog key or for free text.
    """
    if not key.startswith(CAPABILITY_WIDGET_PREFIX):
        return False
    capability = key[len(CAPABILITY_WIDGET_PREFIX):]
    parts = capability.split(".")
    return len(parts) == 2 and all(
        part and part.replace("_", "").isalnum() for part in parts
    )


def _is_known_key(key):
    return key in WIDGET_KEYS or _is_capability_key(key)

#: `size token -> (Persian label, Bootstrap column classes)`.
#:
#: Four steps of the theme's own twelve-column grid, not a free pixel width:
#: a resizable widget still has to line up with every other card on the page
#: and still has to collapse to full width on a phone, which is exactly what
#: the vendor's grid already does. The `col-12` on each is what does the
#: collapsing; the `col-xl-*` is the chosen width once there is room for it.
WIDGET_SIZES = {
    "quarter": ("یک‌چهارم", "col-12 col-sm-6 col-xl-3"),
    "third": ("یک‌سوم", "col-12 col-sm-6 col-xl-4"),
    "half": ("نصف", "col-12 col-xl-6"),
    "full": ("تمام‌عرض", "col-12"),
}

#: The width each widget is designed at, used when the reader has not chosen
#: one. The two chart cards are wide because they carry a plot, not a figure;
#: everything else is a tile.
DEFAULT_WIDGET_SIZES = {
    "trend": "half",
    "breakdown": "third",
    "agent_share": "full",
}
FALLBACK_WIDGET_SIZE = "quarter"

#: A capability tile is a figure and a label; a quarter is what it was
#: designed at and what every one of them renders as until a reader says
#: otherwise. Named rather than left to `FALLBACK_WIDGET_SIZE` so the two can
#: diverge without either becoming a surprise.
DEFAULT_CAPABILITY_SIZE = "quarter"


def arrange_capability_tiles(widgets, user):
    """The top row of the dashboard, arranged for this reader.

    The companion to `apply_layout`, which does the same for the insight
    grid. Two functions rather than one because the two rows are built in
    different places and at different times — the tiles in
    `common.ui_views`, from capabilities and counts, and the insights in
    `common.dashboard` — and folding them together would mean assembling the
    whole page in one of those two just to sort it.

    They share the overlay itself, so a reader's hidden set and widths mean
    the same thing on both rows and a single "back to the default" clears
    both at once.
    """
    layout = effective_layout(user)
    arranged = []
    for widget in widgets:
        key = capability_widget_key(widget["capability"])
        if key in layout["hidden"]:
            continue
        arranged.append({
            **widget,
            "key": key,
            "size": size_class_for(key, layout["sizes"], DEFAULT_CAPABILITY_SIZE),
        })
    return _ordered(arranged, key_of=lambda item: item["key"], order=layout["order"])


def get_dashboard_settings():
    """The deployment's singleton row, creating it (empty — nothing hidden,
    no order override) on first read. Never raises, same reasoning as
    `common.branding.get_brand_settings`.
    """
    row, _ = DashboardSettings.objects.get_or_create(singleton=DashboardSettings.SINGLETON)
    return row


def get_user_layout(user):
    """This reader's own overlay, or `None` when they never saved one.

    `None` rather than an empty row on purpose: "never customised" and
    "customised back to the defaults" look the same on screen but are not
    the same fact, and only the first should silently follow a later change
    to the deployment default.
    """
    return UserDashboardLayout.objects.filter(pk=user.pk).first()


def _clean_keys(value, *, field):
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise BusinessRuleError({field: "فهرست کلیدهای ویجت نامعتبر است."})
    unknown = [key for key in value if not _is_known_key(key)]
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


def _clean_sizes(value, *, field):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise BusinessRuleError({field: "اندازهٔ ویجت‌ها نامعتبر است."})
    unknown_keys = [key for key in value if not _is_known_key(key)]
    if unknown_keys:
        raise BusinessRuleError({field: f"ویجت ناشناخته: {', '.join(sorted(unknown_keys))}"})
    unknown_sizes = sorted({str(size) for size in value.values() if size not in WIDGET_SIZES})
    if unknown_sizes:
        raise BusinessRuleError({field: f"اندازهٔ ناشناخته: {', '.join(unknown_sizes)}"})
    return dict(value)


@transaction.atomic
def update_user_dashboard_layout(*, actor, hidden_widgets=None, widget_order=None, widget_sizes=None):
    """Save this actor's own dashboard arrangement.

    No `user=` parameter, for the same reason `common.preferences.
    update_preferences` has none: a layout belongs to the person looking at
    it, and no role arranges somebody else's screen. Keeping that out of the
    signature means no view can get it wrong by forwarding a parameter.

    Not audit-logged: this is presentation, not a business event. The
    deployment-wide row still carries `updated_by`, and the
    `dashboard_settings.updated` label stays registered in
    `auditlog/labels.py` so the entries an admin's earlier change already
    wrote keep rendering in Persian.
    """
    row, _ = UserDashboardLayout.objects.select_for_update().get_or_create(pk=actor.pk)
    changed = []

    cleaned_hidden = _clean_keys(hidden_widgets, field="hidden_widgets")
    if cleaned_hidden is not None:
        row.hidden_widgets = cleaned_hidden
        changed.append("hidden_widgets")

    cleaned_order = _clean_keys(widget_order, field="widget_order")
    if cleaned_order is not None:
        row.widget_order = cleaned_order
        changed.append("widget_order")

    cleaned_sizes = _clean_sizes(widget_sizes, field="widget_sizes")
    if cleaned_sizes is not None:
        row.widget_sizes = cleaned_sizes
        changed.append("widget_sizes")

    if changed:
        row.save(update_fields=[*changed, "updated_at"])
    return row


@transaction.atomic
def reset_user_dashboard_layout(*, actor):
    """Drop this actor's overlay entirely, so they follow the deployment
    default again — which is not the same as saving an empty overlay; see
    `get_user_layout`.
    """
    UserDashboardLayout.objects.filter(pk=actor.pk).delete()


def _ordered(items, key_of, order):
    """`items` sorted by their position in `order`; an item whose key is
    absent from `order` keeps its original relative position, appended
    after every explicitly ordered item — moving one widget in the editor
    never requires re-listing every other one.
    """
    if not order:
        return items
    position = {key: index for index, key in enumerate(order)}
    explicit = [item for item in items if key_of(item) in position]
    implicit = [item for item in items if key_of(item) not in position]
    explicit.sort(key=lambda item: position[key_of(item)])
    return explicit + implicit


def size_class(key, sizes):
    """The Bootstrap column classes one insight widget should render at."""
    return size_class_for(key, sizes, DEFAULT_WIDGET_SIZES.get(key, FALLBACK_WIDGET_SIZE))


def size_class_for(key, sizes, default):
    """The same, with the caller naming what "unset" means for its own row."""
    token = sizes.get(key) or default
    return WIDGET_SIZES.get(token, WIDGET_SIZES[FALLBACK_WIDGET_SIZE])[1]


def effective_layout(user):
    """The hidden set, order and sizes this reader's dashboard should use,
    with the deployment default underneath and their own overlay on top.

    `hidden` unions the two: the deployment's hidden widgets are a floor a
    user cannot lift, their own are added to it. `order` and `sizes` are
    replaced rather than merged — a reader who has arranged their dashboard
    has said what they want it to look like, and half-inheriting somebody
    else's ordering on top of that produces an arrangement neither of them
    chose.
    """
    deployment = get_dashboard_settings()
    layout = None if user is None else get_user_layout(user)
    hidden = set(deployment.hidden_widgets)
    order = list(deployment.widget_order)
    sizes = {}
    if layout is not None:
        hidden |= set(layout.hidden_widgets)
        if layout.widget_order:
            order = list(layout.widget_order)
        sizes = dict(layout.widget_sizes or {})
    return {
        "hidden": frozenset(hidden),
        "order": order,
        "sizes": sizes,
        "deployment_hidden": frozenset(deployment.hidden_widgets),
        "is_customised": layout is not None,
    }


def apply_layout(dashboard_payload, user=None):
    """`common.dashboard.dashboard_for`'s own return value, arranged for
    this reader — called once, after every KPI has already been scoped, so a
    widget hidden here is genuinely hidden, and a widget nobody may see for
    permission/data-scope reasons was never in the list to begin with.

    A key saved by a since-removed KPI (a widget dropped in a later version)
    is silently ignored, never an error — the same "disabling never breaks
    the page" posture `common.deployment.registry` already documents for
    features generally.

    Each surviving part carries its own `size` (the Bootstrap column classes
    it should render at), so the page never has to hold a second copy of
    that mapping in JavaScript.
    """
    layout = effective_layout(user)
    hidden = layout["hidden"]
    order = layout["order"]
    sizes = layout["sizes"]

    def _sized(item):
        return {**item, "size": size_class(item["key"], sizes)}

    kpis = [_sized(kpi) for kpi in dashboard_payload["kpis"] if kpi["key"] not in hidden]
    kpis = _ordered(kpis, key_of=lambda kpi: kpi["key"], order=order)

    trend = dashboard_payload["trend"]
    if trend is not None and "trend" not in hidden:
        trend = {**trend, "key": "trend", "size": size_class("trend", sizes)}
    else:
        trend = None

    breakdown = dashboard_payload["breakdown"]
    if breakdown is not None and "breakdown" not in hidden:
        breakdown = {**breakdown, "key": "breakdown", "size": size_class("breakdown", sizes)}
    else:
        breakdown = None

    gauges = [_sized(gauge) for gauge in dashboard_payload["gauges"] if gauge["key"] not in hidden]
    gauges = _ordered(gauges, key_of=lambda gauge: gauge["key"], order=order)

    agent_share = dashboard_payload["agent_share"]
    if agent_share is not None and "agent_share" not in hidden:
        agent_share = {**agent_share, "key": "agent_share", "size": size_class("agent_share", sizes)}
    else:
        agent_share = None

    return {
        "kpis": kpis,
        "trend": trend,
        "breakdown": breakdown,
        "gauges": gauges,
        "agent_share": agent_share,
        "layout": {
            "order": order,
            "hidden": sorted(hidden),
            "sizes": sizes,
            # What the editor may *not* offer to unhide. Sent so the page can
            # leave those rows out of the widget list entirely rather than
            # showing a switch that silently does nothing.
            "locked_hidden": sorted(layout["deployment_hidden"]),
            "is_customised": layout["is_customised"],
        },
    }
