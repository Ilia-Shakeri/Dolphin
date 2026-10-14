"""Deriving a full Bootstrap "primary" colour set from one hex value
an admin picked, for `common.branding`'s optional accent colour.

The theme (`common/static/common/ui/css/dolphin-theme.rtl.css`) never reads a single `--bs-primary`
token — buttons, badges, the stepper, links and focus rings each read one of
several derived tokens (`--bs-primary-active` for hover, `--bs-primary-light`
for the `.btn-light-primary`/badge tint, `--bs-primary-clarity` for a focus
ring, `--bs-primary-inverse` for the text colour *on* a primary-filled
surface), and the vendor stylesheet itself defines a different `--bs-primary-
light` value under `[data-bs-theme=light]` than under `[data-bs-theme=dark]`
(a pale tint in light mode, a near-black tint in dark mode) — one flat colour
override would look right in one theme and wrong in the other.

Asking an admin to pick eight coordinated colours is not "cheap, self-
service customisation" — it is the opposite. So this module picks one colour
and derives the rest algorithmically (linear RGB interpolation toward white
or black, the same mechanism every mainstream design-token generator uses),
close enough to the UI kit's own hand-picked derivations to read as "the same
family of colour", not colour-theory-perfect. `--bs-link-color` and its
`-hover`/`-rgb` siblings are included because the theme's own default value
(`#1B84FF`) is the *same* colour as `--bs-primary`, not merely similar — the UI kit's source routes both through the vendor's own SCSS
`$primary` variable, so leaving links unrouted would announce this override
as approximate.
"""

import re

HEX_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")

#: The UI kit's own default accent (`--bs-primary` in `dolphin-theme.rtl.css`,
#: light mode) — offering it back as the "reset to default" affordance means
#: never inventing a colour name for "Dolphin blue" that lives nowhere else.
DEFAULT_ACCENT = "#1B84FF"

#: The panel's own light-mode primary when no deployment colour is set
#: (2.40.36). The UI kit's `#1B84FF` carries white button text at 3.6:1 and is
#: 3.5:1 as link text on the page — under the 4.5:1 that small text needs.
#: `#0071E3` is the same blue a step deeper: 4.7:1 both ways. Dark mode keeps
#: the kit's own fill (`KIT_DARK_PRIMARY`), which carries white text at 5.1:1.
PANEL_LIGHT_ACCENT = "#0071E3"

#: The kit's dark-theme primary and its pale tint (`dolphin-theme.rtl.css`,
#: `[data-bs-theme=dark]`). The 2.40.36 note above said dark mode "reads at
#: 4.9:1"; that was the light blue measured on the dark page. The dark theme's
#: own primary is `#006AE6`, and as text on the dark card it reads at 3.6:1
#: (measured 2.40.46) — fine as a fill, too dark as words.
KIT_DARK_PRIMARY = "#006AE6"
KIT_DARK_PRIMARY_LIGHT = "#172331"

#: WCAG AA for text under 18pt.
TEXT_CONTRAST = 4.5

#: The surfaces primary-coloured *text* sits on, per theme, measured on the
#: served panel (2.40.46): the card, the page behind it (`--bs-app-bg-color`),
#: the light sidebar, a card's raised row, and a warning notice's tint. The
#: colour's own pale tint — under a `.btn-light-primary` or a badge — is added
#: per colour, since it is derived from it.
TEXT_SURFACES = {
    "light": ("#ffffff", "#f2f2f7", "#f6f6f9", "#f9f9f9", "#fff8dd"),
    "dark": ("#15171c", "#09090b", "#1b1c22", "#242320"),
}


def is_valid_hex_color(value):
    return bool(HEX_PATTERN.match(str(value or "")))


def normalize_hex_color(value):
    """`#1b84ff` either case, always lower-cased on the way into storage —
    two admins typing the same colour with different letter-casing must not
    read as "changed" in the audit log or read as two different rows to
    compare against.
    """
    value = str(value or "").strip()
    if not is_valid_hex_color(value):
        raise ValueError(f"{value!r} is not a #RRGGBB colour")
    return value.lower()


def _hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(channel))) for channel in rgb))


def _mix(rgb, target, ratio):
    """`rgb` moved `ratio` (0..1) of the way toward `target`, channel by
    channel — `ratio=0` is `rgb` unchanged, `ratio=1` is `target`.
    """
    return tuple(channel + (target[channel_index] - channel) * ratio for channel_index, channel in enumerate(rgb))


def _relative_luminance(rgb):
    """WCAG relative luminance (0=black, 1=white), for choosing readable text
    on top of a fill of this colour — the same formula the accessibility
    spec defines, not a rough brightness average.
    """

    def _linearize(channel):
        value = channel / 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def contrast_ratio(foreground, background):
    """WCAG contrast between two `(r, g, b)` colours, 1..21."""
    lighter, darker = sorted((_relative_luminance(foreground), _relative_luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _tint(rgb, mode):
    """The colour's pale tint for one theme, the way `--bs-primary-light` is."""
    return _mix(rgb, (255, 255, 255), 0.88) if mode == "light" else _mix(rgb, (0, 0, 0), 0.85)


def text_shade(hex_color, mode, extra_surfaces=()):
    """The accent as *text* (2.40.46): the colour moved toward black (light
    theme) or white (dark theme) only as far as it takes to read at 4.5:1 on
    every surface primary text is drawn on — unchanged when it already does.

    A fill and a word need different things from one colour: white text on a
    button wants the blue dark, the blue as a word on a dark card wants it
    light. Buttons keep the accent; links, `.text-primary`, an active tab, a
    wizard's current step and a light-primary button's label read this.
    """
    rgb = _hex_to_rgb(hex_color)
    surfaces = [_hex_to_rgb(value) for value in (*TEXT_SURFACES[mode], *extra_surfaces)] + [_tint(rgb, mode)]
    target = (0, 0, 0) if mode == "light" else (255, 255, 255)
    for step in range(101):
        # Judged as it will be drawn: rounded to whole channels first.
        candidate = _rgb_to_hex(_mix(rgb, target, step / 100))
        if min(contrast_ratio(_hex_to_rgb(candidate), surface) for surface in surfaces) >= TEXT_CONTRAST:
            return candidate
    return _rgb_to_hex(target)


def _text_variables(hex_color, mode, extra_surfaces=()):
    """`--bs-text-primary` and the link colours, from `text_shade`. A link's
    hover goes one step further the same way, so it never reads worse."""
    shade = _hex_to_rgb(text_shade(hex_color, mode, extra_surfaces))
    hover = _mix(shade, (0, 0, 0) if mode == "light" else (255, 255, 255), 0.18)
    return {
        "bs-text-primary": _rgb_to_hex(shade),
        "bs-link-color": _rgb_to_hex(shade),
        "bs-link-color-rgb": "{}, {}, {}".format(*(round(c) for c in shade)),
        "bs-link-hover-color": _rgb_to_hex(hover),
        "bs-link-hover-color-rgb": "{}, {}, {}".format(*(round(c) for c in hover)),
    }


def accent_theme_variables(hex_color, mode="light"):
    """The full set of derived tokens for one theme mode, keyed by CSS
    custom-property name (without the leading `--`) — same shape for both
    modes; the tint/shade targets differ per mode (`light` mode tints toward
    white, `dark` mode tints toward near-black, matching the vendor's own two
    `--bs-primary-light` values, and the text shade moves the other way).
    """
    rgb = _hex_to_rgb(hex_color)
    active = _mix(rgb, (0, 0, 0), 0.18)
    clarity_r, clarity_g, clarity_b = (round(c) for c in rgb)
    inverse = "#ffffff" if _relative_luminance(rgb) < 0.6 else "#071437"
    return {
        "bs-primary": hex_color,
        "bs-primary-rgb": "{}, {}, {}".format(*(round(c) for c in rgb)),
        "bs-primary-active": _rgb_to_hex(active),
        "bs-primary-inverse": inverse,
        "bs-primary-clarity": f"rgba({clarity_r}, {clarity_g}, {clarity_b}, 0.2)",
        "bs-primary-light": _rgb_to_hex(_tint(rgb, mode)),
        **_text_variables(hex_color, mode),
    }


def accent_theme_css(hex_color):
    """A `<style>` element's inner text overriding the primary-colour tokens
    for both themes at once — `None` when `hex_color` is falsy, so a caller
    can write `{% if brand_accent_css %}` without a second check.

    Placed after the vendor stylesheet in `base.html`, so equal-specificity
    attribute selectors win by source order alone; no `!important` needed.
    """
    if not hex_color:
        return None
    return _light_block(hex_color) + _block("[data-bs-theme=dark]", accent_theme_variables(hex_color, "dark"))


def panel_default_accent_css():
    """The light-mode primary tokens for `PANEL_LIGHT_ACCENT`, for a deployment
    that set no colour of its own. Dark mode keeps the UI kit's fill and gets
    only the text shade of it (2.40.46)."""
    dark_text = _text_variables(KIT_DARK_PRIMARY, "dark", (KIT_DARK_PRIMARY_LIGHT,))
    return _light_block(PANEL_LIGHT_ACCENT) + _block("[data-bs-theme=dark]", dark_text)


def _block(selector, variables):
    declarations = "".join(f"--{name}:{value};" for name, value in variables.items())
    return f"{selector}{{{declarations}}}"


def _light_block(hex_color):
    """The light theme's primary tokens for one colour — shared by a
    deployment's own colour and the panel's default, so the two never drift."""
    return _block("[data-bs-theme=light]", accent_theme_variables(hex_color, "light"))
