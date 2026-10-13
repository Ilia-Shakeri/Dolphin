"""The restore check's schema proof is the code's own schema (2.40.42).

`scripts/verify-postgres-schema.sql` is generated from the models and the
migration graph (`scripts/generate_schema_proof.py`). It was hand-written once
and froze at the 1.x migration counts, so every restore check of a 2.x backup
failed. This keeps the committed file equal to what the code declares.
"""

import importlib.util
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "generate_schema_proof.py"
PROOF = ROOT / "scripts" / "verify-postgres-schema.sql"


def _generator():
    spec = importlib.util.spec_from_file_location("generate_schema_proof", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SchemaProofTests(SimpleTestCase):
    def test_the_committed_proof_matches_the_code(self):
        self.assertEqual(
            PROOF.read_text(encoding="utf-8"),
            _generator().render(),
            "scripts/verify-postgres-schema.sql is stale: run python scripts/generate_schema_proof.py",
        )

    def test_it_names_this_releases_newest_migrations(self):
        from django.db.migrations.loader import MigrationLoader

        proof = PROOF.read_text(encoding="utf-8")
        graph = MigrationLoader(None, ignore_no_migrations=True).graph
        for app, name in graph.leaf_nodes():
            with self.subTest(app=app):
                self.assertIn(f"({app!r}, {name!r})", proof)
