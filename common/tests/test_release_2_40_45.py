"""Roadmap priority 4, laid down but not connected (2.40.45).

A payment gateway, the tax system, email, the messengers and a website chat
box: each has its contract (`integrations/contracts.py`) and a «به‌زودی» row in
the «افزودن اتصال» catalog saying what it needs. Nothing is connected and
nothing pretends to be: no provider implements a contract, no feature names
one, no served code calls one, and the catalog offers nothing to press.
"""

import inspect
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from accounts.models import User
from common import integrations
from common.deployment.registry import ALL_FEATURES
from integrations import contracts
from integrations.providers import CAPABILITY_LABELS, providers

ROOT = Path(__file__).resolve().parents[2]


class ContractTests(SimpleTestCase):
    def test_every_upcoming_service_has_its_contract_and_says_what_it_needs(self):
        keys = [service.key for service in integrations.UPCOMING_SERVICES]
        self.assertEqual(sorted(keys), sorted(contracts.CONTRACTS))
        for service in integrations.UPCOMING_SERVICES:
            with self.subTest(service=service.key):
                self.assertTrue(service.needs)
                self.assertIn(contracts.CONTRACTS[service.key].capability, CAPABILITY_LABELS)

    def test_a_contract_is_only_a_shape(self):
        for key, contract in contracts.CONTRACTS.items():
            with self.subTest(contract=key):
                self.assertTrue(inspect.isabstract(contract))
                self.assertTrue(contract.__abstractmethods__)
                with self.assertRaises(TypeError):
                    contract()

    def test_a_payment_is_verified_by_the_gateway_not_the_browser(self):
        self.assertEqual(contracts.PaymentGateway.__abstractmethods__, frozenset({"start", "verify"}))
        self.assertIn("never on the payer's browser", contracts.PaymentGateway.__doc__)

    def test_nothing_pretends_to_be_connected(self):
        for provider in providers():
            for contract in contracts.CONTRACTS.values():
                self.assertNotIsInstance(provider, contract)
        for key in contracts.CONTRACTS:
            self.assertNotIn(key, ALL_FEATURES)
        callers = [
            path.relative_to(ROOT).as_posix()
            for path in ROOT.glob("*/**/*.py")
            if "tests" not in path.parts and path.name != "contracts.py" and path.parts[0] != "ui_kit"
            and "integrations.contracts" in path.read_text(encoding="utf-8", errors="ignore")
        ]
        self.assertEqual(callers, [])


class FontAddressTests(SimpleTestCase):
    def test_each_icon_font_is_addressed_by_its_content(self):
        """Fonts without `?v=` are cached for a month (nginx), and since 2.40.43
        an icon font changes whenever an icon is used for the first time: with
        a fixed address a returning browser drew the new icons from the old
        font. The build names each font by a hash of its bytes."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("build_ui_kit", ROOT / "scripts" / "build_ui_kit.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        css = (build.SERVED / "css" / "dolphin-plugins.rtl.css").read_text(encoding="utf-8")
        found = build._FONT_URL.findall(css)
        self.assertEqual(sorted(family for family, _ in found), ["duotone", "outline", "solid"])
        for family, version in found:
            content = (build.SERVED / "fonts" / "dolphin-icons" / f"dolphin-icons-{family}.woff").read_bytes()
            self.assertEqual(version, build.font_version(content), family)


class CatalogTests(TestCase):
    def test_the_catalog_names_each_one_with_what_it_needs(self):
        admin = User.objects.create_user(username="catalog.admin", password="Strong-pass-745!", role=User.Role.PLATFORM_ADMIN)
        self.client.force_login(admin)
        page = self.client.get("/settings/integrations/")
        self.assertEqual(page.status_code, 200)
        for service in integrations.UPCOMING_SERVICES:
            with self.subTest(service=service.key):
                self.assertContains(page, f'data-upcoming="{service.key}"')
                self.assertContains(page, f"برای فعال شدن: {service.needs}")
        self.assertContains(page, "گفت‌وگوی زندهٔ سایت")
