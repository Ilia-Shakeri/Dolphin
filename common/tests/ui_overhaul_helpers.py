"""Reading the shipped stylesheet and script, for the UI-overhaul tests.

Not a test module — the runner only collects `test*.py` — but the four
`test_ui_overhaul_*` modules each had their own copy of these, and the copies
were starting to disagree. In particular `CSS.split("@media (max-width: …)")
[-1]` was written in three of them when the sheet had one block at that
breakpoint, and each new section made it point at a different block: by
batch D the boards' reduced-motion assertion was reading the report wizard's
rules. `media_block` asks for the block that actually contains the selector
in question, which cannot drift.
"""

import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "common" / "static" / "common" / "dolphin-app.js").read_text(encoding="utf-8")
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")
TEMPLATES = ROOT / "common" / "templates" / "common"

#: The stylesheet with its explanations removed. Needed wherever a test
#: asserts that a property is *absent*: this sheet explains its reversals
#: where they happened, so the comment saying why `opacity` is gone contains
#: the word `opacity`.
CODE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)


def markup(text):
    """Template markup with its `{% comment %}` prose removed.

    Needed wherever a test asserts that something is *absent*: these
    templates explain their removals in place, and the explanation names the
    thing that went.
    """
    return re.sub(r"\{% comment %\}.*?\{% endcomment %\}", "", text, flags=re.S)


def function_body(name, source=SCRIPT):
    """One top-level function of the panel script, as text."""
    start = source.index(f"function {name}(")
    following = source.find("\n    function ", start + 1)
    return source[start:following if following != -1 else len(source)]


def python_function(name, source):
    """One top-level Python function, as text.

    `function_body` above finds JavaScript, where every function in the
    panel script is indented one level inside an IIFE. A Python module's
    functions start at column zero, so the end marker is different and a
    single helper for both would only be a helper with a flag.
    """
    start = source.index(f"def {name}(")
    following = source.find(chr(10) + "def ", start + 1)
    return source[start:following if following != -1 else len(source)]


def rule(selector, source=CODE):
    """The declarations of the first rule whose selector list contains `selector`."""
    for block in source.split("}"):
        if "{" not in block:
            continue
        head, body = block.split("{", 1)
        if selector in head:
            return body
    return ""


def media_block(query, containing, source=CODE):
    """The `@media <query>` block that mentions `containing`.

    By the selector it holds rather than by position: the sheet has several
    blocks at the same breakpoint and gains more with every section, so
    "the last one" names a different block each time.

    Returns "" when no such block exists, which is what the assertion should
    then fail on.
    """
    marker = f"@media {query}"
    for chunk in source.split(marker)[1:]:
        # Balance braces from the block's own opening one, so a nested rule
        # does not end it early.
        depth = 0
        for index, character in enumerate(chunk):
            if character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    body = chunk[:index]
                    if containing in body:
                        return body
                    break
    return ""
