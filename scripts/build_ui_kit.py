"""Build the UI kit files the panel serves from the kit's full sources (2.40.43).

`ui_kit/` holds the kit as it was adapted from the reference template — the
whole theme stylesheet, the whole icon stylesheet and icon fonts, and the
vendor libraries — and never ships (`.dockerignore`). This writes what
`common/static/common/ui/` serves:

    js/dolphin-plugins.js        Popper and Bootstrap, loaded by every page
    js/dolphin-charts.js         ApexCharts, fetched the first time a chart is
                                 drawn (`ui/charts.js`, `apexReady`)
    css/dolphin-theme.rtl.css    the theme rules a first-party file can produce
                                 a class for
    css/dolphin-plugins.rtl.css  the icon rules of the icons the panel uses
    fonts/dolphin-icons/*.woff   those icons' glyphs only

What "used" means: a class name appears in a template, a script (the panel's
own, the theme's, a vendor library's — they add classes at run time), or a
Python module of a Django app or `config/`; or it starts with a prefix one of them builds a name from
(`badge-light-${tone}`, `text-{{ … }}`, `"menu-" + …`, a vendor component's
`baseClass + '-' + direction`). A rule is kept when every class it names is
used; `:not(…)` is ignored, since a class missing there makes the selector
match, not fail.

Run it after a template or a script uses a theme class or an icon for the first
time, or after upgrading a vendor library (put the new file in `ui_kit/vendor/`
and change its name in `BUNDLES`):

    python scripts/build_ui_kit.py

`--check` writes nothing and lists what the served files lack;
`common/tests/test_ui_kit_build.py` runs it, so a class or an icon used without
a rebuild fails the suite rather than rendering unstyled. Subsetting the icon
fonts needs fontTools, a development tool and not a dependency of the panel.
"""

import argparse
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "ui_kit"
SERVED = ROOT / "common" / "static" / "common" / "ui"

#: Served bundle -> (what it is, the vendor files it is made of, in order).
BUNDLES = {
    "js/dolphin-plugins.js": (
        "Popper 2.11.8 and Bootstrap 5.3.3, loaded by every page (Bootstrap reads `window.Popper`)",
        ("popper-2.11.8.js", "bootstrap-5.3.3.js"),
    ),
    "js/dolphin-charts.js": (
        "ApexCharts 3.48.0, fetched by `ui/charts.js` the first time a chart is drawn",
        ("apexcharts-3.48.0.js",),
    ),
}
ICON_FAMILIES = ("duotone", "outline", "solid")
FAMILY_CLASSES = {f"di-{family}" for family in ICON_FAMILIES}

# --- what the panel uses ------------------------------------------------------

#: Python is read from the Django apps (a folder with an `apps.py`) and
#: `config/` — the code that renders pages. Tests and migrations draw nothing.
_SKIP_DIRS = {"tests", "migrations", "__pycache__"}


def _python_roots():
    return sorted({path.parent for path in ROOT.glob("*/apps.py")} | {ROOT / "config"})


def _sources():
    templates = [ROOT / "common" / "templates", ROOT / "profiles" / "templates"]
    for base in templates:
        for pattern in ("**/*.html", "**/*.inc", "**/*.txt"):
            yield from base.glob(pattern)
    yield from (ROOT / "common" / "static" / "common" / "js").rglob("*.js")
    yield SERVED / "js" / "dolphin-theme.js"
    yield from (SERVED / "plugins").rglob("*.js")
    yield from (KIT / "vendor").glob("*.js")
    for root in _python_roots():
        for path in root.rglob("*.py"):
            if not _SKIP_DIRS.intersection(path.relative_to(ROOT).parts):
                yield path


def usage():
    """Every word the panel's sources contain, and the prefixes they build class names from."""
    tokens, prefixes = set(), set()
    for path in _sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        tokens.update(re.findall(r"[A-Za-z_][\w-]*", text))
        prefixes.update(re.findall(r"([A-Za-z_][\w-]*-)\$\{", text))
        prefixes.update(re.findall(r"([A-Za-z_][\w-]*-)\{\{", text))
        prefixes.update(re.findall(r"([A-Za-z_][\w-]*-)\"\s*\+", text))
        prefixes.update(re.findall(r"([A-Za-z_][\w-]*-)'\s*\+", text))
        if path.suffix == ".js":
            prefixes.update(base + "-" for base in re.findall(r"""baseClass:\s*['"]([\w-]+)['"]""", text))
    return tokens, {prefix for prefix in prefixes if len(prefix) > 2}


# --- a small CSS walker -------------------------------------------------------

def _split_top(text, separator):
    parts, depth, current = [], 0, []
    for character in text:
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        if character == separator and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(character)
    parts.append("".join(current))
    return parts


def _block_end(css, start):
    """Index just past the `}` closing the block whose `{` is just before `start`."""
    depth, index, length, in_string = 1, start, len(css), None
    while index < length:
        character = css[index]
        if in_string:
            if character == "\\":
                index += 2
                continue
            if character == in_string:
                in_string = None
        elif character in "\"'":
            in_string = character
        elif css.startswith("/*", index):
            index = css.index("*/", index) + 2
            continue
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise ValueError("unbalanced braces")


def _classes(selector):
    without_not = re.sub(r":not\((?:[^()]|\([^()]*\))*\)", "", selector)
    return re.findall(r"\.(-?[A-Za-z_][\w-]*)", without_not)


def filter_css(css, keep_selector, rules=None, context=""):
    """The stylesheet with every rule whose selectors all fail `keep_selector`
    dropped (and a rule's failing selectors removed from its list). Comments,
    at-rules other than @media/@supports, and element selectors are kept as
    they are. `rules`, when given, collects `(context, selectors, body)` for
    every style rule kept — what `--check` compares."""
    out, index, length = [], 0, len(css)
    while index < length:
        if css.startswith("/*", index):
            end = css.index("*/", index) + 2
            out.append(css[index:end])
            index = end
            continue
        if css[index].isspace():
            out.append(css[index])
            index += 1
            continue
        brace, semicolon = css.find("{", index), css.find(";", index)
        if css[index] == "@" and semicolon != -1 and (brace == -1 or semicolon < brace):
            out.append(css[index:semicolon + 1])
            index = semicolon + 1
            continue
        if brace == -1:
            out.append(css[index:])
            break
        prelude = css[index:brace]
        end = _block_end(css, brace + 1)
        body = css[brace + 1:end - 1]
        head = prelude.strip()
        if head.startswith(("@media", "@supports")):
            inner = filter_css(body, keep_selector, rules, context + " " + " ".join(head.split()))
            if "{" in inner:
                out.append(prelude + "{" + inner + "}")
        elif head.startswith("@"):
            out.append(css[index:end])
        else:
            selectors = _split_top(prelude, ",")
            kept = [selector for selector in selectors if keep_selector(selector)]
            if kept:
                if len(kept) != len(selectors):
                    prelude = ",".join(kept)
                out.append(prelude + "{" + body + "}")
                if rules is not None:
                    rules.add((context, " ".join(" ".join(kept).split()), " ".join(body.split())))
        index = end
    return "".join(out)


def style_rules(css):
    """Every style rule of a stylesheet, as `filter_css` records it."""
    rules = set()
    filter_css(css, lambda selector: True, rules)
    return rules


# --- the outputs ----------------------------------------------------------------

def theme_css(tokens, prefixes, rules=None):
    def used(name):
        return name in tokens or any(name.startswith(prefix) for prefix in prefixes)

    source = (KIT / "css" / "dolphin-theme.rtl.css").read_text(encoding="utf-8")
    result = filter_css(source, lambda selector: all(used(name) for name in _classes(selector)), rules)
    return re.sub(r"\n{3,}", "\n\n", result)


def plugins_css(tokens, prefixes, rules=None):
    # An icon is used by name (`di-wallet`) or through a prefix its name is
    # built from (`di-arrow-${direction}` keeps `di-arrow-up` and `di-arrow-down`).
    def used(icon):
        return icon in tokens or any(icon.startswith(prefix) for prefix in prefixes)

    def keep(selector):
        return all(used(name) for name in _classes(selector) if name.startswith("di-") and name not in FAMILY_CLASSES)

    source = (KIT / "css" / "dolphin-plugins.rtl.css").read_text(encoding="utf-8")
    result = filter_css(source, keep, rules)
    # Every browser the panel supports reads WOFF; the TrueType copies were a
    # second download for none of them.
    result = re.sub(r'(url\("\.\./fonts/dolphin-icons/[\w-]+\.woff"\) format\("woff"\)),\s*url\("[^"]+\.ttf"\) format\("truetype"\)',
                    r"\1", result)
    return re.sub(r"\n{3,}", "\n\n", result)


def icon_codepoints(css):
    """Family -> the code points the stylesheet's icon rules draw."""
    points = {family: set() for family in ICON_FAMILIES}
    for context, selectors, body in style_rules(css):
        match = re.search(r'content:\s*"\\([0-9a-fA-F]{4,5})"', body)
        if not match or ".di-" not in selectors:
            continue
        family = "outline" if ".di-outline" in selectors else "solid" if ".di-solid" in selectors else "duotone"
        points[family].add(int(match.group(1), 16))
    return points


def bundle(name):
    what, files = BUNDLES[name]
    banner = ("/*!\n * Dolphin UI kit — " + what + ".\n"
              " * Built by scripts/build_ui_kit.py from ui_kit/vendor/; do not edit it by hand.\n"
              " * Each library keeps its own licence banner below.\n */\n")
    return banner + "".join((KIT / "vendor" / file).read_text(encoding="utf-8") for file in files)


def subset_font(family, codepoints):
    from fontTools import subset
    from fontTools.ttLib import TTFont

    options = subset.Options()
    options.flavor = "woff"
    options.layout_features = []
    options.name_IDs = ["*"]
    options.notdef_outline = True
    # The source font's own timestamp, not the time of the build: the same
    # glyphs give the same bytes, so a rebuild changes a font only when its
    # glyphs change.
    font = TTFont(KIT / "fonts" / f"dolphin-icons-{family}.woff", recalcTimestamp=False)
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=sorted(codepoints))
    subsetter.subset(font)
    buffer = io.BytesIO()
    font.flavor = "woff"
    font.save(buffer)
    return buffer.getvalue()


def font_cmap(path):
    from fontTools.ttLib import TTFont

    return set(TTFont(path).getBestCmap())


# --- run ------------------------------------------------------------------------

def check(*, fonts=True):
    """What the served files lack, as sentences; empty when they are current.
    `fonts=False` leaves out the icon fonts, the one part that needs fontTools."""
    tokens, prefixes = usage()
    problems = []
    if "di-" in prefixes:
        problems.append("a source builds an icon class from a bare name (`di-${icon}`): every icon is then kept; "
                        "write the icon's whole class in the data (`di-check`) instead")
    for name in BUNDLES:
        if (SERVED / name).read_text(encoding="utf-8") != bundle(name):
            problems.append(f"{name} is not what ui_kit/vendor/ builds")
    wanted = set()
    theme_css(tokens, prefixes, wanted)
    missing = wanted - style_rules((SERVED / "css" / "dolphin-theme.rtl.css").read_text(encoding="utf-8"))
    if missing:
        problems.append(f"dolphin-theme.rtl.css lacks {len(missing)} rule(s) the panel now uses, e.g. {sorted(missing)[0][1][:80]}")
    wanted = set()
    plugins_css(tokens, prefixes, wanted)
    served_plugins = (SERVED / "css" / "dolphin-plugins.rtl.css").read_text(encoding="utf-8")
    missing = wanted - style_rules(served_plugins)
    if missing:
        problems.append(f"dolphin-plugins.rtl.css lacks {len(missing)} icon rule(s), e.g. {sorted(missing)[0][1][:80]}")
    if not fonts:
        return problems
    try:
        for family, points in icon_codepoints(served_plugins).items():
            absent = points - font_cmap(SERVED / "fonts" / "dolphin-icons" / f"dolphin-icons-{family}.woff")
            if absent:
                problems.append(f"dolphin-icons-{family}.woff lacks {len(absent)} glyph(s) its stylesheet draws")
    except ImportError:
        problems.append("fontTools is not installed: the icon fonts were not checked (pip install fonttools)")
    return problems


def build():
    tokens, prefixes = usage()
    written = []
    for name in BUNDLES:
        (SERVED / name).write_text(bundle(name), encoding="utf-8", newline="\n")
        written.append(name)
    (SERVED / "css" / "dolphin-theme.rtl.css").write_text(theme_css(tokens, prefixes), encoding="utf-8", newline="\n")
    plugins = plugins_css(tokens, prefixes)
    (SERVED / "css" / "dolphin-plugins.rtl.css").write_text(plugins, encoding="utf-8", newline="\n")
    written += ["css/dolphin-theme.rtl.css", "css/dolphin-plugins.rtl.css"]
    fonts = SERVED / "fonts" / "dolphin-icons"
    for family, points in icon_codepoints(plugins).items():
        (fonts / f"dolphin-icons-{family}.woff").write_bytes(subset_font(family, points))
        written.append(f"fonts/dolphin-icons/dolphin-icons-{family}.woff ({len(points)} glyphs)")
    for stale in fonts.glob("*.ttf"):
        stale.unlink()
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="write nothing; list what the served files lack")
    options = parser.parse_args(argv)
    if options.check:
        problems = check()
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    for line in build():
        print("wrote", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
