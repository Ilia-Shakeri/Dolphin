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

import base64
import html
import http.client
import importlib.util
import inspect
import io
import json
import shutil
import sys
import tempfile
import threading
import types
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from common.deployment.manifest import decode_public_keys, verify_manifest_bytes
from common.deployment.registry import FEATURE_DEPENDENCIES
from scripts import deployment_records

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


class ConsoleStoreIsolationMixin:
    """Any test that submits `deploy_slug`+`deploy_host` now also registers a
    console record (`scripts/deployment_records.py`) as a side effect — so
    every such test must point the store at a throwaway temp directory
    first, or it would write into this checkout's real
    `scripts/.dolphin-console/` on every run.
    """

    def setUp(self):
        super().setUp()
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        self._real_store_path = deployment_records.DEFAULT_STORE_PATH
        deployment_records.DEFAULT_STORE_PATH = Path(tmp_dir) / "deployments.json"
        self.addCleanup(self._restore_store_path)

    def _restore_store_path(self):
        deployment_records.DEFAULT_STORE_PATH = self._real_store_path


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

    def test_an_unfamiliar_but_well_formed_profile_now_signs_not_refuses(self):
        """2026-09-05 design change: a profile id this release has never
        seen (well-formed, not one of the three in `PROFILES`) is exactly
        how a real new customer is onboarded with no code change — see the
        comment above `PROFILES` in `common/deployment/registry.py`. Until
        this date this exact input was refused."""
        page = self.build(
            profile_id="a-brand-new-customer", key_id="k1", private_key_path=self.key_path,
            feature=["customers"],
        )
        self.assertIn("ساخته و امضا شد", page)

    def test_a_malformed_profile_is_still_refused(self):
        page = self.build(
            profile_id="Not A Valid Shape!", key_id="k1", private_key_path=self.key_path,
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


class EnvDraftTests(ConsoleStoreIsolationMixin, SimpleTestCase):
    """Level 2: the optional `.env` draft alongside the signed manifest."""

    def setUp(self):
        super().setUp()
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
        self.assertIn("DOLPHIN_COMPOSE_PROJECT_NAME=tiara", page)
        self.assertIn("DJANGO_ALLOWED_HOSTS=crm.tiara.ir", page)
        self.assertIn("POSTGRES_DB=tiara", page)
        # The manifest's own public-key line lands directly in the draft, so
        # the two artefacts from one submission already agree with each other.
        public_key = builder.derive_public_key(builder.read_private_seed(self.key_path))
        line = builder.format_public_key("k1", public_key)
        self.assertIn(f"DOLPHIN_DEPLOYMENT_MANIFEST_KEYS={line}", page)

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
        self.assertIn("DOLPHIN_APP_IMAGE=dolphin-app:latest", page)
        self.assertIn("DOLPHIN_DEPLOYMENT_MANIFEST_PATH=/srv/dolphin/secrets/manifest.json", page)

    def test_a_slug_and_host_submission_also_registers_a_console_record(self):
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_slug="tiara", deploy_host="crm.tiara.ir",
        )
        self.assertIn("در کنسول هم ثبت شد", page)
        self.assertIn("/console/tiara/", page)
        record = deployment_records.get("tiara")
        self.assertIsNotNone(record)
        self.assertEqual(record.host, "crm.tiara.ir")
        self.assertEqual(record.profile_id, "demo")
        self.assertEqual(record.features, ("customers",))

    def test_reusing_the_same_slug_updates_the_existing_record_not_a_duplicate(self):
        self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_slug="tiara", deploy_host="crm.tiara.ir",
        )
        self.build(
            profile_id="client-1", key_id="k1", private_key_path=self.key_path,
            feature=["payments"], deploy_slug="tiara", deploy_host="crm.tiara.ir",
        )
        self.assertEqual(len(deployment_records.load_all()), 1)
        record = deployment_records.get("tiara")
        self.assertEqual(record.profile_id, "client-1")

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

    def test_the_preview_button_skips_html5_validation_of_the_key_fields(self):
        """A live-browser click on «پیش‌نمایش زنده» once did nothing at all:
        `key_id`/`private_key_path` carry `required`, and a browser enforces
        every `required` field in a `<form>` before submitting it through
        *any* button inside it — including one with its own `formaction` —
        unless that button also opts out with `formnovalidate`. No amount of
        server-side testing sees this; only an actual browser blocking the
        submit does. Kept here as the cheapest regression guard available
        outside a real browser.
        """
        page = builder._page()
        self.assertIn('formaction="/preview/start" formnovalidate', page)

    def test_no_brand_colour_field_exists(self):
        """Documented decision (module docstring): nothing reads one yet.

        `custom_branding` (2026-09-03, `common.branding` — the customer's own
        name/logo, toggled per deployment exactly like every other feature)
        legitimately contains "brand" now, so the blanket substring check
        this test used before that feature existed would reject its own
        checkbox — `feature="custom_branding"` is named for what it is.
        """
        self.assertNotIn("رنگ برند", builder._page())
        self.assertNotIn("brand-colour", builder._page().lower())
        self.assertNotIn("brand_color", builder._page().lower())

    def test_select_all_and_select_none_buttons_are_present(self):
        page = builder._page()
        self.assertIn('data-feature-select="all"', page)
        self.assertIn('data-feature-select="none"', page)

    def test_the_home_link_is_present(self):
        self.assertIn('href="/start/"', builder._page())


class StyleTests(SimpleTestCase):
    """The 2026-09-05 visual pass (product-owner request): a real embedded
    typeface instead of the system-default Tahoma this tool started with,
    and consistent spacing tokens instead of ad-hoc pixel values repeated
    per rule.
    """

    def test_the_product_font_is_embedded_not_left_to_the_system_default(self):
        self.assertIn("@font-face", builder._STYLE)
        self.assertIn("IRANSansWeb", builder._STYLE)
        self.assertNotIn("Tahoma, sans-serif;", builder._STYLE.split("font-family:")[1][:40])

    def test_the_embedded_font_data_actually_loaded_from_the_repository_asset(self):
        """Distinguishes a real embed from a silently-empty one: the same
        `assets/fonts/IRANSansWeb.woff2` the served product itself loads
        (`assets/css/style.bundle.rtl.css`) is what this reads, so a
        near-tiny base64 string here would mean the read quietly failed
        rather than that the font is genuinely small.
        """
        self.assertGreater(len(builder._IRANSANS_WOFF2_BASE64), 10_000)

    def test_spacing_uses_shared_tokens_not_repeated_magic_numbers(self):
        self.assertIn("--gap:", builder._STYLE)
        self.assertIn("var(--gap)", builder._STYLE)


class LandingPageTests(SimpleTestCase):
    """`/start/` — what actually opens when the tool launches (2026-09-05
    product-owner request: "two options, not straight into the form").
    """

    def test_it_offers_exactly_two_options(self):
        page = builder._landing_page()
        self.assertEqual(page.count('class="option-card"'), 2)

    def test_one_option_leads_to_the_quick_form(self):
        page = builder._landing_page()
        self.assertIn('href="/"', page)
        self.assertIn("ساخت جدید", page)

    def test_the_other_leads_to_the_console(self):
        page = builder._landing_page()
        self.assertIn('href="/console/"', page)
        self.assertIn("مدیریت همهٔ استقرارها", page)

    def test_main_opens_the_landing_page_not_the_form_directly(self):
        """The regression this whole page exists to prevent: `main()` used
        to point `webbrowser.open`/the desktop window at `/` — the form —
        directly. If either ever silently reverts to that, this page still
        renders fine but nothing sends anyone to it.
        """
        with patch.object(builder, "webbrowser") as mock_webbrowser, \
             patch.object(builder, "ThreadingHTTPServer") as mock_server_cls:
            mock_server = MagicMock()
            mock_server.server_forever = MagicMock()
            mock_server_cls.return_value = mock_server
            mock_server.serve_forever.side_effect = KeyboardInterrupt
            builder.main(["--port", "18799"])
        opened_url = mock_webbrowser.open.call_args.args[0]
        self.assertTrue(opened_url.endswith("/start/"), opened_url)


class ConsolePageTests(SimpleTestCase):
    """The console's page-builder functions, given records directly — no
    HTTP, no store I/O. `LiveServerTests` below exercises the same pages
    through the real routes.
    """

    def test_the_list_page_explains_itself_when_empty(self):
        page = builder._console_list_page({})
        self.assertIn("هنوز هیچ استقراری در کنسول ثبت نشده", page)

    def test_the_list_page_shows_every_recorded_deployment(self):
        record = deployment_records.DeploymentRecord(
            slug="tiara", display_name="Tiara CRM", host="crm.tiara.ir",
            profile_id="demo", features=("customers",), app_image="dolphin-app:v1",
            manifest_issued_at="2026-01-01T00:00:00Z",
        )
        page = builder._console_list_page({"tiara": record})
        self.assertIn("Tiara CRM", page)
        self.assertIn("/console/tiara/", page)
        self.assertIn("crm.tiara.ir", page)

    def test_the_list_page_never_claims_a_live_connection(self):
        """The console is a local archive, not a health dashboard — the page
        itself must keep saying so, not just this module's docstring.
        """
        page = builder._console_list_page({})
        self.assertIn("بایگانی محلی", page)

    def test_the_detail_page_shows_the_records_own_state(self):
        record = deployment_records.DeploymentRecord(
            slug="tiara", display_name="Tiara CRM", host="crm.tiara.ir",
            profile_id="demo", features=("customers", "audit_log"),
            notes="یادداشت تست",
        )
        page = builder._console_detail_page(record)
        self.assertIn("Tiara CRM", page)
        self.assertIn('value="customers" checked', page)
        self.assertIn('value="audit_log" checked', page)
        self.assertIn("یادداشت تست", page)
        # The private key is never stored, so its field must render blank
        # even though the key id is repopulated.
        self.assertIn('name="private_key_path" value=""', page)

    def test_the_detail_pages_reissue_form_also_offers_select_all_and_none(self):
        record = deployment_records.DeploymentRecord(
            slug="tiara", display_name="Tiara CRM", host="crm.tiara.ir",
            profile_id="demo", features=("customers",),
        )
        page = builder._console_detail_page(record)
        self.assertIn('data-feature-select="all"', page)
        self.assertIn('data-feature-select="none"', page)

    def test_every_console_page_links_back_to_the_landing_page(self):
        empty_list = builder._console_list_page({})
        record = deployment_records.DeploymentRecord(slug="tiara", profile_id="demo", features=("customers",))
        detail = builder._console_detail_page(record)
        not_found = builder._not_found_console_page("ghost")
        for page in (empty_list, detail, not_found):
            self.assertIn('href="/start/"', page)

    def test_the_not_found_page_names_the_missing_slug(self):
        page = builder._not_found_console_page("ghost")
        self.assertIn("ghost", page)


class ImportManifestTests(ConsoleStoreIsolationMixin, SimpleTestCase):
    """Bringing an already-signed manifest into the local console archive
    with no private key and no re-signing (2026-09-05 product-owner
    request: TIARA's real manifest.json, signed by hand with
    `sign_deployment_manifest.py` two days before the console existed, has
    never appeared at `/console/` for exactly this reason).
    """

    def setUp(self):
        super().setUp()
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        self.tmp_dir = tmp_dir
        key_path = str(Path(tmp_dir) / "signing.pem")
        signer.generate_key(key_path)
        self.seed = signer.read_private_seed(key_path)

    def write_manifest(self, *, key_id="tiara-2026", profile_id="client-1",
                        features=("customers", "leads"), issued_at="2026-09-01T09:51:39Z"):
        manifest_bytes = signer.build_manifest(
            seed=self.seed, key_id=key_id, profile_id=profile_id,
            features=list(features), issued_at=issued_at,
        )
        path = Path(self.tmp_dir) / "to_import.json"
        path.write_bytes(manifest_bytes)
        return str(path)

    def build(self, **fields):
        form = {"import_slug": [""], "import_manifest_path": [""],
                "import_display_name": [""], "import_host": [""]}
        form.update({key: (value if isinstance(value, list) else [value]) for key, value in fields.items()})
        return builder._build_import_result_html(form)

    def test_importing_needs_no_private_key_at_all(self):
        """The defining constraint: nothing about the signing key — not its
        path, not its bytes — appears anywhere in the import form or path."""
        source = inspect.getsource(builder._build_import_result_html)
        source += inspect.getsource(builder._decode_manifest_payload)
        self.assertNotIn("private_key", source)
        self.assertNotIn("read_private_seed", source)

    def test_a_well_formed_manifest_is_imported_as_an_editable_record(self):
        manifest_path = self.write_manifest(
            key_id="tiara-2026", profile_id="client-1",
            features=("customers", "leads", "sales"),
            issued_at="2026-09-01T09:51:39Z",
        )
        page = self.build(import_slug="tiara", import_manifest_path=manifest_path,
                           import_display_name="TIARA")
        self.assertIn("به بایگانی کنسول اضافه شد", page)
        record = deployment_records.get("tiara")
        self.assertIsNotNone(record)
        self.assertEqual(record.profile_id, "client-1")
        self.assertEqual(set(record.features), {"customers", "leads", "sales"})
        self.assertEqual(record.key_id, "tiara-2026")
        self.assertEqual(record.manifest_issued_at, "2026-09-01T09:51:39Z")
        self.assertEqual(record.display_name, "TIARA")

    def test_the_imported_record_is_reachable_and_pre_ticked_on_its_own_console_page(self):
        manifest_path = self.write_manifest(features=("customers", "leads", "after_sales"))
        self.build(import_slug="tiara", import_manifest_path=manifest_path)
        record = deployment_records.get("tiara")
        detail_page = builder._console_detail_page(record)
        for feature in ("customers", "leads", "after_sales"):
            self.assertIn(f'value="{feature}" checked', detail_page)
        self.assertIn('value="client-1"', detail_page)

    def test_reissuing_from_an_imported_record_only_adds_the_requested_feature(self):
        """The other half of the concrete verification this feature was
        built against: import, then sign fresh with one feature added, and
        the decoded payload must be exactly the original set plus that one
        — nothing dropped, nothing else added."""
        original_features = ("after_sales", "audit_log", "customer_ledger", "customers",
                              "inbound_sms", "inventory", "invoices", "leads", "orders",
                              "payments", "products", "reports", "sales", "sales_documents")
        manifest_path = self.write_manifest(features=original_features)
        self.build(import_slug="tiara", import_manifest_path=manifest_path)
        record = deployment_records.get("tiara")

        new_key_path = str(Path(self.tmp_dir) / "reissue-signing.pem")
        signer.generate_key(new_key_path)
        reissue_form = {
            "profile_id": [record.profile_id],
            "key_id": [record.key_id],
            "private_key_path": [new_key_path],
            "feature": list(record.features) + ["attachments"],
            "deploy_image": [""],
            "regenerate_env": [""],
        }
        reissue_html = builder._build_reissue_result_html(record, reissue_form)
        envelope = json.loads(html.unescape(reissue_html.split("<pre>")[-1].split("</pre>")[0]))
        payload = json.loads(base64.b64decode(envelope["payload"]))
        self.assertEqual(set(payload["features"]), set(original_features) | {"attachments"})
        self.assertEqual(payload["profile_id"], "client-1")

    def test_the_real_repo_root_manifest_is_importable_and_left_untouched(self):
        """The exact concrete scenario reported: TIARA's real manifest.json
        at the repository root, signed before the console existed."""
        repo_manifest = REPOSITORY_ROOT / "manifest.json"
        if not repo_manifest.exists():
            self.skipTest("no repo-root manifest.json in this checkout")
        original_bytes = repo_manifest.read_bytes()
        page = self.build(import_slug="tiara", import_manifest_path=str(repo_manifest))
        self.assertIn("به بایگانی کنسول اضافه شد", page)
        record = deployment_records.get("tiara")
        self.assertEqual(record.profile_id, "client-1")
        self.assertEqual(len(record.features), 14)
        self.assertEqual(repo_manifest.read_bytes(), original_bytes)

    def test_a_missing_slug_is_refused(self):
        manifest_path = self.write_manifest()
        page = self.build(import_manifest_path=manifest_path)
        self.assertIn("درون‌ریزی نشد", page)
        self.assertIsNone(deployment_records.get("tiara"))

    def test_a_missing_file_path_is_refused(self):
        page = self.build(import_slug="tiara")
        self.assertIn("درون‌ریزی نشد", page)

    def test_a_nonexistent_file_produces_a_readable_error_not_a_crash(self):
        page = self.build(import_slug="tiara", import_manifest_path=str(Path(self.tmp_dir) / "ghost.json"))
        self.assertIn("درون‌ریزی نشد", page)

    def test_malformed_json_produces_a_readable_error_not_a_crash(self):
        path = Path(self.tmp_dir) / "bad.json"
        path.write_text("{not valid json", encoding="utf-8")
        page = self.build(import_slug="tiara", import_manifest_path=str(path))
        self.assertIn("درون‌ریزی نشد", page)

    def test_a_malformed_profile_id_inside_the_payload_is_refused(self):
        """Reading is not the same as trusting blindly: even a
        structurally-fine envelope with a payload that itself violates the
        same shape rule `common/deployment/manifest.py` enforces is refused,
        not imported as-is."""
        payload = json.dumps(
            {"manifest_version": 1, "profile_id": "Not Valid!", "issued_at": "2026-01-01T00:00:00Z",
             "features": ["customers"]},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        _, signature = signer.sign(self.seed, payload)
        envelope = {
            "manifest_version": 1, "algorithm": "ed25519", "key_id": "k1",
            "payload": base64.b64encode(payload).decode("ascii"),
            "signature": base64.b64encode(signature).decode("ascii"),
        }
        path = Path(self.tmp_dir) / "bad_profile.json"
        path.write_text(json.dumps(envelope), encoding="utf-8")
        page = self.build(import_slug="tiara", import_manifest_path=str(path))
        self.assertIn("درون‌ریزی نشد", page)
        self.assertIsNone(deployment_records.get("tiara"))

    def test_importing_twice_updates_the_same_record_not_a_duplicate(self):
        manifest_path = self.write_manifest(features=("customers",))
        self.build(import_slug="tiara", import_manifest_path=manifest_path)
        first = deployment_records.get("tiara")

        manifest_path_2 = self.write_manifest(features=("customers", "leads"), issued_at="2026-09-02T00:00:00Z")
        self.build(import_slug="tiara", import_manifest_path=manifest_path_2)
        second = deployment_records.get("tiara")

        self.assertEqual(len(deployment_records.load_all()), 1)
        self.assertEqual(set(second.features), {"customers", "leads"})
        # `created_at` is preserved across the update, same as a reissue.
        self.assertEqual(first.created_at, second.created_at)


class LiveServerTests(ConsoleStoreIsolationMixin, SimpleTestCase):
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

    def test_the_landing_page_loads_over_a_real_request_too(self):
        status, page = self.request("GET", "/start/")
        self.assertEqual(status, 200)
        self.assertEqual(page.count('class="option-card"'), 2)

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
        self.assertIn("DOLPHIN_COMPOSE_PROJECT_NAME=tiara", page)

    def _register(self, *, slug="tiara", host="crm.tiara.ir", key_path):
        body = (
            f"profile_id=demo&key_id=k1&private_key_path={key_path.replace(chr(92), '%5C')}"
            f"&feature=customers&deploy_slug={slug}&deploy_host={host}"
        )
        return self.request("POST", "/build", body=body)

    def test_the_console_list_is_empty_until_something_is_registered(self):
        status, page = self.request("GET", "/console/")
        self.assertEqual(status, 200)
        self.assertIn("هنوز هیچ استقراری در کنسول ثبت نشده", page)

    def test_a_registered_deployment_appears_in_the_console_and_its_own_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = str(Path(tmp) / "signing.pem")
            signer.generate_key(key_path)
            self._register(key_path=key_path)

            list_status, list_page = self.request("GET", "/console/")
            self.assertEqual(list_status, 200)
            self.assertIn("/console/tiara/", list_page)

            detail_status, detail_page = self.request("GET", "/console/tiara/")
        self.assertEqual(detail_status, 200)
        self.assertIn("tiara", detail_page)
        self.assertIn('value="customers" checked', detail_page)

    def test_an_unregistered_slug_detail_page_is_a_clear_404_not_a_crash(self):
        status, page = self.request("GET", "/console/does-not-exist/")
        self.assertEqual(status, 404)
        self.assertIn("پیدا نشد", page)

    def test_reissue_signs_a_fresh_manifest_and_updates_the_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = str(Path(tmp) / "signing.pem")
            signer.generate_key(key_path)
            self._register(key_path=key_path)

            body = (
                f"profile_id=demo&key_id=k1&private_key_path={key_path.replace(chr(92), '%5C')}"
                "&feature=customers&feature=audit_log"
            )
            status, page = self.request("POST", "/console/tiara/reissue", body=body)
        self.assertEqual(status, 200)
        self.assertIn("Manifest تازه ساخته و امضا شد", page)
        record = deployment_records.get("tiara")
        self.assertEqual(record.features, ("audit_log", "customers"))

    def test_reissue_only_regenerates_env_when_asked_to(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = str(Path(tmp) / "signing.pem")
            signer.generate_key(key_path)
            self._register(key_path=key_path)

            without = (
                f"profile_id=demo&key_id=k1&private_key_path={key_path.replace(chr(92), '%5C')}"
                "&feature=customers"
            )
            _, page_without = self.request("POST", "/console/tiara/reissue", body=without)
            self.assertNotIn("پیش‌نویس .env تازه هم ساخته شد", page_without)

            with_env = without + "&regenerate_env=1"
            status, page_with = self.request("POST", "/console/tiara/reissue", body=with_env)
        self.assertEqual(status, 200)
        self.assertIn("پیش‌نویس .env تازه هم ساخته شد", page_with)
        self.assertIn("DOLPHIN_COMPOSE_PROJECT_NAME=tiara", page_with)

    def test_reissue_of_an_unregistered_slug_is_a_404(self):
        status, _ = self.request("POST", "/console/does-not-exist/reissue", body="profile_id=demo")
        self.assertEqual(status, 404)

    def test_update_changes_only_bookkeeping_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = str(Path(tmp) / "signing.pem")
            signer.generate_key(key_path)
            self._register(key_path=key_path)

            status, page = self.request(
                "POST", "/console/tiara/update",
                body="display_name=Tiara+CRM&notes=%D9%85%D8%B4%D8%AA%D8%B1%DB%8C+%D9%85%D9%87%D9%85",
            )
        self.assertEqual(status, 200)
        self.assertIn("اطلاعات ذخیره شد", page)
        record = deployment_records.get("tiara")
        self.assertEqual(record.display_name, "Tiara CRM")
        self.assertEqual(record.host, "crm.tiara.ir")  # untouched by this action
        self.assertEqual(record.features, ("customers",))  # untouched by this action

    def test_delete_removes_the_record_and_redirects_to_the_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_path = str(Path(tmp) / "signing.pem")
            signer.generate_key(key_path)
            self._register(key_path=key_path)

            status, _ = self.request("POST", "/console/tiara/delete", body="")
        self.assertEqual(status, 303)
        self.assertIsNone(deployment_records.get("tiara"))

    def test_deleting_an_unregistered_slug_is_a_404_not_a_crash(self):
        status, _ = self.request("POST", "/console/does-not-exist/delete", body="")
        self.assertEqual(status, 404)


class DesktopModeTests(SimpleTestCase):
    """`--desktop` (the desktop mini-app window, `_run_desktop_window`).

    Neither test here actually opens a window: `pywebview` is genuinely not
    installed in this environment (confirmed by `test_..._is_not_installed_
    here`, which is itself part of the contract — this repository has no
    dependency on it, see `scripts/requirements-console.txt`), so the two
    behaviours worth proving are the missing-dependency message and, with a
    fake `webview` module injected the same way a real install would provide
    one, that the real function is actually called with the real URL.
    """

    def test_pywebview_is_not_installed_in_this_environment(self):
        """The premise every other test in this class depends on: if this
        ever starts failing because pywebview became an actual project
        dependency, the two tests below need to be revisited, not silently
        left half-covering a package that is now always present.
        """
        self.assertNotIn("webview", sys.modules)
        with self.assertRaises(ImportError):
            __import__("webview")

    def test_without_pywebview_it_explains_itself_and_returns_a_failure_code(self):
        with patch.dict(sys.modules, {"webview": None}):
            exit_code = builder._run_desktop_window("http://127.0.0.1:8799/")
        self.assertEqual(exit_code, 1)

    def test_with_pywebview_available_it_opens_the_real_url(self):
        fake_webview = types.SimpleNamespace(create_window=MagicMock(), start=MagicMock())
        with patch.dict(sys.modules, {"webview": fake_webview}):
            exit_code = builder._run_desktop_window("http://127.0.0.1:8799/")
        self.assertEqual(exit_code, 0)
        fake_webview.create_window.assert_called_once()
        self.assertEqual(fake_webview.create_window.call_args.args[1], "http://127.0.0.1:8799/")
        fake_webview.start.assert_called_once()

    def test_main_wires_the_flag_all_the_way_through(self):
        """A real `main(["--desktop", ...])` call, not just the parser: this
        is what actually proves the flag reaches `_run_desktop_window` and
        that the server it started in the background is shut down again
        afterwards rather than left running on the port for the next test.
        """
        exit_code = builder.main(["--desktop", "--port", "0"])
        self.assertEqual(exit_code, 1)  # pywebview genuinely absent here


class PreviewButtonTests(SimpleTestCase):
    """`_build_preview_result_html` and `_preview_status_html` —
    `scripts.preview_runner` itself is mocked throughout, so these run fast
    and prove only what belongs to `manifest_builder.py`: form validation,
    the "a typed name implies custom_branding" rule, and rendering. The real
    subprocess mechanics have their own dedicated, much slower suite,
    `common/tests/test_preview_runner.py`.
    """

    def build(self, **fields):
        form = {"profile_id": [""], "feature": []}
        form.update({key: (value if isinstance(value, list) else [value]) for key, value in fields.items()})
        return builder._build_preview_result_html(form)

    def test_an_unfamiliar_but_well_formed_profile_previews_not_refuses(self):
        """Same 2026-09-05 change as ResultHtmlTests — previewing a
        brand-new customer's own not-yet-real profile id is exactly the
        case this button exists for."""
        with patch.object(builder.preview_runner, "start") as start:
            self.build(profile_id="a-brand-new-customer", feature=["customers"])
        start.assert_called_once()

    def test_a_malformed_profile_is_refused_before_calling_preview_runner(self):
        with patch.object(builder.preview_runner, "start") as start:
            page = self.build(profile_id="Not A Valid Shape!", feature=["customers"])
        start.assert_not_called()
        self.assertIn("پیش‌نمایش ساخته نشد", page)

    def test_no_features_is_refused_before_calling_preview_runner(self):
        with patch.object(builder.preview_runner, "start") as start:
            page = self.build(profile_id="demo")
        start.assert_not_called()
        self.assertIn("پیش‌نمایش ساخته نشد", page)

    def test_a_typed_name_adds_custom_branding_to_the_requested_features(self):
        with patch.object(builder.preview_runner, "start") as start:
            self.build(profile_id="demo", feature=["customers"], preview_display_name="تیارا")
        start.assert_called_once()
        self.assertIn("custom_branding", start.call_args.kwargs["features"])
        self.assertEqual(start.call_args.kwargs["display_name"], "تیارا")

    def test_no_name_does_not_add_custom_branding_on_its_own(self):
        with patch.object(builder.preview_runner, "start") as start:
            self.build(profile_id="demo", feature=["customers"])
        self.assertNotIn("custom_branding", start.call_args.kwargs["features"])

    def test_a_missing_dependency_is_still_completed_for_the_preview(self):
        with patch.object(builder.preview_runner, "start") as start:
            self.build(profile_id="demo", feature=["payments"])
        features = start.call_args.kwargs["features"]
        self.assertIn("invoices", features)
        self.assertIn("customers", features)

    def test_a_preview_error_becomes_a_readable_message_not_a_crash(self):
        with patch.object(builder.preview_runner, "start", side_effect=builder.preview_runner.PreviewError("خطا")):
            page = self.build(profile_id="demo", feature=["customers"])
        self.assertIn("پیش‌نمایش بالا نیامد", page)
        self.assertIn("خطا", page)

    def test_an_unexpected_exception_from_preview_runner_also_becomes_a_message(self):
        with patch.object(builder.preview_runner, "start", side_effect=OSError("disk full")):
            page = self.build(profile_id="demo", feature=["customers"])
        self.assertIn("پیش‌نمایش بالا نیامد", page)

    def test_success_returns_no_extra_block_the_banner_already_covers_it(self):
        with patch.object(builder.preview_runner, "start", return_value={"port": 8918}):
            page = self.build(profile_id="demo", feature=["customers"])
        self.assertEqual(page, "")

    def test_status_banner_is_empty_when_nothing_is_running(self):
        with patch.object(builder.preview_runner, "status", return_value=None):
            self.assertEqual(builder._preview_status_html(), "")

    def test_status_banner_shows_the_running_previews_own_details(self):
        state = {
            "port": 8918, "username": "preview_admin", "password": "s3cr3t",
            "display_name": "تیارا", "profile_id": "demo", "features": ("customers", "leads"),
            "started_at": "2026-01-01T00:00:00Z",
        }
        with patch.object(builder.preview_runner, "status", return_value=state):
            banner = builder._preview_status_html()
        self.assertIn("تیارا", banner)
        self.assertIn("8918", banner)
        self.assertIn("s3cr3t", banner)
        self.assertIn("/preview/stop", banner)

    def test_the_username_and_password_each_get_their_own_copy_button(self):
        """2026-09-05 product-owner request: these are the only two values on
        any page this tool renders that a reader would otherwise retype by
        hand off the screen character-for-character."""
        state = {
            "port": 8918, "username": "preview_admin", "password": "s3cr3t",
            "display_name": "", "profile_id": "demo", "features": ("customers",),
            "started_at": "2026-01-01T00:00:00Z",
        }
        with patch.object(builder.preview_runner, "status", return_value=state):
            banner = builder._preview_status_html()
        self.assertIn('data-copy="preview_admin"', banner)
        self.assertIn('data-copy="s3cr3t"', banner)
        self.assertEqual(banner.count("data-copy="), 2)


class PreviewRouteTests(SimpleTestCase):
    """The HTTP routes, over a real `ThreadingHTTPServer` — same live-server
    pattern as `LiveServerTests` below — but with `preview_runner` mocked so
    no real subprocess is ever involved here.
    """

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

    def request(self, method, path, *, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.putrequest(method, path, skip_host=True)
            conn.putheader("Host", "127.0.0.1")
            if body is not None:
                conn.putheader("Content-Type", "application/x-www-form-urlencoded")
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body.encode("utf-8") if body is not None else None)
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8")
        finally:
            conn.close()

    def test_preview_start_over_real_http_calls_preview_runner_and_renders_the_page(self):
        # `quote` matters here, not decoration: an un-encoded non-ASCII value
        # in a raw request body makes `len(body)` (characters) disagree with
        # its actual UTF-8 byte length, so `Content-Length` undercounts and
        # the server-side read truncates mid-character.
        from urllib.parse import quote

        with patch.object(builder.preview_runner, "start", return_value={"port": 8918}) as start:
            status, page = self.request(
                "POST", "/preview/start",
                body=f"profile_id=demo&feature=customers&preview_display_name={quote('تیارا')}",
            )
        self.assertEqual(status, 200)
        start.assert_called_once()
        self.assertIn("تیارا", page)  # the form field is repopulated

    def test_preview_start_failure_shows_the_error_and_stays_200(self):
        with patch.object(builder.preview_runner, "start", side_effect=builder.preview_runner.PreviewError("مشکل")):
            status, page = self.request("POST", "/preview/start", body="profile_id=demo&feature=customers")
        self.assertEqual(status, 200)
        self.assertIn("پیش‌نمایش بالا نیامد", page)

    def test_preview_stop_calls_preview_runner_and_redirects_home(self):
        with patch.object(builder.preview_runner, "stop") as stop:
            status, _ = self.request("POST", "/preview/stop", body="")
        self.assertEqual(status, 303)
        stop.assert_called_once()

    def test_the_home_page_shows_a_running_previews_banner(self):
        state = {
            "port": 8918, "username": "preview_admin", "password": "s3cr3t",
            "display_name": "", "profile_id": "demo", "features": ("customers",),
            "started_at": "2026-01-01T00:00:00Z",
        }
        with patch.object(builder.preview_runner, "status", return_value=state):
            status, page = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("پیش‌نمایش زنده در حال اجراست", page)


class DeploymentBundleTests(SimpleTestCase):
    """The deployment-bundle zip `_build_result_html` offers once slug+host
    are both given — no mocking needed, it is pure computation over bytes
    already in hand.
    """

    def setUp(self):
        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        self.key_path = str(Path(tmp_dir) / "signing.pem")
        signer.generate_key(self.key_path)
        self._real_store_path = deployment_records.DEFAULT_STORE_PATH
        deployment_records.DEFAULT_STORE_PATH = Path(tmp_dir) / "deployments.json"
        self.addCleanup(self._restore_store_path)

    def _restore_store_path(self):
        deployment_records.DEFAULT_STORE_PATH = self._real_store_path

    def build(self, **fields):
        form = {"profile_id": [""], "key_id": [""], "private_key_path": [""], "feature": []}
        form.update({key: (value if isinstance(value, list) else [value]) for key, value in fields.items()})
        return builder._build_result_html(form)

    def test_the_bundle_download_only_appears_once_slug_and_host_are_given(self):
        manifest_only = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path, feature=["customers"],
        )
        self.assertNotIn("بستهٔ استقرار", manifest_only)

    def test_the_bundle_zip_contains_the_manifest_env_and_deploy_steps(self):
        page = self.build(
            profile_id="demo", key_id="k1", private_key_path=self.key_path,
            feature=["customers"], deploy_slug="tiara", deploy_host="crm.tiara.ir",
        )
        self.assertIn("بستهٔ استقرار", page)
        # Three downloads on this page each have their own `const hex = "..."`
        # script (manifest, bundle, env, in that order) — anchor on the
        # bundle's own element id rather than picking the first match, which
        # would silently grab the manifest's hex instead.
        bundle_section = page.split('id="download-link-bundle"')[1]
        bundle_hex = bundle_section.split('const hex = "')[1].split('"')[0]
        archive = zipfile.ZipFile(io.BytesIO(bytes.fromhex(bundle_hex)))
        names = set(archive.namelist())
        self.assertEqual(names, {"manifest.json", "dolphin.env", "DEPLOY-STEPS.txt"})

        manifest_in_zip = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest_in_zip["key_id"], "k1")

        env_in_zip = archive.read("dolphin.env").decode("utf-8")
        self.assertIn("DOLPHIN_COMPOSE_PROJECT_NAME=tiara", env_in_zip)

        steps = archive.read("DEPLOY-STEPS.txt").decode("utf-8")
        self.assertIn("--slug tiara --host crm.tiara.ir", steps)
        self.assertIn("quickstart.sh", steps)
