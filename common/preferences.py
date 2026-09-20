"""One reader's own view of the panel: typeface, scale, currency unit, theme.

Three settings surfaces now exist and they are deliberately not the same
thing:

* `common/branding.py` — what *this deployment* calls itself. One row,
  Platform Admin only, seen by every user and by anonymous visitors.
* `common/dashboard_layout.py` — which widgets *this deployment* shows, plus
  each user's own arrangement on top.
* this module — how *one reader* wants their own screen to look.

Nothing here is a permission or a feature gate. A preference may change what
a figure looks like; it may never change which figures a reader is allowed to
receive. That is still `common/permissions.py` and
`common/deployment/profile.py`, unchanged.

The currency unit is the one preference with a value beyond presentation, so
it is worth being explicit: **every amount in this product is stored in rial
and keeps being stored in rial.** «تومان» is a display unit — a division by
ten on the way out and a multiplication by ten on the way back in
(`to_display_amount` / `to_storage_amount`). Two users with different units
looking at the same invoice are looking at the same stored number.
"""

from decimal import Decimal

from django.db import DatabaseError, transaction

from common.models import (
    DEFAULT_PANEL_FONT_FAMILY,
    DEFAULT_PANEL_FONT_SCALE,
    PANEL_FONT_FAMILIES,
    PANEL_FONT_FAMILY_STACKS,
    PANEL_FONT_SCALE_SIZES,
    PANEL_FONT_SCALES,
    UserPreference,
)

#: Rial per toman. Named rather than spelled `10` at each site so the places
#: that scale an amount cannot drift apart, and so a reader of any one of
#: them can see immediately which direction the conversion goes.
RIALS_PER_TOMAN = Decimal(10)

CURRENCY_LABELS = {
    UserPreference.CurrencyUnit.RIAL: "ریال",
    UserPreference.CurrencyUnit.TOMAN: "تومان",
}

DEFAULTS = {
    "font_family": DEFAULT_PANEL_FONT_FAMILY,
    "font_scale": DEFAULT_PANEL_FONT_SCALE,
    "currency_unit": UserPreference.CurrencyUnit.RIAL,
    "theme": UserPreference.Theme.SYSTEM,
}


def catalog():
    """The choices the settings page renders, built from the model's own
    tuples so the page can never offer a value the field would reject."""
    return {
        "font_families": [{"value": value, "label": label} for value, label, _stack in PANEL_FONT_FAMILIES],
        "font_scales": [{"value": value, "label": label} for value, label, _size in PANEL_FONT_SCALES],
        "currency_units": [
            {"value": value, "label": label} for value, label in UserPreference.CurrencyUnit.choices
        ],
        "themes": [{"value": value, "label": label} for value, label in UserPreference.Theme.choices],
    }


def effective_preferences(user):
    """What this reader's screen should actually use — defaults for anyone
    who never saved anything, and for an anonymous visitor on the login page.

    Never raises. This is read by a context processor on every single
    rendered page, including the 500 handler, so a database that is briefly
    unreachable must not turn one failure into two — the same posture
    `common.branding.effective_brand` already takes and for the same reason.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return dict(DEFAULTS)
    try:
        row = UserPreference.objects.filter(pk=user.pk).first()
    except DatabaseError:
        return dict(DEFAULTS)
    if row is None:
        return dict(DEFAULTS)
    return {
        "font_family": row.font_family,
        "font_scale": row.font_scale,
        "currency_unit": row.currency_unit,
        "theme": row.theme,
    }


@transaction.atomic
def update_preferences(*, actor, font_family=None, font_scale=None, currency_unit=None, theme=None):
    """Save this actor's own preferences. Every argument is independent and
    optional, the same shape `common.branding.update_brand_settings` uses.

    There is no `user=` parameter on purpose: a preference belongs to the
    account owner, and no role — not even Platform Admin — sets somebody
    else's typeface. Restricting it at the signature means no view can get
    this wrong by forwarding a request parameter.

    Not audit-logged, also on purpose. `auditlog` records what changed about
    the *business*; that a colleague prefers a larger font is not an event
    anybody investigating an invoice needs to page through.
    """
    row, _ = UserPreference.objects.select_for_update().get_or_create(pk=actor.pk)
    changed = []
    for field, value in (
        ("font_family", font_family),
        ("font_scale", font_scale),
        ("currency_unit", currency_unit),
        ("theme", theme),
    ):
        if value is None:
            continue
        setattr(row, field, value)
        changed.append(field)
    if changed:
        row.save(update_fields=[*changed, "updated_at"])
    return row


def preference_css(preferences):
    """A `<style>` element's inner text carrying this reader's typeface and
    scale — `None` when they kept both defaults, so `base.html` can write
    `{% if panel_preference_css %}` with no second check.

    An inline style rather than a rule in `dolphin.css`, and that is the
    point, not a shortcut: that sheet is forbidden from choosing the panel's
    typeface (`test_the_override_sheet_does_not_rebuild_the_themes_
    components`) because the purchased theme owns typography. This does not
    take that decision away from the theme — it carries one reader's own
    override, per request, exactly the way `common.color.accent_theme_css`
    already carries one deployment's accent colour.
    """
    family = preferences.get("font_family") or DEFAULT_PANEL_FONT_FAMILY
    scale = preferences.get("font_scale") or DEFAULT_PANEL_FONT_SCALE
    declarations = []
    if family != DEFAULT_PANEL_FONT_FAMILY:
        stack = PANEL_FONT_FAMILY_STACKS.get(family)
        if stack:
            # Both the token and the literal, because the theme overrides its
            # own token. `style.bundle.rtl.css` defines
            # `--bs-font-sans-serif` on `:root` and reaches it through
            # `body { font-family: var(--bs-body-font-family) }` — and then,
            # near the end of the same sheet, sets `html, body { font-family:
            # IRANSansWeb, ... }` outright, which wins by source order and
            # leaves the token unread. Measured in a browser, not inferred:
            # setting only the token left `--bs-font-sans-serif` correct and
            # the rendered face unchanged. Setting the token as well keeps
            # anything that *does* read it in step.
            declarations.append(":root{--bs-font-sans-serif:" + stack + ";}")
            declarations.append("html,body{font-family:" + stack + ";}")
            # ApexCharts' own text is the one place the vendor hardcodes a
            # family with `!important` (see the note beside the matching rule
            # in dolphin.css), so a reader's choice has to be restated there
            # or every chart label stays on the default face while the card
            # around it moves.
            declarations.append(
                ".apexcharts-text,.apexcharts-title-text,.apexcharts-legend-text"
                "{font-family:" + stack + "!important;}"
            )
    if scale != DEFAULT_PANEL_FONT_SCALE:
        size = PANEL_FONT_SCALE_SIZES.get(scale)
        if size:
            # `!important` here and nowhere else in this function, because
            # the declaration it has to beat carries one: the theme's own
            # `html, body { font-size: 13px !important }`. Nothing weaker
            # reaches the page — source order and specificity both lose to
            # an `!important` author declaration.
            declarations.append("html,body{font-size:" + size + "!important;}")
    return "".join(declarations) or None


def currency_label(unit):
    return CURRENCY_LABELS.get(unit, CURRENCY_LABELS[UserPreference.CurrencyUnit.RIAL])


def to_display_amount(amount, unit):
    """A stored rial amount in the reader's own unit, as an exact `Decimal`.

    Exact, not rounded: rounding belongs to the formatter that is about to
    print the figure, and to nothing else. A caller that needs the number
    back — a form field being populated — must get a value that multiplies
    cleanly back to the rial it came from, or a round trip through an edit
    form would silently move the amount.
    """
    value = Decimal(amount or 0)
    if unit == UserPreference.CurrencyUnit.TOMAN:
        return value / RIALS_PER_TOMAN
    return value


def to_storage_amount(amount, unit):
    """The inverse of `to_display_amount` — what the API must be sent."""
    value = Decimal(amount or 0)
    if unit == UserPreference.CurrencyUnit.TOMAN:
        return value * RIALS_PER_TOMAN
    return value
