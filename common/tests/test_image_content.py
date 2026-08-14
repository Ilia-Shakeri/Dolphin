import importlib.util
from pathlib import Path

from django.test import SimpleTestCase


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = PROJECT_ROOT / "scripts" / "validate_image_content.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_image_content", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load_validator()


class DockerignorePatternTests(SimpleTestCase):
    """The pattern translator must follow Docker's own matching rules."""

    def test_star_does_not_cross_path_separator(self):
        compiled = validator.pattern_to_regex("*.md")
        self.assertTrue(validator.path_matches("BACKEND_SPEC.md", compiled))
        self.assertFalse(validator.path_matches("docs/ops/TLS.md", compiled))

    def test_double_star_spans_directories(self):
        compiled = validator.pattern_to_regex("**/tests")
        for candidate in ("tests", "accounts/tests", "a/b/c/tests"):
            self.assertTrue(validator.path_matches(candidate, compiled), candidate)

    def test_directory_match_covers_whole_subtree(self):
        compiled = validator.pattern_to_regex("docs")
        self.assertTrue(validator.path_matches("docs/ops/RELEASE_CHECKLIST.md", compiled))

    def test_bare_pattern_is_root_anchored(self):
        # This is the Docker behaviour that made the original bare
        # `__pycache__` entry ineffective for nested directories.
        compiled = validator.pattern_to_regex("__pycache__")
        self.assertTrue(validator.path_matches("__pycache__/x.pyc", compiled))
        self.assertFalse(validator.path_matches("accounts/__pycache__/x.pyc", compiled))


class BuildContextContentTests(SimpleTestCase):
    """The current .dockerignore must not ship developer or ops material."""

    def setUp(self):
        self.paths = validator.collect_context_paths()

    def test_build_context_passes_validation(self):
        self.assertEqual(validator.validate(self.paths, "test", quiet=True), 0)

    def test_runtime_essentials_are_present(self):
        for expected in validator.EXPECT_PRESENT:
            self.assertIn(expected, self.paths)

    def test_migrations_are_present(self):
        migrations = [path for path in self.paths if "/migrations/0" in path]
        self.assertGreater(len(migrations), 0)

    def test_forbidden_material_is_absent(self):
        forbidden_prefixes = ("docs/", "scripts/", "nginx/", "assets/", "src/")
        for path in self.paths:
            self.assertFalse(
                path.startswith(forbidden_prefixes),
                f"forbidden path in build context: {path}",
            )
            self.assertNotIn("/tests/", path, f"test module in build context: {path}")
            self.assertFalse(path.endswith(".pyc"), f"bytecode in build context: {path}")

    def test_no_root_markdown_documents(self):
        root_markdown = [
            path for path in self.paths if "/" not in path and path.endswith(".md")
        ]
        self.assertEqual(root_markdown, [])


class ValidatorDetectsViolationsTests(SimpleTestCase):
    """A regression guard must actually fail on bad content."""

    def test_forbidden_path_fails(self):
        bad = list(validator.EXPECT_PRESENT) + ["docs/ops/DEPLOYMENT.md"]
        self.assertEqual(validator.validate(bad, "test", quiet=True), 1)

    def test_test_module_fails(self):
        bad = list(validator.EXPECT_PRESENT) + ["accounts/tests/test_accounts.py"]
        self.assertEqual(validator.validate(bad, "test", quiet=True), 1)

    def test_missing_runtime_file_fails(self):
        incomplete = [path for path in validator.EXPECT_PRESENT if path != "manage.py"]
        self.assertEqual(validator.validate(incomplete, "test", quiet=True), 1)

    def test_clean_listing_passes(self):
        self.assertEqual(validator.validate(list(validator.EXPECT_PRESENT), "test", quiet=True), 0)


class ImageListingModeTests(SimpleTestCase):
    """`--listing` mode must normalise real `find /app` output."""

    def test_strips_image_prefix(self):
        listing = PROJECT_ROOT / "common" / "tests" / "__image_listing_fixture.txt"
        listing.write_text(
            "/app/manage.py\n/app/config/wsgi.py\n/app/docs/ops/TLS.md\n",
            encoding="utf-8",
        )
        try:
            paths = validator.read_listing(listing, "/app")
            self.assertIn("manage.py", paths)
            self.assertIn("config/wsgi.py", paths)
            self.assertIn("docs/ops/TLS.md", paths)
        finally:
            listing.unlink()
