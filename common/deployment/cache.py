"""The derived database cache of the active deployment profile.

Option C keeps a queryable copy of the resolved feature set so admin screens and
reports can join against it. That copy is a **cache and nothing else**. It is
never read to decide whether a feature is available — `feature_enabled` reads
only the signature-verified manifest held in memory.

This matters most after a restore. A `pg_restore` of an older dump brings back
whatever row that dump contained, possibly naming features this deployment is no
longer entitled to run. Because the cache is never authoritative, that stale row
changes nothing; and the first read or refresh rewrites it from the manifest.
"""

from django.db import transaction

from common.deployment.profile import active_profile


def _row_matches(row, profile):
    return (
        row.profile_id == profile.profile_id
        and row.manifest_fingerprint == profile.fingerprint
        and sorted(row.features or []) == sorted(profile.features)
        and row.source == profile.source
    )


def refresh_profile_cache(profile=None):
    """Rewrite the cache row from the manifest and return it."""
    from common.models import DeploymentProfileCache

    profile = profile or active_profile()
    with transaction.atomic():
        row, _ = DeploymentProfileCache.objects.select_for_update().get_or_create(
            singleton=DeploymentProfileCache.SINGLETON,
            defaults={
                "profile_id": profile.profile_id,
                "manifest_fingerprint": profile.fingerprint,
                "features": sorted(profile.features),
                "source": profile.source,
            },
        )
        if not _row_matches(row, profile):
            row.profile_id = profile.profile_id
            row.manifest_fingerprint = profile.fingerprint
            row.features = sorted(profile.features)
            row.source = profile.source
            row.save(
                update_fields=[
                    "profile_id",
                    "manifest_fingerprint",
                    "features",
                    "source",
                    "updated_at",
                ]
            )
    return row


def cached_profile_row():
    """Return the cache row, repairing it first if it disagrees with the manifest.

    Reading through this function is the only supported way to touch the cache,
    so a stale row — for example one brought back by restoring an old backup —
    can never be observed as if it were current.
    """
    return refresh_profile_cache()
