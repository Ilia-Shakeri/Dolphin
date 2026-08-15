"""The active deployment profile, resolved once at startup from the manifest.

PROFILE-001 selected Option C: the signed external manifest is the sole source
of truth for feature availability, and the database row in
`common/deployment/cache.py` is a derived cache that is never consulted for a
decision. Every authorisation-relevant read goes through `feature_enabled`,
which reads only this in-memory, signature-verified state.

Feature availability is one of three independent controls and must not be
confused with the other two: role permission lives in `accounts/access.py`, and
object scope lives in each app's `selectors.py`. Turning a feature off removes
access to a module; it changes no role, and it deletes no historical row.
"""

import threading

from django.core.exceptions import ImproperlyConfigured

from common.deployment.manifest import ManifestError, decode_public_keys, read_manifest_file
from common.deployment.registry import ALL_FEATURES, FEATURES


DEVELOPMENT_PROFILE_ID = "development"


class DeploymentProfile:
    """An immutable view of the feature set this deployment may run."""

    __slots__ = ("profile_id", "features", "key_id", "issued_at", "fingerprint", "source")

    def __init__(self, *, profile_id, features, source, key_id="", issued_at="", fingerprint=""):
        self.profile_id = profile_id
        self.features = frozenset(features)
        self.source = source
        self.key_id = key_id
        self.issued_at = issued_at
        self.fingerprint = fingerprint

    @property
    def is_signed(self):
        return self.source == "signed-manifest"

    def __repr__(self):
        return (
            f"DeploymentProfile(profile_id={self.profile_id!r}, source={self.source!r}, "
            f"features={sorted(self.features)!r}, fingerprint={self.fingerprint!r})"
        )


_state = threading.local()
_active_profile = None


def _development_profile():
    """The profile used only where no manifest is configured.

    Production settings set `DEPLOYMENT_MANIFEST_REQUIRED = True`, so a customer
    deployment can never reach this: it refuses to start instead.
    """
    return DeploymentProfile(
        profile_id=DEVELOPMENT_PROFILE_ID,
        features=ALL_FEATURES,
        source="development-fallback",
    )


def load_profile_from_settings(settings):
    """Resolve the profile a set of Django settings describes, or fail closed."""
    path = getattr(settings, "DEPLOYMENT_MANIFEST_PATH", "") or ""
    required = bool(getattr(settings, "DEPLOYMENT_MANIFEST_REQUIRED", False))

    if not path:
        if required:
            raise ImproperlyConfigured(
                "DEPLOYMENT_MANIFEST_PATH must name a signed deployment manifest."
            )
        return _development_profile()

    configured_keys = getattr(settings, "DEPLOYMENT_MANIFEST_PUBLIC_KEYS", None)
    try:
        public_keys = decode_public_keys(configured_keys)
        manifest = read_manifest_file(path, public_keys)
    except ManifestError as error:
        # No partial trust: an unreadable, unsigned, or unacceptable manifest
        # stops the deployment rather than falling back to anything.
        raise ImproperlyConfigured(f"Deployment manifest refused: {error}") from error

    return DeploymentProfile(
        profile_id=manifest.profile_id,
        features=manifest.features,
        source="signed-manifest",
        key_id=manifest.key_id,
        issued_at=manifest.issued_at,
        fingerprint=manifest.fingerprint,
    )


def configure_from_settings(settings):
    """Resolve and install the active profile. Called once from AppConfig.ready."""
    global _active_profile
    _active_profile = load_profile_from_settings(settings)
    return _active_profile


def active_profile():
    """Return the profile in force, preferring a test override if one is set."""
    override = getattr(_state, "override", None)
    if override is not None:
        return override
    if _active_profile is None:
        raise ImproperlyConfigured("The deployment profile has not been resolved yet.")
    return _active_profile


def feature_enabled(name):
    """True only for a feature this release ships and this deployment enables.

    An unregistered name is always False, so a typo in a gate denies access
    rather than granting it.
    """
    if name not in FEATURES:
        return False
    return name in active_profile().features


class override_active_profile:
    """Temporarily run under another profile. For tests and management commands."""

    def __init__(self, profile):
        self.profile = profile
        self.previous = None

    def __enter__(self):
        self.previous = getattr(_state, "override", None)
        _state.override = self.profile
        return self.profile

    def __exit__(self, exception_type, exception, traceback):
        _state.override = self.previous
        return False
