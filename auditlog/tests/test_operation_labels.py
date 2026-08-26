"""«رویداد های سامانه باید فارسی باشند چون سایت و پنل فارسی است.»

The panel is Persian, so the activity log must read as Persian. What is pinned
here is that the translation is complete — every operation the code actually
emits has a name — and that adding an untranslated one is caught here rather
than discovered by a reader looking at an English string in a Persian table.

The stored value is deliberately unchanged and that is pinned too: the log is
filtered by `operation`, and rows written before this existed still carry the
ASCII form.
"""

import pathlib
import re

from django.test import SimpleTestCase

from auditlog.labels import OPERATION_LABELS, operation_label


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
#: `log_activity(..., operation="noun.verb", ...)` as written in the source.
CALL = re.compile(r'operation=["\']([a-z0-9_.]+)["\']')
#: Directories that are vendor demo material or tests, not first-party services.
SKIP = {
    "node_modules", ".git", "assets", "src", "dashboards", "pages", "apps",
    "layouts", "toolbars", "widgets", "utilities", "account", "authentication",
    "tests", "migrations", "__pycache__",
}


def emitted_operations():
    """Every operation string the first-party code passes to `log_activity`."""
    found = set()
    for path in REPOSITORY_ROOT.rglob("*.py"):
        if SKIP.intersection(path.parts):
            continue
        found.update(CALL.findall(path.read_text(encoding="utf-8")))
    return found


class OperationLabelTests(SimpleTestCase):
    def test_every_operation_the_code_emits_has_a_persian_name(self):
        missing = sorted(emitted_operations() - set(OPERATION_LABELS))
        self.assertEqual(
            missing,
            [],
            "These operations are written to the audit log with no Persian "
            f"label, so the panel would show them in English: {missing}",
        )

    def test_the_labels_are_actually_persian(self):
        """A label left as its own ASCII key would pass the check above."""
        persian = re.compile(r"[؀-ۿ]")
        untranslated = sorted(
            key for key, label in OPERATION_LABELS.items() if not persian.search(label)
        )
        self.assertEqual(untranslated, [])

    def test_an_unknown_operation_falls_back_to_its_stored_form(self):
        """Ugly, never blank: an audit row must not lose its name."""
        self.assertEqual(operation_label("something.new"), "something.new")

    def test_a_missing_operation_is_not_rendered_as_empty(self):
        self.assertEqual(operation_label(""), "—")
        self.assertEqual(operation_label(None), "—")

    def test_a_known_operation_reads_in_persian(self):
        self.assertEqual(operation_label("invoice.issued"), "صدور فاکتور")
        self.assertEqual(operation_label("payment.registered"), "ثبت سند مالی")

    def test_no_two_operations_share_a_label(self):
        """Two events with one name are indistinguishable in the log."""
        seen = {}
        collisions = []
        for key, label in OPERATION_LABELS.items():
            if label in seen:
                collisions.append((seen[label], key, label))
            seen[label] = key
        self.assertEqual(collisions, [])
