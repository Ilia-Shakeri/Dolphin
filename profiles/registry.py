"""The kinds of person a profile page can show, and what each one offers.

Dolphin has two kinds of person today — a customer and a user (a colleague) —
and one profile page for both (2.19.0). Everything that differs between them
lives in a `PersonAdapter`: how one is found within a viewer's scope, what
the header says, which tabs and quick actions a viewer gets. The page, its
template and its script know nothing about either type.

A third kind (a supplier, a partner) is one adapter module and one
`register(...)` call — no change to the page, the template or the tables that
refer to a person, because those store the adapter's `key` beside the id
(`person_type` + `person_id`, decision D1 in
`docs/PERSON_PROFILE_AND_INTEGRATIONS_PLAN.md`) rather than a foreign key per
type or a `ContentType` id that differs between databases.

Nothing here authorises anything by itself. Each adapter reads through the
owning module's own selector (`customers_for`, `crm_identities`, …), and every
API a tab calls re-checks feature, capability and object scope on its own.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProfileTab:
    """One tab: `key` is what `?tab=` names; `template` renders its body."""

    key: str
    label: str
    icon: str
    template: str
    icon_paths: int = 2

    @property
    def paths(self):
        return range(1, self.icon_paths + 1)


@dataclass(frozen=True)
class QuickAction:
    """One header button, or one entry under «بیشتر» when `in_menu`.

    Exactly one of `href`, `tab` or `action` says what it does: follow a
    link, switch to a tab, or run a named page behaviour
    (`data-profile-action`). An action with none of them is never built —
    there are no decorative buttons on this page.
    """

    key: str
    label: str
    icon: str
    href: str = ""
    tab: str = ""
    action: str = ""
    primary: bool = False
    in_menu: bool = False
    icon_paths: int = 2
    #: Extra `data-*` attributes the action's behaviour reads.
    data: dict = field(default_factory=dict)

    @property
    def paths(self):
        """`.path1`…`.pathN` — a duotone icon-font glyph draws nothing without them."""
        return range(1, self.icon_paths + 1)


class PersonAdapter:
    """What one kind of person looks like to the profile page.

    Subclasses set `key`/`label` and implement the methods that raise
    `NotImplementedError`; the rest have sensible defaults.
    """

    key = ""
    label = ""
    #: The deployment feature the whole profile needs, if any
    #: (`FeatureGatedViewMixin` semantics: off means 404).
    required_feature = None

    def may_open_any(self, viewer):
        """Whether `viewer` may open a profile of this kind at all.

        `False` is a 403 on the page; a viewer who may open *some* profiles of
        this kind but not the one asked for gets a 404 from `resolve`
        instead, so a person outside their scope is never confirmed to exist.
        """
        return True

    def scoped_queryset(self, viewer):
        raise NotImplementedError

    def resolve(self, viewer, person_id):
        return self.scoped_queryset(viewer).filter(pk=person_id).first()

    def display_name(self, person):
        raise NotImplementedError

    def header(self, viewer, person):
        raise NotImplementedError

    def tabs(self, viewer, person):
        raise NotImplementedError

    def quick_actions(self, viewer, person):
        return []

    def timeline(self, viewer, person):
        """`{"count": n, "events": [...]}` in `common.customer_timeline`'s shape."""
        return {"count": 0, "events": []}

    def profile_url(self, person):
        raise NotImplementedError


_ADAPTERS = {}


def register(adapter):
    if not adapter.key:
        raise ValueError("A person adapter needs a key.")
    if adapter.key in _ADAPTERS and type(_ADAPTERS[adapter.key]) is not type(adapter):
        raise ValueError(f"Person type {adapter.key!r} is already registered.")
    _ADAPTERS[adapter.key] = adapter
    return adapter


def adapter_for(key):
    """The adapter for `key`, or `None` for a type nobody registered."""
    return _ADAPTERS.get(key)


def person_types():
    return tuple(sorted(_ADAPTERS))


def resolve_person(viewer, person_type, person_id):
    """`(adapter, person)` within `viewer`'s scope, or `(adapter, None)`.

    The one entry point tables that store `person_type` + `person_id` use to
    turn a reference back into a record — never a direct `objects.get`, which
    would skip the viewer's scope.
    """
    adapter = adapter_for(person_type)
    if adapter is None:
        return None, None
    return adapter, adapter.resolve(viewer, person_id)
