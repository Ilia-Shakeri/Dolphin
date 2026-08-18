"""The static layer a Linux deployment depends on.

The theme's tree is the static root, so `collectstatic` decides what a released
image can serve. These tests pin both halves of that: every asset a served page
requests is collected, and the demo material none of them requests is not.

This matters more than it looks. The favicon had been 404ing in development for
a long time because a prefixed `STATICFILES_DIRS` entry does not resolve
forward-slash URLs on Windows, and nothing noticed. And the ignore list was a
settings constant that no code read until `common/management/commands/
collectstatic.py` existed — it excluded nothing at all.
"""

import posixpath
import re
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.management import call_command, get_commands
from django.test import SimpleTestCase, override_settings


ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "common" / "templates" / "common"

#: Everything a served page loads, by the exact path it asks for.
REQUIRED = (
    "css/style.bundle.rtl.css",
    "plugins/global/plugins.bundle.rtl.css",
    "js/scripts.bundle.js",
    "common/forooshbin.css",
    "common/forooshbin-app.js",
    "common/favicon.ico",
    "fonts/IRANSansWeb.woff",
    "plugins/global/fonts/keenicons/keenicons-duotone.woff",
)

#: Theme material no served page can reach.
EXCLUDED = (
    "media",
    "plugins/custom",
    "js/custom",
    "plugins/global/fonts/line-awesome",
    "plugins/global/fonts/@fortawesome",
    "plugins/global/plugins.bundle.js",
    "js/widgets.bundle.js",
    "css/style.bundle.css",
)


class StaticResolutionTests(SimpleTestCase):
    def test_every_asset_a_served_shell_references_resolves(self):
        referenced = set()
        for name in ("base.html", "print_base.html", "error.html"):
            text = (TEMPLATES / name).read_text(encoding="utf-8")
            referenced |= set(re.findall(r"{% static '([^']+)' %}", text))
        self.assertTrue(referenced)
        missing = sorted(ref for ref in referenced if not finders.find(ref))
        self.assertEqual(missing, [])

    def test_the_theme_stylesheets_find_every_font_they_ask_for(self):
        """A missing font file is a 404 on every page that loads the sheet."""
        missing = []
        for sheet, base in (
            ("css/style.bundle.rtl.css", "css"),
            ("plugins/global/plugins.bundle.rtl.css", "plugins/global"),
        ):
            located = finders.find(sheet)
            self.assertIsNotNone(located, sheet)
            text = Path(located).read_text(encoding="utf-8", errors="ignore")
            for url in set(re.findall(r'url\("?([^"()]+\.(?:woff2?|ttf|eot))[^"()]*"?\)', text)):
                # `../fonts/x` from `css/` is `fonts/x`; collapse it rather
                # than stripping the dots, which would give `css/fonts/x`.
                candidate = posixpath.normpath(posixpath.join(base, url))
                if not finders.find(candidate):
                    missing.append(f"{sheet} -> {url}")
        self.assertEqual(missing, [])

    def test_a_prefixed_static_dir_is_not_reintroduced(self):
        """Prefixed entries do not resolve forward-slash URLs on Windows.

        `FileSystemFinder` joins the prefix with `os.sep`, so `metronic/css/x`
        never matches `metronic\\css\\`. That silently broke the favicon here for
        a long time, so the shape of this setting is pinned rather than trusted.
        """
        for entry in settings.STATICFILES_DIRS:
            self.assertNotIsInstance(entry, (tuple, list), entry)


class CollectStaticContentTests(SimpleTestCase):
    """What a release image would actually contain."""

    def test_the_override_is_the_command_that_runs(self):
        # Django resolves a command to the first app in INSTALLED_APPS that
        # provides it; if `common` slipped below staticfiles the ignore list
        # would silently stop applying.
        self.assertEqual(get_commands()["collectstatic"], "common")
        self.assertLess(
            settings.INSTALLED_APPS.index("common"),
            settings.INSTALLED_APPS.index("django.contrib.staticfiles"),
        )

    def test_collected_output_has_what_is_needed_and_not_what_is_not(self):
        destination = Path(tempfile.mkdtemp(prefix="forooshbin-static-"))
        try:
            with override_settings(STATIC_ROOT=str(destination)):
                call_command("collectstatic", interactive=False, verbosity=0)
            for asset in REQUIRED:
                with self.subTest(required=asset):
                    self.assertTrue((destination / asset).is_file(), asset)
            for asset in EXCLUDED:
                with self.subTest(excluded=asset):
                    self.assertFalse((destination / asset).exists(), asset)
        finally:
            shutil.rmtree(destination, ignore_errors=True)


class ImageBuildContextTests(SimpleTestCase):
    """The theme must survive the trip into the Docker image.

    This is the regression guard for a real Linux deployment failure: the
    `.dockerignore` excluded `assets` wholesale, so `/app/assets` did not exist
    in the image, `collectstatic` collected only `admin/`, `common/` and
    `rest_framework/`, and every page rendered unstyled with a 404 for each
    theme bundle. Nothing caught it because the image-content contract *also*
    listed `assets` as forbidden — the gate was certifying the exclusion that
    broke the UI.

    Verifying the paths exist in the repository would not have caught it either.
    What is checked here is the file set the *build context* would carry, and
    then what `collectstatic` produces from exactly that set.
    """

    @staticmethod
    def _context_paths():
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "validate_image_content", ROOT / "scripts" / "validate_image_content.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return set(module.collect_context_paths())

    def test_the_build_context_carries_the_theme_runtime(self):
        context = self._context_paths()
        for required in (
            "assets/css/style.bundle.rtl.css",
            "assets/plugins/global/plugins.bundle.rtl.css",
            "assets/js/scripts.bundle.js",
            "assets/fonts/IRANSansWeb.woff",
            "assets/plugins/global/fonts/keenicons/keenicons-duotone.woff",
            "assets/plugins/global/fonts/keenicons/keenicons-outline.woff",
            "assets/plugins/global/fonts/keenicons/keenicons-solid.woff",
        ):
            with self.subTest(required=required):
                self.assertIn(required, context)

    def test_the_build_context_still_excludes_the_demo_tree(self):
        context = self._context_paths()
        offenders = sorted(
            path
            for path in context
            if path.startswith("assets/")
            and (
                path.startswith(("assets/media/", "assets/plugins/custom/", "assets/js/custom/"))
                or "/fonts/line-awesome/" in path
                or "/fonts/@fortawesome/" in path
                or "/fonts/bootstrap-icons/" in path
                or path.endswith(("plugins.bundle.js", "widgets.bundle.js", "style.bundle.css"))
            )
        )
        self.assertEqual(offenders, [])

    def test_collectstatic_from_the_image_file_set_serves_the_theme(self):
        """Copy only what the image would hold, then collect from it."""
        import os
        import subprocess
        import sys

        image = Path(tempfile.mkdtemp(prefix="forooshbin-image-"))
        try:
            for relative in self._context_paths():
                source = ROOT / relative
                if not source.is_file():
                    continue
                destination = image / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            self.assertTrue((image / "assets").is_dir(), "/app/assets missing from the image")

            result = subprocess.run(
                [sys.executable, "manage.py", "collectstatic", "--noinput", "-v", "0"],
                cwd=image,
                env=dict(os.environ, DJANGO_SETTINGS_MODULE="config.test_settings"),
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])

            collected = image / "staticfiles"
            for asset in REQUIRED:
                with self.subTest(asset=asset):
                    self.assertTrue((collected / asset).is_file(), asset)
            # The four theme roots that were absent during the Linux failure.
            for directory in ("css", "js", "fonts", "plugins"):
                with self.subTest(directory=directory):
                    self.assertTrue((collected / directory).is_dir(), directory)
        finally:
            shutil.rmtree(image, ignore_errors=True)
