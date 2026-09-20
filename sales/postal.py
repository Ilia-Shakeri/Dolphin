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

    `icon` is a keenicon name from the purchased theme — presentation, kept
    beside the state so the panel needs no second table of its own, the same
    way `common.ui_views.WIDGET_STYLE` already keeps a tile's icon beside its
    capability. The four were chosen against the pictures the product owner
    asked for: a store, a box on its way out, a parcel in the postal
    network, and a delivery truck.
    """

    key: str
    label: str
    icon: str
    #: How many `<span class="pathN">` children that keenicon needs. Duotone
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
        icon="ki-shop",
        icon_paths=5,
        description="مرسوله آماده شده و هنوز در انبار فروشگاه است.",
    ),
    PostalState(
        key="handed_to_post",
        label="ارسال به پست",
        icon="ki-delivery-3",
        icon_paths=3,
        description="مرسوله از انبار خارج و برای تحویل به پست فرستاده شده است.",
    ),
    PostalState(
        key="with_post",
        label="بستهٔ دست پست است",
        icon="ki-parcel-tracking",
        icon_paths=3,
        description="پست مرسوله را تحویل گرفته و در شبکهٔ پستی است.",
    ),
    PostalState(
        key="out_for_delivery",
        label="ارسال به مشتری",
        icon="ki-truck",
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


def state_for(value):
    """The state a stored `postal_status` names, or `None` for free text.

    Matched by key first and then by label, because both forms are real: a
    row written since 3.0.0 holds the key, and a row an operator typed before
    it may hold the label word for word.
    """
    if not value:
        return None
    text = str(value).strip()
    return _BY_KEY.get(text) or _BY_LABEL.get(text)


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


def choices():
    """`[(key, label)]`, for a form that offers the vocabulary."""
    return [(state.key, state.label) for state in POSTAL_STATES]


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


#: code -> carrier. One entry today. A provider is added here and becomes
#: selectable; nothing else in the product has to learn its name.
CARRIERS = {ManualCarrier.code: ManualCarrier()}


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
