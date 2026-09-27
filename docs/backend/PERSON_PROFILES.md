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
| Tab shell and tab loaders | `common/static/common/dolphin-app.js` — `setupPersonProfile`, `setupProfileTabs`, `customerProfileLoaders`, `userProfileLoaders` |
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

## Phones

`common.phones.normalize_customer_phone` is the single normaliser (E.164
`+98…`; Persian/Arabic digits, `0098`, `98`, a leading `0` accepted).
`normalized_or_blank` wraps it for fields that merely *may* hold an Iranian
number: `User.phone` keeps whatever was typed, and `User.normalized_phone` is
blank when it does not normalise.
