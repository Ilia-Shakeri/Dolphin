"""Batch E of the 2026-09-20 UI pass: the build console and profile pictures.

**Item 12 — the console.** Its feature checklist offered bare keys
(`sales_documents`) and said nothing about what ticking one actually turns
on. It now names the panel pages each feature opens, and those names are
*derived*: `common/deployment/pages.py` walks the panel's own URL table and
reads each route's `required_feature` off the view class that serves it —
the same attribute `FeatureGatedViewMixin` enforces at request time. A page
added to the panel appears in the console without anyone remembering to add
it, which is what «با منبع واقعی فیچرها همگام باشند (نه یک لیست دستیِ
قدیمی)» asked for. The console also gained a Persian/English switch and a
`.exe` build, and the checklist became a grid that does not break a feature
away from its own page list.

**Item 13 — profile pictures.** A person can upload one; it is cropped
square and resized to 512px in the browser before it is sent, and the server
re-checks the size and sniffs the real type rather than trusting what the
client declared. Until they upload one they get one of Metronic's 52 cartoon
avatars, chosen by a stable hash of their id — so it never changes under
them and costs no column.

Browser-measured at the time: a 1200×800 PNG of 25,444 bytes went in and the
server stored a 512×512 JPEG of 4,149 bytes, served as `image/jpeg` with
`private, max-age=300` and `nosniff`; the header avatar rendered at 35×35
after a reload with no placeholder flash; a non-image was refused with the
Persian message and a 3 MiB body with a 413; deleting brought the cartoon
back and the image endpoint 404ed once the browser cache was bypassed. The
console rendered 28 feature rows in a two-column grid with each one naming
its pages, and `?lang=en` flipped the document to `lang="en" dir="ltr"` with
the chrome in English and the page titles still Persian.
"""

import pathlib
import re
import subprocess
import sys

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts import avatars
from common.deployment import pages as page_inventory
from common.deployment.registry import FEATURE_DEPENDENCIES
from common.tests.ui_overhaul_helpers import (  # noqa: E402
    CODE,
    CSS,
    ROOT,
    SCRIPT,
    TEMPLATES,
    function_body,
    markup,
    python_function,
    media_block,
    rule,
)

BASE = (TEMPLATES / "base.html").read_text(encoding="utf-8")
CONSOLE = (ROOT / "scripts" / "manifest_builder.py").read_text(encoding="utf-8")
CONSOLE_STRINGS = (ROOT / "scripts" / "console_strings.py").read_text(encoding="utf-8")
EXE_BUILDER = (ROOT / "scripts" / "build_console_exe.py").read_text(encoding="utf-8")

User = get_user_model()
PASSWORD = "Aa!23456pass"

#: A one-pixel PNG, for the tests that need real image bytes rather than a
#: plausible-looking string — the service sniffs the magic bytes, so a fake
#: would be refused for the right reason and prove nothing.
ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000100ffff03000006000557bfabd4000000"
    "0049454e44ae426082"
)


# ===========================================================================
# Item 12 — the console's page inventory
# ===========================================================================


class PageInventoryTests(SimpleTestCase):
    def test_every_routed_panel_page_has_a_title(self):
        """The one hand-written part of the inventory, pinned against the
        real route list — so a page added without a title fails here rather
        than showing up in the console as a URL slug."""
        missing = sorted(page_inventory.routed_page_names() - set(page_inventory.PAGE_TITLES))
        self.assertEqual(missing, [], f"routes with no Persian title: {missing}")

    def test_no_title_names_a_page_that_is_not_routed(self):
        """The other direction: a title left behind by a removed page would
        quietly promise something the panel no longer has."""
        stale = sorted(set(page_inventory.PAGE_TITLES) - page_inventory.routed_page_names())
        self.assertEqual(stale, [], f"titles with no route: {stale}")

    def test_the_feature_of_a_page_is_read_off_the_view_that_serves_it(self):
        """Not a table. `required_feature` is what the request-time gate
        uses, so the console and the deployment cannot disagree."""
        source = (ROOT / "common" / "deployment" / "pages.py").read_text(encoding="utf-8")
        self.assertIn('getattr(view_class, "required_feature", None)', source)

    def test_a_real_feature_maps_to_the_pages_it_really_opens(self):
        titles = page_inventory.feature_page_titles()
        self.assertIn("رهگیری پستی", titles["sales_documents"])
        self.assertIn("گزارش اسناد فروش و پست", titles["sales_documents"])
        self.assertIn("مشتریان", titles["customers"])

    def test_ungated_pages_are_reported_separately_rather_than_attributed(self):
        """The login screen and the settings page belong to no feature, and
        listing them under one would say ticking it adds them."""
        grouped = page_inventory.pages_by_feature()
        always = {title for _name, title in grouped.get(None, [])}
        self.assertIn("ورود", always)
        self.assertIn("تنظیمات", always)
        for feature, rows in grouped.items():
            if feature is None:
                continue
            with self.subTest(feature=feature):
                self.assertNotIn("ورود", {title for _name, title in rows})

    def test_every_feature_that_gates_a_page_is_a_real_feature(self):
        gated = {f for f in page_inventory.pages_by_feature() if f is not None}
        self.assertLessEqual(gated, set(FEATURE_DEPENDENCIES))


class ConsoleChecklistTests(SimpleTestCase):
    def test_the_checklist_reads_the_derived_inventory(self):
        self.assertIn("from common.deployment.pages import feature_page_titles", CONSOLE)
        self.assertIn("_feature_pages()", CONSOLE)

    def test_it_says_what_a_feature_opens_and_what_it_needs(self):
        body = python_function("_feature_checkboxes_html", CONSOLE)
        self.assertIn("feature-pages", body)
        self.assertIn("feature-needs", body)

    def test_a_feature_that_opens_no_page_says_so_rather_than_nothing(self):
        body = python_function("_feature_checkboxes_html", CONSOLE)
        self.assertIn('T(lang, "no_pages")', body)

    def test_a_missing_route_table_degrades_rather_than_crashing(self):
        """A checkout without Django installed still gets a usable console —
        keys and dependencies — and says on stderr what it lost."""
        body = python_function("_feature_pages", CONSOLE)
        self.assertIn("except (ImportError, RuntimeError)", body)
        self.assertIn("_FEATURE_PAGES = {}", body)

    def test_the_fallback_is_not_a_bare_except(self):
        """It was, during development, and it swallowed a `NameError` on an
        unimported `os` — every feature silently showed as opening no pages.
        A narrow except is what turns that into a traceback next time."""
        body = python_function("_feature_pages", CONSOLE)
        self.assertNotIn("except Exception", body)

    def test_the_checklist_is_a_grid_that_keeps_a_row_together(self):
        """Each row is three lines now, and CSS `columns` was breaking
        between a feature and its own page list."""
        self.assertIn("grid-template-columns: repeat(auto-fill", CONSOLE)
        self.assertNotIn("columns: 2; column-gap", CONSOLE)


class ConsoleLanguageTests(SimpleTestCase):
    def test_both_languages_are_offered(self):
        self.assertIn('("fa", "فارسی")', CONSOLE_STRINGS)
        self.assertIn('("en", "English")', CONSOLE_STRINGS)

    def test_an_unknown_language_falls_back_to_persian(self):
        from scripts.console_strings import T, normalize_language

        self.assertEqual(normalize_language("de"), "fa")
        self.assertEqual(normalize_language(""), "fa")
        self.assertEqual(T("de", "requires"), "نیازمند")

    def test_an_unknown_key_reads_as_itself_rather_than_as_nothing(self):
        """A blank button is something nobody can report."""
        from scripts.console_strings import T

        self.assertEqual(T("fa", "no_such_key"), "no_such_key")

    def test_every_string_has_both_languages(self):
        from scripts.console_strings import STRINGS

        for key, entry in STRINGS.items():
            with self.subTest(key=key):
                self.assertTrue(entry.get("fa"))
                self.assertTrue(entry.get("en"))

    def test_the_document_direction_follows_the_language(self):
        body = python_function("_document_attrs", CONSOLE)
        self.assertIn('lang="en" dir="ltr"', body)
        self.assertIn('lang="fa" dir="rtl"', body)

    def test_no_page_is_hard_coded_persian_any_more(self):
        self.assertNotIn('<html lang="fa" dir="rtl">', CONSOLE)
        self.assertEqual(CONSOLE.count("<html {_document_attrs(lang)}>"), 5)

    def test_the_switch_is_a_link_that_keeps_you_where_you_are(self):
        body = python_function("_language_bar_html", CONSOLE)
        self.assertIn('href="{html.escape(path)}?lang={code}"', body)

    def test_the_handler_reads_the_language_off_the_query(self):
        body = python_function("_path_and_language", CONSOLE)
        self.assertIn("normalize_language", body)
        self.assertIn('parse_qs(query).get("lang", [])', body)

    def test_identifiers_are_deliberately_not_translated(self):
        """Feature keys go into a signed manifest; an operator reading one
        word and typing another is how a manifest ends up wrong."""
        self.assertIn("identifiers, not prose", CONSOLE_STRINGS)


class ConsoleExeTests(SimpleTestCase):
    def test_pyinstaller_is_an_operator_only_dependency(self):
        requirements = (ROOT / "scripts" / "requirements-console.txt").read_text(encoding="utf-8")
        self.assertIn("pyinstaller", requirements.lower())
        for shipped in ("requirements.txt", "requirements-direct.txt"):
            path = ROOT / shipped
            if path.exists():
                with self.subTest(file=shipped):
                    self.assertNotIn("pyinstaller", path.read_text(encoding="utf-8").lower())

    def test_the_builder_refuses_to_install_it_for_you(self):
        """A build tool that pip-installs is a build tool that can change
        what it builds."""
        self.assertIn("will not", EXE_BUILDER)
        self.assertNotIn("pip install --user", EXE_BUILDER)
        self.assertIn("raise SystemExit(2)", EXE_BUILDER)

    def test_the_project_packages_are_bundled_explicitly(self):
        """Django finds its apps by name at startup, so PyInstaller's import
        analysis cannot see them."""
        for package in ("django", "config", "common", "accounts", "sales"):
            with self.subTest(package=package):
                self.assertIn(f'"{package}"', EXE_BUILDER.split("COLLECT = (")[1].split(")")[0])

    def test_the_build_verifies_the_binary_rather_than_trusting_it(self):
        """The failure it guards does not crash: a bundle missing a project
        package loses the route table and shows every feature as opening no
        pages."""
        self.assertIn("--self-check", EXE_BUILDER)
        self.assertIn("failed its own self-check", EXE_BUILDER)

    def test_the_self_check_is_a_real_mode_of_the_console(self):
        self.assertIn('"--self-check"', CONSOLE)
        body = python_function("_self_check", CONSOLE)
        self.assertIn("if not pages:", body)
        self.assertIn("return 1", body)

    def test_the_self_check_passes_against_this_checkout(self):
        """Run for real, not asserted from source: it is the thing the
        frozen build is verified with, so it has to work unfrozen too."""
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "manifest_builder.py"), "--self-check"],
            capture_output=True, text=True, timeout=300, cwd=str(ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok", result.stdout)
        self.assertRegex(result.stdout, r"panel pages behind a feature: [1-9]")


# ===========================================================================
# Item 13 — profile pictures
# ===========================================================================


class DefaultAvatarTests(SimpleTestCase):
    def test_the_cartoon_set_ships_with_the_panel(self):
        """Copied into first-party static rather than un-excluding the
        theme's whole `media` directory, which is 46MB of stock photography
        `collectstatic` deliberately drops."""
        directory = ROOT / "common" / "static" / "common" / "avatars"
        self.assertTrue(directory.is_dir())
        self.assertGreaterEqual(len(list(directory.glob("*.svg"))), 40)

    def test_a_person_always_gets_the_same_one(self):
        class Fake:
            pk = 41

        first = avatars.default_avatar_for(Fake())
        self.assertTrue(first)
        self.assertEqual(first, avatars.default_avatar_for(Fake()))

    def test_neighbouring_ids_do_not_get_neighbouring_pictures(self):
        """`pk % count` would walk the set in order, and a team created in
        one sitting would look like a tidy run through it."""
        class Fake:
            def __init__(self, pk):
                self.pk = pk

        names = avatars.default_avatar_names()
        picked = [avatars.default_avatar_for(Fake(pk)) for pk in range(1, 9)]
        indexes = [names.index(name) for name in picked]
        consecutive = sum(1 for a, b in zip(indexes, indexes[1:]) if b - a == 1)
        self.assertLess(consecutive, 4, indexes)

    def test_a_build_with_no_cartoons_gives_a_blank_circle_not_an_error(self):
        class Fake:
            pk = 1

        original = avatars._DEFAULT_AVATARS
        avatars._DEFAULT_AVATARS = ()
        try:
            self.assertIsNone(avatars.default_avatar_for(Fake()))
            self.assertIsNone(avatars.default_avatar_url(Fake()))
        finally:
            avatars._DEFAULT_AVATARS = original

    def test_the_type_is_sniffed_not_believed(self):
        self.assertEqual(avatars.sniff_avatar_content_type(ONE_PIXEL_PNG), "image/png")
        self.assertEqual(avatars.sniff_avatar_content_type(b"\xff\xd8\xff\xe0"), "image/jpeg")
        self.assertIsNone(avatars.sniff_avatar_content_type(b"<svg xmlns="))
        self.assertIsNone(avatars.sniff_avatar_content_type(b"GIF89a"))

    def test_svg_is_deliberately_not_allowed(self):
        """It is a document, it can carry script, and nothing about a
        profile photo needs it."""
        self.assertNotIn("image/svg+xml", avatars.ALLOWED_AVATAR_CONTENT_TYPES)


class AvatarServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.agent = User.objects.create_user(
            username="av.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.other = User.objects.create_user(
            username="av.other", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.admin = User.objects.create_user(
            username="av.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN
        )

    def test_a_person_may_set_their_own(self):
        avatars.set_avatar(actor=self.agent, target=self.agent, content=ONE_PIXEL_PNG)
        self.assertTrue(avatars.has_avatar(self.agent))

    def test_the_row_is_written_whole(self):
        """Every column is required and constrained, so a row created empty
        and filled in afterwards cannot be inserted — which is exactly how
        the first version of this failed."""
        row = avatars.set_avatar(actor=self.agent, target=self.agent, content=ONE_PIXEL_PNG)
        self.assertEqual(row.content_type, "image/png")
        self.assertEqual(row.size_bytes, len(ONE_PIXEL_PNG))
        self.assertGreater(row.size_bytes, 0)

    def test_uploading_twice_replaces_rather_than_duplicates(self):
        avatars.set_avatar(actor=self.agent, target=self.agent, content=ONE_PIXEL_PNG)
        avatars.set_avatar(actor=self.agent, target=self.agent, content=b"\xff\xd8\xff" + b"0" * 40)
        from accounts.models import UserAvatar

        self.assertEqual(UserAvatar.objects.filter(pk=self.agent.pk).count(), 1)
        self.assertEqual(avatars.avatar_for(self.agent).content_type, "image/jpeg")

    def test_a_marketer_may_not_set_somebody_elses(self):
        from common.exceptions import BusinessPermissionDenied

        with self.assertRaises(BusinessPermissionDenied):
            avatars.set_avatar(actor=self.agent, target=self.other, content=ONE_PIXEL_PNG)

    def test_a_user_administrator_may(self):
        avatars.set_avatar(actor=self.admin, target=self.agent, content=ONE_PIXEL_PNG)
        self.assertTrue(avatars.has_avatar(self.agent))

    def test_an_oversized_picture_is_refused(self):
        from common.exceptions import BusinessRuleError

        with self.assertRaises(BusinessRuleError):
            avatars.set_avatar(
                actor=self.agent,
                target=self.agent,
                content=b"\xff\xd8\xff" + b"0" * avatars.MAX_AVATAR_BYTES,
            )

    def test_something_that_is_not_an_image_is_refused(self):
        from common.exceptions import BusinessRuleError

        with self.assertRaises(BusinessRuleError):
            avatars.set_avatar(actor=self.agent, target=self.agent, content=b"not an image")

    def test_clearing_brings_the_cartoon_back(self):
        avatars.set_avatar(actor=self.agent, target=self.agent, content=ONE_PIXEL_PNG)
        avatars.clear_avatar(actor=self.agent, target=self.agent)
        self.assertFalse(avatars.has_avatar(self.agent))
        self.assertTrue(avatars.default_avatar_url(self.agent))

    def test_clearing_deletes_the_row_rather_than_blanking_it(self):
        """"No picture" and "a picture of nothing" are not the same fact,
        and only the first falls back to the cartoon."""
        from accounts.models import UserAvatar

        avatars.set_avatar(actor=self.agent, target=self.agent, content=ONE_PIXEL_PNG)
        avatars.clear_avatar(actor=self.agent, target=self.agent)
        self.assertFalse(UserAvatar.objects.filter(pk=self.agent.pk).exists())


class AvatarApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.agent = User.objects.create_user(
            username="ava.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def _client(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(self.agent)
        return client

    def test_the_state_endpoint_always_names_a_url(self):
        """So the panel never has to choose between two URLs."""
        response = self._client().get("/api/v1/profile/avatar/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["has_avatar"])
        self.assertIn("/static/common/avatars/", response.data["url"])

    def test_uploading_then_reading_back(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        client = self._client()
        upload = SimpleUploadedFile("me.png", ONE_PIXEL_PNG, content_type="image/png")
        response = client.post("/api/v1/profile/avatar/", {"avatar": upload}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["has_avatar"])

        image = client.get(f"/api/v1/users/{self.agent.pk}/avatar/image/")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image["Content-Type"], "image/png")
        self.assertEqual(image["X-Content-Type-Options"], "nosniff")
        self.assertIn("private", image["Cache-Control"])

    def test_the_declared_content_type_is_not_believed(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile("lie.png", b"this is not a png", content_type="image/png")
        response = self._client().post(
            "/api/v1/profile/avatar/", {"avatar": upload}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)

    def test_an_empty_post_is_refused_rather_than_reported_as_success(self):
        response = self._client().post("/api/v1/profile/avatar/", {}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_a_person_with_no_picture_has_no_image_to_serve(self):
        response = self._client().get(f"/api/v1/users/{self.agent.pk}/avatar/image/")
        self.assertEqual(response.status_code, 404)

    def test_signing_in_is_required_to_see_a_colleagues_face(self):
        """Unlike the brand logo, which an unauthenticated login page shows."""
        from rest_framework.test import APIClient

        avatars.set_avatar(actor=self.agent, target=self.agent, content=ONE_PIXEL_PNG)
        response = APIClient().get(f"/api/v1/users/{self.agent.pk}/avatar/image/")
        self.assertIn(response.status_code, {401, 403})


class AvatarUiTests(SimpleTestCase):
    def test_the_crop_happens_before_anything_is_sent(self):
        body = function_body("cropAvatarFile")
        self.assertIn("Math.min(source.naturalWidth, source.naturalHeight)", body)
        self.assertIn("canvas.width = AVATAR_EDGE", body)
        self.assertIn('"image/jpeg"', body)

    def test_a_file_the_browser_cannot_decode_is_not_sent(self):
        body = function_body("setupAvatarInput")
        self.assertIn("این فایل یک تصویر خوانا نیست.", body)

    def test_the_upload_keeps_its_multipart_boundary(self):
        body = function_body("setupAvatarInput")
        self.assertIn("raw: true", body)

    def test_the_preview_cache_busts_because_the_url_does_not_change(self):
        body = function_body("setupAvatarInput")
        self.assertIn("?v=${Date.now()}", body)

    def test_the_shell_renders_the_face_server_side(self):
        """So the header never flashes a placeholder first."""
        self.assertEqual(markup(BASE).count('src="{{ own_avatar_url }}"'), 2)
        self.assertIn('context["own_avatar_url"]',
                      (ROOT / "common" / "ui_views.py").read_text(encoding="utf-8"))

    def test_the_theme_sizes_the_picture_not_a_utility_class(self):
        """Measured: `w-100 h-100` (100% !important) beat the theme's fixed
        35px, the symbol had no width of its own to be 100% of, and the
        header avatar rendered at 300px."""
        self.assertNotIn('class="dolphin-avatar w-100 h-100"', BASE)
        self.assertNotIn("width:", rule(".dolphin-avatar"))

    def test_the_picker_is_reachable_by_keyboard(self):
        """Restated 2026-09-21: the pencil control became a real `<button>`
        that opens the picker dialog (it used to be a `<label for>` a hidden
        file input) — focus now lands on the button itself, so the ring is
        `:focus-visible` on `.avatar-input-pick` directly rather than a
        `:focus-within` on its wrapping frame."""
        self.assertIn(".avatar-input-pick:focus-visible", CODE)
        self.assertIn('<button type="button" class="avatar-input-pick" id="open-avatar-picker"', markup(BASE))


class DefaultAvatarChoiceTests(TestCase):
    """Item 3 of the 2026-09-21 follow-up: «کاربران باید بتوانند بین
    عکس‌های پیش‌فرض انتخاب کنند و اپشن آپلود شخصی هم در مودالی که تازه باز
    می‌شود باشد». `chosen_default_avatar` (accounts.User) is the one column
    this needed — the hash-derived pick above never had to be stored, but a
    person's own choice has to survive a reload, which "derive it again"
    cannot do.
    """

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.agent = User.objects.create_user(
            username="dac.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.other = User.objects.create_user(
            username="dac.other", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def test_an_explicit_pick_wins_over_the_hash(self):
        hash_derived = avatars.default_avatar_for(self.agent)
        names = [n for n in avatars.default_avatar_names() if n != hash_derived]
        chosen = names[0]
        avatars.set_default_avatar_choice(actor=self.agent, target=self.agent, name=chosen)
        self.agent.refresh_from_db()
        self.assertEqual(avatars.default_avatar_for(self.agent), chosen)
        self.assertEqual(avatars.chosen_default_avatar_for(self.agent), chosen)

    def test_picking_a_default_drops_any_upload(self):
        """An upload always wins over a default while both exist
        (`_state`/`ui_views.profile_photo_url`), so a pick made on top of one
        would otherwise have no visible effect — it has to actually replace
        the upload, not just sit unused beside it."""
        avatars.set_avatar(actor=self.agent, target=self.agent, content=ONE_PIXEL_PNG)
        self.assertTrue(avatars.has_avatar(self.agent))
        name = avatars.default_avatar_names()[0]
        avatars.set_default_avatar_choice(actor=self.agent, target=self.agent, name=name)
        self.assertFalse(avatars.has_avatar(self.agent))

    def test_clearing_an_upload_falls_back_to_the_last_choice_not_a_random_one(self):
        name = avatars.default_avatar_names()[3]
        avatars.set_default_avatar_choice(actor=self.agent, target=self.agent, name=name)
        avatars.set_avatar(actor=self.agent, target=self.agent, content=ONE_PIXEL_PNG)
        avatars.clear_avatar(actor=self.agent, target=self.agent)
        self.agent.refresh_from_db()
        self.assertEqual(avatars.default_avatar_for(self.agent), name)

    def test_an_unknown_name_is_refused(self):
        from common.exceptions import BusinessRuleError

        with self.assertRaises(BusinessRuleError):
            avatars.set_default_avatar_choice(
                actor=self.agent, target=self.agent, name="not-a-real-file.svg"
            )
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.chosen_default_avatar, "")

    def test_a_stale_choice_from_a_smaller_build_falls_back_gracefully(self):
        """A deployment that ships fewer cartoons than it used to must not
        point a browser at a file that no longer exists."""
        self.agent.chosen_default_avatar = "999-does-not-exist.svg"
        self.agent.save(update_fields=["chosen_default_avatar"])
        self.assertIsNone(avatars.chosen_default_avatar_for(self.agent))
        self.assertIn(avatars.default_avatar_for(self.agent), avatars.default_avatar_names())

    def test_a_marketer_may_not_choose_for_somebody_else(self):
        from common.exceptions import BusinessPermissionDenied

        name = avatars.default_avatar_names()[0]
        with self.assertRaises(BusinessPermissionDenied):
            avatars.set_default_avatar_choice(actor=self.agent, target=self.other, name=name)

    def test_default_avatar_choices_names_every_shipped_cartoon(self):
        choices = avatars.default_avatar_choices()
        names = avatars.default_avatar_names()
        self.assertEqual(len(choices), len(names))
        self.assertEqual({c["name"] for c in choices}, set(names))
        self.assertTrue(all(c["url"].endswith(c["name"]) for c in choices))


class AvatarDefaultChoiceApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.agent = User.objects.create_user(
            username="dacapi.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def _client(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(self.agent)
        return client

    def test_the_gallery_endpoint_lists_every_cartoon(self):
        response = self._client().get("/api/v1/avatar-defaults/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), len(avatars.default_avatar_names()))
        self.assertIn("name", response.data[0])
        self.assertIn("url", response.data[0])

    def test_choosing_one_updates_the_state_endpoint(self):
        name = avatars.default_avatar_names()[0]
        response = self._client().post(
            "/api/v1/profile/avatar/default/", {"name": name}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["chosen_default_name"], name)
        self.assertFalse(response.data["has_avatar"])

        state = self._client().get("/api/v1/profile/avatar/")
        self.assertEqual(state.data["chosen_default_name"], name)

    def test_an_unknown_name_is_a_400_not_a_500(self):
        response = self._client().post(
            "/api/v1/profile/avatar/default/", {"name": "../../etc/passwd"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_signed_out_cannot_pick_one(self):
        from rest_framework.test import APIClient

        name = avatars.default_avatar_names()[0]
        response = APIClient().post(
            "/api/v1/profile/avatar/default/", {"name": name}, format="json"
        )
        self.assertIn(response.status_code, {401, 403})


class AvatarPickerUiTests(SimpleTestCase):
    """The gallery dialog itself — source-scanned the same way the rest of
    this file's UI assertions are; the interactive behaviour (click a tile,
    see the preview change, reopen and see the pick survive) was checked
    live in the browser and is recorded in PROGRESS.md."""

    def test_the_dialog_exists_with_both_the_gallery_and_the_upload(self):
        markup_text = markup(BASE)
        self.assertIn('<dialog id="avatar-picker-dialog"', markup_text)
        self.assertIn('id="avatar-picker-grid"', markup_text)
        self.assertIn('for="profile-avatar-file"', markup_text)

    def test_the_edit_button_opens_the_dialog_not_the_file_picker_directly(self):
        """It used to be a `<label for="profile-avatar-file">`; picking a
        default first meant it has to open a dialog instead."""
        markup_text = markup(BASE)
        self.assertNotIn('<label class="avatar-input-pick"', markup_text)
        body = function_body("setupProfileDialog", SCRIPT)
        self.assertIn('getElementById("open-avatar-picker")', body)
        self.assertIn("avatarDialog.showModal()", body)

    def test_the_grid_is_filled_from_the_real_deployed_set_not_hardcoded(self):
        """`scripts/console_strings.py`'s reasoning applies here too: a
        written-down list of 52 filenames is a list that falls behind the
        moment the shipped set changes."""
        body = function_body("setupAvatarInput", SCRIPT)
        self.assertIn('apiRequest("/api/v1/avatar-defaults/")', body)
        self.assertNotIn("001-boy.svg", SCRIPT)

    def test_choosing_a_default_and_uploading_share_one_preview(self):
        """Both actions call the same `show`, so the circle and the
        selected-tile ring can never disagree about which picture is
        active."""
        body = function_body("setupAvatarInput", SCRIPT)
        self.assertIn("show(await apiRequest(chooseEndpoint", body)
        self.assertIn('show(await apiRequest(endpoint, {method: "POST", body, raw: true}))', body)

    def test_the_selected_tile_is_visibly_marked(self):
        self.assertIn(".avatar-picker-tile.is-selected", CODE)
        body = function_body("setupAvatarInput", SCRIPT)
        self.assertIn('classList.toggle("is-selected"', body)

    def test_the_gallery_is_a_responsive_grid_not_a_fixed_column_count(self):
        rule_body = rule(".avatar-picker-grid")
        self.assertIn("auto-fill", rule_body)
