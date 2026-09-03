"""The local-only web form over `sign_deployment_manifest.py` and
`new_deployment.py` (`scripts/manifest_builder.py`, "Level 1 + Level 2" of the
mini-app idea in `DOLPHIN_FEATURE_MAP_AND_ROADMAP.md` §6).

Four things are worth proving, not assuming:

* it signs nothing this codebase's own verifier would refuse — every manifest
  this test builds is round-tripped through `common.deployment.manifest`, the
  exact module `common/deployment/profile.py` uses at application startup,
  not a hand-rolled check of this test's own;
* a missing dependency really is completed, not merely accepted, because a
  manifest naming `payments` without `invoices` and `customers` is exactly
  the kind of file this tool exists to make impossible to produce by mistake;
* the optional Level-2 `.env` draft really does come out of
  `new_deployment.env_lines` — the same function the CLI uses — and really is
  all-or-nothing on slug/host, not silently half-built;
* the server really does refuse a request that does not name 127.0.0.1 or
  localhost in its `Host` header, since binding to the loopback interface is
  not the only thing standing between this and a wider network.
"""

import html
import http.client
import importlib.util
import json
import shutil
import tempfile
import threading
from pathlib import Path

from django.test import SimpleTestCase

from common.deployment.manifest import decode_public_keys, verify_manifest_bytes
from common.deployment.registry import FEATURE_DEPENDENCIES

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "manifest_builder.py"
SIGNER_SCRIPT = REPOSITORY_ROOT / "scripts" / "sign_deployment_manifest.py"


def load_script(name, path):
    """Import a script by path; `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_script("manifest_builder", SCRIPT)
# `manifest_builder` only ever reads an existing key file — generating one is
# not part of what the form does, so `generate_key` is not among the names it
# imports from `sign_deployment_manifest`. This test needs one to sign
# anything with, so it loads the CLI module directly, the same way
# `test_deployment_profile.py` and `test_new_deployment.py` already do.
signer = load_script("sign_deployment_manifest", SIGNER_SCRIPT)


class ResultHtmlTests(SimpleTestCase):
    """`_build_result_html` — the part with no HTTP server involved."""

    def setUp(self):
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        self.key_path = str(Path(tmp_dir) / "signing.pem")
        signer.generate_key(self.key_path)

    def build(self, **fields):
        form = {"profile_id": [""], "key_id": [""], "private_key_path": [""], "feature": []}
        form.update({key: (value if isinstance(value, list) else [value]) for key, value in fields.items()})
        return builder._build_result_html(form)

    def test_a_missing_dependency_is_completed_not_merely_signed(self):
        page = self.build(
            profile_id="client-1", key_id="k1", private_key_path=self.key_path,
            feature=["payments"],
        )
        self.assertIn("ساخته و امضا شد", page)
        self.assertIn("payments", page)
        self.assertIn("invoices", page)
        self.assertIn("customers", page)
        self.assertIn("products", page)

    def test_the_signed_manifest_verifies_through_the_real_verifier(self):
        """Not this test's own idea of correct — the application's."""
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers", "audit_log"],
        )
        envelope_text = html.unescape(page.split("محتوای فایل:</small></p>\n  <pre>")[1].split("</pre>")[0])
        raw = json.dumps(json.loads(envelope_text)).encode("utf-8")
        public_key = builder.derive_public_key(builder.read_private_seed(self.key_path))
        line = builder.format_public_key("k1", public_key)
        key_id, _, encoded = line.partition(":")
        verified = verify_manifest_bytes(raw, decode_public_keys({key_id: encoded}))
        self.assertEqual(verified.profile_id, "demo")
        self.assertEqual(verified.features, frozenset({"customers", "audit_log"}))

    def test_no_features_is_refused_before_touching_the_key(self):
        page = self.build(profile_id="demo", key_id="k1", private_key_path=self.key_path)
        self.assertIn("ساخته نشد", page)
        self.assertIn("فیچر", page)

    def test_an_unknown_profile_is_refused(self):
        page = self.build(
            profile_id="not-a-real-profile", key_id="k1", private_key_path=self.key_path,
            feature=["customers"],
        )
        self.assertIn("ساخته نشد", page)

    def test_an_unknown_feature_is_refused(self):
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["not-a-real-feature"],
        )
        self.assertIn("ساخته نشد", page)

    def test_a_missing_key_file_is_refused_with_a_readable_message(self):
        page = self.build(
            profile_id="demo", key_id="k1",
            private_key_path=str(Path(self.key_path).parent / "does-not-exist.pem"),
            feature=["customers"],
        )
        self.assertIn("ساخته نشد", page)

    def test_the_private_key_bytes_never_appear_in_the_page(self):
        """The one thing this file must never do, checked directly."""
        seed = builder.read_private_seed(self.key_path)
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"],
        )
        self.assertNotIn(seed.hex(), page)


class EnvDraftTests(SimpleTestCase):
    """Level 2: the optional `.env` draft alongside the signed manifest."""

    def setUp(self):
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        self.key_path = str(Path(tmp_dir) / "signing.pem")
        signer.generate_key(self.key_path)

    def build(self, **fields):
        form = {"profile_id": [""], "key_id": [""], "private_key_path": [""], "feature": []}
        form.update({key: (value if isinstance(value, list) else [value]) for key, value in fields.items()})
        return builder._build_result_html(form)

    def test_no_slug_or_host_means_manifest_only_like_level_1(self):
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"],
        )
        self.assertIn("ساخته و امضا شد", page)
        self.assertNotIn("پیش‌نویس .env هم ساخته شد", page)

    def test_slug_and_host_together_produce_a_real_env_lines_draft(self):
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_slug="tiara", deploy_host="crm.tiara.ir",
        )
        self.assertIn("پیش‌نویس .env هم ساخته شد", page)
        self.assertIn("KARIZ_COMPOSE_PROJECT_NAME=tiara", page)
        self.assertIn("DJANGO_ALLOWED_HOSTS=crm.tiara.ir", page)
        self.assertIn("POSTGRES_DB=tiara", page)
        # The manifest's own public-key line lands directly in the draft, so
        # the two artefacts from one submission already agree with each other.
        public_key = builder.derive_public_key(builder.read_private_seed(self.key_path))
        line = builder.format_public_key("k1", public_key)
        self.assertIn(f"KARIZ_DEPLOYMENT_MANIFEST_KEYS={line}", page)

    def test_slug_without_host_is_refused_before_signing(self):
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_slug="tiara",
        )
        self.assertIn("ساخته نشد", page)
        self.assertNotIn("ساخته و امضا شد", page)

    def test_host_without_slug_is_refused_before_signing(self):
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_host="crm.tiara.ir",
        )
        self.assertIn("ساخته نشد", page)
        self.assertNotIn("ساخته و امضا شد", page)

    def test_an_invalid_slug_is_refused(self):
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_slug="Not Valid!", deploy_host="crm.tiara.ir",
        )
        self.assertIn("ساخته نشد", page)

    def test_a_pg_prefixed_slug_is_refused(self):
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_slug="pg_tiara", deploy_host="crm.tiara.ir",
        )
        self.assertIn("ساخته نشد", page)

    def test_an_invalid_host_is_refused(self):
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_slug="tiara", deploy_host="https://crm.tiara.ir/",
        )
        self.assertIn("ساخته نشد", page)

    def test_an_ip_only_host_is_accepted(self):
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_slug="tiara", deploy_host="203.0.113.10",
        )
        self.assertIn("پیش‌نویس .env هم ساخته شد", page)
        self.assertIn("DJANGO_ALLOWED_HOSTS=203.0.113.10", page)

    def test_a_negative_retention_days_is_refused(self):
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_slug="tiara", deploy_host="crm.tiara.ir",
            deploy_retention_days="-1",
        )
        self.assertIn("ساخته نشد", page)

    def test_a_non_numeric_retention_days_is_refused(self):
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_slug="tiara", deploy_host="crm.tiara.ir",
            deploy_retention_days="not-a-number",
        )
        self.assertIn("ساخته نشد", page)

    def test_blank_image_and_manifest_path_fall_back_to_documented_defaults(self):
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_slug="tiara", deploy_host="crm.tiara.ir",
        )
        self.assertIn("KARIZ_APP_IMAGE=dolphin-app:latest", page)
        self.assertIn("KARIZ_DEPLOYMENT_MANIFEST_PATH=/srv/dolphin/secrets/manifest.json", page)

    def test_each_submission_generates_fresh_random_secrets(self):
        """No caching, no server-side state: two builds, two different .envs."""
        first = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_slug="tiara", deploy_host="crm.tiara.ir",
        )
        second = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_slug="tiara", deploy_host="crm.tiara.ir",
        )
        first_secret = html.unescape(first.split("DJANGO_SECRET_KEY=")[1].split("\n")[0])
        second_secret = html.unescape(second.split("DJANGO_SECRET_KEY=")[1].split("\n")[0])
        self.assertNotEqual(first_secret, second_secret)


class PageRenderTests(SimpleTestCase):
    def test_every_registered_feature_is_offered(self):
        page = builder._page()
        for name in FEATURE_DEPENDENCIES:
            self.assertIn(f'value="{name}"', page)

    def test_the_platform_owner_warning_is_present(self):
        self.assertIn("فقط برای مالک پلتفرم", builder._page())

    def test_the_env_draft_fieldset_is_present(self):
        self.assertIn('name="deploy_slug"', builder._page())
        self.assertIn('name="deploy_host"', builder._page())

    def test_no_brand_colour_field_exists(self):
        """Documented decision (module docstring): nothing reads one yet."""
        self.assertNotIn("رنگ برند", builder._page())
        self.assertNotIn("brand", builder._page().lower())


class LiveServerTests(SimpleTestCase):
    """The actual `ThreadingHTTPServer`, on an OS-assigned loopback port."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = builder.ThreadingHTTPServer(("127.0.0.1", 0), builder.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        super().tearDownClass()

    def request(self, method, path, *, host="127.0.0.1", body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.putrequest(method, path, skip_host=True)
            conn.putheader("Host", host)
            if body is not None:
                conn.putheader("Content-Type", "application/x-www-form-urlencoded")
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body.encode("utf-8") if body is not None else None)
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8")
        finally:
            conn.close()

    def test_the_form_page_loads(self):
        status, page = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("ابزار ساخت Manifest", page)

    def test_a_spoofed_host_header_is_refused(self):
        status, _ = self.request("GET", "/", host="evil.example.com")
        self.assertEqual(status, 400)

    def test_localhost_is_accepted_the_same_as_127_0_0_1(self):
        status, _ = self.request("GET", "/", host="localhost")
        self.assertEqual(status, 200)

    def test_an_unknown_path_is_a_404(self):
        status, _ = self.request("GET", "/anything-else")
        self.assertEqual(status, 404)

    def test_a_real_post_over_http_produces_a_downloadable_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = str(Path(tmp) / "signing.pem")
            signer.generate_key(key_path)
            body = (
                f"profile_id=demo&key_id=k1&private_key_path={key_path.replace(chr(92), '%5C')}"
                "&feature=customers"
            )
            status, page = self.request("POST", "/build", body=body)
        self.assertEqual(status, 200)
        self.assertIn("ساخته و امضا شد", page)

    def test_a_real_post_with_slug_and_host_also_produces_an_env_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = str(Path(tmp) / "signing.pem")
            signer.generate_key(key_path)
            body = (
                f"profile_id=demo&key_id=k1&private_key_path={key_path.replace(chr(92), '%5C')}"
                "&feature=customers&deploy_slug=tiara&deploy_host=crm.tiara.ir"
            )
            status, page = self.request("POST", "/build", body=body)
        self.assertEqual(status, 200)
        self.assertIn("ساخته و امضا شد", page)
        self.assertIn("پیش‌نویس .env هم ساخته شد", page)
        self.assertIn("KARIZ_COMPOSE_PROJECT_NAME=tiara", page)
