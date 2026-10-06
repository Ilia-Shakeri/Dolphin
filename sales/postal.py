"""Where a parcel is, and who is allowed to say so.

Two things live here and nowhere else: the states a parcel can be in, and the
seam a real post-office API will be connected through.

**The states.** Until 3.0.0 `SalesDocument.postal_status` was free text —
whatever an operator typed. That was honest while nobody had decided what the
states *were*, and it meant the panel could not draw a progress stepper, the
composition chart grouped typos as separate statuses, and nothing could be
mapped onto a carrier's own vocabulary. The product owner named the four on
2026-09-20:

    ۱. انبار فروشگاه        ۲. ارسال به پست
    ۳. بستهٔ دست پست است    ۴. ارسال به مشتری

They are ordered, because a stepper is only meaningful if "before" and "after"
mean something, and the order is the physical one a parcel actually travels.

**Free text still works.** An existing deployment has rows carrying whatever
its operators typed, and a vocabulary is not a reason to lose them (CLAUDE.md
§7). `state_for` returns `None` for a value outside the table and every reader
here is written to cope: such a document renders its stored text and no
stepper, rather than being forced into a state nobody chose for it.

**The carrier seam.** `PostalCarrier` is the interface a real integration
implements; `ManualCarrier` is the one this product ships, and it is honest
about being manual — it tracks nothing and says so. A future provider adds a
subclass and a row in `CARRIERS`, and the panel, the services and the history
table need no change, because what a carrier returns is already expressed in
*these* states rather than in its own. `map_carrier_status` is the one place
a provider's vocabulary is translated, which is the whole point of having a
seam rather than letting a provider's strings reach the database.

Nothing here invents a business rule. Which state a document is in is still
only ever set by `sales.services.transition_postal_status`, through the same
capability check, with the same history row written.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PostalState:
    """One stop on a parcel's journey.

    `icon` is an icon-font glyph name from the purchased theme — presentation, kept
    beside the state so the panel needs no second table of its own, the same
    way `common.ui_views.WIDGET_STYLE` already keeps a tile's icon beside its
    capability. The four were chosen against the pictures the product owner
    asked for: a store, a box on its way out, a parcel in the postal
    network, and a delivery truck.
    """

    key: str
    label: str
    icon: str
    #: How many `<span class="pathN">` children that icon-font glyph needs. Duotone
    #: icons are drawn from two to seven layered paths and render as a smudge
    #: with the wrong count.
    icon_paths: int
    description: str


#: The four states, in the order a parcel travels them. The order is the
#: whole meaning of the stepper — index is "how far along", and `state_index`
#: is what every reader here asks rather than comparing labels.
POSTAL_STATES = (
    PostalState(
        key="in_store",
        label="انبار فروشگاه",
        icon="di-shop",
        icon_paths=5,
        description="مرسوله آماده شده و هنوز در انبار فروشگاه است.",
    ),
    PostalState(
        key="handed_to_post",
        label="ارسال به پست",
        icon="di-delivery-3",
        icon_paths=3,
        description="مرسوله از انبار خارج و برای تحویل به پست فرستاده شده است.",
    ),
    PostalState(
        key="with_post",
        label="بستهٔ دست پست است",
        icon="di-parcel-tracking",
        icon_paths=3,
        description="پست مرسوله را تحویل گرفته و در شبکهٔ پستی است.",
    ),
    PostalState(
        key="out_for_delivery",
        label="ارسال به مشتری",
        icon="di-truck",
        icon_paths=5,
        description="مرسوله برای تحویل به نشانی مشتری در مسیر است.",
    ),
)

#: The state a freshly registered document starts in, unless the operator
#: names another. The first stop, which is where a parcel actually is.
DEFAULT_POSTAL_STATE = POSTAL_STATES[0].key

_BY_KEY = {state.key: state for state in POSTAL_STATES}
#: Persian label -> state. A deployment that has been typing «ارسال به پست»
#: into the free-text field for months is already using these words, and
#: recognising them costs nothing and loses nothing.
_BY_LABEL = {state.label: state for state in POSTAL_STATES}


@dataclass(frozen=True)
class CarrierStatus:
    """One of Iran Post's own parcel statuses (2.40.26).

    The four `POSTAL_STATES` are the stages a parcel moves through; these are
    every status the post office itself reports — including the ones that are
    not a stage at all (a return, a seizure, an expired parcel). `stage` is the
    stage a status belongs to, for the stepper, or `None` when it is outside
    the journey; `tone` colours its badge. Each has its own icon from the UI
    kit's set, and no two share one (`test_postal_statuses`).
    """

    key: str
    label: str
    icon: str
    icon_paths: int
    stage: str | None
    tone: str
    #: The web service's numeric code (`sales.ebazar.PARCEL_STATUSES`), or
    #: `None` for a status the post office shows but the service does not code.
    code: int | None = None


CARRIER_STATUSES = (
    CarrierStatus("under_review", "تحت بررسی", "di-search-list", 3, "in_store", "info", 0),
    CarrierStatus("ready_to_send", "آماده ارسال", "di-package", 3, "handed_to_post", "primary", 2),
    CarrierStatus("sent", "ارسال شده", "di-send", 2, "with_post", "primary", 5),
    CarrierStatus("arrived_province", "وارده به استان توزیع", "di-geolocation", 2, "with_post", "info"),
    CarrierStatus("with_postman", "تحویل به نامه رسان", "di-scooter", 7, "out_for_delivery", "primary"),
    CarrierStatus("first_visit", "مراجعه اول", "di-home-2", 2, "out_for_delivery", "info"),
    CarrierStatus("second_visit", "مراجعه دوم", "di-notification-status", 4, "out_for_delivery", "warning"),
    CarrierStatus("po_box", "توزیع درصندوق پستی", "di-sms", 2, "out_for_delivery", "success"),
    CarrierStatus("smart_locker", "توزیع درصندوق هوشمند (لاکرز)", "di-safe-home", 2, "out_for_delivery", "success"),
    CarrierStatus("delivered", "توزیع شده", "di-check-circle", 2, "out_for_delivery", "success", 7),
    CarrierStatus("finance_confirmed", "تایید شده مالی", "di-verify", 2, None, "success", 70),
    CarrierStatus("collected", "وصول شده", "di-dollar", 3, None, "success", 71),
    CarrierStatus("not_found", "پیدا نشد", "di-question-2", 3, None, "danger", -1),
    CarrierStatus("cancelled_by_sender", "انصرافی", "di-cross-circle", 2, None, "danger", 1),
    CarrierStatus("ready_error", "اشتباه در آماده به ارسال", "di-shield-cross", 3, None, "warning", 3),
    CarrierStatus("manager_absent", "عدم حضور مدیر", "di-user-square", 3, None, "warning", 4),
    CarrierStatus("refused", "عدم قبول", "di-dislike", 2, None, "danger", 6),
    CarrierStatus("counter_held", "باجه معطله", "di-time", 2, None, "warning", 8),
    CarrierStatus("seized", "توقیفی", "di-lock", 3, None, "danger", 9),
    CarrierStatus("pre_return", "پیش برگشتی", "di-arrow-circle-right", 2, None, "warning", 10),
    CarrierStatus("returned", "برگشتی نهایی", "di-exit-left", 2, None, "danger", 11),
    CarrierStatus("return_confirmed", "تایید برگشتی", "di-arrows-loop", 2, None, "danger", 255),
    CarrierStatus("damaged", "خسارتی", "di-cross-square", 2, None, "danger"),
    CarrierStatus("shortage", "بی ترتیبی(کسری مرسوله)", "di-information-5", 3, None, "warning"),
    CarrierStatus("expired", "منقضی شده", "di-calendar-remove", 6, None, "danger"),
)

_CARRIER_BY_KEY = {status.key: status for status in CARRIER_STATUSES}
_CARRIER_BY_LABEL = {status.label: status for status in CARRIER_STATUSES}
_CARRIER_BY_CODE = {status.code: status for status in CARRIER_STATUSES if status.code is not None}


def carrier_status_for(value=None, *, code=None):
    """A post-office status by its key, its label or its numeric code."""
    if code is not None:
        return _CARRIER_BY_CODE.get(code)
    if not value:
        return None
    text = str(value).strip()
    return _CARRIER_BY_KEY.get(text) or _CARRIER_BY_LABEL.get(text)


def badge_for(value=None, *, code=None, text=""):
    """What to draw for a status: `{key, label, icon, icon_paths, tone}`.

    A stored stage, a stored post-office status, or (for a shipment) the
    carrier's code or words; `None` when none of them is known."""
    detail = carrier_status_for(value) or carrier_status_for(code=code) or carrier_status_for(text)
    if detail is not None:
        return {"key": detail.key, "label": detail.label, "icon": detail.icon,
                "icon_paths": detail.icon_paths, "tone": detail.tone}
    stage = _BY_KEY.get(str(value or "").strip()) or _BY_LABEL.get(str(value or "").strip())
    if stage is not None:
        return {"key": stage.key, "label": stage.label, "icon": stage.icon,
                "icon_paths": stage.icon_paths, "tone": "primary"}
    return None


def state_for(value):
    """The state a stored `postal_status` names, or `None` for free text.

    Matched by key first and then by label, because both forms are real: a
    row written since 3.0.0 holds the key, and a row an operator typed before
    it may hold the label word for word.
    """
    if not value:
        return None
    text = str(value).strip()
    stage = _BY_KEY.get(text) or _BY_LABEL.get(text)
    if stage is not None:
        return stage
    # A post-office status (2.40.26) sits on the stage it belongs to, if any.
    detail = carrier_status_for(text)
    return _BY_KEY.get(detail.stage) if detail is not None and detail.stage else None


def state_index(value):
    """How far along `value` is, or `None` when it is not a known state."""
    state = state_for(value)
    return POSTAL_STATES.index(state) if state is not None else None


def label_for(value):
    """What to call a stored status on screen.

    A known state's own Persian label, or the stored text unchanged — never
    an empty string and never a key: a reader looking at a document written
    before the vocabulary existed should see what was actually recorded.
    """
    detail = carrier_status_for(value)
    if detail is not None:
        return detail.label
    state = state_for(value)
    return state.label if state is not None else (str(value).strip() or "نامشخص")


def stepper_for(value):
    """The four stops, each marked `done`, `current` or `upcoming`.

    Returns `[]` for a status outside the vocabulary rather than guessing:
    drawing a four-step progress bar with none of them current would say
    something false about where the parcel is.
    """
    index = state_index(value)
    if index is None:
        return []
    marks = []
    for position, state in enumerate(POSTAL_STATES):
        if position < index:
            stage = "done"
        elif position == index:
            stage = "current"
        else:
            stage = "upcoming"
        marks.append({
            "key": state.key,
            "label": state.label,
            "icon": state.icon,
            "icon_paths": state.icon_paths,
            "description": state.description,
            "stage": stage,
        })
    return marks


def icon_for(value):
    """`{"icon", "icon_paths"}` of a known state, or `None` for free text —
    the same table every surface draws from (2.40.7)."""
    badge = badge_for(value)
    return {"icon": badge["icon"], "icon_paths": badge["icon_paths"]} if badge is not None else None


def keys_matching(text):
    """Every vocabulary key whose Persian label contains `text` (2.40.31), so a
    search in the words people read finds rows that store the key."""
    needle = str(text or "").strip()
    if not needle:
        return []
    return [key for key, label in choices() if needle in label]


def choices():
    """`[(key, label)]`, for a form that offers the vocabulary."""
    return [(state.key, state.label) for state in POSTAL_STATES] + [
        (status.key, status.label) for status in CARRIER_STATUSES
    ]


# --- the carrier seam --------------------------------------------------------


class PostalCarrier:
    """What a post-office integration has to be able to do.

    Deliberately small. A carrier is asked one question — where is this
    tracking number — and answers in *this product's* states, never in its
    own. Everything else about a parcel (who it belongs to, what is in it,
    what happened to it before) is already in this database and is not a
    carrier's to report.

    `track` returns `(state_key, raw_status)` or `None` when the carrier has
    nothing to say. The raw status travels alongside so an operator can be
    shown what the provider actually said when the mapping is unclear, and so
    a mapping gap is visible in a log rather than silently becoming the
    default state.
    """

    #: Stable identifier, stored in configuration rather than a class name.
    code = ""
    #: What an operator sees when choosing one.
    label = ""
    #: Whether this carrier can answer `track` at all. A manual carrier
    #: cannot, and the panel uses this to decide whether to offer a "refresh
    #: from the carrier" control rather than offering one that never works.
    supports_tracking = False

    #: Provider status -> one of `POSTAL_STATES`' keys. The one place a
    #: provider's own vocabulary is translated; a subclass fills it in.
    STATUS_MAP = {}

    def track(self, tracking_number):  # pragma: no cover - interface
        raise NotImplementedError

    def map_status(self, raw_status):
        """`raw_status` as one of this product's states, or `None`.

        `None` rather than a default: a status a provider sends and this
        table does not know is a gap to be noticed and filled, and quietly
        answering "in store" would hide it behind a plausible-looking screen.
        """
        if raw_status is None:
            return None
        key = self.STATUS_MAP.get(str(raw_status).strip())
        return key if key in _BY_KEY else None


class ManualCarrier(PostalCarrier):
    """No integration: an operator moves the parcel along by hand.

    What this product ships, and what every deployment uses until a real
    provider is connected. It answers `track` with `None` rather than raising,
    because "nobody is tracking this" is a true answer and not an error.
    """

    code = "manual"
    label = "ثبت دستی (بدون اتصال به پست)"
    supports_tracking = False

    def track(self, tracking_number):
        return None


class EbazarCarrier(PostalCarrier):
    """Iran Post through the «بازار الکترونیک» web service (`sales/ebazar.py`).

    Its vocabulary is the carrier's numeric status code; only the codes that
    mean the same thing as one of this product's states are mapped, and every
    other code (return, cancelled, not found) is left unmapped on purpose.
    """

    code = "ebazar"
    label = "پست ایران (بازار الکترونیک)"
    supports_tracking = True

    @property
    def STATUS_MAP(self):
        from sales import ebazar

        return {str(code): state for code, (_, state) in ebazar.PARCEL_STATUSES.items() if state}

    def track(self, tracking_number):
        from sales import shipping

        return shipping.track(tracking_number)


#: code -> carrier. A provider is added here and becomes
#: selectable; nothing else in the product has to learn its name.
CARRIERS = {ManualCarrier.code: ManualCarrier(), EbazarCarrier.code: EbazarCarrier()}


def carrier_for(code):
    """The configured carrier, falling back to manual.

    Falling back rather than raising: a deployment whose configured provider
    has been removed from a later build must still be able to open its own
    parcels page, and manual is what it was doing before the provider existed.
    """
    return CARRIERS.get(code or ManualCarrier.code, CARRIERS[ManualCarrier.code])


def map_carrier_status(code, raw_status):
    """Translate one provider status into one of this product's states."""
    return carrier_for(code).map_status(raw_status)
