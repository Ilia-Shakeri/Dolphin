"""Deriving a full Bootstrap/Metronic "primary" colour set from one hex value
an admin picked, for `common.branding`'s optional accent colour.

The theme (`assets/css/style.bundle.css`) never reads a single `--bs-primary`
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
close enough to Metronic's own hand-picked derivations to read as "the same
family of colour", not colour-theory-perfect. `--bs-link-color` and its
`-hover`/`-rgb` siblings are included because the theme's own default value
(`#1B84FF`) is the *same* colour as `--bs-primary`, not merely similar — https://github.com/keenthemes routes both through the vendor's own SCSS
`$primary` variable, so leaving links unrouted would announce this override
as approximate.
"""

import re

HEX_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")

#: Metronic's own default accent (`--bs-primary` in `style.bundle.css`,
#: light mode) — offering it back as the "reset to default" affordance means
#: never inventing a colour name for "Dolphin blue" that lives nowhere else.
DEFAULT_ACCENT = "#1B84FF"


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


def accent_theme_variables(hex_color):
    """The full set of derived tokens for one theme mode, keyed by CSS
    custom-property name (without the leading `--`) — same shape regardless
    of which mode calls it; only the tint/shade targets differ per mode
    (`light` mode tints toward white, `dark` mode tints toward near-black,
    matching the vendor's own two `--bs-primary-light` values).
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
        "bs-link-color": hex_color,
        "bs-link-color-rgb": "{}, {}, {}".format(*(round(c) for c in rgb)),
        "bs-link-hover-color": _rgb_to_hex(active),
        "bs-link-hover-color-rgb": "{}, {}, {}".format(*(round(c) for c in active)),
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
    rgb = _hex_to_rgb(hex_color)
    light_variables = accent_theme_variables(hex_color)
    light_variables["bs-primary-light"] = _rgb_to_hex(_mix(rgb, (255, 255, 255), 0.88))
    dark_variables = accent_theme_variables(hex_color)
    dark_variables["bs-primary-light"] = _rgb_to_hex(_mix(rgb, (0, 0, 0), 0.85))

    def _block(selector, variables):
        declarations = "".join(f"--{name}:{value};" for name, value in variables.items())
        return f"{selector}{{{declarations}}}"

    return _block("[data-bs-theme=light]", light_variables) + _block("[data-bs-theme=dark]", dark_variables)
