"""Roadmap priority 3 (2.40.42).

Two-factor sign-in (item 12) and the account security page (item 13), the
test debt (item 11: a generated schema proof, browser tests that run), and the
defects those turned up: wizard errors in the browser's language, a review step
that threw on a segmented toggle, and a field pattern invalid in today's Chrome.
"""

import re
from io import StringIO
from pathlib import Path

from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from accounts import two_factor
from accounts.models import TwoFactorDevice, User
from auditlog.models import ActivityLog
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES, DEFAULT_FEATURES

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "common" / "static" / "common" / "js"
TEMPLATES = ROOT / "common" / "templates"
PASSWORD = "Strong-pass-742!"


def without_two_factor():
    return DeploymentProfile(
        profile_id="client-1", features=frozenset(ALL_FEATURES) - frozenset({"two_factor"}), source="signed-manifest",
    )


class TotpTests(SimpleTestCase):
    def test_codes_follow_rfc_6238(self):
        # RFC 6238 appendix B, SHA-1, T = 59 s: 94287082 — the last six digits.
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of "12345678901234567890"
        self.assertEqual(two_factor.code_at(secret, two_factor.current_step(59)), "287082")
        self.assertEqual(two_factor.code_at(secret, two_factor.current_step(1111111109)), "081804")

    def test_what_the_reader_typed_is_read_generously(self):
        self.assertEqual(two_factor.clean_code("۲۸۷ ۰۸۲"), "287082")
        self.assertEqual(two_factor.clean_code("abcde-fghij"), "ABCDEFGHIJ")

    def test_the_qr_code_is_an_svg_data_uri(self):
        uri = two_factor.provisioning_uri("ABCDEFGH", "admin")
        self.assertTrue(uri.startswith("otpauth://totp/Dolphin%3Aadmin?"))
        self.assertIn("secret=ABCDEFGH", uri)
        self.assertTrue(two_factor.qr_data_uri(uri).startswith("data:image/svg+xml"))

    def test_it_is_a_feature_a_deployment_asks_for(self):
        self.assertIn("two_factor", ALL_FEATURES)
        self.assertNotIn("two_factor", DEFAULT_FEATURES)


class TwoFactorFlowTests(TestCase):
    def setUp(self):
        cache.clear()  # the sign-in throttle counts across tests otherwise
        self.admin = User.objects.create_user(username="tf.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.agent = User.objects.create_user(username="tf.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.client = APIClient()
        self.client.force_login(self.agent)

    def enrol(self, user=None, client=None):
        client = client or self.client
        user = user or self.agent
        response = client.post("/api/v1/auth/me/two-factor/setup/", {"password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        secret = response.json()["secret"]
        code = two_factor.code_at(secret, two_factor.current_step())
        confirmed = client.post("/api/v1/auth/me/two-factor/confirm/", {"code": code}, format="json")
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        return secret, confirmed.json()["recovery_codes"]

    def test_turning_it_on_asks_for_the_password_and_a_working_code(self):
        refused = self.client.post("/api/v1/auth/me/two-factor/setup/", {"password": "wrong"}, format="json")
        self.assertEqual(refused.status_code, 400)
        started = self.client.post("/api/v1/auth/me/two-factor/setup/", {"password": PASSWORD}, format="json").json()
        self.assertTrue(started["qr"].startswith("data:image/svg+xml"))
        device = TwoFactorDevice.objects.get(user=self.agent)
        self.assertNotIn(started["secret"], device.secret_token)  # stored encrypted
        self.assertIsNone(device.confirmed_at)
        bad = self.client.post("/api/v1/auth/me/two-factor/confirm/", {"code": "000000"}, format="json")
        self.assertEqual(bad.status_code, 400)
        code = two_factor.code_at(started["secret"], two_factor.current_step())
        codes = self.client.post("/api/v1/auth/me/two-factor/confirm/", {"code": code}, format="json").json()["recovery_codes"]
        self.assertEqual(len(codes), 10)
        status = self.client.get("/api/v1/auth/me/two-factor/").json()
        self.assertEqual((status["enabled"], status["recovery_codes_left"]), (True, 10))
        self.assertTrue(ActivityLog.objects.filter(operation="two_factor.enabled").exists())

    def test_signing_in_then_asks_for_the_code_and_a_code_works_once(self):
        secret, _ = self.enrol()
        guest = APIClient()
        first = guest.post("/api/v1/auth/login/", {"username": "tf.agent", "password": PASSWORD}, format="json")
        self.assertEqual(first.json(), {"two_factor_required": True})
        self.assertEqual(guest.get("/api/v1/auth/me/").status_code, 403)  # nothing signed in yet
        self.assertEqual(guest.post("/api/v1/auth/login/two-factor/", {"code": "000000"}, format="json").status_code, 400)
        code = two_factor.code_at(secret, two_factor.current_step())
        TwoFactorDevice.objects.filter(user=self.agent).update(last_used_step=0)
        signed_in = guest.post("/api/v1/auth/login/two-factor/", {"code": code}, format="json")
        self.assertEqual(signed_in.status_code, 200, signed_in.content)
        self.assertEqual(signed_in.json()["username"], "tf.agent")
        self.assertEqual(guest.get("/api/v1/auth/me/").status_code, 200)
        # The same code again, on a new sign-in: refused.
        again = APIClient()
        again.post("/api/v1/auth/login/", {"username": "tf.agent", "password": PASSWORD}, format="json")
        self.assertEqual(again.post("/api/v1/auth/login/two-factor/", {"code": code}, format="json").status_code, 400)

    def test_a_recovery_code_signs_in_once(self):
        _, codes = self.enrol()
        guest = APIClient()
        guest.post("/api/v1/auth/login/", {"username": "tf.agent", "password": PASSWORD}, format="json")
        self.assertEqual(guest.post("/api/v1/auth/login/two-factor/", {"code": codes[0].lower()}, format="json").status_code, 200)
        other = APIClient()
        other.post("/api/v1/auth/login/", {"username": "tf.agent", "password": PASSWORD}, format="json")
        self.assertEqual(other.post("/api/v1/auth/login/two-factor/", {"code": codes[0]}, format="json").status_code, 400)

    def test_five_wrong_codes_end_the_attempt(self):
        secret, _ = self.enrol()
        guest = APIClient()
        guest.post("/api/v1/auth/login/", {"username": "tf.agent", "password": PASSWORD}, format="json")
        for _ in range(5):
            guest.post("/api/v1/auth/login/two-factor/", {"code": "000000"}, format="json")
        TwoFactorDevice.objects.filter(user=self.agent).update(last_used_step=0)
        code = two_factor.code_at(secret, two_factor.current_step())
        answer = guest.post("/api/v1/auth/login/two-factor/", {"code": code}, format="json")
        self.assertEqual(answer.status_code, 400)
        self.assertIn("دوباره نام کاربری", str(answer.json()["code"]))

    def test_turning_it_off_needs_the_password_and_a_code(self):
        _, codes = self.enrol()
        refused = self.client.post("/api/v1/auth/me/two-factor/disable/", {"password": PASSWORD, "code": "000000"}, format="json")
        self.assertEqual(refused.status_code, 400)
        done = self.client.post("/api/v1/auth/me/two-factor/disable/", {"password": PASSWORD, "code": codes[1]}, format="json")
        self.assertEqual(done.status_code, 200)
        self.assertFalse(done.json()["enabled"])
        self.assertFalse(TwoFactorDevice.objects.filter(user=self.agent).exists())

    def test_the_platform_admin_resets_a_lost_phone_never_their_own(self):
        self.enrol()
        admin = APIClient()
        admin.force_login(self.admin)
        self.assertTrue(admin.get(f"/api/v1/users/{self.agent.pk}/").json()["two_factor_enabled"])
        self.assertEqual(admin.post(f"/api/v1/users/{self.agent.pk}/reset-two-factor/").status_code, 204)
        self.assertFalse(two_factor.enabled_for(self.agent))
        self.assertTrue(ActivityLog.objects.filter(operation="two_factor.reset").exists())
        self.enrol(user=self.admin, client=admin)
        self.assertEqual(admin.post(f"/api/v1/users/{self.admin.pk}/reset-two-factor/").status_code, 400)
        # The host command is the way back for the Platform Admin's own account.
        out = StringIO()
        call_command("reset_two_factor", "--username", "tf.admin", stdout=out)
        self.assertFalse(two_factor.enabled_for(self.admin))

    def test_without_the_feature_nothing_changes_and_nothing_is_offered(self):
        self.enrol()
        with override_active_profile(without_two_factor()):
            self.assertEqual(self.client.get("/api/v1/auth/me/two-factor/").status_code, 404)
            guest = APIClient()
            answer = guest.post("/api/v1/auth/login/", {"username": "tf.agent", "password": PASSWORD}, format="json")
            self.assertEqual(answer.json()["username"], "tf.agent")
            self.assertNotIn("login-code", guest.get("/login/").content.decode("utf-8"))

    @override_settings(DOLPHIN_SECRETS_KEY="")
    def test_without_a_secrets_key_it_cannot_be_turned_on(self):
        self.assertFalse(self.client.get("/api/v1/auth/me/two-factor/").json()["available"])
        refused = self.client.post("/api/v1/auth/me/two-factor/setup/", {"password": PASSWORD}, format="json")
        self.assertEqual(refused.status_code, 409)
        self.assertIn("DOLPHIN_SECRETS_KEY", refused.json()["detail"])


class SecurityPageTests(TestCase):
    def test_the_settings_page_has_a_security_tab_with_both_cards(self):
        user = User.objects.create_user(username="tf.page", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.client.force_login(user)
        page = self.client.get("/settings/?tab=security").content.decode("utf-8")
        self.assertIn('id="settings-tab-security"', page)
        self.assertIn('id="two-factor-card"', page)
        self.assertIn("data-open-sessions", page)
        with override_active_profile(without_two_factor()):
            page = self.client.get("/settings/?tab=security").content.decode("utf-8")
        self.assertNotIn('id="two-factor-card"', page)
        self.assertIn("data-open-sessions", page)

    def test_the_login_page_gains_exactly_one_code_step(self):
        page = self.client.get("/login/").content.decode("utf-8")
        names = re.findall(r'<input\b[^>]*\bname="([^"]+)"', page)
        self.assertEqual(sorted(set(names)), ["code", "csrfmiddlewaretoken", "password", "username"])
        self.assertIn('id="login-code-step" class="login-code-step" hidden', page)


class FormMessageTests(SimpleTestCase):
    def test_a_refused_wizard_step_explains_itself_in_persian(self):
        wizard = (JS / "ui" / "wizard.js").read_text(encoding="utf-8")
        self.assertIn("const text = validityText(field);", wizard)
        self.assertNotIn("slot.textContent = field.validationMessage", wizard)
        messages = (JS / "core" / "messages.js").read_text(encoding="utf-8")
        self.assertIn('"این فیلد را پر کنید."', messages)

    def test_a_segmented_toggle_reads_in_the_review_step(self):
        wizard = (JS / "ui" / "wizard.js").read_text(encoding="utf-8")
        self.assertIn('document.querySelector(`[data-segmented-for="${field.id}"]`)', wizard)

    def test_every_field_pattern_is_valid_in_unicode_sets_mode(self):
        # Chrome compiles `pattern` with the `v` flag, where a hyphen inside a
        # class must be escaped unless it makes a range.
        offenders = []
        for template in sorted(TEMPLATES.rglob("*.html")):
            for pattern in re.findall(r'\bpattern="([^"]*)"', template.read_text(encoding="utf-8")):
                for body in re.findall(r"\[((?:\\.|[^\]])*)\]", pattern):
                    stripped = re.sub(r"\\.", "", body)
                    stripped = re.sub(r".-.", "", stripped)
                    if "-" in stripped:
                        offenders.append(f"{template.name}: {pattern}")
        self.assertEqual(offenders, [])


class AttachmentLibraryTests(TestCase):
    """«اسناد و پیوست‌ها»: every file the reader may see, and only those."""

    def setUp(self):
        from attachments.services import upload_attachment
        from sales.services import create_customer_with_phone

        self.manager = User.objects.create_user(username="lib.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="lib.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.other = User.objects.create_user(username="lib.other", password=PASSWORD, role=User.Role.SALES_AGENT)
        mine = create_customer_with_phone(actor=self.agent, full_name="مشتری من", phone={"raw_phone": "09121115001"})
        theirs = create_customer_with_phone(actor=self.other, full_name="مشتری دیگری", phone={"raw_phone": "09121115002"})
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        pdf = b"%PDF-1.4\n" + b"\x00" * 32
        upload_attachment(actor=self.agent, field_name="customer", parent_id=mine.pk, original_filename="رسید.png", content=png)
        upload_attachment(actor=self.agent, field_name="customer", parent_id=mine.pk, original_filename="قرارداد.pdf", content=pdf)
        upload_attachment(actor=self.other, field_name="customer", parent_id=theirs.pk, original_filename="دیگری.pdf", content=pdf)

    def files(self, user, **params):
        client = APIClient()
        client.force_login(user)
        response = client.get("/api/v1/attachments/library/", params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["results"]

    def test_each_reader_sees_the_files_of_the_records_they_see(self):
        names = {row["original_filename"] for row in self.files(self.agent)}
        self.assertEqual(names, {"رسید.png", "قرارداد.pdf"})
        self.assertEqual(len(self.files(self.manager)), 3)
        row = self.files(self.agent, search="رسید")[0]
        self.assertEqual((row["parent_type_display"], row["parent_name"]), ("مشتری", "مشتری من"))
        self.assertTrue(row["parent_url"].startswith("/customers/"))
        self.assertFalse(row["can_delete"])  # a marketer holds no `customers.delete`

    def test_it_narrows_by_kind_and_record(self):
        self.assertEqual([row["original_filename"] for row in self.files(self.agent, kind="pdf")], ["قرارداد.pdf"])
        self.assertEqual(len(self.files(self.agent, parent="invoice")), 0)
        client = APIClient()
        client.force_login(self.agent)
        self.assertEqual(client.get("/api/v1/attachments/library/", {"kind": "exe"}).status_code, 400)

    def test_the_page_and_its_menu_entry(self):
        self.client.force_login(self.agent)
        page = self.client.get("/files/").content.decode("utf-8")
        self.assertIn('id="attachment-library-table-body"', page)
        self.assertIn('data-module="attachment-library"', page)


class StylesheetLayerTests(SimpleTestCase):
    """`dolphin.css` became ordered layers (`common/stylesheets.py`)."""

    def test_every_page_links_every_layer_in_cascade_order(self):
        from common.stylesheets import STYLESHEETS
        from common.templatetags.ui_modules import dolphin_stylesheets

        linked = re.findall(r'href="/static/([^"?]+)\?v=', str(dolphin_stylesheets()))
        self.assertEqual(linked, list(STYLESHEETS))
        for name in ("base.html", "print_base.html", "error.html"):
            with self.subTest(template=name):
                page = (TEMPLATES / "common" / name).read_text(encoding="utf-8")
                self.assertEqual(page.count("{% dolphin_stylesheets %}"), 1)
                self.assertNotIn("dolphin.css' %}", page)

    def test_the_folder_holds_exactly_the_listed_layers(self):
        from common.stylesheets import STYLESHEETS, stylesheet_paths

        folder = ROOT / "common" / "static" / "common" / "css"
        self.assertEqual(sorted(path.name for path in folder.glob("*")), sorted(Path(name).name for name in STYLESHEETS))
        self.assertTrue(all(path.is_file() for path in stylesheet_paths()))
        self.assertFalse((ROOT / "common" / "static" / "common" / "dolphin.css").exists())

    def test_the_pdf_page_inlines_every_layer(self):
        from common import pdf
        from common.stylesheets import stylesheet_text

        pdf._STYLESHEET_CACHE.clear()
        self.assertEqual(pdf.inline_stylesheet(), stylesheet_text())
        self.assertIn(".print-page", pdf.inline_stylesheet())

    def test_no_first_party_file_still_names_the_old_sheet(self):
        sources = [*JS.rglob("*.js"), *TEMPLATES.rglob("*.html"), *TEMPLATES.rglob("*.inc")]
        sources += [*(ROOT / "common").glob("*.py"), *(ROOT / "common" / "templatetags").glob("*.py")]
        named = [
            path.relative_to(ROOT).as_posix() for path in sources
            if path.name != "stylesheets.py" and "dolphin.css" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(named, [])


class KitCleanupTests(SimpleTestCase):
    UI = ROOT / "common" / "static" / "common" / "ui"

    def test_the_theme_script_lost_the_layout_builder_demo_only(self):
        theme = (self.UI / "js" / "dolphin-theme.js").read_text(encoding="utf-8")
        self.assertNotIn("DolphinAppLayoutBuilder", theme)
        for kept in ("var DolphinLayoutSearch", "var DolphinMenu", "var DolphinDrawer", "var DolphinUtil"):
            self.assertIn(kept, theme)

    def test_the_theme_stylesheet_keeps_what_the_panel_draws_with(self):
        theme = (self.UI / "css" / "dolphin-theme.rtl.css").read_text(encoding="utf-8")
        self.assertLess(len(theme.encode("utf-8")), 600_000)
        for selector in (".app-sidebar", ".card-body", ".btn-primary", ".menu-link", ".badge-light-success",
                         ".form-control-solid", ".drawer", ".table-row-dashed", ".symbol-label",
                         # Built at run time by the drawer (`baseClass + '-' + direction`), so
                         # no source names them; the slimming once dropped them and every
                         # drawer lost its place.
                         ".drawer.drawer-start {", ".drawer.drawer-end {"):
            self.assertIn(selector, theme)
        self.assertEqual(theme.count("{"), theme.count("}"))

    def test_dead_code_is_gone(self):
        self.assertFalse((JS / "ui" / "transitions.js").exists())
        script = "\n".join(path.read_text(encoding="utf-8") for path in JS.rglob("*.js"))
        for name in ("bindTransitions", "localDateValue", "CALL_DIRECTION_ICON", "PAYMENT_DIRECTION_TEXT",
                     "INSTALLMENT_STATUS_TEXT", "customerKindLabel", "isDialogDirty"):
            self.assertNotRegex(script, rf"\b{name}\b", name)

    def test_the_postal_card_is_a_module_of_its_page(self):
        self.assertFalse((ROOT / "common" / "static" / "common" / "postal-shipment.js").exists())
        page = (TEMPLATES / "common" / "sales_documents" / "detail.html").read_text(encoding="utf-8")
        self.assertNotIn("<script", page.split('id="postal-shipment-card"')[1].split("{% endif %}")[0])
        detail = (JS / "features" / "sales" / "sales-document-detail.js").read_text(encoding="utf-8")
        self.assertIn('import {setupPostalShipment} from "dolphin/features/sales/postal-shipment.js";', detail)
        self.assertIn("    setupPostalShipment();\n", detail)
        card = (JS / "features" / "sales" / "postal-shipment.js").read_text(encoding="utf-8")
        self.assertIn("await confirmDialog(", card)
        self.assertNotIn("window.confirm", card)
        self.assertIn("say(errorReason(error))", card)

    def test_every_module_imports_the_shared_functions_it_calls(self):
        """An ES module that calls another module's export without importing it
        parses, loads and fails only when that line runs. The dashboard split
        left `chartResetEvents` unimported — it was only ever spread
        (`...chartResetEvents(…)`) — so the trend chart threw on mount, and the
        dashboard's own `.catch` hid it: the arrange pencil silently stopped
        working. Every call and spread of an exported name must be an import or a
        local declaration of that module."""

        def code(text):
            text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
            text = re.sub(r"(?m)(^|[^:\"'`\\])//.*$", r"\1", text)
            text = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', text)
            return re.sub(r"'(?:[^'\\\n]|\\.)*'", "''", text)

        exports = {}
        for path in JS.rglob("*.js"):
            for name in re.findall(r"^export\s+(?:async\s+)?(?:function|const|let|class)\s+([A-Za-z_$][\w$]*)",
                                   path.read_text(encoding="utf-8"), re.M):
                exports.setdefault(name, path)
        missing = []
        for path in JS.rglob("*.js"):
            raw = path.read_text(encoding="utf-8")
            text = code(raw)
            imported = set()
            for match in re.finditer(r"import\s*\{([^}]*)\}", raw):
                imported |= {name.strip().split(" as ")[-1] for name in match.group(1).split(",") if name.strip()}
            declared = set(re.findall(r"(?:function\*?|const|let|var|class)\s+([A-Za-z_$][\w$]*)", text))
            for name, owner in exports.items():
                if owner == path or name in imported or name in declared:
                    continue
                if re.search(rf"(?<![\w$.]){re.escape(name)}\s*\(", text) or re.search(rf"\.\.\.{re.escape(name)}\b", text):
                    missing.append(f"{path.relative_to(JS).as_posix()}: {name}")
        self.assertEqual(missing, [])

    def test_the_two_large_modules_are_split_without_a_cycle(self):
        dashboard = JS / "features" / "dashboard"
        self.assertEqual(
            sorted(path.name for path in dashboard.glob("*.js")),
            ["dashboard.js", "editor.js", "grid.js", "widget-cards.js", "widget-charts.js"],
        )
        editor = (dashboard / "editor.js").read_text(encoding="utf-8")
        self.assertNotIn("features/dashboard/dashboard.js", editor)
        self.assertIn("{refresh}", editor)
        customers = JS / "features" / "customers"
        for part in ("person-profile.js", "profile-user.js", "profile-customer.js", "profile-header.js",
                     "profile-activity.js", "profile-cards.js", "profile-work.js", "profile-calls.js"):
            self.assertTrue((customers / part).is_file(), part)
        for path in [*dashboard.glob("*.js"), *customers.glob("profile-*.js"), customers / "person-profile.js"]:
            with self.subTest(module=path.name):
                self.assertLess(len(path.read_text(encoding="utf-8").splitlines()), 1300)


class RequestTimingsTests(SimpleTestCase):
    def test_it_folds_record_ids_and_reports_the_slowest_routes_first(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("request_timings", ROOT / "scripts" / "request_timings.py")
        timings = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(timings)
        lines = [
            'web-1 | {"event":"http_request","method":"GET","path":"/customers/%d/","status":200,"duration_ms":%d}' % (n, 10 + n)
            for n in range(1, 11)
        ] + [
            '{"event":"http_request","method":"GET","path":"/api/v1/leads/","status":200,"duration_ms":400}',
            '{"event":"http_request","method":"GET","path":"/static/common/css/tokens.css","status":200,"duration_ms":1}',
            "not a log line",
        ]
        routes = timings.read(lines)
        self.assertEqual(set(routes), {"GET /customers/{id}/", "GET /api/v1/leads/"})
        self.assertEqual(len(routes["GET /customers/{id}/"]), 10)
        report = timings.report(routes, least=1).splitlines()
        self.assertTrue(report[1].startswith("GET /api/v1/leads/"))
        self.assertTrue(report[-1].startswith("all requests"))
        self.assertEqual(timings.read(lines, api_only=True).keys(), {"GET /api/v1/leads/"})


class HelpDrawerTests(SimpleTestCase):
    """Help never describes what the reader cannot reach."""

    def test_a_section_is_summed_up_by_the_pages_this_reader_sees(self):
        from common.help import topics_for

        groups = [{"key": "leads", "label": "سرنخ‌ها و پیگیری", "links": [
            {"module": "leads", "label": "سرنخ‌ها"}, {"module": "interactions", "label": "تماس‌ها"},
        ]}]
        [topic] = topics_for(groups)
        self.assertEqual(topic["summary"], "«سرنخ‌ها» و «تماس‌ها».")
        tips = " ".join(topic["points"])
        self.assertNotIn("تقویم", tips)
        self.assertNotIn("تابلو", tips)

    def test_a_tip_waits_for_its_feature_or_capability(self):
        from common.help import shortcuts_for, topics_for

        groups = [
            {"key": "settings", "label": "تنظیمات", "links": [{"module": "settings", "label": "تنظیمات"}]},
            {"key": "shipping", "label": "ارسال و پست", "links": [{"module": "sales-documents", "label": "رهگیری پستی"}]},
        ]
        plain = {topic["key"]: topic["points"] for topic in topics_for(groups)}
        self.assertNotIn("دومرحله‌ای", " ".join(plain["settings"]))
        self.assertEqual(plain["shipping"], [])
        full = {topic["key"]: topic["points"] for topic in topics_for(
            groups, features={"two_factor"}, capabilities={"sales_documents.manage"},
        )}
        self.assertIn("دومرحله‌ای", " ".join(full["settings"]))
        self.assertEqual(len(full["shipping"]), 1)
        self.assertNotIn("Ctrl + K", [keys for keys, _ in shortcuts_for(set())])
        self.assertIn("Ctrl + K", [keys for keys, _ in shortcuts_for({"global_search"})])

    def test_every_tip_names_a_page_of_its_own_section(self):
        from common.help import HELP_TOPICS
        from common.navigation import GROUPS

        modules = {group.key: {item.module for item in group.items} for group in GROUPS}
        self.assertLessEqual(set(HELP_TOPICS), set(modules))
        for key, (_, tips) in HELP_TOPICS.items():
            for text, needs in tips:
                for need in needs:
                    if ":" not in need:
                        with self.subTest(section=key, tip=text):
                            self.assertIn(need, modules[key])
