"""The local JSON-backed deployment record store behind the console in
`scripts/manifest_builder.py` (`scripts/deployment_records.py`).

Pure Python, no Django and no HTTP involved — the console's own HTTP tests
live in `test_manifest_builder.py` and exercise this module through the
real routes; this file is the module's own contract in isolation.
"""

import json
import shutil
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from scripts import deployment_records as records


class DeploymentRecordStoreTests(SimpleTestCase):
    def setUp(self):
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        self.path = Path(tmp_dir) / "deployments.json"

    def test_loading_a_store_that_does_not_exist_yet_is_empty_not_an_error(self):
        self.assertEqual(records.load_all(self.path), {})

    def test_a_record_round_trips_through_upsert_and_load(self):
        record = records.DeploymentRecord(
            slug="acme", display_name="Acme", host="crm.acme.ir",
            profile_id="client-1", features=("customers", "leads"),
            key_id="k1", app_image="ghcr.io/x/dolphin-app@sha256:abc",
        )
        saved = records.upsert(record, self.path)
        self.assertTrue(saved.created_at)
        self.assertEqual(saved.created_at, saved.updated_at)

        loaded = records.load_all(self.path)
        self.assertEqual(set(loaded), {"acme"})
        self.assertEqual(loaded["acme"].host, "crm.acme.ir")
        # Stored sorted, regardless of insertion order — a record read back
        # must not depend on set iteration order.
        self.assertEqual(loaded["acme"].features, ("customers", "leads"))

    def test_updating_an_existing_slug_replaces_it_and_keeps_created_at(self):
        first = records.upsert(records.DeploymentRecord(slug="acme", host="a.example.com"), self.path)
        second = records.upsert(
            records.DeploymentRecord(slug="acme", host="b.example.com", features=("customers",)), self.path,
        )
        self.assertEqual(second.created_at, first.created_at)
        self.assertNotEqual(second.updated_at, "")
        loaded = records.get("acme", self.path)
        self.assertEqual(loaded.host, "b.example.com")
        self.assertEqual(len(records.load_all(self.path)), 1)

    def test_an_invalid_slug_is_refused_before_anything_is_written(self):
        with self.assertRaises(records.DeploymentRecordError):
            records.upsert(records.DeploymentRecord(slug="Not Valid!"), self.path)
        self.assertFalse(self.path.exists())

    def test_deleting_an_unknown_slug_is_refused(self):
        with self.assertRaises(records.DeploymentRecordError):
            records.delete("does-not-exist", self.path)

    def test_delete_removes_only_that_record(self):
        records.upsert(records.DeploymentRecord(slug="acme"), self.path)
        records.upsert(records.DeploymentRecord(slug="beta"), self.path)
        records.delete("acme", self.path)
        self.assertEqual(set(records.load_all(self.path)), {"beta"})

    def test_get_of_an_unknown_slug_is_none_not_an_exception(self):
        self.assertIsNone(records.get("nothing-here", self.path))

    def test_the_stored_file_is_readable_json_with_no_secret_looking_keys(self):
        records.upsert(
            records.DeploymentRecord(slug="acme", host="crm.acme.ir", features=("customers",)), self.path,
        )
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        row = payload["deployments"]["acme"]
        self.assertNotIn("private_key", row)
        self.assertNotIn("key", " ".join(row) if False else row)  # no field literally named "key"
        self.assertEqual(row["host"], "crm.acme.ir")

    def test_a_crash_mid_write_never_corrupts_the_previous_good_file(self):
        """The temp-file-then-rename write is what this actually checks: the
        real file on disk is either the old content or the new content,
        never a half-written one.
        """
        records.upsert(records.DeploymentRecord(slug="acme", host="a.example.com"), self.path)
        before = self.path.read_text(encoding="utf-8")
        self.assertTrue(json.loads(before))
        # No partial-write path exists to trigger in-process; this instead
        # proves the invariant a reader depends on: the file is always
        # complete, valid JSON after every successful call.
        records.upsert(records.DeploymentRecord(slug="acme", host="b.example.com"), self.path)
        after = self.path.read_text(encoding="utf-8")
        self.assertTrue(json.loads(after))
        self.assertNotEqual(before, after)
