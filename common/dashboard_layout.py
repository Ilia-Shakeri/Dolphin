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
    ("panel_tasks", "وظایف من", "وظایف"),
    ("panel_chat", "گفتگوهای اخیر", "گفتگوی داخلی"),
    ("panel_agenda", "برنامهٔ امروز", "یادآورها"),
    ("panel_calendar", "تقویم ماه", "وظایف"),
    ("panel_calls", "تماس‌های اخیر", "تلفن"),
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
#: Steps of the theme's own twelve-column grid, not a free pixel width: a
#: resizable widget still has to line up with every other card on the page
#: and still has to collapse to full width on a phone, which is exactly what
#: the vendor's grid already does. The `col-12` on each is what does the
#: collapsing; the `col-xl-*` is the chosen width once there is room for it.
#:
#: Four steps until 2.18.4; two-thirds and three-quarters were added when
#: resizing became a drag on the box's own border, where a jump straight
#: from half to full width read as the border refusing to follow the hand.
WIDGET_SIZES = {
    "quarter": ("یک‌چهارم", "dashboard-span-3"),
    "third": ("یک‌سوم", "dashboard-span-4"),
    "half": ("نصف", "dashboard-span-6"),
    "two_thirds": ("دوسوم", "dashboard-span-8"),
    "three_quarters": ("سه‌چهارم", "dashboard-span-9"),
    "full": ("تمام‌عرض", "dashboard-span-12"),
}

#: `height token -> minimum card height`, for dragging a box's top or bottom
#: border (2.18.4, product owner: «همهٔ باکس‌ها باید از لبه‌ها به‌صورت افقی و
#: عمودی بزرگ و کوچک شوند»).
#:
#: A *minimum*, never a fixed height: a box can be made taller than its
#: content, never shorter than it — clipping a figure or a legend to honour a
#: drag is not a size anybody wants. `rem`, so a reader's own font scale
#: (`common.preferences`) scales the box with the text inside it. A widget
#: missing from a reader's map takes its content's own height, which is what
#: every box did before this existed.
#: The dashboard is a grid of **cells** (2.38.1): a fixed row unit
#: (`--dashboard-row`, 0.5rem, in dolphin.css) and twelve columns, the way a phone
#: home screen is built from one cell size. A widget occupies a whole number of
#: columns (`WIDGET_SIZES`) and rows (below), widgets of different sizes pack
#: side by side, and a box is dragged or resized to the nearest cell. The row
#: and gap below must stay equal to the CSS custom properties.
ROW_REM = 0.5
GAP_REM = 0.0
GUTTER_REM = 0.5  # each box's own margin: two of them are the visible gap between boxes
#: A fine row (0.5rem, no grid gap — the gap is each box's own margin) so a box
#: can be as tall as its content with at most half a rem of air, rather than
#: snapping to a few tall steps: the page measures each box and takes the smallest
#: number of rows that holds it. Steps are every row from 6 to 120.
ROW_STEPS = tuple(range(6, 121))
#: Columns on the wide grid; a position's column is 1..GRID_COLUMNS.
GRID_COLUMNS = 12
MAX_ROW_POSITION = 800


def _span_length(rows):
    """The height of the *card* of a box spanning `rows` rows, in rem: the rows
    less the margin the box keeps on each side."""
    return f"{rows * ROW_REM - 2 * GUTTER_REM:g}rem"


#: `row token -> height of that many rows`, for dragging a box's top or bottom
#: border. A *minimum* in spirit: the editor never lets a box be made shorter
#: than what it has to show.
WIDGET_HEIGHTS = {f"r{rows}": _span_length(rows) for rows in ROW_STEPS}
ROWS_FOR_TOKEN = {f"r{rows}": rows for rows in ROW_STEPS}

#: Tokens saved before 2.38.1, when a height was a free minimum in rem. They are
#: read as the nearest row step and never rewritten behind anyone's back.
for _legacy_rem in (10, 12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 40):
    _rows = min(ROW_STEPS, key=lambda steps: abs(steps * ROW_REM - 2 * GUTTER_REM - _legacy_rem))
    ROWS_FOR_TOKEN[f"h{_legacy_rem}"] = _rows

#: How many rows each widget is designed at when nobody has chosen. A figure tile
#: is two; a gauge three; the lists and charts carry a body, so they are taller.
#: Only the first-paint guess: the page measures every box that has no chosen
#: height and sets the rows it actually needs.
DEFAULT_WIDGET_ROWS = {
    "sales_amount_this_month": 30,
    "sales_count_this_month": 30,
    "outstanding": 30,
    "calls_this_week": 30,
    "after_sales_open": 30,
    "after_sales_closed_this_month": 30,
    "lead_conversion_rate": 36,
    "receivables_collection_rate": 36,
    "after_sales_closure_rate": 36,
    "trend": 50,
    "breakdown": 50,
    "agent_share": 50,
    "panel_tasks": 54,
    "panel_chat": 54,
    "panel_agenda": 54,
    "panel_calendar": 62,
    "panel_calls": 54,
}
FALLBACK_WIDGET_ROWS = 22

#: The width each widget is designed at, used when the reader has not chosen
#: one. The two chart cards are wide because they carry a plot, not a figure;
#: everything else is a tile.
DEFAULT_WIDGET_SIZES = {
    "trend": "half",
    "breakdown": "third",
    "agent_share": "full",
    "panel_tasks": "third",
    "panel_chat": "third",
    "panel_agenda": "third",
    "panel_calendar": "third",
    "panel_calls": "third",
}
FALLBACK_WIDGET_SIZE = "quarter"

#: The smallest box each widget still reads at (2.40.2), in the same two units
#: the editor snaps to: a width step of `WIDGET_SIZES` and a number of rows.
#: Below these a chart's axis labels and legend no longer fit beside the plot
#: (the twelve-week trend at a quarter's width was the case that broke), so
#: the editor stops there, the server raises a smaller saved size to it, and a
#: layout saved before this existed is read at the minimum — never rewritten.
#: A widget absent here may take any step; its height still never drops below
#: its own content (`fitDashboardRows`).
WIDGET_MIN_SIZES = {
    "trend": "half",
    "breakdown": "third",
    "agent_share": "half",
    "panel_tasks": "third",
    "panel_chat": "third",
    "panel_agenda": "third",
    "panel_calendar": "third",
    "panel_calls": "third",
}
WIDGET_MIN_ROWS = {
    "trend": 40,
    "breakdown": 40,
    "agent_share": 40,
    "lead_conversion_rate": 30,
    "receivables_collection_rate": 30,
    "after_sales_closure_rate": 30,
    "panel_tasks": 40,
    "panel_chat": 40,
    "panel_agenda": 40,
    "panel_calendar": 50,
    "panel_calls": 40,
}
_SIZE_STEPS = list(WIDGET_SIZES)


def clamp_size(key, token):
    """`token`, or this widget's minimum when `token` is narrower."""
    minimum = WIDGET_MIN_SIZES.get(key)
    if minimum is None or token not in WIDGET_SIZES:
        return token
    return minimum if _SIZE_STEPS.index(token) < _SIZE_STEPS.index(minimum) else token


def min_rows(key):
    return WIDGET_MIN_ROWS.get(key, ROW_STEPS[0])


def widget_minimums():
    """The minimums in the shape the editor reads (`dashboard-layout-state`):
    `{key: [size step, rows]}`. A pair, not a nested object: the state is
    rendered into the page, and a page must never contain `}}` (it reads as
    leaked template syntax — `test_ui_connectivity`)."""
    keys = sorted(set(WIDGET_MIN_SIZES) | set(WIDGET_MIN_ROWS))
    return {key: [WIDGET_MIN_SIZES.get(key, _SIZE_STEPS[0]), min_rows(key)] for key in keys}

#: A capability tile is a figure and a label; a quarter is what it was
#: designed at and what every one of them renders as until a reader says
#: otherwise. Named rather than left to `FALLBACK_WIDGET_SIZE` so the two can
#: diverge without either becoming a surprise.
DEFAULT_CAPABILITY_SIZE = "quarter"


def arrange_capability_tiles(widgets, user, layout=None):
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

    `layout` is `effective_layout(user)` when the caller already has it —
    the dashboard view does, for `layout_state` — so one page render reads
    the two layout rows once rather than twice.
    """
    if layout is None:
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
            "height": height_for(key, layout["heights"]),
            "height_chosen": key in layout["heights"],
            "position": layout["positions"].get(key),
        })
    return _ordered(arranged, key_of=lambda item: item["key"], order=layout["order"])


def capability_tile_catalog(widgets, layout):
    """Every capability tile this reader could have on their dashboard —
    shown or hidden by them — for the "افزودن ویجت" dialog (2.18.2).

    `widgets` is the view's own list, already filtered to the reader's
    capabilities and this deployment's features, so this adds nothing a
    reader may not see; it only stops dropping the tiles *they* hid, so the
    dialog can offer them back with their real figure. A tile the
    deployment hides stays out, like everywhere else.
    """
    catalog = []
    for widget in widgets:
        key = capability_widget_key(widget["capability"])
        if key in layout["deployment_hidden"]:
            continue
        catalog.append({
            "key": key,
            "family": "tile",
            "label": widget["label"],
            "value": widget["value"],
            "icon": widget.get("icon"),
            "icon_paths": widget.get("icon_paths"),
            "accent": widget.get("accent"),
        })
    return catalog


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


def _clean_heights(value, *, field):
    """`{widget key: height token}`, the tokens being `WIDGET_HEIGHTS`'.

    A key mapped to `None` is dropped rather than refused: that is how the
    editor says "back to this box's own content height" without having to
    re-send every other box's height.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise BusinessRuleError({field: "ارتفاع ویجت‌ها نامعتبر است."})
    unknown_keys = [key for key in value if not _is_known_key(key)]
    if unknown_keys:
        raise BusinessRuleError({field: f"ویجت ناشناخته: {', '.join(sorted(unknown_keys))}"})
    unknown_heights = sorted({
        str(height) for height in value.values() if height is not None and height not in ROWS_FOR_TOKEN
    })
    if unknown_heights:
        raise BusinessRuleError({field: f"ارتفاع ناشناخته: {', '.join(unknown_heights)}"})
    # A height below the widget's minimum is raised to it, not refused: the
    # editor already stops there, so only a stale page or a hand-made request
    # sends one, and the reader still gets the nearest size that works.
    return {
        key: height if ROWS_FOR_TOKEN[height] >= min_rows(key) else f"r{min_rows(key)}"
        for key, height in value.items() if height is not None
    }


def _clean_positions(value, *, field):
    """`{widget key: [column, row]}`; a key mapped to `None` is dropped.

    Only the shape is checked here (two whole numbers in range): whether the box
    fits beside its neighbours is the page's business, and the server never
    needs to know — the page never places two boxes on the same cell, and an
    overlap from a stale save is resolved on the next paint.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise BusinessRuleError({field: "جای ویجت‌ها نامعتبر است."})
    unknown_keys = [key for key in value if not _is_known_key(key)]
    if unknown_keys:
        raise BusinessRuleError({field: f"ویجت ناشناخته: {', '.join(sorted(unknown_keys))}"})
    cleaned = {}
    for key, spot in value.items():
        if spot is None:
            continue
        if (
            not isinstance(spot, (list, tuple)) or len(spot) != 2
            or not all(isinstance(part, int) and not isinstance(part, bool) for part in spot)
            or not 1 <= spot[0] <= GRID_COLUMNS or not 1 <= spot[1] <= MAX_ROW_POSITION
        ):
            raise BusinessRuleError({field: f"جای ویجت «{key}» نامعتبر است."})
        cleaned[key] = [spot[0], spot[1]]
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
    # Raised to the widget's minimum, for the same reason as heights above.
    return {key: clamp_size(key, size) for key, size in value.items()}


@transaction.atomic
def update_user_dashboard_layout(
    *, actor, hidden_widgets=None, widget_order=None, widget_sizes=None, widget_heights=None,
    widget_positions=None,
):
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

    cleaned_heights = _clean_heights(widget_heights, field="widget_heights")
    if cleaned_heights is not None:
        row.widget_heights = cleaned_heights
        changed.append("widget_heights")

    cleaned_positions = _clean_positions(widget_positions, field="widget_positions")
    if cleaned_positions is not None:
        # Merged, not replaced, and `None` frees one box: the page sends only
        # the boxes it moved, so one move never has to re-send every other.
        merged = {**(row.widget_positions or {}), **cleaned_positions}
        for key, spot in (widget_positions or {}).items():
            if spot is None:
                merged.pop(key, None)
        row.widget_positions = merged
        changed.append("widget_positions")

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
    token = clamp_size(key, sizes.get(key) or default)
    return WIDGET_SIZES.get(token, WIDGET_SIZES[FALLBACK_WIDGET_SIZE])[1]


def height_for(key, heights):
    """How many grid rows this box spans: the reader's choice, else the
    widget's own default. A token saved by a since-removed step falls back to
    the default rather than to nothing."""
    chosen = ROWS_FOR_TOKEN.get(heights.get(key))
    return max(chosen or DEFAULT_WIDGET_ROWS.get(key, FALLBACK_WIDGET_ROWS), min_rows(key))


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
    heights = {}
    positions = {}
    if layout is not None:
        hidden |= set(layout.hidden_widgets)
        if layout.widget_order:
            order = list(layout.widget_order)
        sizes = dict(layout.widget_sizes or {})
        heights = dict(layout.widget_heights or {})
        positions = dict(layout.widget_positions or {})
    return {
        "hidden": frozenset(hidden),
        "order": order,
        "sizes": sizes,
        "heights": heights,
        "positions": positions,
        "deployment_hidden": frozenset(deployment.hidden_widgets),
        "is_customised": layout is not None,
    }


def size_choices():
    """`WIDGET_SIZES` in the shape the editor snaps a width drag to."""
    return [
        {"value": token, "label": label, "classes": classes}
        for token, (label, classes) in WIDGET_SIZES.items()
    ]


def height_choices():
    """`WIDGET_HEIGHTS` in the shape the editor snaps a height drag to."""
    return [
        {"value": token, "length": length, "rows": ROWS_FOR_TOKEN[token]}
        for token, length in WIDGET_HEIGHTS.items()
    ]


def layout_state(layout):
    """`effective_layout`'s result in the shape the page's editor reads —
    the same keys `apply_layout` returns under `"layout"`, so the editor has
    one shape to start from whether it arrived with the insight payload or
    was rendered into the page itself (`home.html`, `dashboard-layout-state`).
    """
    return {
        "order": list(layout["order"]),
        "hidden": sorted(layout["hidden"]),
        "sizes": dict(layout["sizes"]),
        "heights": dict(layout["heights"]),
        "positions": dict(layout["positions"]),
        "locked_hidden": sorted(layout["deployment_hidden"]),
        "is_customised": layout["is_customised"],
    }


def apply_layout(dashboard_payload, user=None):
    """`common.dashboard.dashboard_for`'s own return value, arranged for
    this reader — called once, after every KPI has already been scoped, so a
    widget hidden here is genuinely off the dashboard, and a widget nobody
    may see for permission/data-scope reasons was never in the list to begin
    with. (Since 2.18.2 a widget the reader hid *themselves* still travels
    under `hidden_available`, for the "افزودن ویجت" preview — see
    `_hidden_available`; a deployment-hidden one never does.)

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

    heights = layout["heights"]
    positions = layout["positions"]

    def _sized(item):
        return {
            **item,
            "size": size_class(item["key"], sizes),
            "height": height_for(item["key"], heights),
            # The row count is *chosen* only when the reader saved one; otherwise
            # the page measures the box and fits it.
            "height_chosen": item["key"] in heights,
            "position": positions.get(item["key"]),
        }

    kpis = [_sized(kpi) for kpi in dashboard_payload["kpis"] if kpi["key"] not in hidden]
    kpis = _ordered(kpis, key_of=lambda kpi: kpi["key"], order=order)

    trend = dashboard_payload["trend"]
    if trend is not None and "trend" not in hidden:
        trend = _sized({**trend, "key": "trend"})
    else:
        trend = None

    breakdown = dashboard_payload["breakdown"]
    if breakdown is not None and "breakdown" not in hidden:
        breakdown = _sized({**breakdown, "key": "breakdown"})
    else:
        breakdown = None

    gauges = [_sized(gauge) for gauge in dashboard_payload["gauges"] if gauge["key"] not in hidden]
    gauges = _ordered(gauges, key_of=lambda gauge: gauge["key"], order=order)

    agent_share = dashboard_payload["agent_share"]
    if agent_share is not None and "agent_share" not in hidden:
        agent_share = _sized({**agent_share, "key": "agent_share"})
    else:
        agent_share = None

    panels = [_sized(panel) for panel in dashboard_payload.get("panels", []) if panel["key"] not in hidden]
    panels = _ordered(panels, key_of=lambda panel: panel["key"], order=order)

    return {
        "kpis": kpis,
        "panels": panels,
        "trend": trend,
        "breakdown": breakdown,
        "gauges": gauges,
        "agent_share": agent_share,
        "hidden_available": _hidden_available(dashboard_payload, layout),
        # `locked_hidden` is what the editor may *not* offer to unhide — sent
        # so the page can leave those rows out of the widget list entirely
        # rather than showing a switch that silently does nothing.
        "layout": layout_state(layout),
    }


#: The families the "افزودن ویجت" dialog draws a preview for, per insight
#: part — the same five shapes the dashboard itself renders.
_SINGLE_PARTS = (("trend", "trend"), ("breakdown", "breakdown"), ("agent_share", "agent_share"))


def _hidden_available(dashboard_payload, layout):
    """The parts *this reader* hid themselves and could have back, with their
    real figures — for the "افزودن ویجت" dialog's preview.

    Only the reader's own hidden set, never the deployment's: a widget the
    deployment hides is a floor nobody lifts, so offering it would be a
    control that does nothing. And only parts that are in the payload at
    all — which `dashboard_for` already scoped to this reader's features,
    permissions and data — so nothing here widens what anybody may see: it is
    the same figure the widget would show if they put it back.

    Until 2.18.2 the dialog showed an invented sample per widget, because
    the page never had the real one for a widget it did not render.
    """
    reader_hidden = layout["hidden"] - layout["deployment_hidden"]
    sizes = layout["sizes"]
    available = []
    for kpi in dashboard_payload["kpis"]:
        if kpi["key"] in reader_hidden:
            available.append({"family": "kpi", **kpi, "size": size_class(kpi["key"], sizes)})
    for gauge in dashboard_payload["gauges"]:
        if gauge["key"] in reader_hidden:
            available.append({"family": "gauge", **gauge, "size": size_class(gauge["key"], sizes)})
    for panel in dashboard_payload.get("panels", []):
        if panel["key"] in reader_hidden:
            available.append({**panel, "size": size_class(panel["key"], sizes)})
    for key, family in _SINGLE_PARTS:
        part = dashboard_payload[key]
        if part is not None and key in reader_hidden:
            available.append({"family": family, **part, "key": key, "size": size_class(key, sizes)})
    return available
