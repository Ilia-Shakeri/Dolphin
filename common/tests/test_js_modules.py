"""The shape of the panel's script: a layered tree of ES modules.

The rules here are what keeps the code modular rather than merely split into
files:

* `core/` knows nothing above itself, `ui/` builds on `core/`, `shell/` (what runs
  on every page) builds on both, and a `features/<name>/` module builds on
  `core/` and `ui/` and on other modules of the *same* feature only — never on
  another feature and never on `shell/`;
* no module imports another in a cycle;
* every import names a file that exists and a name that file exports;
* every page a template declares is served by an entry in `pages.js`.

A feature that a deployment does not license can therefore be left out of a
build without touching anything else.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from common.tests.panel_js import MODULE_ROOT, module_paths, module_source

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
PROFILE_TEMPLATES = Path(__file__).resolve().parents[2] / "profiles" / "templates"

STATIC_IMPORT = re.compile(r'^import \{([^}]*)\} from "dolphin/([^"]+)\.js";', re.M)
DYNAMIC_IMPORT = re.compile(r'import\("dolphin/([^"]+)\.js"\)')
EXPORT = re.compile(r"^export (?:async function|function|const|let|class) ([A-Za-z_$][\w$]*)", re.M)

#: Pages served by markup alone, with nothing for the script to bind.
PAGES_WITHOUT_ENTRY = {"shell", "chat"}


def imports_of(relative):
    text = module_source(relative)
    edges = {}
    for names, target in STATIC_IMPORT.findall(text):
        edges.setdefault(f"{target}.js", set()).update(name.strip() for name in names.split(",") if name.strip())
    return edges


def layer_of(relative):
    return relative.split("/")[0] if "/" in relative else relative


class ModuleGraphTests(SimpleTestCase):
    def test_the_entry_point_and_the_page_table_exist(self):
        self.assertTrue((MODULE_ROOT / "main.js").is_file())
        self.assertTrue((MODULE_ROOT / "pages.js").is_file())

    def test_no_import_is_hidden_inside_a_comment(self):
        """An import inserted into a doc comment is matched by the regex
        above yet never runs: `ui/searchable-select.js` called
        `dispatchUserEvent` from 2.39.14 to 2.40.7 with its import inside
        `/** … */`, so choosing an option threw. Imports sit above any comment."""
        problems = []
        for relative in module_paths():
            for comment in re.findall(r"/\*.*?\*/", module_source(relative), flags=re.S):
                if re.search(r"^\s*import\s*\{", comment, flags=re.M):
                    problems.append(relative)
        self.assertEqual(problems, [])

    def test_every_import_resolves_to_a_file_and_an_export(self):
        exports = {relative: set(EXPORT.findall(module_source(relative))) for relative in module_paths()}
        problems = []
        for relative in module_paths():
            for target, names in imports_of(relative).items():
                if target not in exports:
                    problems.append(f"{relative} imports missing {target}")
                    continue
                for name in sorted(names - exports[target]):
                    problems.append(f"{relative} imports {name}, which {target} does not export")
        self.assertEqual(problems, [])

    def test_the_layers_only_point_downwards(self):
        problems = []
        for relative in module_paths():
            layer = layer_of(relative)
            for target in imports_of(relative):
                other = layer_of(target)
                if layer == "core" and other != "core":
                    problems.append(f"{relative} -> {target}")
                elif layer == "ui" and other not in {"core", "ui"}:
                    problems.append(f"{relative} -> {target}")
                elif layer == "shell" and other not in {"core", "ui", "shell"}:
                    problems.append(f"{relative} -> {target}")
                elif layer == "features":
                    feature = relative.split("/")[1]
                    if other in {"shell", "main.js", "pages.js"}:
                        problems.append(f"{relative} -> {target}")
                    elif other == "features" and target.split("/")[1] != feature:
                        problems.append(f"{relative} -> {target} (another feature)")
        self.assertEqual(problems, [])

    def test_no_module_imports_another_in_a_cycle(self):
        graph = {relative: set(imports_of(relative)) for relative in module_paths()}
        visiting, done = set(), set()

        def visit(node, trail):
            if node in done:
                return None
            if node in visiting:
                return trail + [node]
            visiting.add(node)
            for other in sorted(graph.get(node, ())):
                found = visit(other, trail + [node])
                if found:
                    return found
            visiting.discard(node)
            done.add(node)
            return None

        for relative in graph:
            cycle = visit(relative, [])
            self.assertIsNone(cycle, " -> ".join(cycle or []))

    def test_only_the_entry_point_and_the_page_table_load_features(self):
        """A feature is reached through `pages.js`, never by a static import."""
        for relative in module_paths():
            if relative in {"main.js", "pages.js"}:
                continue
            for target in imports_of(relative):
                if layer_of(target) == "features":
                    self.assertEqual(layer_of(relative), "features", f"{relative} -> {target}")

    def test_the_import_map_covers_every_module(self):
        from common.templatetags.ui_modules import module_paths as mapped

        self.assertEqual(list(mapped()), sorted(module_paths()))


class PageTableTests(SimpleTestCase):
    def declared_pages(self):
        pages = set()
        for root in (TEMPLATES, PROFILE_TEMPLATES):
            for path in root.rglob("*"):
                if path.suffix in {".html", ".inc"}:
                    pages |= set(re.findall(r"{% block page_id %}([a-z-]+){% endblock %}", path.read_text(encoding="utf-8")))
        return pages

    def served_pages(self):
        return set(re.findall(r'^\s+"([a-z-]+)": async', module_source("pages.js"), re.M))

    def test_every_page_a_template_declares_has_an_entry(self):
        missing = sorted(self.declared_pages() - self.served_pages() - PAGES_WITHOUT_ENTRY)
        self.assertEqual(missing, [])

    def test_every_entry_serves_a_page_that_exists(self):
        stale = sorted(self.served_pages() - self.declared_pages())
        self.assertEqual(stale, [])

    def test_every_entry_calls_a_function_its_module_exports(self):
        text = module_source("pages.js")
        problems = []
        for target in DYNAMIC_IMPORT.findall(text):
            self.assertTrue((MODULE_ROOT / f"{target}.js").is_file(), target)
        # single-module entries: import("dolphin/x.js")).setupThing()
        for target, function in re.findall(r'import\("dolphin/([^"]+)\.js"\)\)\.(\w+)\(\)', text):
            if function not in EXPORT.findall(module_source(f"{target}.js")):
                problems.append(f"{target} does not export {function}")
        # multi-module entries: moduleN.setupThing()
        blocks = re.findall(r'"[a-z-]+": async \(\) => \{(.*?)\n    \},', text, re.S)
        for block in blocks:
            modules = dict(re.findall(r'const (module\d+) = await import\("dolphin/([^"]+)\.js"\);', block))
            for name, function in re.findall(r"(module\d+)\.(\w+)\(\);", block):
                if function not in EXPORT.findall(module_source(f"{modules[name]}.js")):
                    problems.append(f"{modules[name]} does not export {function}")
        self.assertEqual(problems, [])


class ModuleSyntaxTests(SimpleTestCase):
    def test_every_module_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is not installed")
        failures = []
        with tempfile.TemporaryDirectory() as directory:
            for relative in module_paths():
                target = Path(directory) / (relative.replace("/", "__") + ".mjs")
                target.write_text(module_source(relative), encoding="utf-8")
                result = subprocess.run(
                    [node, "--check", str(target)], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60,
                )
                if result.returncode != 0:
                    failures.append(f"{relative}: {(result.stderr.strip().splitlines() or [''])[-1]}")
        self.assertEqual(failures, [])
