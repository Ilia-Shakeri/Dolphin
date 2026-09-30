"""The panel's script as one string, for tests that assert on its source.

The script is a tree of ES modules under `common/static/common/js/`. Many
tests pin behaviour by reading the source text — a constant, the body of one
function, the wiring of one page — and were written when the script was a
single closure. This joins the modules back into that shape: imports are
dropped, `export` is removed and every module is indented one level, so the
same searches keep their meaning wherever a function now lives. The page table
is rendered back as the `if (page === ...)` dispatch it replaced.

New tests should read the module that owns the code (`module_source`) instead.
"""

import re
from functools import lru_cache
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1] / "static" / "common" / "js"

_IMPORT_LINE = re.compile(r'^import .*? from "dolphin/[^"]+";\s*$', re.M)
_EXPORT_PREFIX = re.compile(r"^export (?=(?:async function|function|const|let|class)\b)", re.M)
_NEXT_DECLARATION = re.compile(r"\n    (?:async function|function|const|let|class) ")
_SINGLE_ENTRY = re.compile(r'"([a-z-]+)": async \(\) => \(await import\("dolphin/[^"]+\.js"\)\)\.(\w+)\(\),')
_MULTI_ENTRY = re.compile(r'"([a-z-]+)": async \(\) => \{(.*?)\n    \},', re.S)


def module_paths():
    """Every module relative to the module root, `main.js` last (as the boot code was)."""
    paths = sorted(path.relative_to(MODULE_ROOT).as_posix() for path in MODULE_ROOT.rglob("*.js"))
    paths.remove("main.js")
    return paths + ["main.js"]


@lru_cache(maxsize=None)
def module_source(relative):
    return (MODULE_ROOT / relative).read_text(encoding="utf-8").replace("\r\n", "\n")


def _legacy_shape(relative, text):
    text = _IMPORT_LINE.sub("", text)
    text = _EXPORT_PREFIX.sub("", text)
    if relative == "main.js":
        text = text.replace("function boot() {", "", 1)
        return re.sub(r"\n}\n\nboot\(\);\s*$", "\n", text)
    return "\n".join(("    " + line) if line.strip() else line for line in text.split("\n"))


def _legacy_dispatch():
    text = module_source("pages.js")
    lines = [f'    if (page === "{page}") {root}();' for page, root in _SINGLE_ENTRY.findall(text)]
    for page, block in _MULTI_ENTRY.findall(text):
        lines.append(f'    if (page === "{page}") {{')
        lines.extend(f"        {call}();" for call in re.findall(r"module\d+\.(\w+)\(\);", block))
        lines.append("    }")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def panel_script():
    modules = "\n\n".join(_legacy_shape(relative, module_source(relative)) for relative in module_paths())
    return modules + "\n\n" + _legacy_dispatch() + "\n"


def function_body(name):
    """The source of one top-level function, up to the next top-level declaration."""
    script = panel_script()
    for prefix in (f"async function {name}(", f"function {name}("):
        start = script.find(prefix)
        if start != -1:
            break
    else:
        raise ValueError(f"function {name} not found")
    following = _NEXT_DECLARATION.search(script, start + 1)
    return script[start:following.start() if following else len(script)]


class PanelScript:
    """Stands in for the old single-file path in `read_text()` calls."""

    def read_text(self, encoding="utf-8", errors=None):
        return panel_script()

    def exists(self):
        return MODULE_ROOT.is_dir()

    def __str__(self):
        return str(MODULE_ROOT)


PANEL_SCRIPT = PanelScript()
