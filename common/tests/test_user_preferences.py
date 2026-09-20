"""`common.preferences` and `/settings/` — one reader's own view of the
panel: typeface, scale, currency unit and colour theme.

Product-owner request, 2026-09-20 (item 13 of thirteen): a settings page
for admin, manager and ordinary users alike, carrying «اندازهٔ فونت کل پنل
برای هر کاربر»، «فونت از یک لیست آماده برای هر کاربر»، «ریال یا تومان برای
هر کاربر» و «تم روشن/تیره».

What is worth proving here, beyond that the fields save:

* **a preference is presentation, never permission.** No feature gate, no
  role check beyond "signed in", and — the part that matters — no way to
  set anybody else's. `update_preferences` takes an actor and no user, so
  there is no parameter a request could forward;
* **the typeface reaches a `<style>` element**, which makes an unvalidated
  value a stylesheet-injection hole. Two independent guards are checked: the
  serializer refuses an unknown token, and `preference_css` emits only a
  stack it looked up itself;
* **«تومان» never changes stored data.** Amounts are stored in rial; the
  unit divides on the way out and multiplies on the way back, and the three
  formatters in this product (Python helper, template filter, the panel's
  own JavaScript) have to agree digit for digit or a printed invoice and the
  screen it was checked against would not;
* a reader who never opened the page has no row at all and gets every
  default — so adding this table changed nothing for anyone already using
  the product;
* the panel keeps rendering when the preference cannot be read, because
  this runs in a context processor on every page including the 500 handler.
"""

import pathlib
from decimal import Decimal

from django.db import DatabaseError
from django.test import TestCase
from django.test.client import RequestFactory
from rest_framework.test import APIClient

from accounts.models import User
from common import preferences
from common.context_processors import panel_preferences
from common.formatting import money as python_money
from common.models import (
    DEFAULT_PANEL_FONT_FAMILY,
    DEFAULT_PANEL_FONT_SCALE,
    PANEL_FONT_FAMILIES,
    PANEL_FONT_SCALES,
    UserPreference,
)
from common.templatetags.money_tags import money as template_money

PASSWORD = "Strong-pass-882!"

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin-app.js"
).read_text(encoding="utf-8")
BASE_TEMPLATE = (
    pathlib.Path(__file__).resolve().parents[2]
    / "common" / "templates" / "common" / "base.html"
).read_text(encoding="utf-8")


class PreferenceFixtures(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user(
            username="pref.agent", password=PASSWORD, role=User.Role.SALES_AGENT,
        )
        self.admin = User.objects.create_user(
            username="pref.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN,
        )

    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client


class DefaultsTests(PreferenceFixtures):
    def test_a_user_who_never_saved_anything_has_no_row(self):
        self.assertFalse(UserPreference.objects.filter(pk=self.agent.pk).exists())

    def test_and_gets_every_default(self):
        self.assertEqual(preferences.effective_preferences(self.agent), preferences.DEFAULTS)

    def test_an_anonymous_visitor_gets_the_defaults_too(self):
        """The login page renders through the same context processor."""
        self.assertEqual(preferences.effective_preferences(None), preferences.DEFAULTS)

    def test_the_defaults_emit_no_css_at_all(self):
        """`base.html` writes `{% if panel_preference_css %}`, so "kept the
        defaults" has to be falsy, not an empty-but-present style block."""
        self.assertIsNone(preferences.preference_css(preferences.DEFAULTS))

    def test_an_unreadable_database_falls_back_rather_than_raising(self):
        """This runs on every page including the 500 handler; one failure
        must not become two — the same posture `effective_brand` takes."""
        original = UserPreference.objects.filter

        def explode(*args, **kwargs):
            raise DatabaseError("unavailable")

        UserPreference.objects.filter = explode
        try:
            self.assertEqual(preferences.effective_preferences(self.agent), preferences.DEFAULTS)
        finally:
            UserPreference.objects.filter = original


class ServiceTests(PreferenceFixtures):
    def test_each_field_is_independent(self):
        preferences.update_preferences(actor=self.agent, font_scale="lg")
        row = preferences.update_preferences(actor=self.agent, currency_unit="toman")
        self.assertEqual(row.font_scale, "lg")
        self.assertEqual(row.currency_unit, "toman")
        self.assertEqual(row.font_family, DEFAULT_PANEL_FONT_FAMILY)

    def test_the_service_has_no_user_parameter_to_forward(self):
        """Not a stylistic point: it is what makes "you can only change your
        own" unreachable by a request parameter rather than merely
        unchecked."""
        import inspect

        signature = inspect.signature(preferences.update_preferences)
        self.assertNotIn("user", signature.parameters)
        self.assertIn("actor", signature.parameters)

    def test_the_catalog_only_offers_values_the_field_accepts(self):
        catalog = preferences.catalog()
        self.assertEqual(
            [entry["value"] for entry in catalog["font_families"]],
            [value for value, _label, _stack in PANEL_FONT_FAMILIES],
        )
        self.assertEqual(
            [entry["value"] for entry in catalog["font_scales"]],
            [value for value, _label, _size in PANEL_FONT_SCALES],
        )
        self.assertEqual(
            [entry["value"] for entry in catalog["currency_units"]],
            list(UserPreference.CurrencyUnit.values),
        )

    def test_every_font_stack_ends_in_the_one_persian_face_this_product_ships(self):
        """A reader who picks a family their machine does not have must
        still get Persian glyphs, not whatever the OS substitutes."""
        for _value, _label, stack in PANEL_FONT_FAMILIES:
            self.assertIn("IRANSansWeb", stack, stack)


class GeneratedCssTests(PreferenceFixtures):
    def test_a_chosen_family_sets_the_themes_own_token(self):
        css = preferences.preference_css({**preferences.DEFAULTS, "font_family": "tahoma"})
        self.assertIn("--bs-font-sans-serif:", css)
        self.assertIn("Tahoma", css)

    def test_a_chosen_family_is_also_written_as_a_literal(self):
        """The token alone does nothing. Verified in a real browser: the
        purchased sheet reads `--bs-font-sans-serif` through
        `body { font-family: var(--bs-body-font-family) }` and then, later in
        the same file, sets `html, body { font-family: IRANSansWeb, ... }`
        outright — which wins on source order and leaves the token unread.
        """
        css = preferences.preference_css({**preferences.DEFAULTS, "font_family": "tahoma"})
        self.assertIn("html,body{font-family:Tahoma", css)

    def test_a_chosen_family_is_restated_for_apex_chart_text(self):
        """The vendor hardcodes a Latin family on chart text with
        `!important`; without this the labels stay on the default face while
        the card around them moves."""
        css = preferences.preference_css({**preferences.DEFAULTS, "font_family": "tahoma"})
        self.assertIn(".apexcharts-text", css)
        self.assertIn("!important", css)

    def test_a_chosen_scale_moves_the_root_font_size(self):
        """`!important`, and pixels stepped off the theme's own base rather
        than a percentage of the browser default — both measured against the
        rendered page, not assumed. `style.bundle.rtl.css` ends with
        `html, body { font-size: 13px !important }`, so a weaker declaration
        never applies and a percentage would be read against 16px, turning a
        step up into a 38% jump.
        """
        css = preferences.preference_css({**preferences.DEFAULTS, "font_scale": "lg"})
        self.assertIn("html,body{font-size:14.5px!important;}", css)

    def test_the_scale_steps_are_relative_to_the_themes_own_base(self):
        from common.models import PANEL_FONT_SCALE_SIZES

        self.assertEqual(PANEL_FONT_SCALE_SIZES[DEFAULT_PANEL_FONT_SCALE], "13px")
        vendor = (
            pathlib.Path(__file__).resolve().parents[2]
            / "assets" / "css" / "style.bundle.rtl.css"
        )
        if vendor.exists():
            self.assertIn("font-size: 13px !important", vendor.read_text(encoding="utf-8"))

    def test_the_settings_pages_live_preview_uses_the_same_steps(self):
        """The preview is a second copy of the mapping by necessity (it runs
        before any save). It has to agree with the server's, or the choice a
        reader accepts is not the one they were shown."""
        self.assertIn(
            'const FONT_SIZES = {sm: "12px", md: "13px", lg: "14.5px", xl: "16px"};', SCRIPT,
        )

    def test_an_unknown_family_emits_nothing_rather_than_echoing_it(self):
        """The second of the two guards: even if a value reached the model,
        only a stack looked up from `PANEL_FONT_FAMILY_STACKS` is ever
        written into the page."""
        css = preferences.preference_css(
            {**preferences.DEFAULTS, "font_family": "</style><script>x()</script>"},
        )
        self.assertIsNone(css)

    def test_the_stylesheet_itself_still_chooses_no_typeface(self):
        """`dolphin.css` is forbidden from owning the panel's type
        (`test_the_override_sheet_does_not_rebuild_the_themes_components`).
        This feature does not change that — it renders per request, inline,
        the way the brand accent colour already does."""
        stylesheet = (
            pathlib.Path(__file__).resolve().parents[2]
            / "common" / "static" / "common" / "dolphin.css"
        ).read_text(encoding="utf-8")
        self.assertNotIn("--bs-font-sans-serif", stylesheet)


class ContextProcessorTests(PreferenceFixtures):
    def context_for(self, user):
        request = RequestFactory().get("/")
        request.user = user
        return panel_preferences(request)

    def test_it_exports_the_css_and_the_raw_unit(self):
        preferences.update_preferences(actor=self.agent, currency_unit="toman", font_scale="xl")
        context = self.context_for(self.agent)
        self.assertEqual(context["panel_currency_unit"], "toman")
        self.assertEqual(context["panel_currency_label"], "تومان")
        self.assertIn("html,body{font-size:16px!important;}", context["panel_preference_css"])

    def test_the_shell_stamps_the_unit_where_the_script_reads_it(self):
        self.assertIn('data-currency-unit="{{ panel_currency_unit', BASE_TEMPLATE)
        self.assertIn('document.body?.dataset.currencyUnit', SCRIPT)

    def test_the_saved_theme_is_applied_before_any_stylesheet_paints(self):
        """Not after load: a dark-mode reader who has already been shown a
        white page has seen the flash this inline script exists to
        prevent."""
        head = BASE_TEMPLATE.split("</head>")[0]
        self.assertIn("var defaultThemeMode = \"{{ panel_theme", head)

    def test_the_saved_theme_wins_over_this_machines_localstorage(self):
        """It is the one the reader set on purpose, and the one that has to
        follow them to another browser."""
        self.assertIn('defaultThemeMode !== "system"', BASE_TEMPLATE)


class CurrencyUnitTests(PreferenceFixtures):
    def test_choosing_toman_stores_nothing_different(self):
        """The unit is display only. Nothing in this product writes an
        amount in anything but rial."""
        preferences.update_preferences(actor=self.agent, currency_unit="toman")
        self.assertEqual(
            preferences.to_storage_amount(preferences.to_display_amount(Decimal("12345"), "toman"), "toman"),
            Decimal("12345"),
        )

    def test_the_display_conversion_is_exact_not_rounded(self):
        """A rounded value would move the stored amount the next time the
        field it filled was saved."""
        self.assertEqual(preferences.to_display_amount(Decimal("12345"), "toman"), Decimal("1234.5"))

    def test_rial_is_left_completely_alone(self):
        self.assertEqual(preferences.to_display_amount(Decimal("12345"), "rial"), Decimal("12345"))
        self.assertEqual(preferences.to_storage_amount(Decimal("12345"), "rial"), Decimal("12345"))

    def test_the_python_helper_and_the_template_filter_agree_digit_for_digit(self):
        """A printed document and the screen it was checked against must
        not disagree; both round the magnitude up, both group with the
        Arabic comma, both print Persian digits."""
        for amount in ("12500000.00", "9.00", "12345.60", "0.00"):
            for unit in ("rial", "toman"):
                self.assertEqual(
                    python_money(Decimal(amount), unit),
                    str(template_money(Decimal(amount), unit)),
                    f"{amount} {unit}",
                )

    def test_toman_is_a_tenth_of_the_rial_figure_and_named_as_such(self):
        self.assertEqual(python_money(Decimal("12500000.00"), "toman"), "۱،۲۵۰،۰۰۰ تومان")
        self.assertEqual(python_money(Decimal("12500000.00"), "rial"), "۱۲،۵۰۰،۰۰۰ ریال")

    def test_the_unit_is_applied_before_the_round_up_not_after(self):
        """Rounding the rial up and then dividing would report a tenth of a
        rial more than is owed — the direction the round-up rule exists to
        avoid on the other side."""
        self.assertEqual(python_money(Decimal("12345"), "toman"), "۱،۲۳۵ تومان")

    def test_the_panels_javascript_converts_the_same_way(self):
        """Read off the source rather than executed: the rule that matters
        is that it moves the decimal point rather than dividing, because a
        rial total can exceed what a double holds exactly."""
        self.assertIn('if (CURRENCY_UNIT === "toman") {', SCRIPT)
        self.assertIn("function moneyToStorage(text)", SCRIPT)

    def test_a_money_field_is_submitted_in_rial_not_in_what_was_typed(self):
        """Every submit path goes through `moneyToStorage`; `moneyValue`
        alone would post a toman figure into a rial column."""
        for site in (
            "payload.current_price = moneyToStorage(",
            "amount: moneyToStorage(",
        ):
            self.assertIn(site, SCRIPT)

    def test_regrouping_a_field_as_it_is_typed_does_not_convert_it(self):
        """`moneyDigits` converts a stored amount for display; running it on
        every keystroke would divide the field by ten per character."""
        handler = SCRIPT.split("function setupMoneyInputs(")[1].split("\n    }")[0]
        self.assertIn("groupDigits(digits)", handler)
        self.assertNotIn("moneyDigits(digits)", handler)

    def test_a_field_is_filled_exactly_so_a_round_trip_cannot_move_it(self):
        self.assertIn("money(value, {withCurrency: false, exact: true})", SCRIPT)


class PrintedDocumentTests(PreferenceFixtures):
    def test_the_printed_invoice_follows_the_readers_unit(self):
        """Product owner: «همه‌جا، شامل فاکتور و اسناد چاپی»."""
        template = (
            pathlib.Path(__file__).resolve().parents[2]
            / "common" / "templates" / "common" / "invoices" / "print.html"
        ).read_text(encoding="utf-8")
        self.assertIn("|money:panel_currency_unit", template)
        self.assertNotIn("|money }}", template)

    def test_the_column_headings_name_the_same_unit_as_the_figures_under_them(self):
        """A column headed ریال over figures printed in تومان would be a
        tenfold misstatement on a document a customer keeps."""
        template = (
            pathlib.Path(__file__).resolve().parents[2]
            / "common" / "templates" / "common" / "invoices" / "print.html"
        ).read_text(encoding="utf-8")
        self.assertIn("مبلغ واحد به {{ panel_currency_label }}", template)
        self.assertNotIn("مبلغ واحد به ریال", template)


class APITests(PreferenceFixtures):
    def test_every_signed_in_role_may_read_its_own(self):
        response = self.client_for(self.agent).get("/api/v1/preferences/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["font_family"], DEFAULT_PANEL_FONT_FAMILY)
        self.assertEqual(response.data["font_scale"], DEFAULT_PANEL_FONT_SCALE)

    def test_an_anonymous_visitor_is_refused(self):
        response = APIClient().get("/api/v1/preferences/")
        self.assertIn(response.status_code, (401, 403))

    def test_saving_works_for_an_ordinary_role(self):
        response = self.client_for(self.agent).post(
            "/api/v1/preferences/",
            {"font_family": "tahoma", "font_scale": "lg", "currency_unit": "toman", "theme": "dark"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        row = UserPreference.objects.get(pk=self.agent.pk)
        self.assertEqual(row.font_family, "tahoma")
        self.assertEqual(row.currency_unit, "toman")
        self.assertEqual(row.theme, "dark")

    def test_saving_reaches_only_the_callers_own_row(self):
        self.client_for(self.agent).post("/api/v1/preferences/", {"font_scale": "xl"}, format="json")
        self.assertFalse(UserPreference.objects.filter(pk=self.admin.pk).exists())

    def test_a_request_naming_another_user_is_refused_as_an_unknown_field(self):
        response = self.client_for(self.agent).post(
            "/api/v1/preferences/", {"user": self.admin.pk, "font_scale": "xl"}, format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(UserPreference.objects.filter(pk=self.agent.pk).exists())

    def test_an_unknown_font_is_a_400_not_a_stored_value(self):
        """The first of the two injection guards — this value would
        otherwise end up inside a `<style>` element."""
        response = self.client_for(self.agent).post(
            "/api/v1/preferences/",
            {"font_family": "</style><script>alert(1)</script>"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(UserPreference.objects.filter(pk=self.agent.pk).exists())

    def test_an_unknown_scale_theme_or_unit_is_a_400(self):
        client = self.client_for(self.agent)
        for field, value in (("font_scale", "huge"), ("theme", "neon"), ("currency_unit", "dollar")):
            response = client.post("/api/v1/preferences/", {field: value}, format="json")
            self.assertEqual(response.status_code, 400, field)

    def test_the_response_is_never_cached(self):
        response = self.client_for(self.agent).get("/api/v1/preferences/")
        self.assertEqual(response["Cache-Control"], "private, no-store")


class SettingsPageTests(PreferenceFixtures):
    def page(self, user):
        self.client.force_login(user)
        return self.client.get("/settings/")

    def test_an_ordinary_user_can_open_it(self):
        """Explicitly asked for: «صفحه تنظیمات برای کاربر ادمین و مدیر و
        کاربر عادی»."""
        response = self.page(self.agent)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "common/settings/settings.html")

    def test_it_offers_all_four_shared_controls(self):
        page = self.page(self.agent).content.decode("utf-8")
        for control in ("preference-font-family", "preference-font-scale"):
            self.assertIn(control, page)
        self.assertIn('name="currency_unit"', page)
        self.assertIn('name="theme"', page)

    def test_the_saved_values_are_already_selected_server_side(self):
        """No loading state and no first paint showing the defaults before
        the real choice arrives."""
        preferences.update_preferences(actor=self.agent, font_scale="xl")
        page = self.page(self.agent).content.decode("utf-8")
        self.assertIn('<option value="xl" selected>', page)

    def test_it_says_plainly_that_the_unit_does_not_change_stored_data(self):
        page = self.page(self.agent).content.decode("utf-8")
        self.assertIn("به ریال ذخیره می‌شوند", page)

    def test_an_ordinary_user_is_not_offered_the_deployment_wide_sections(self):
        page = self.page(self.agent).content.decode("utf-8")
        self.assertNotIn("تنظیمات استقرار", page)
        self.assertNotIn("برند، رنگ و لوگوی پنل", page)

    def test_a_platform_admin_is(self):
        page = self.page(self.admin).content.decode("utf-8")
        self.assertIn("تنظیمات استقرار", page)
        self.assertIn("برند، رنگ و لوگوی پنل", page)

    def test_it_is_reachable_from_the_account_menu_on_every_page(self):
        self.client.force_login(self.agent)
        page = self.client.get("/").content.decode("utf-8")
        self.assertIn('id="open-settings"', page)
        self.assertIn('href="/settings/"', page)

    def test_the_page_module_is_wired(self):
        self.assertIn('if (page === "settings") {', SCRIPT)
        self.assertIn("setupSettingsPage();", SCRIPT)


class DigitScriptTests(PreferenceFixtures):
    """A found bug, not a new rule: the dashboard's capability tiles put raw
    Latin digits on the page while every figure beside them was Persian.

    It stayed invisible because IRANSansWeb draws ASCII digits in a
    Persian-looking form — choosing Tahoma on the new settings page makes
    `203` and «۲۰۳» sit side by side on one screen. Fixed where the
    numbers are rendered rather than by refusing the other faces.
    """

    def test_the_capability_tiles_render_persian_digits(self):
        self.client.force_login(self.admin)
        page = self.client.get("/").content.decode("utf-8")
        tiles = page.split('class="text-gray-900 fw-bolder fs-2hx lh-1"')
        self.assertGreater(len(tiles), 1, "the capability tiles are gone")
        for tile in tiles[1:]:
            figure = tile.split(">", 1)[1].split("<", 1)[0].strip()
            self.assertFalse(
                any(character.isdigit() and character.isascii() for character in figure),
                figure,
            )
