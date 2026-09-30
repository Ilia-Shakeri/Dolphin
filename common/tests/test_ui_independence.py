"""The panel must not depend on the reference template folder at the repository root.

That folder exists only until it is deleted by hand. Everything the served UI
needs was copied into `common/static/common/ui/` under Dolphin's own names, so
removing the folder must change nothing. These tests make that a checked
property rather than a claim:

* no static directory outside an app is configured, so nothing at the root is
  ever served,
* every static file a served shell asks for resolves without that folder,
* no first-party file refers to the folder or carries the vendor's names.
"""

import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "common" / "templates" / "common"

# Built from pieces so this file does not itself carry the names it forbids.
REFERENCE_FOLDER = "metro" + "nic"
VENDOR_NAMES = (REFERENCE_FOLDER, "keen" + "themes", "keen" + "icons", "متر" + "ونیک")
VENDOR_TOKENS = re.compile(r"data-" r"kt-|(?<![A-Za-z0-9_])KT[A-Z][a-z]|(?<![A-Za-z0-9_])kt_[a-z]")

SKIPPED_DIRECTORIES = {
    REFERENCE_FOLDER, "build", "wheels", ".git", ".claude", "apple-design-skill",
    "codex-plugin-cc-probe", "node_modules", "__pycache__", "staticfiles", ".scratch",
    ".pytest_cache",
}
SCANNED_SUFFIXES = {".py", ".js", ".css", ".html", ".inc", ".md", ".conf", ".sh", ".yml", ".json", ".txt"}
#: Historical record, and the few files that must name the folder to exclude it.
MAY_NAME_THE_FOLDER = {
    "CHANGELOG.md",
    ".dockerignore",
    "scripts/validate_image_content.py",
    "common/tests/test_static_assets.py",
    "common/tests/test_report_toolbars_and_log_filter.py",
}


def first_party_files():
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        if SKIPPED_DIRECTORIES.intersection(relative.parts):
            continue
        yield relative.as_posix(), path


class ReferenceFolderIndependenceTests(SimpleTestCase):
    def test_no_static_directory_outside_an_app_is_configured(self):
        self.assertEqual(list(settings.STATICFILES_DIRS), [])

    def test_the_shell_assets_resolve_from_app_static_alone(self):
        referenced = set()
        for name in ("base.html", "login.html", "print_base.html", "error.html"):
            text = (TEMPLATES / name).read_text(encoding="utf-8")
            referenced |= set(re.findall(r"{% static '([^']+)' %}", text))
        self.assertTrue(referenced)
        for reference in sorted(referenced):
            with self.subTest(asset=reference):
                located = finders.find(reference)
                self.assertTrue(located, reference)
                self.assertNotIn(REFERENCE_FOLDER, Path(located).parts)

    def test_the_ui_kit_lives_in_first_party_static(self):
        kit = ROOT / "common" / "static" / "common" / "ui"
        for relative in (
            "css/dolphin-theme.rtl.css", "css/dolphin-plugins.rtl.css",
            "js/dolphin-theme.js", "js/dolphin-plugins.js",
            "fonts/IRANSansWeb.woff", "fonts/dolphin-icons/dolphin-icons-duotone.woff",
        ):
            with self.subTest(file=relative):
                self.assertTrue((kit / relative).is_file())

    def test_no_first_party_file_names_the_vendor_or_the_folder(self):
        offenders = []
        for relative, path in first_party_files():
            if relative in MAY_NAME_THE_FOLDER:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for name in VENDOR_NAMES:
                if name in text:
                    offenders.append(f"{relative}: {name}")
        self.assertEqual(offenders, [])

    def test_no_first_party_file_uses_the_vendor_component_prefix(self):
        offenders = []
        for relative, path in first_party_files():
            if relative == "CHANGELOG.md":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            match = VENDOR_TOKENS.search(text)
            if match:
                offenders.append(f"{relative}: {match.group(0)}")
        self.assertEqual(offenders, [])
