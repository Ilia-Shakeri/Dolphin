"""Local, operator-only record of every deployment the platform owner has
issued a manifest for — the storage behind the deployment console in
`scripts/manifest_builder.py` (§6 of `DOLPHIN_FEATURE_MAP_AND_ROADMAP.md`).

**What this is not.** It is not a live connection to a customer's server:
nothing here reads or writes anything on a deployed host, and none of it
requires one to be reachable. A record's `app_image` and `manifest_issued_at`
are exactly what the operator typed or what this tool itself last signed —
useful bookkeeping ("what did I last hand this customer"), not a verified
live status. A genuine live multi-deployment health view is a materially
different, harder problem (each deployment would need to expose something to
poll, and something would need to reach it over the network) and is
deliberately not this.

**What is stored.** Only non-secret bookkeeping: slug, display name, host,
profile, feature set, the key id used, the image reference, and timestamps —
the same shape `scripts/new_deployment.py --list-features` already prints to
a terminal. The signing private key is never part of a record and this module
never writes one to disk; every signing call still reads the key fresh from a
path typed into the console's own form, exactly as manifest_builder.py's
single-shot form already did.

**Where it lives.** A JSON file under `scripts/.dolphin-console/`, which
`.gitignore` excludes — the same boundary `secrets/` and every per-deployment
`.env` already sit behind. No customer name is hardcoded anywhere in this
repository; every value in a record is supplied by the operator at runtime.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_STORE_PATH = Path(__file__).resolve().parent / ".dolphin-console" / "deployments.json"

#: The same shape `new_deployment.py`'s own `SLUG_PATTERN` requires — a
#: deployment record is keyed by the same slug that names its database, so a
#: record for a slug that could never be provisioned is not a useful record.
SLUG_PATTERN = re.compile(r"\A[a-z][a-z0-9_]{1,40}\Z")


class DeploymentRecordError(Exception):
    """A record could not be read, written, or validated."""


@dataclass
class DeploymentRecord:
    slug: str
    display_name: str = ""
    host: str = ""
    profile_id: str = ""
    features: tuple = field(default_factory=tuple)
    key_id: str = ""
    app_image: str = ""
    manifest_path: str = "/srv/dolphin/secrets/manifest.json"
    retention_days: int = 0
    manifest_issued_at: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self):
        data = asdict(self)
        data["features"] = sorted(self.features)
        return data

    @classmethod
    def from_dict(cls, data):
        known = set(cls.__dataclass_fields__)
        cleaned = {key: value for key, value in data.items() if key in known}
        cleaned["features"] = tuple(sorted(cleaned.get("features") or ()))
        return cls(**cleaned)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_all(path=None):
    """`{slug: DeploymentRecord}`, empty if the store does not exist yet.

    A missing file is not an error — it means no deployment has been
    recorded yet, the same as a fresh checkout of this tool.

    `path=None` resolves `DEFAULT_STORE_PATH` at call time rather than at
    import time (a plain default argument would bind the value once, when
    this module is first loaded) — so a test can point `DEFAULT_STORE_PATH`
    at a temp directory and every caller that never passes its own `path`,
    manifest_builder.py's console included, honours it.
    """
    path = path or DEFAULT_STORE_PATH
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise DeploymentRecordError(f"Could not read {path}: {error}") from error
    return {
        slug: DeploymentRecord.from_dict({**item, "slug": slug})
        for slug, item in raw.get("deployments", {}).items()
    }


def _save_all(records, path=None):
    path = path or DEFAULT_STORE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"deployments": {slug: record.to_dict() for slug, record in records.items()}}
    # Write to a temp file in the same directory and rename over the real
    # one: a crash or a killed process mid-write must never leave behind a
    # half-written file that the next `load_all` cannot parse, since this
    # store has no other copy of what it holds.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def get(slug, path=None):
    return load_all(path).get(slug)


def upsert(record, path=None):
    """Create a record, or replace one with the same slug. Returns it.

    `created_at` is preserved across an update — it is set once, the first
    time a slug is ever recorded, never overwritten by a later edit.
    """
    if not SLUG_PATTERN.match(record.slug):
        raise DeploymentRecordError(
            "Slug must be 2-41 characters, lowercase, starting with a letter — the same rule new_deployment.py enforces."
        )
    records = load_all(path)
    existing = records.get(record.slug)
    now = _now()
    record.created_at = existing.created_at if existing else now
    record.updated_at = now
    records[record.slug] = record
    _save_all(records, path)
    return record


def delete(slug, path=None):
    """Remove a record. Only the local bookkeeping — never anything on a
    customer's own server, which this module has no access to at all.
    """
    records = load_all(path)
    if slug not in records:
        raise DeploymentRecordError(f"No such deployment record: {slug}")
    del records[slug]
    _save_all(records, path)
