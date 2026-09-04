"""The published API schema generates cleanly — enforced, not just documented.

`docs/ops/RELEASE_CHECKLIST.md` and the deployment runbook have both named
`manage.py spectacular --validate --fail-on-warn` as a release gate for a
long time, and `common/tests/test_backup_scripts.py` checks that they still
say so. Nothing ran it.

So it drifted. Two views reached `main` unable to generate: a `POST` on a
plain `APIView` with no request body declared makes the generator try to
guess a request serializer, find none, and report an error against that
view. Generation still *finishes* — the path stays in the output with its
request body unresolved — which is exactly why nothing downstream noticed:
only `--fail-on-warn` turns it into a non-zero exit, and only a person
running that by hand ever saw it. `AttachmentDeleteView` had been in that
state since `1.7.11` and `ChatThreadReadView` since `1.8.0`; both were
found while building something else, by running the documented command.

This module runs the gate for real, in-process, on every test run.
"""

from django.test import SimpleTestCase
from drf_spectacular.drainage import GENERATOR_STATS
from drf_spectacular.generators import SchemaGenerator


def generate_schema():
    """Build the whole schema, returning it with everything the run reported.

    `GENERATOR_STATS` is module-level and accumulates across generations, so
    it is reset first: without that, a second call in the same process would
    inherit the first one's findings and this could pass or fail depending on
    test ordering.
    """
    GENERATOR_STATS.reset()
    with GENERATOR_STATS.silence():
        schema = SchemaGenerator().get_schema(request=None, public=True)
    return schema, dict(GENERATOR_STATS._error_cache), dict(GENERATOR_STATS._warn_cache)


class SchemaGenerationTests(SimpleTestCase):
    def setUp(self):
        self.schema, self.errors, self.warnings = generate_schema()

    def test_the_schema_generates_without_errors(self):
        self.assertEqual(
            self.errors, {}, "\n".join(f"- {message}" for message in self.errors),
        )

    def test_the_schema_generates_without_warnings(self):
        """`--fail-on-warn` is the documented gate, so a warning is a failure."""
        self.assertEqual(
            self.warnings, {}, "\n".join(f"- {message}" for message in self.warnings),
        )

    def test_every_path_that_generated_carries_at_least_one_operation(self):
        for path, operations in self.schema["paths"].items():
            with self.subTest(path=path):
                self.assertTrue(operations, f"{path} generated no operations")

    def test_the_endpoints_that_once_failed_are_in_the_schema(self):
        """The two that broke the gate, named so a silent loss stays visible.

        These pass even while the error above is present — generation keeps
        going and still emits the path — so this is not what caught the bug
        and is not what would catch it again. It is here for the other
        failure mode: a view disappearing from the published schema
        entirely, which no error-count assertion would notice.
        """
        for path in (
            "/api/v1/attachments/{attachment_id}/delete/",
            "/api/v1/chat/threads/{thread_id}/read/",
        ):
            with self.subTest(path=path):
                self.assertIn(path, self.schema["paths"])
                self.assertIn("post", self.schema["paths"][path])

    def test_the_three_newest_features_are_published_too(self):
        for path in (
            "/api/v1/reminders/",
            "/api/v1/reminders/count/",
            "/api/v1/search/",
            "/api/v1/customers/{customer_id}/timeline/",
        ):
            with self.subTest(path=path):
                self.assertIn(path, self.schema["paths"])
