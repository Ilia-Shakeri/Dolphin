# Person profiles

Since 2.19.0 Dolphin has one profile page for every kind of person — today a
customer and a user (a colleague). This document is the contract for that page
and the guide to adding a third kind. The product decisions behind it are in
[`docs/PERSON_PROFILE_AND_INTEGRATIONS_PLAN.md`](../PERSON_PROFILE_AND_INTEGRATIONS_PLAN.md).

## Where things live

| Piece | File |
|---|---|
| Adapter interface, registry, person references | `profiles/registry.py` |
| The customer and user adapters | `profiles/adapters.py` |
| Registration | `profiles/apps.py` (`ProfilesConfig.ready`) |
| Page views and the two legacy redirects | `profiles/ui_views.py` (routed in `common/ui_urls.py`) |
| Timeline API | `profiles/views.py`, `profiles/urls.py` |
| A user's activity timeline | `profiles/user_timeline.py` |
| Page template and one template per tab | `profiles/templates/profiles/profile.html`, `…/tabs/*.inc` |
| Tab shell and tab loaders | `common/static/common/js/` — `setupPersonProfile`, `setupProfileTabs`, `customerProfileLoaders`, `userProfileLoaders` |
| Presence | `accounts/middleware.py` (`PresenceMiddleware`, `is_online`) |
| Province list | `common/provinces.py` (reads `common/static/common/iran-provinces.json`) |

## The three controls

The profile never decides access by itself. For each person type:

1. **Feature** — `PersonAdapter.required_feature` gates the whole page (404 when
   off); each tab is added only when its own feature is on.
2. **Permission** — each tab and quick action is added only when the viewer holds
   the capability its data needs (`capabilities_for`).
3. **Object scope** — `PersonAdapter.scoped_queryset(viewer)` reads through the
   owning module's selector (`customers_for`, `crm_identities` narrowed by the
   administration and performance scopes). A person outside it is a 404.

Every API a tab calls re-checks all three on its own; the page only decides
what to render.

## The page

- **Header** (`PersonAdapter.header`): name, avatar or initials, an optional
  badge, presence (users), and three fixed facts — #1 job title (falls back to
  the role or the customer kind, with a tooltip saying so), #2 province, #3 the
  primary phone as a `tel:` link in E.164. A missing value renders as «—» with a
  tooltip and a screen-reader reason.
- **Quick actions** (`PersonAdapter.quick_actions`): each `QuickAction` has
  exactly one of `href`, `tab` or `action`; an action with none of them must not
  be built. `in_menu=True` puts it under «بیشتر».
- **Tabs** (`PersonAdapter.tabs`): a list of `ProfileTab(key, label, icon,
  template)`. The server renders every permitted tab's empty shell; the script
  fills a tab the first time it opens. `?tab=<key>` opens that tab first and
  `history.pushState` keeps Back working.
- **Telephony** (2.23.0, only with the `telephony` feature — the adapters ask
  `telephony.profile` and `telephony.services`, never the other way round): the
  customer «تماس‌ها» tab gains a PBX-calls section beside the logged calls
  (either half alone keeps the tab); users get a «تماس‌ها» tab for
  `calls.company` or for themselves with `calls.own`; «تماس» and the header
  phone become click-to-call (`data-originate-number`) for a viewer with an
  extension; PBX calls join both timelines; «عملکرد» shows the period's call
  figures. Contract: `docs/backend/TELEPHONY.md`.

## Referring to a person from another table

Tables that point at "a person" (the timeline store, tasks, scores and calls in
later phases) store the adapter key and the primary key:

```python
person_type = models.CharField(max_length=32)
person_id = models.PositiveBigIntegerField()

class Meta:
    indexes = [models.Index(fields=["person_type", "person_id"])]
```

Resolve one back with `profiles.registry.resolve_person(viewer, person_type,
person_id)`, never with a direct `objects.get` — that is what keeps the viewer's
scope.

## Adding a person type

1. Write an adapter subclassing `profiles.registry.PersonAdapter`: set `key`
   (stable, stored in other tables — never rename it), `label` and
   `required_feature`, and implement `scoped_queryset`, `display_name`,
   `header`, `tabs`, `profile_url`, and optionally `quick_actions` and
   `timeline`.
2. Register it in `ProfilesConfig.ready()` (or the owning app's own `ready()`):
   `register(SupplierAdapter())`.
3. Route its page to a `PersonProfileView` subclass with `person_type`,
   `person_id_kwarg` and `required_feature` set, and add the route's Persian
   title to `common/deployment/pages.py`.
4. Add one template per tab (a `.inc` partial) under `profiles/templates/profiles/tabs/` and a
   loader map for the type in `setupPersonProfile`.
5. Tests: scope (404 outside it), a disabled feature removes its tabs, every
   quick action does something.

## Stat cards (2.20.0)

`profiles/cards.py` holds one `StatCard` per slot and person type — `key`,
`label`, icon, the features it needs, `visible(viewer, person)` and
`compute(viewer, person, period)`. The page renders a shell only for the cards
`cards_for(viewer, …)` returns and the API computes only those, so a hidden
card's value never leaves the server. A value that cannot be computed is
`_missing(reason)`: «—» with the reason as its tooltip. Periods are Jalali
(`period_for`), each with the equal window before it for the trend.

To add a card: write `visible` and `compute`, add a `StatCard` to `CARDS`, and
test both its value and that a reader without the right does not get it.

## Completion bar

`profiles/completion.py` lists, per person type, the fields that make a record
useful and how much each counts (they sum to 100), with the «اطلاعات» input
that fills each one. A reader who may edit gets links that open that tab and
focus the input (`data-focus`).

## Scores

`scoring/strategies.py` has one strategy per person type. Each factor is
measured as a ratio 0..1 with a Persian reason, or `None` when it cannot be
measured for that person — then it is left out of the denominator. `prepare`
reads a whole batch with grouped queries, so the nightly
`recalculate_person_scores` is a handful of queries per two hundred people.
Weights live in `scoring.ScoringSettings` (defaults in code); snapshots in
`scoring.PersonScore`, stored only when the score or its breakdown changed or
the last one is a day old. Scores read *every* row about a person — who may
see one is decided by the score card's `visible`.

To add a strategy (an AI model, say): subclass `ScoringStrategy`, give it the
same `factors`/`prepare`/`evaluate` interface and register it in `STRATEGIES`.

## Tasks and notes

`tasks` and `timeline` are ordinary modules with their own features,
capabilities and matrix rows; both refer to a person by `person_type` +
`person_id` and resolve it through the viewer's scope. Anything that happens to
a person and has no row of its own elsewhere is recorded with
`timeline.services.record(...)` — pass a `source_ref` so a retry never
duplicates it.

## Phones

`common.phones.normalize_customer_phone` is the single normaliser (E.164
`+98…`; Persian/Arabic digits, `0098`, `98`, a leading `0` accepted).
`normalized_or_blank` wraps it for fields that merely *may* hold an Iranian
number: `User.phone` keeps whatever was typed, and `User.normalized_phone` is
blank when it does not normalise.
