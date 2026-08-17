import base64
import importlib.util
import json
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from common.deployment import ed25519
from common.deployment.cache import cached_profile_row, refresh_profile_cache
from common.deployment.manifest import (
    ManifestError,
    decode_public_keys,
    read_manifest_file,
    verify_manifest_bytes,
)
from common.deployment.profile import (
    DeploymentProfile,
    active_profile,
    feature_enabled,
    load_profile_from_settings,
    override_active_profile,
)
from common.deployment.registry import (
    ALL_FEATURES,
    FEATURE_DEPENDENCIES,
    PROFILES,
    missing_dependencies,
    unknown_features,
)
from common.models import DeploymentProfileCache
from sales.models import Customer, Sale
from sales.services import create_customer_with_phone


ROOT = Path(__file__).resolve().parents[2]
SIGNER_PATH = ROOT / "scripts" / "sign_deployment_manifest.py"

_spec = importlib.util.spec_from_file_location("sign_deployment_manifest", SIGNER_PATH)
signer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(signer)


# A throwaway signing seed used only by this test module. It is not a
# deployment key: the real private key is generated with OpenSSL by the platform
# owner and never enters this repository.
TEST_SEED = bytes(range(32))
OTHER_SEED = bytes(range(100, 132))
KEY_ID = "test-signer"


def public_key_for(seed):
    return signer.sign(seed, b"")[0]


def signed_manifest(
    *,
    profile_id="client-1",
    features=("customers", "leads", "sales"),
    seed=TEST_SEED,
    key_id=KEY_ID,
    manifest_version=1,
    payload_version=1,
    algorithm="ed25519",
    issued_at="2026-08-15T00:00:00Z",
):
    """Build an envelope directly, so malformed variants can be built too."""
    payload = json.dumps(
        {
            "manifest_version": payload_version,
            "profile_id": profile_id,
            "issued_at": issued_at,
            "features": list(features),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    _, signature = signer.sign(seed, payload)
    return json.dumps(
        {
            "manifest_version": manifest_version,
            "algorithm": algorithm,
            "key_id": key_id,
            "payload": base64.b64encode(payload).decode("ascii"),
            "signature": base64.b64encode(signature).decode("ascii"),
        }
    ).encode("utf-8")


def trusted_keys(seed=TEST_SEED, key_id=KEY_ID):
    return {key_id: public_key_for(seed)}


class Ed25519ReferenceVectorTests(SimpleTestCase):
    """RFC 8032 section 7.1 vectors, an authority outside this repository."""

    VECTORS = [
        (
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
            "",
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a"
            "33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
        ),
        (
            "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
            "72",
            "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e1"
            "5996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
        ),
        (
            "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
            "af82",
            "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d1"
            "6f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
        ),
    ]

    def test_reference_signatures_verify(self):
        for public_key, message, signature in self.VECTORS:
            with self.subTest(public_key=public_key):
                self.assertTrue(
                    ed25519.verify(
                        bytes.fromhex(public_key),
                        bytes.fromhex(message),
                        bytes.fromhex(signature),
                    )
                )

    def test_signing_reproduces_the_reference_public_keys_and_signatures(self):
        seeds = [
            "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
            "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
            "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
        ]
        for seed, (public_key, message, signature) in zip(seeds, self.VECTORS):
            with self.subTest(seed=seed):
                derived_key, derived_signature = signer.sign(
                    bytes.fromhex(seed), bytes.fromhex(message)
                )
                self.assertEqual(derived_key.hex(), public_key)
                self.assertEqual(derived_signature.hex(), signature)

    def test_every_corruption_is_rejected(self):
        public_key, message, signature = self.VECTORS[1]
        public_key = bytes.fromhex(public_key)
        message = bytes.fromhex(message)
        signature = bytes.fromhex(signature)
        flipped = bytearray(signature)
        flipped[0] ^= 1
        cases = {
            "wrong message": (public_key, b"\x73", signature),
            "flipped signature byte": (public_key, message, bytes(flipped)),
            "wrong public key": (bytes.fromhex(self.VECTORS[0][0]), message, signature),
            "short signature": (public_key, message, signature[:63]),
            "short public key": (public_key[:31], message, signature),
            "empty signature": (public_key, message, b""),
            "scalar at group order": (
                public_key,
                message,
                signature[:32] + ed25519.Q.to_bytes(32, "little"),
            ),
        }
        for name, (key, text, sign_bytes) in cases.items():
            with self.subTest(case=name):
                self.assertFalse(ed25519.verify(key, text, sign_bytes))


class ManifestVerificationTests(SimpleTestCase):
    def test_a_correctly_signed_manifest_is_accepted(self):
        manifest = verify_manifest_bytes(signed_manifest(), trusted_keys())
        self.assertEqual(manifest.profile_id, "client-1")
        self.assertEqual(manifest.features, frozenset({"customers", "leads", "sales"}))
        self.assertEqual(manifest.key_id, KEY_ID)
        self.assertEqual(len(manifest.fingerprint), 64)

    def test_a_tampered_payload_is_refused(self):
        raw = signed_manifest(features=("customers",))
        envelope = json.loads(raw)
        # Re-issue the payload with an extra feature, keeping the old signature.
        forged = json.dumps(
            {
                "manifest_version": 1,
                "profile_id": "client-1",
                "issued_at": "2026-08-15T00:00:00Z",
                "features": ["customers", "audit_log"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        envelope["payload"] = base64.b64encode(forged).decode("ascii")
        with self.assertRaisesMessage(ManifestError, "signature is not valid"):
            verify_manifest_bytes(json.dumps(envelope).encode("utf-8"), trusted_keys())

    def test_a_manifest_signed_by_another_key_is_refused(self):
        raw = signed_manifest(seed=OTHER_SEED)
        with self.assertRaisesMessage(ManifestError, "signature is not valid"):
            verify_manifest_bytes(raw, trusted_keys())

    def test_an_unknown_key_id_is_refused(self):
        raw = signed_manifest(key_id="somebody-elses-key")
        with self.assertRaisesMessage(ManifestError, "untrusted key"):
            verify_manifest_bytes(raw, trusted_keys())

    def test_no_trusted_key_can_never_verify(self):
        for keys in ({}, None):
            with self.subTest(keys=keys):
                with self.assertRaises(ManifestError):
                    verify_manifest_bytes(signed_manifest(), keys)

    def test_an_unknown_algorithm_is_refused(self):
        raw = signed_manifest(algorithm="none")
        with self.assertRaisesMessage(ManifestError, "algorithm is not supported"):
            verify_manifest_bytes(raw, trusted_keys())

    def test_an_unknown_profile_is_refused_even_when_correctly_signed(self):
        envelope = json.loads(signed_manifest())
        payload = json.dumps(
            {
                "manifest_version": 1,
                "profile_id": "client-99",
                "issued_at": "2026-08-15T00:00:00Z",
                "features": ["customers"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        _, signature = signer.sign(TEST_SEED, payload)
        envelope["payload"] = base64.b64encode(payload).decode("ascii")
        envelope["signature"] = base64.b64encode(signature).decode("ascii")
        with self.assertRaisesMessage(ManifestError, "unknown profile"):
            verify_manifest_bytes(json.dumps(envelope).encode("utf-8"), trusted_keys())

    def test_an_unknown_feature_is_refused(self):
        raw = signed_manifest(features=("customers", "invoicing"))
        with self.assertRaisesMessage(ManifestError, "does not ship"):
            verify_manifest_bytes(raw, trusted_keys())

    def test_unmet_feature_dependencies_are_refused(self):
        raw = signed_manifest(features=("sales",))
        with self.assertRaisesMessage(ManifestError, "unmet feature dependencies"):
            verify_manifest_bytes(raw, trusted_keys())

    def test_structurally_broken_manifests_are_refused(self):
        cases = {
            "not json": b"not json at all",
            "json array": b"[]",
            "empty": b"",
            "unsupported envelope version": signed_manifest(manifest_version=2),
            "unsupported payload version": signed_manifest(payload_version=2),
            "oversized": b"{}" + b" " * (64 * 1024),
        }
        for name, raw in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ManifestError):
                    verify_manifest_bytes(raw, trusted_keys())

    def test_malformed_envelope_fields_are_refused(self):
        for field, value in (
            ("payload", "not base64!!"),
            ("signature", "not base64!!"),
            ("key_id", ""),
            ("payload", 17),
        ):
            with self.subTest(field=field, value=value):
                envelope = json.loads(signed_manifest())
                envelope[field] = value
                with self.assertRaises(ManifestError):
                    verify_manifest_bytes(
                        json.dumps(envelope).encode("utf-8"), trusted_keys()
                    )

    def test_a_repeated_feature_is_refused(self):
        raw = signed_manifest(features=("customers", "customers"))
        with self.assertRaisesMessage(ManifestError, "repeats a feature"):
            verify_manifest_bytes(raw, trusted_keys())

    def test_public_key_configuration_is_validated(self):
        with self.assertRaises(ManifestError):
            decode_public_keys({"k": "not base64!!"})
        with self.assertRaises(ManifestError):
            decode_public_keys({"k": base64.b64encode(b"too short").decode("ascii")})
        self.assertEqual(
            decode_public_keys(
                {"k": base64.b64encode(public_key_for(TEST_SEED)).decode("ascii")}
            ),
            {"k": public_key_for(TEST_SEED)},
        )


class ProfileResolutionTests(SimpleTestCase):
    def write_manifest(self, raw):
        path = Path(self.enterContext(__import__("tempfile").TemporaryDirectory()))
        target = path / "manifest.json"
        target.write_bytes(raw)
        return str(target)

    def settings_with(self, **values):
        return type("Settings", (), values)

    def test_a_valid_manifest_becomes_the_active_profile(self):
        path = self.write_manifest(signed_manifest(features=("customers", "products")))
        profile = load_profile_from_settings(
            self.settings_with(
                DEPLOYMENT_MANIFEST_PATH=path,
                DEPLOYMENT_MANIFEST_PUBLIC_KEYS={
                    KEY_ID: base64.b64encode(public_key_for(TEST_SEED)).decode("ascii")
                },
                DEPLOYMENT_MANIFEST_REQUIRED=True,
            )
        )
        self.assertEqual(profile.profile_id, "client-1")
        self.assertEqual(profile.features, frozenset({"customers", "products"}))
        self.assertTrue(profile.is_signed)

    def test_an_unreadable_manifest_stops_the_deployment(self):
        with self.assertRaises(ImproperlyConfigured):
            load_profile_from_settings(
                self.settings_with(
                    DEPLOYMENT_MANIFEST_PATH=str(ROOT / "no-such-manifest.json"),
                    DEPLOYMENT_MANIFEST_PUBLIC_KEYS={},
                    DEPLOYMENT_MANIFEST_REQUIRED=True,
                )
            )

    def test_a_tampered_manifest_stops_the_deployment_rather_than_degrading(self):
        envelope = json.loads(signed_manifest())
        envelope["signature"] = base64.b64encode(b"\x00" * 64).decode("ascii")
        path = self.write_manifest(json.dumps(envelope).encode("utf-8"))
        with self.assertRaises(ImproperlyConfigured):
            load_profile_from_settings(
                self.settings_with(
                    DEPLOYMENT_MANIFEST_PATH=path,
                    DEPLOYMENT_MANIFEST_PUBLIC_KEYS={
                        KEY_ID: base64.b64encode(public_key_for(TEST_SEED)).decode("ascii")
                    },
                    DEPLOYMENT_MANIFEST_REQUIRED=True,
                )
            )

    def test_a_deployment_that_requires_a_manifest_refuses_to_run_without_one(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "DEPLOYMENT_MANIFEST_PATH"):
            load_profile_from_settings(
                self.settings_with(
                    DEPLOYMENT_MANIFEST_PATH="",
                    DEPLOYMENT_MANIFEST_PUBLIC_KEYS={},
                    DEPLOYMENT_MANIFEST_REQUIRED=True,
                )
            )

    def test_production_settings_require_a_manifest(self):
        production = (ROOT / "config" / "production_settings.py").read_text(encoding="utf-8")
        self.assertIn("DEPLOYMENT_MANIFEST_REQUIRED = True", production)

    def test_development_runs_on_the_named_development_profile(self):
        profile = load_profile_from_settings(
            self.settings_with(
                DEPLOYMENT_MANIFEST_PATH="",
                DEPLOYMENT_MANIFEST_PUBLIC_KEYS={},
                DEPLOYMENT_MANIFEST_REQUIRED=False,
            )
        )
        self.assertEqual(profile.profile_id, "development")
        self.assertFalse(profile.is_signed)
        self.assertEqual(profile.features, ALL_FEATURES)


class FeatureRegistryTests(SimpleTestCase):
    def test_two_distinct_profiles_can_be_expressed(self):
        # P3 completion gate: at least two profiles, differing only in features.
        full = signed_manifest(profile_id="client-1", features=sorted(ALL_FEATURES))
        reduced = signed_manifest(
            profile_id="demo", features=("customers", "products")
        )
        client_one = verify_manifest_bytes(full, trusted_keys())
        demo = verify_manifest_bytes(reduced, trusted_keys())
        self.assertNotEqual(client_one.profile_id, demo.profile_id)
        self.assertNotEqual(client_one.features, demo.features)
        self.assertLess(demo.features, client_one.features)

    def test_every_dependency_names_a_registered_feature(self):
        for feature, required in FEATURE_DEPENDENCIES.items():
            with self.subTest(feature=feature):
                self.assertFalse(unknown_features(required), feature)
                self.assertNotIn(feature, required)

    def test_the_full_feature_set_has_no_unmet_dependency(self):
        self.assertEqual(missing_dependencies(ALL_FEATURES), {})

    def test_an_unregistered_feature_name_is_never_enabled(self):
        with override_active_profile(
            DeploymentProfile(
                profile_id="client-1", features=ALL_FEATURES, source="signed-manifest"
            )
        ):
            self.assertTrue(feature_enabled("customers"))
            # A typo denies rather than grants.
            self.assertFalse(feature_enabled("customer"))
            self.assertFalse(feature_enabled(""))
            self.assertFalse(feature_enabled("invoicing"))

    def test_the_development_profile_id_is_registered(self):
        self.assertIn("development", PROFILES)
        self.assertIn("client-1", PROFILES)
        self.assertIn("demo", PROFILES)


class FeatureGateEnforcementTests(TestCase):
    """A disabled feature must be refused by the backend, not just hidden."""

    @classmethod
    def setUpTestData(cls):
        cls.password = "Feature-Gate-Proof-741!"
        cls.admin = User.objects.create_user(
            username="feature.platform",
            password=cls.password,
            role=User.Role.PLATFORM_ADMIN,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def reduced_profile(self, *features):
        return DeploymentProfile(
            profile_id="demo",
            features=frozenset(features),
            source="signed-manifest",
            fingerprint="a" * 64,
        )

    def test_enabled_modules_answer_and_disabled_modules_do_not_exist(self):
        with override_active_profile(self.reduced_profile("customers", "products")):
            self.assertEqual(self.client.get("/api/v1/customers/").status_code, 200)
            self.assertEqual(self.client.get("/api/v1/products/").status_code, 200)
            for path in (
                "/api/v1/leads/",
                "/api/v1/sales/",
                "/api/v1/sales-documents/",
                "/api/v1/after-sales/",
                "/api/v1/activity-logs/",
                "/api/v1/inbound-sms/report/",
                "/api/v1/reports/user-performance/",
            ):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path).status_code, 404)

    def test_a_disabled_module_refuses_writes_as_well_as_reads(self):
        with override_active_profile(self.reduced_profile("customers")):
            response = self.client.post(
                "/api/v1/products/",
                data={"sku": "GATE-1", "name": "gated", "current_price": "1.00"},
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 404)

    def test_disabled_pages_are_not_reachable(self):
        with override_active_profile(self.reduced_profile("customers")):
            self.assertEqual(self.client.get(reverse("common_ui:customers")).status_code, 200)
            for name in ("common_ui:leads", "common_ui:sales", "common_ui:after-sales"):
                with self.subTest(page=name):
                    self.assertEqual(self.client.get(reverse(name)).status_code, 404)

    def test_navigation_hides_a_disabled_module(self):
        with override_active_profile(self.reduced_profile("customers")):
            body = self.client.get(reverse("common_ui:home")).content.decode("utf-8")
        self.assertIn('data-module="customers"', body)
        self.assertNotIn('data-module="sales"', body)
        self.assertNotIn('data-module="after-sales"', body)

    def test_a_feature_never_changes_what_a_role_may_do(self):
        # Role permission is a separate control: enabling every feature does not
        # give an agent a manager's capability, and disabling one does not take
        # a capability away.
        from accounts.access import capabilities_for

        agent = User.objects.create_user(
            username="feature.agent", password=self.password, role=User.Role.SALES_AGENT
        )
        with override_active_profile(self.reduced_profile(*ALL_FEATURES)):
            with_everything = capabilities_for(agent)
        with override_active_profile(self.reduced_profile("customers")):
            with_one = capabilities_for(agent)
        self.assertEqual(with_everything, with_one)
        self.assertNotIn("users.manage_all", with_everything)

    def test_object_scope_still_applies_inside_an_enabled_feature(self):
        # Feature availability does not widen object scope.
        from sales.selectors import customers_for

        other_agent = User.objects.create_user(
            username="feature.other", password=self.password, role=User.Role.SALES_AGENT
        )
        create_customer_with_phone(
            actor=self.admin,
            full_name="GATE SCOPE CUSTOMER",
            phone={"raw_phone": "09120000055", "is_primary": True},
            city="GateCity",
        )
        with override_active_profile(self.reduced_profile(*ALL_FEATURES)):
            self.assertEqual(customers_for(other_agent).count(), 0)
            self.assertEqual(customers_for(self.admin).count(), 1)


class FeatureDisablingPreservesDataTests(TestCase):
    """Turning a feature off withholds access; it never deletes history."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="retention.platform",
            password="Retention-Proof-741!",
            role=User.Role.PLATFORM_ADMIN,
        )
        cls.customer = create_customer_with_phone(
            actor=cls.admin,
            full_name="RETENTION CUSTOMER",
            phone={"raw_phone": "09120000077", "is_primary": True},
            city="RetentionCity",
        )

    def test_rows_survive_a_profile_that_no_longer_enables_their_module(self):
        before = Customer.objects.count()
        with override_active_profile(
            DeploymentProfile(profile_id="demo", features=frozenset(), source="signed-manifest")
        ):
            self.client.force_login(self.admin)
            self.assertEqual(self.client.get("/api/v1/customers/").status_code, 404)
            # The gate is on access, not on storage.
            self.assertEqual(Customer.objects.count(), before)
        self.assertEqual(Customer.objects.count(), before)
        self.assertTrue(Customer.objects.filter(full_name="RETENTION CUSTOMER").exists())
        self.assertEqual(Sale.objects.count(), 0)

    def test_re_enabling_a_feature_shows_the_same_rows_again(self):
        with override_active_profile(
            DeploymentProfile(profile_id="demo", features=frozenset(), source="signed-manifest")
        ):
            pass
        with override_active_profile(
            DeploymentProfile(
                profile_id="client-1", features=ALL_FEATURES, source="signed-manifest"
            )
        ):
            self.client.force_login(self.admin)
            response = self.client.get("/api/v1/customers/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                [row["full_name"] for row in response.json()["results"]],
                ["RETENTION CUSTOMER"],
            )


class ProfileCacheIsNeverAuthoritativeTests(TestCase):
    def signed_profile(self, *features, profile_id="client-1", fingerprint="b" * 64):
        return DeploymentProfile(
            profile_id=profile_id,
            features=frozenset(features),
            source="signed-manifest",
            fingerprint=fingerprint,
        )

    def test_the_cache_is_written_from_the_manifest(self):
        profile = self.signed_profile("customers", "products")
        with override_active_profile(profile):
            row = refresh_profile_cache()
        self.assertEqual(row.profile_id, "client-1")
        self.assertEqual(row.features, ["customers", "products"])
        self.assertEqual(row.manifest_fingerprint, "b" * 64)
        self.assertEqual(DeploymentProfileCache.objects.count(), 1)

    def test_a_stale_restored_row_cannot_enable_a_withdrawn_feature(self):
        # Stand in for `pg_restore` of an older dump: a row naming features the
        # deployment is no longer entitled to run.
        DeploymentProfileCache.objects.create(
            singleton=DeploymentProfileCache.SINGLETON,
            profile_id="client-1",
            manifest_fingerprint="c" * 64,
            features=sorted(ALL_FEATURES),
            source="signed-manifest",
        )
        current = self.signed_profile("customers")
        with override_active_profile(current):
            self.assertFalse(feature_enabled("after_sales"))
            self.assertFalse(feature_enabled("sales"))
            self.assertTrue(feature_enabled("customers"))
            self.client.force_login(
                User.objects.create_user(
                    username="cache.platform",
                    password="Cache-Proof-741!",
                    role=User.Role.PLATFORM_ADMIN,
                )
            )
            self.assertEqual(self.client.get("/api/v1/after-sales/").status_code, 404)
            # Reading the cache repairs it rather than trusting it.
            row = cached_profile_row()
        self.assertEqual(row.features, ["customers"])
        self.assertEqual(row.manifest_fingerprint, "b" * 64)
        self.assertEqual(DeploymentProfileCache.objects.count(), 1)

    def test_a_row_deleted_by_a_restore_is_rebuilt_without_changing_behaviour(self):
        profile = self.signed_profile("customers", "leads")
        with override_active_profile(profile):
            refresh_profile_cache()
            DeploymentProfileCache.objects.all().delete()
            self.assertTrue(feature_enabled("leads"))
            row = cached_profile_row()
        self.assertEqual(row.features, ["customers", "leads"])

    def test_rolling_back_to_an_earlier_manifest_takes_effect_immediately(self):
        with override_active_profile(self.signed_profile(*ALL_FEATURES, fingerprint="d" * 64)):
            refresh_profile_cache()
            self.assertTrue(feature_enabled("audit_log"))
        rolled_back = self.signed_profile("customers", fingerprint="e" * 64)
        with override_active_profile(rolled_back):
            self.assertFalse(feature_enabled("audit_log"))
            row = cached_profile_row()
        self.assertEqual(row.manifest_fingerprint, "e" * 64)
        self.assertEqual(row.features, ["customers"])

    def test_the_cache_table_holds_at_most_one_row(self):
        with override_active_profile(self.signed_profile("customers")):
            refresh_profile_cache()
            refresh_profile_cache()
        self.assertEqual(DeploymentProfileCache.objects.count(), 1)


class SigningToolSafetyTests(SimpleTestCase):
    def test_the_signing_tool_is_excluded_from_the_shipped_image(self):
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("scripts", ignore)

    def test_the_repository_carries_no_private_signing_key(self):
        for path in ROOT.glob("*.pem"):
            self.fail(f"A key file is present in the repository root: {path.name}")
        settings_text = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
        self.assertNotIn("PRIVATE KEY", settings_text)
        self.assertIn("DEPLOYMENT_MANIFEST_PUBLIC_KEYS", settings_text)

    def test_the_tool_refuses_an_unknown_profile_or_feature(self):
        with self.assertRaises(ValueError):
            signer.build_manifest(
                seed=TEST_SEED,
                key_id=KEY_ID,
                profile_id="client-99",
                features=["customers"],
                issued_at="2026-08-15T00:00:00Z",
            )
        with self.assertRaises(ValueError):
            signer.build_manifest(
                seed=TEST_SEED,
                key_id=KEY_ID,
                profile_id="client-1",
                features=["invoicing"],
                issued_at="2026-08-15T00:00:00Z",
            )
        with self.assertRaises(ValueError):
            signer.build_manifest(
                seed=TEST_SEED,
                key_id=KEY_ID,
                profile_id="client-1",
                features=["sales"],
                issued_at="2026-08-15T00:00:00Z",
            )

    def test_a_tool_issued_manifest_verifies_and_round_trips(self):
        raw = signer.build_manifest(
            seed=TEST_SEED,
            key_id=KEY_ID,
            profile_id="demo",
            features=["customers", "leads"],
            issued_at="2026-08-15T00:00:00Z",
        )
        manifest = verify_manifest_bytes(raw, trusted_keys())
        self.assertEqual(manifest.profile_id, "demo")
        self.assertEqual(manifest.features, frozenset({"customers", "leads"}))

    def test_reading_a_manifest_from_disk_matches_reading_it_from_bytes(self):
        import tempfile

        raw = signer.build_manifest(
            seed=TEST_SEED,
            key_id=KEY_ID,
            profile_id="client-1",
            features=sorted(ALL_FEATURES),
            issued_at="2026-08-15T00:00:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_bytes(raw)
            from_disk = read_manifest_file(str(path), trusted_keys())
        from_bytes = verify_manifest_bytes(raw, trusted_keys())
        self.assertEqual(from_disk.fingerprint, from_bytes.fingerprint)
        self.assertEqual(from_disk.features, from_bytes.features)


class ActiveProfileDefaultTests(SimpleTestCase):
    def test_the_test_suite_runs_on_the_development_profile_with_every_feature(self):
        profile = active_profile()
        self.assertEqual(profile.profile_id, "development")
        self.assertEqual(profile.features, ALL_FEATURES)
        self.assertFalse(profile.is_signed)

    @override_settings()
    def test_every_registered_feature_is_enabled_by_default(self):
        for feature in ALL_FEATURES:
            with self.subTest(feature=feature):
                self.assertTrue(feature_enabled(feature))
